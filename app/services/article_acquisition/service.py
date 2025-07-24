"""
Article Acquisition Service - Orchestrated Multi-Source Content Retrieval

This module provides the main service class for orchestrating article acquisition from
multiple data sources. It manages various acquisition strategies, handles concurrent
operations, and provides intelligent deduplication and progress reporting.

The service supports dynamic strategy selection, allowing runtime configuration of
search modes and parameters. It's designed to be extensible, with easy registration
of new acquisition strategies and flexible configuration options.
"""

import asyncio
from typing import Any

import httpx

from app.config import settings
from app.schemas import SourceArticle
from app.services.article_acquisition.components import SemanticSearchComponent
from app.services.article_acquisition.hybrid_strategy import (
    DatasetWikipediaEnHybridStrategy,
)
from app.services.article_acquisition.strategies import (
    DataAcquisitionStrategy,
    DatasetWikipediaEnStrategy,
    OnlineWikinewsStrategy,
    OnlineWikipediaStrategy,
)
from app.services.process_callback import ProgressCallback
from app.utils.logger import setup_logger

logger = setup_logger("article_acquisition_service")

DEFAULT_BM25_WEIGHT = 0.4
DEFAULT_VECTOR_WEIGHT = 0.6
DEFAULT_SEARCH_MODE = "hybrid_title_search"  # other choices: semantic


