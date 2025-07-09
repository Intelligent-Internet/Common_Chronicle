"""
Hybrid Search Strategy - Advanced Multi-Modal Content Discovery

This module implements sophisticated hybrid search strategies that combine multiple
search approaches to achieve optimal content discovery performance. The hybrid
approach leverages both semantic (vector-based) and traditional (BM25) search
methods to provide comprehensive and relevant article retrieval.
"""

import asyncio
from typing import Any, Literal

from app.config import settings
from app.schemas import SourceArticle
from app.services.article_acquisition.components import SemanticSearchComponent
from app.services.article_acquisition.strategies import DataAcquisitionStrategy
from app.utils.logger import setup_logger

logger = setup_logger("hybrid_strategy")


class DatasetWikipediaEnHybridStrategy(DataAcquisitionStrategy):
    """
    A hybrid search strategy that combines semantic (vector) search with
    BM25 full-text search on titles to retrieve articles. It uses a weighted
    fusion of scores from both methods to rank the results.
    """

    def __init__(
        self,
        semantic_search_component: SemanticSearchComponent,
        article_limit: int = settings.default_article_limit,
        bm25_mode: Literal["title_only"] = "title_only",
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
    ):
        """
        Initializes the hybrid strategy.
        """
        self.component = semantic_search_component
        self.article_limit = article_limit
        self.bm25_mode = bm25_mode
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.max_distance = 2.0  # Max possible cosine distance

    async def get_articles(self, query_data: dict[str, Any]) -> list[SourceArticle]:
        """
        Orchestrates the hybrid search process. It now dynamically handles
        pure vector, pure BM25, or hybrid modes based on weights.
        """
        viewpoint_text = query_data.get("viewpoint_text", "")
        if not viewpoint_text:
            return []

        # --- Dynamic Search Path ---
        # Determine the search mode based on weights
        is_vector_search = self.vector_weight > 0
        is_bm25_search = self.bm25_weight > 0

        logger.info(
            f"Executing search for '{viewpoint_text[:50]}...'. Mode: "
            f"{'Hybrid' if is_vector_search and is_bm25_search else 'Vector-only' if is_vector_search else 'BM25-only' if is_bm25_search else 'None'}"
        )

        # We fetch more candidates to have a good pool for fusion.
        candidate_limit = self.article_limit * 10

        # --- Perform Searches ---
        if query_data.get("user_language") != "en":
            _search_viewpoint_text = query_data.get("translated_viewpoint")
        else:
            _search_viewpoint_text = viewpoint_text
        if not _search_viewpoint_text:
            raise ValueError("No search viewpoint text provided.")

        tasks = []
        if is_vector_search:
            tasks.append(
                self.component.search_article_chunks(
                    _search_viewpoint_text, candidate_limit
                )
            )
        if is_bm25_search:
            tasks.append(
                self.component.search_articles_by_title_only_bm25(
                    _search_viewpoint_text, candidate_limit
                )
            )

        if not tasks:
            logger.warning(
                "Both vector_weight and bm25_weight are zero. No search performed."
            )
            return []

        results = await asyncio.gather(*tasks)

        vector_results_raw = results[0] if is_vector_search else []
        bm25_results_raw = (
            results[1] if is_vector_search and is_bm25_search else results[0]
        )

        logger.info(
            f"Retrieved {len(vector_results_raw)} vector candidates and "
            f"{len(bm25_results_raw)} BM25 candidates."
        )

        # --- Fuse or Process Results ---
        merged_chunks = {}

        # Process vector results
        if is_vector_search:
            for chunk in vector_results_raw:
                chunk_id = f"{chunk['doc_id']}_{chunk['chunk_index']}"
                similarity = chunk.get("similarity", 0)
                merged_chunks[chunk_id] = {
                    **chunk,
                    "normalized_distance": similarity,  # Use similarity directly
                    "normalized_score": 0.0,
                    "fusion_score": 0.0,
                }

        # Process and merge BM25 results
        if is_bm25_search:
            max_score = (
                max(c.get("score", 0) for c in bm25_results_raw)
                if bm25_results_raw
                else 1.0
            )
            for chunk in bm25_results_raw:
                chunk_id = f"{chunk['source_id']}_{chunk['chunk_index']}"
                normalized_score = chunk.get("score", 0) / max_score
                if chunk_id in merged_chunks:
                    merged_chunks[chunk_id]["normalized_score"] = normalized_score
                else:
                    merged_chunks[chunk_id] = {
                        **chunk,
                        "normalized_distance": 0.0,
                        "normalized_score": normalized_score,
                        "fusion_score": 0.0,
                    }

        if not merged_chunks:
            return []

        # --- Calculate Final Score ---
        for chunk in merged_chunks.values():
            chunk["fusion_score"] = (
                self.vector_weight * chunk["normalized_distance"]
            ) + (self.bm25_weight * chunk["normalized_score"])

        # 4. Aggregate chunks into articles, ranking by the best chunk score
        merged_articles = {}
        for chunk in merged_chunks.values():
            # Use source_id from BM25 result or doc_id from vector result
            source_id = chunk.get("source_id") or chunk.get("doc_id")
            if source_id not in merged_articles:
                merged_articles[source_id] = {
                    "source_id": source_id,
                    "title": chunk["title"],
                    "url": chunk["url"],
                    "chunks": [],
                    "max_fusion_score": -1.0,
                }
            merged_articles[source_id]["chunks"].append(chunk)
            merged_articles[source_id]["max_fusion_score"] = max(
                merged_articles[source_id]["max_fusion_score"], chunk["fusion_score"]
            )

        # 5. Sort articles by their best chunk's fusion score
        sorted_articles_data = sorted(
            merged_articles.values(),
            key=lambda x: x["max_fusion_score"],
            reverse=True,
        )

        # 6. Build final SourceArticle objects
        final_articles = []
        for article_data in sorted_articles_data[: self.article_limit]:
            sorted_chunks = sorted(
                article_data["chunks"], key=lambda x: x["chunk_index"]
            )
            full_text = "".join(c["chunk_text"] for c in sorted_chunks)

            final_articles.append(
                SourceArticle(
                    source_name="dataset_wikipedia_en_hybrid",
                    source_url=article_data["url"],
                    source_identifier=str(article_data["source_id"]),
                    title=article_data["title"],
                    text_content=full_text,
                    language="en",
                )
            )

        logger.info(f"Hybrid search produced {len(final_articles)} final articles.")
        return final_articles