class ArticleAcquisitionService:
    """Service for acquiring articles from various sources."""

    def __init__(
        self,
        strategies: dict[str, DataAcquisitionStrategy] | None = None,
        # Allow passing http_client for strategies that might need it directly
        # or for the service to manage it if it were to make its own calls.
        # For OnlineWikiStrategy, it expects http_client in query_data.
        http_client: httpx.AsyncClient | None = None,
        # Allow injecting SemanticSearchComponent for LocalSemanticSearchStrategy
        # This is useful for testing or if the component has a complex setup.
        semantic_search_component: SemanticSearchComponent | None = None,
    ):
        self.http_client = http_client if http_client else httpx.AsyncClient()

        if strategies is None:
            self.strategies = {}
            # Initialize DatasetWikipediaEnStrategy (formerly LocalSemanticSearchStrategy)
            default_ssc = (
                semantic_search_component
                if semantic_search_component
                else SemanticSearchComponent()
            )
            if default_ssc.is_ready():
                self.strategies["dataset_wikipedia_en"] = DatasetWikipediaEnStrategy(
                    semantic_search_component=default_ssc
                )
                logger.info(
                    "Initialized DatasetWikipediaEnStrategy with unified embedding service."
                )
            else:
                logger.error(
                    "Failed to initialize SemanticSearchComponent for DatasetWikipediaEnStrategy due to embedding service not ready."
                )

            # Initialize OnlineWikipediaStrategy (formerly OnlineWikiStrategy)
            self.strategies["online_wikipedia"] = OnlineWikipediaStrategy()
            logger.info("Initialized OnlineWikipediaStrategy.")

            # Initialize OnlineWikinewsStrategy
            if callable(OnlineWikinewsStrategy) and callable(
                getattr(OnlineWikinewsStrategy, "get_articles", None)
            ):
                try:
                    self.strategies["online_wikinews"] = OnlineWikinewsStrategy()
                    logger.info("Initialized OnlineWikinewsStrategy.")
                except Exception as e:
                    logger.error(
                        f"Failed to initialize OnlineWikinewsStrategy: {e}",
                        exc_info=True,
                    )
            else:
                logger.error(
                    "OnlineWikinewsStrategy or its get_articles method is not correctly defined/imported."
                )

            logger.info(
                f"ArticleAcquisitionService initialized with default strategies: {list(self.strategies.keys())}"
            )
        else:
            self.strategies = strategies
            logger.info(
                f"ArticleAcquisitionService initialized with provided strategies: {list(self.strategies.keys())}"
            )

        # Check if the explicitly provided dataset_wikipedia_en strategy (if any) has a loaded model
        if "dataset_wikipedia_en" in self.strategies and isinstance(
            self.strategies["dataset_wikipedia_en"], DatasetWikipediaEnStrategy
        ):
            if (
                not self.strategies["dataset_wikipedia_en"].component
                or not self.strategies["dataset_wikipedia_en"].component.is_ready()
            ):
                logger.warning(
                    "DatasetWikipediaEnStrategy is configured but its SemanticSearchComponent embedding service is not ready. It may not yield results."
                )

    async def acquire_articles(
        self,
        query_data: dict[str, Any],
        progress_callback: ProgressCallback | None = None,
    ) -> list[SourceArticle]:
        """
        Acquires articles using strategies determined by data_source_preference in query_data.

        This method now includes conditional viewpoint preprocessing:
        - For Wikipedia-based sources: extracts keywords using viewpoint_processor
        - For dataset-based sources: enhances viewpoint semantically using llm_extractor
        """
        parent_request_id = query_data.get("parent_request_id")
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""

        # Default to online_wikipedia if no preference is specified
        data_source_preference_str = query_data.get("data_source_preference")
        if not data_source_preference_str:
            logger.warning("No data_source_preference found in query_data.")
            data_source_preference_str = "online_wikipedia"

        logger.info(
            f"{log_prefix}Acquiring articles with data_source_preference string: '{data_source_preference_str}'"
        )

        if "http_client" not in query_data:
            logger.debug(
                f"{log_prefix}Adding default http_client to query_data as it was not present."
            )
            query_data["http_client"] = self.http_client

        # Parse the comma-separated string into a list of preferences
        # Ensure keys match those used in self.strategies dictionary
        requested_sources = [
            source.strip()
            for source in data_source_preference_str.split(",")
            if source.strip()
        ]

        if (
            not requested_sources
        ):  # Fallback if string was empty or only whitespace/commas
            logger.warning(
                f"{log_prefix}No valid data sources parsed from preference string '{data_source_preference_str}'. Defaulting to 'online_wikipedia'."
            )
            requested_sources = ["online_wikipedia"]

        logger.info(f"{log_prefix}Requested sources after parsing: {requested_sources}")

        # === NEW: DYNAMIC STRATEGY SELECTION ===
        # Based on task config, we can switch to the new hybrid strategy.
        task_config = query_data.get("config", {})
        search_mode = task_config.get(
            "search_mode", DEFAULT_SEARCH_MODE
        )  # Default to old behavior

        if (
            search_mode == DEFAULT_SEARCH_MODE
            and "dataset_wikipedia_en" in self.strategies
        ):
            logger.info(
                "Switching to DatasetWikipediaEnHybridStrategy based on task config."
            )
            # We can safely assume the component is loaded if the original strategy exists.
            existing_component = self.strategies["dataset_wikipedia_en"].component

            # Create a new instance of the hybrid strategy
            hybrid_strategy = DatasetWikipediaEnHybridStrategy(
                semantic_search_component=existing_component,
                article_limit=task_config.get(
                    "article_limit", settings.default_article_limit
                ),  # Allow config override
                vector_weight=task_config.get("vector_weight", DEFAULT_VECTOR_WEIGHT),
                bm25_weight=task_config.get("bm25_weight", DEFAULT_BM25_WEIGHT),
            )
            # Replace the strategy for this specific call
            self.strategies["dataset_wikipedia_en"] = hybrid_strategy
        # === END: DYNAMIC STRATEGY SELECTION ===

        tasks = []
        selected_strategies = {
            source: self.strategies[source]
            for source in requested_sources
            if source in self.strategies
        }

        if not selected_strategies:
            logger.warning(
                f"{log_prefix}None of the requested sources {requested_sources} have a configured strategy. No articles will be acquired."
            )
            return []

        logger.info(
            f"{log_prefix}Using the following strategies for acquisition: {list(selected_strategies.keys())}"
        )

        for source_name, strategy in selected_strategies.items():
            logger.debug(
                f"{log_prefix}Creating task for article acquisition via '{source_name}' strategy."
            )
            # Each strategy receives the same, comprehensive query_data package
            tasks.append(strategy.get_articles(query_data))

        # Run all selected strategies concurrently
        results_from_strategies = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and deduplicate articles
        all_articles: list[SourceArticle] = []
        total_strategies = len(selected_strategies)

        for i, result in enumerate(results_from_strategies):
            source_name = list(selected_strategies.keys())[i]
            current_index = i + 1

            if isinstance(result, Exception):
                logger.error(
                    f"{log_prefix}Error from '{source_name}' strategy: {result}",
                    exc_info=result,
                )

                # Report progress for failed strategy
                if progress_callback:
                    await progress_callback.report(
                        f"Strategy {current_index}/{total_strategies}: '{source_name}' failed with error",
                        "article_strategy_result",
                        {
                            "current": current_index,
                            "total": total_strategies,
                            "strategy_name": source_name,
                            "article_count": 0,
                            "status": "error",
                            "error": str(result),
                        },
                        query_data.get("parent_request_id"),
                    )

            elif result is None:
                logger.warning(f"{log_prefix}'{source_name}' strategy returned None.")

                # Report progress for empty strategy
                if progress_callback:
                    await progress_callback.report(
                        f"Strategy {current_index}/{total_strategies}: '{source_name}' returned no articles",
                        "article_strategy_result",
                        {
                            "current": current_index,
                            "total": total_strategies,
                            "strategy_name": source_name,
                            "article_count": 0,
                            "status": "empty",
                        },
                        query_data.get("parent_request_id"),
                    )

            else:
                logger.info(
                    f"{log_prefix}'{source_name}' strategy returned {len(result)} articles."
                )
                all_articles.extend(result)

                # Report progress for successful strategy
                if progress_callback:
                    await progress_callback.report(
                        f"Strategy {current_index}/{total_strategies}: '{source_name}' returned {len(result)} articles",
                        "article_strategy_result",
                        {
                            "current": current_index,
                            "total": total_strategies,
                            "strategy_name": source_name,
                            "article_count": len(result),
                            "status": "success",
                        },
                        query_data.get("parent_request_id"),
                    )

        if not all_articles:
            logger.warning(
                f"{log_prefix}No articles were acquired from any of the selected strategies."
            )
            return []

        # Deduplicate articles based on URL
        logger.info(f"{log_prefix}{len(all_articles)} articles to deduplicate.")

        if progress_callback:
            await progress_callback.report(
                f"Starting deduplication of {len(all_articles)} articles...",
                "article_deduplication_start",
                {
                    "total_articles_before_dedup": len(all_articles),
                },
                query_data.get("parent_request_id"),
            )

        unique_articles: dict[str, SourceArticle] = {}
        duplicates_removed = 0

        for article in all_articles:
            if article.source_url not in unique_articles:
                unique_articles[article.source_url] = article
                logger.debug(
                    f"{log_prefix}Added article: {article.source_identifier} {article.title}"
                )
            else:
                duplicates_removed += 1
                logger.debug(
                    f"{log_prefix}Duplicate article found and removed: {article.source_identifier} {article.title}"
                )

        final_articles = list(unique_articles.values())
        logger.info(
            f"{log_prefix}Total articles after acquisition and deduplication: {len(final_articles)}"
        )

        if progress_callback:
            await progress_callback.report(
                f"Deduplication complete: {len(final_articles)} unique articles (removed {duplicates_removed} duplicates)",
                "article_deduplication_complete",
                {
                    "final_article_count": len(final_articles),
                    "duplicates_removed": duplicates_removed,
                    "total_articles_before_dedup": len(all_articles),
                },
                query_data.get("parent_request_id"),
            )
        return final_articles

    async def close_http_client(self):
        """Closes the service's own HTTP client if it was created by the service."""
        # This is important if the service creates its own client and is long-lived.
        # If client is passed in, the caller is responsible for its lifecycle.
        if hasattr(self, "http_client") and self.http_client:
            # Check if the client was created by this instance or passed in.
            # This is a simplistic check; a more robust way might be needed.
            # For now, we assume if it exists, we can try to close it.
            # The responsibility of closing clients passed in query_data lies elsewhere.
            try:
                await self.http_client.aclose()
                logger.info("ArticleAcquisitionService's internal HTTP client closed.")
            except Exception as e:
                logger.error(
                    f"Error closing ArticleAcquisitionService's HTTP client: {e}"
                )

    def register_strategy(self, name: str, strategy: DataAcquisitionStrategy):
        """Register or replace a data acquisition strategy."""
        logger.info(f"Registering strategy: {name}")
        self.strategies[name] = strategy
