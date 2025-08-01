"""
Timeline Orchestrator Service for coordinating end-to-end timeline generation.

Architecture: Orchestrates multi-stage pipeline from viewpoint text to final events.
Key Features: Article acquisition, event extraction, relevance filtering, event merging.
"""

import functools
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AppAsyncSessionLocal
from app.db_handlers import (
    EntityDBHandler,
    EventDBHandler,
    TaskDBHandler,
    ViewpointDBHandler,
    check_local_db,
)
from app.models import (
    Event,
    EventEntityAssociation,
    EventRawEventAssociation,
    Task,
    Viewpoint,
    ViewpointEventAssociation,
)
from app.schemas import (
    ArticleAcquisitionConfig,
    CanonicalEventData,
    KeywordExtractionResult,
    MergedEventGroupOutput,
    MergedEventGroupSchema,
    ParsedDateInfo,
    SourceArticle,
    TimelineEventForAPI,
    TimelineGenerationResult,
)
from app.services.article_acquisition import ArticleAcquisitionService
from app.services.embedding_event_merger import EmbeddingEventMerger
from app.services.embedding_service import embedding_service
from app.services.event_relevance_service import EventRelevanceService
from app.services.llm_extractor import (
    parse_date_string_with_llm,
    score_articles_relevance,
)
from app.services.process_callback import ProgressCallback
from app.services.viewpoint_processor import extract_keywords_from_viewpoint
from app.services.viewpoint_service import ViewpointService
from app.utils.logger import setup_logger

logger = setup_logger("timeline_orchestrator", level="DEBUG")


class TimelineOrchestratorService:
    """Orchestrates complete timeline generation pipeline."""

    def __init__(self):
        # Core services initialized with application-wide configuration
        self.viewpoint_service = ViewpointService()
        self.relevance_service = EventRelevanceService(
            batch_size=settings.timeline_batch_size,
            relevance_threshold=settings.timeline_relevance_threshold,
        )

        # Database handlers for direct database operations
        self.entity_handler = EntityDBHandler()
        self.event_handler = EventDBHandler()
        self.viewpoint_handler = ViewpointDBHandler()
        self.task_db_handler = TaskDBHandler()

    async def run_timeline_generation_task(
        self,
        task: Task,
        request_id: str,
        websocket_callback: Callable | None = None,
    ):
        """Execute timeline generation as background task with lifecycle management."""
        task_id = task.id
        start_time = datetime.now(UTC)
        try:
            # Stage 1: Task configuration validation and preprocessing
            try:
                task_config = ArticleAcquisitionConfig.model_validate(task.config or {})
                logger.info(
                    f"[BG Task {task_id}] Using validated task config: {task_config.model_dump_json()}"
                )
            except ValidationError as e:
                error_msg = f"Invalid task configuration: {e}"
                logger.error(f"[BG Task {task_id}] {error_msg}", exc_info=True)
                await self.task_db_handler.update_task_status(
                    task_id=task_id,
                    status="failed",
                    notes=f"Configuration error: {str(e)}",
                )
                return  # Early termination on configuration errors

            # Stage 2: Progress tracking system initialization
            # Set up dual callback system for database and WebSocket updates
            db_progress_callback = functools.partial(
                self._save_task_progress_to_db, task_id
            )
            callbacks = [db_progress_callback]
            if websocket_callback:
                callbacks.append(websocket_callback)
            progress_callback = ProgressCallback(callbacks)

            logger.info(
                f"[BG Task {task_id}] Starting background timeline generation for task type: {task.task_type}"
            )

            # Stage 3: Task status transition to processing state
            await self.task_db_handler.update_task_status(
                task_id=task_id,
                status="processing",
                notes=f"Background processing started {request_id}",
            )

            # Stage 4: Route to appropriate processing method based on task type
            generation_result = None

            if task.task_type == "synthetic_viewpoint":
                # Traditional synthetic viewpoint processing
                generation_result = await self._run_generic_timeline_task(
                    task=task,
                    task_config=task_config,
                    progress_callback=progress_callback,
                    request_id=request_id,
                    # Use default processing pipeline (no overrides)
                )
            elif task.task_type == "entity_canonical":
                # Entity canonical processing
                if progress_callback:
                    await progress_callback.report(
                        f"Starting entity canonical processing for entity {task.entity_id}",
                        "entity_canonical_start",
                        {"entity_id": str(task.entity_id)},
                        request_id,
                    )

                # Prepare entity source articles
                (
                    source_articles,
                    entity_name,
                    effective_data_source,
                ) = await self._prepare_entity_source_articles(
                    task.entity_id, request_id, f"[BG Task {task.id}] "
                )

                if not source_articles:
                    generation_result = TimelineGenerationResult(events=[])
                else:
                    # Use generic pipeline with entity-specific configurations
                    generation_result = await self._run_generic_timeline_task(
                        task=task,
                        task_config=task_config,
                        progress_callback=progress_callback,
                        request_id=request_id,
                        # Entity-specific parameters
                        skip_keyword_extraction=True,
                        skip_article_acquisition=True,
                        skip_relevance_filtering=True,  # All events from entity documents are relevant
                        viewpoint_topic_override=f"Entity Timeline: {entity_name}",
                        effective_data_source_override=effective_data_source,
                        source_articles=source_articles,
                        keywords_extracted_override=[entity_name],
                        articles_processed_override=len(source_articles),
                    )
            elif task.task_type == "document_canonical":
                # Document canonical processing
                if progress_callback:
                    await progress_callback.report(
                        f"Starting document canonical processing for document {task.source_document_id}",
                        "document_canonical_start",
                        {"source_document_id": str(task.source_document_id)},
                        request_id,
                    )

                # Prepare document source article
                (
                    source_article,
                    document_title,
                    effective_data_source,
                ) = await self._prepare_document_source_article(
                    task.source_document_id, request_id, f"[BG Task {task.id}] "
                )

                if not source_article:
                    generation_result = TimelineGenerationResult(events=[])
                else:
                    # Use generic pipeline with document-specific configurations
                    generation_result = await self._run_generic_timeline_task(
                        task=task,
                        task_config=task_config,
                        progress_callback=progress_callback,
                        request_id=request_id,
                        # Document-specific parameters
                        skip_keyword_extraction=True,
                        skip_article_acquisition=True,
                        skip_relevance_filtering=True,  # All events from document are relevant
                        viewpoint_topic_override=f"Document Timeline: {document_title}",
                        effective_data_source_override=effective_data_source,
                        source_articles=[source_article],
                        keywords_extracted_override=[document_title],
                        articles_processed_override=1,
                    )
            else:
                raise ValueError(f"Unsupported task type: {task.task_type}")

            # Stage 5: Result validation and task completion handling
            # Validate generation results and determine final task status
            if generation_result and generation_result.events:
                await self.task_db_handler.update_task_status(
                    task_id=task_id,
                    status="completed",
                    processing_duration=(
                        datetime.now(UTC) - start_time
                    ).total_seconds(),
                    notes="Background processing completed successfully",
                )
            else:
                # Handle case where no events were generated despite successful processing
                logger.warning(
                    f"[BG Task {task_id}] Timeline generation resulted in 0 events. Marking task as failed."
                )
                await self.task_db_handler.update_task_status(
                    task_id=task_id,
                    status="failed",
                    processing_duration=(
                        datetime.now(UTC) - start_time
                    ).total_seconds(),
                    notes="Timeline generation resulted in 0 events.",
                )

        except Exception as e:
            # Comprehensive error handling and recovery
            logger.error(
                f"[BG Task {task_id}] Critical error in background task: {e}",
                exc_info=True,
            )
            # Safe duration calculation with fallback for undefined start_time
            duration = (
                (datetime.now(UTC) - start_time).total_seconds()
                if "start_time" in locals()
                else -1
            )
            await self.task_db_handler.update_task_status(
                task_id=task_id,
                status="failed",
                notes=f"Critical background task error: {str(e)[:500]}",
                processing_duration=duration,
            )

    async def _save_task_progress_to_db(
        self,
        task_id: uuid.UUID,
        message: str,
        step: str,
        data: dict[str, Any] | None,
        request_id: str | None,
    ):
        """Database progress callback for persistent task progress tracking."""
        try:
            # Data parameter is part of callback signature but not used for database persistence
            _ = data
            current_time = datetime.now(UTC).isoformat()

            # Create progress step with automatic session management
            # The create_viewpoint_progress_step method is decorated with @check_local_db,
            # which handles session creation, commit, and rollback automatically
            await self.task_db_handler.create_viewpoint_progress_step(
                task_id=task_id,
                step_name=step,
                message=message,
                event_timestamp=current_time,
                request_id=request_id or "",
            )
        except Exception as e:
            # Error handling with context preservation
            # The handler method should have already logged the specific database error.
            # We log a higher-level error indicating the context without duplicate stack traces.
            logger.error(
                f"[{request_id}] Failed to save progress for task {task_id} during step '{step}': {e}",
                exc_info=False,  # Avoid duplicate stack traces in logs
            )

    async def _populate_existing_viewpoint_with_timeline(
        self,
        viewpoint_id: uuid.UUID,
        viewpoint_text: str,
        data_source_preference: str,
        progress_callback: ProgressCallback | None = None,
        request_id: str | None = None,
        task_id: uuid.UUID | None = None,
        task_config: ArticleAcquisitionConfig | None = None,
    ) -> TimelineGenerationResult:
        """Orchestrate complete timeline generation pipeline for existing viewpoint."""
        log_prefix = f"[RequestID: {request_id}] " if request_id else ""
        logger.info(
            f"{log_prefix}Starting timeline population for existing viewpoint {viewpoint_id}: '{viewpoint_text[:30]}...'"
        )

        # Initialize progress callback with default if not provided
        progress_callback = progress_callback or ProgressCallback([])

        try:
            # Pipeline Stage 1: Language detection and keyword extraction
            # This stage processes text without requiring database transactions
            keyword_result = await self._extract_keywords(
                viewpoint_text, request_id, progress_callback, task_config
            )
            language_code = keyword_result.viewpoint_language
            logger.info(f"{log_prefix}Detected language: {language_code}")

            # Pipeline Stage 2: Multi-source article acquisition
            # Acquires articles from various sources based on extracted keywords
            articles = await self._acquire_articles(
                viewpoint_text=viewpoint_text,
                keyword_result=keyword_result,
                language_code=language_code,
                data_source_preference=data_source_preference,
                request_id=request_id,
                progress_callback=progress_callback,
                task_config=task_config,
            )
            # Early termination handling for empty article acquisition
            if not articles:
                logger.warning(
                    f"{log_prefix}No articles acquired. Timeline generation will be empty."
                )
                # Mark viewpoint as failed since no articles were found
                await self.viewpoint_service.mark_viewpoint_failed_with_transaction(
                    viewpoint_id
                )
                return TimelineGenerationResult(events=[])

            # Pipeline Stage 3: Article relevance scoring and filtering
            # Filters articles based on relevance to the viewpoint using LLM scoring
            # Use task-level timeline_relevance_threshold if available, otherwise fall back to settings
            task_relevance_threshold = (
                task_config.timeline_relevance_threshold
                if task_config
                else settings.timeline_relevance_threshold
            )
            relevant_articles = await self._filter_articles_by_relevance(
                articles,
                viewpoint_text,
                request_id,
                progress_callback,
                relevance_threshold=task_relevance_threshold,
                article_limit=task_config.article_limit if task_config else None,
            )
            if not relevant_articles:
                logger.warning(
                    f"{log_prefix}No relevant articles found after scoring. Timeline generation will be empty."
                )
                # Mark viewpoint as failed since no relevant articles were found
                await self.viewpoint_service.mark_viewpoint_failed_with_transaction(
                    viewpoint_id
                )
                return TimelineGenerationResult(events=[])

            # Pipeline Stage 4: Event extraction and canonical viewpoint creation
            # Processes articles to extract events and create canonical viewpoints
            # Child services manage their own atomic transactions for each article
            all_canonical_event_ids = await self._get_canonical_events(
                relevant_articles,
                data_source_preference,
                request_id,
                progress_callback,
                task_config,
            )

            # Pipeline Stage 5-7: Database transaction for final processing
            # Start new database session to consolidate results from child services
            # All previous work is committed by child services, now we perform final operations
            async with AppAsyncSessionLocal() as db:
                # Pipeline Stage 5: Event relevance filtering and selection
                # Filter canonical events based on relevance to the viewpoint
                event_id_to_score = await self._filter_events_by_relevance(
                    all_canonical_event_ids,
                    viewpoint_text,
                    request_id,
                    progress_callback,
                    db=db,
                    translated_viewpoint_text=keyword_result.translated_viewpoint,
                )

                # Pipeline Stage 6: Intelligent event merging and deduplication
                # Merge related events using multi-stage matching algorithms
                merged_event_groups = await self._merge_events(
                    list(event_id_to_score.keys()),
                    language_code,
                    db=db,
                    request_id=request_id,
                    progress_callback=progress_callback,
                )

                # Pipeline Stage 7: Final viewpoint population and persistence
                # Populate viewpoint with merged events and establish associations
                final_events = await self._populate_existing_viewpoint_with_events(
                    viewpoint_id=viewpoint_id,
                    merged_event_groups=merged_event_groups,
                    event_id_to_score=event_id_to_score,
                    request_id=request_id,
                    progress_callback=progress_callback,
                    db=db,
                )

                # Critical: Commit the transaction to persist all changes
                await db.commit()

                logger.info(
                    f"{log_prefix}Timeline population process completed successfully for viewpoint {viewpoint_id}."
                )

                # Return comprehensive result with metadata for tracking and analysis
                return TimelineGenerationResult(
                    events=final_events,
                    viewpoint_id=viewpoint_id,
                    events_count=len(final_events),
                    keywords_extracted=keyword_result.english_keywords,
                    articles_processed=len(relevant_articles),
                )

        except Exception as e:
            # Comprehensive error handling with proper cleanup
            logger.error(
                f"{log_prefix}Timeline population for viewpoint {viewpoint_id} failed: {e}",
                exc_info=True,
            )

            # Mark the viewpoint as failed in an isolated transaction
            await self.viewpoint_service.mark_viewpoint_failed_with_transaction(
                viewpoint_id
            )
            raise  # Re-raise exception for upstream handling by task runner

    async def _extract_keywords(
        self,
        viewpoint_text: str,
        request_id: str,
        progress_callback: ProgressCallback | None = None,
        task_config: ArticleAcquisitionConfig | None = None,
    ) -> KeywordExtractionResult:
        """Extract keywords and detect language from viewpoint text."""
        if progress_callback:
            await progress_callback.report(
                "Detecting language and extracting keywords...",
                "keyword_extraction_start",
                None,
                request_id,
            )

        # Get article limit from task config for keyword extraction strategy
        article_limit = (
            task_config.article_limit if task_config else settings.default_article_limit
        )

        keyword_result = await extract_keywords_from_viewpoint(
            viewpoint_text, article_limit=article_limit, parent_request_id=request_id
        )

        if not keyword_result.english_keywords:
            logger.warning(
                f"[RequestID: {request_id}] No keywords were extracted from viewpoint."
            )
            # We might want to stop here if no keywords are found.
            # For now, we'll let it continue, but it will likely find no articles.

        if progress_callback:
            await progress_callback.report(
                f"Language detected: {keyword_result.viewpoint_language}",
                "language_detection_complete",
                {"language": keyword_result.viewpoint_language},
                request_id,
            )

            await progress_callback.report(
                f"Extracted {len(keyword_result.english_keywords)} keywords:{', '.join(keyword_result.original_keywords)}",
                "keyword_extraction_complete",
                {
                    "language": keyword_result.viewpoint_language,
                    "keywords": keyword_result.original_keywords,
                },
                request_id,
            )

        return keyword_result

    async def _filter_articles_by_relevance(
        self,
        articles: list[SourceArticle],
        viewpoint_text: str,
        request_id: str,
        progress_callback: ProgressCallback | None = None,
        relevance_threshold: float = None,  # Use default from settings
        article_limit: int | None = None,  # New parameter for limiting article count
    ) -> list[SourceArticle]:
        """Filter articles by relevance to viewpoint and limit to specified count based on relevance ranking."""

        # Use default from settings if not provided
        if relevance_threshold is None:
            relevance_threshold = settings.article_filter_relevance_threshold

        if not articles:
            logger.warning(
                f"[RequestID: {request_id}] No articles acquired to score for relevance."
            )
            return []

        if progress_callback:
            await progress_callback.report(
                f"Scoring relevance of {len(articles)} acquired articles...",
                "article_relevance_scoring_start",
                {"article_count": len(articles)},
                request_id,
            )

        articles_to_score = [
            {"title": article.title, "text_content": article.text_content}
            for article in articles
        ]

        relevance_scores = await score_articles_relevance(
            viewpoint_text=viewpoint_text,
            articles=articles_to_score,
            parent_request_id=request_id,
        )

        # Collect articles with their relevance scores
        scored_articles = []
        total_articles = len(articles)

        for i, article in enumerate(articles):
            score = relevance_scores.get(article.title)
            current_index = i + 1

            if score is not None and score >= relevance_threshold:
                scored_articles.append((article, score))
                # Handle None score gracefully in formatting
                score_text = f"{score:.2f}" if score is not None else "None"
                logger.info(
                    f"[RequestID: {request_id}] Article '{article.title}' is relevant with score {score_text}."
                )

                # Report progress for relevant article
                if progress_callback:
                    await progress_callback.report(
                        f"Article {current_index}/{total_articles}: '{article.title}' is relevant (score: {score_text})",
                        "article_relevance_check",
                        {
                            "current": current_index,
                            "total": total_articles,
                            "article_title": article.title,
                            "score": score,
                            "is_relevant": True,
                            "relevant_count": len(scored_articles),
                        },
                        request_id,
                    )
            else:
                logger.info(
                    f"[RequestID: {request_id}] Article '{article.title}' is NOT relevant with score {score}. Discarding."
                )

                # Report progress for non-relevant article
                if progress_callback:
                    # Handle None score gracefully in formatting
                    score_text = f"{score:.2f}" if score is not None else "None"
                    await progress_callback.report(
                        f"Article {current_index}/{total_articles}: '{article.title}' is not relevant (score: {score_text})",
                        "article_relevance_check",
                        {
                            "current": current_index,
                            "total": total_articles,
                            "article_title": article.title,
                            "score": score,
                            "is_relevant": False,
                            "relevant_count": len(scored_articles),
                        },
                        request_id,
                    )

        # Sort articles by relevance score in descending order (highest relevance first)
        scored_articles.sort(key=lambda x: x[1], reverse=True)

        # Apply article limit if specified
        if article_limit and len(scored_articles) > article_limit:
            logger.info(
                f"[RequestID: {request_id}] Limiting articles from {len(scored_articles)} to {article_limit} based on relevance ranking"
            )
            scored_articles = scored_articles[:article_limit]

        # Extract the articles from the scored tuples
        relevant_articles = [article for article, score in scored_articles]

        logger.info(
            f"[RequestID: {request_id}] Filtered down to {len(relevant_articles)} relevant articles from {len(articles)} total articles."
        )

        if progress_callback:
            await progress_callback.report(
                f"Found {len(relevant_articles)} relevant articles after scoring and limiting.",
                "article_relevance_scoring_complete",
                {
                    "relevant_article_count": len(relevant_articles),
                    "total_article_count": len(articles),
                },
                request_id,
            )

        return relevant_articles

    async def _acquire_articles(
        self,
        viewpoint_text: str,
        keyword_result: KeywordExtractionResult,
        language_code: str,
        data_source_preference: str,
        request_id: str,
        progress_callback: ProgressCallback | None = None,
        task_config: ArticleAcquisitionConfig | None = None,
    ) -> list[SourceArticle]:
        """Acquire articles from various sources based on extracted keywords."""
        if progress_callback:
            await progress_callback.report(
                "Acquiring source articles...",
                "article_acquisition_start",
                {
                    "keywords": keyword_result.original_keywords,
                    "language": language_code,
                },
                request_id,
            )

        # Based on the user's language and preferences, we call the acquisition service
        query_data = {
            "keywords": keyword_result.original_keywords,
            "user_language": language_code,
            "english_keywords": keyword_result.english_keywords,
            "viewpoint_text": viewpoint_text,
            "task_config": task_config.model_dump() if task_config else {},
            "data_source_preference": data_source_preference,
            "translated_viewpoint": keyword_result.translated_viewpoint,
        }
        logger.info(f"acquire_articles query_data: {query_data}")

        acquisition_service = ArticleAcquisitionService()
        articles = await acquisition_service.acquire_articles(
            query_data, progress_callback
        )

        logger.info(
            f"[RequestID: {request_id}] Acquired {len(articles)} articles for processing."
        )

        if not articles:
            logger.warning(
                f"[RequestID: {request_id}] No articles acquired for viewpoint. Timeline generation will be empty."
            )
            if progress_callback:
                await progress_callback.report(
                    "No source articles found.",
                    "article_acquisition_complete",
                    None,
                    request_id,
                )
            return []

        if progress_callback:
            await progress_callback.report(
                f"Acquired {len(articles)} articles.",
                "article_acquisition_complete",
                {"article_count": len(articles)},
                request_id,
            )
        return articles

    @check_local_db
    async def _get_canonical_events(
        self,
        articles: list[SourceArticle],
        data_source_preference: str,
        request_id: str,
        progress_callback: ProgressCallback | None = None,
        task_config: ArticleAcquisitionConfig | None = None,
        *,
        db: AsyncSession = None,
    ) -> list[uuid.UUID]:
        """Process articles to extract events and create canonical viewpoints."""
        assert db is not None, "Database session is required"

        if progress_callback:
            await progress_callback.report(
                "Starting to process articles for canonical events...",
                "canonical_event_extraction_start",
                {"article_count": len(articles)},
                request_id,
            )

        processed_article_count = 0
        total_articles = len(articles)

        # Use a set to collect unique event IDs
        all_canonical_event_ids: set[uuid.UUID] = set()

        for i, article in enumerate(articles):
            try:
                logger.info(
                    f"[RequestID: {request_id}] Processing article {i + 1}/{total_articles}: "
                    f"{article.source_identifier} ({article.title})"
                )

                event_ids = (
                    await self.viewpoint_service.get_or_create_canonical_viewpoint(
                        article,
                        data_source_preference=data_source_preference,
                        request_id=request_id,
                        progress_callback=progress_callback,
                        task_config=task_config,
                        db=db,
                    )
                )

                if event_ids:
                    logger.info(
                        f"[RequestID: {request_id}] Successfully committed canonical viewpoint "
                        f"for article {article.source_identifier}. Retrieved {len(event_ids)} events."
                    )
                    all_canonical_event_ids.update(event_ids)
                    processed_article_count += 1
                else:
                    # If no events were produced, rollback this article's session
                    logger.warning(
                        f"[RequestID: {request_id}] No events were generated for article "
                        f"{article.source_identifier}. Nothing to commit."
                    )

                if progress_callback:
                    await progress_callback.report(
                        f"Processed article {i + 1}/{total_articles}: '{article.title}' got {len(event_ids)} events",
                        "canonical_events_progress",
                        {
                            "current": i + 1,
                            "total": total_articles,
                            "article_title": article.title,
                        },
                        request_id,
                    )
            except Exception as e:
                logger.error(
                    f"[RequestID: {request_id}] Error processing article "
                    f"{article.source_identifier} ({article.title}). Error: {e}",
                    exc_info=True,
                )
                # Continue to the next article
                continue

        logger.info(
            f"[RequestID: {request_id}] Canonical event retrieval finished. "
            f"Successfully processed {processed_article_count}/{total_articles} articles."
        )

        if not all_canonical_event_ids:
            logger.warning(
                f"[{request_id}] No canonical events were found after processing all articles."
            )
            if progress_callback:
                await progress_callback.report(
                    "Finished article processing, but no events were found.",
                    "canonical_events_complete",
                    {
                        "processed_count": processed_article_count,
                        "total_count": total_articles,
                        "unique_event_count": 0,
                    },
                    request_id,
                )
            return []

        # Convert set to list for return
        unique_event_ids = list(all_canonical_event_ids)

        logger.info(
            f"[{request_id}] Successfully collected {len(unique_event_ids)} unique event IDs."
        )

        if progress_callback:
            await progress_callback.report(
                f"Finished processing {processed_article_count} articles, yielding {len(unique_event_ids)} unique events.",
                "canonical_events_complete",
                {
                    "processed_count": processed_article_count,
                    "total_count": total_articles,
                    "unique_event_count": len(unique_event_ids),
                },
                request_id,
            )
        return unique_event_ids

    async def _filter_events_by_relevance(
        self,
        all_canonical_event_ids: list[uuid.UUID],
        viewpoint_text: str,
        request_id: str,
        progress_callback: ProgressCallback | None,
        db: AsyncSession,
        translated_viewpoint_text: str | None = None,
    ) -> dict[uuid.UUID, float]:
        """Filter extracted events by relevance to viewpoint text and return event IDs with their relevance scores."""
        if progress_callback:
            await progress_callback.report(
                f"Filtering {len(all_canonical_event_ids)} events for relevance...",
                "relevance_filtering_start",
                {"event_count": len(all_canonical_event_ids)},
                request_id,
            )

        # First, fetch the events we need to evaluate
        # logger.info(f"all_canonical_event_ids: {all_canonical_event_ids}")

        events = await self.event_handler.get_events_by_ids(
            all_canonical_event_ids, db=db
        )

        # logger.info(f"events: {[event.to_dict() for event in events]}")

        # Convert events to the format expected by the relevance service
        event_data_list = [
            {
                "event_data": {
                    "description": event.description,
                    "date": event.event_date_str,
                },
                "original_event_id": event.id,  # Store the ID for later reference
            }
            for event in events
        ]

        # logger.info(f"event_data_list: {event_data_list}")

        # Filter events by relevance
        # Use translated viewpoint text if available, otherwise fall back to original
        effective_viewpoint_text = translated_viewpoint_text or viewpoint_text
        (
            relevant_event_data_list,
            stats,
        ) = await self.relevance_service.filter_relevant_events(
            event_data_list, effective_viewpoint_text, request_id
        )

        # Create a mapping of event IDs to their relevance scores
        event_id_to_score = {}
        for item in relevant_event_data_list:
            event_id = item["original_event_id"]
            relevance_score = item.get("relevance_score", 0.0)
            event_id_to_score[event_id] = relevance_score

        logger.info(
            f"[RequestID: {request_id}] Filtered {len(all_canonical_event_ids)} events down to {len(event_id_to_score)} relevant events. Stats: {stats}"
        )
        if progress_callback:
            await progress_callback.report(
                f"Found {len(event_id_to_score)} relevant events.",
                "relevance_filtering_complete",
                {"relevant_event_count": len(event_id_to_score)},
                request_id,
            )
        return event_id_to_score

    async def _merge_events(
        self,
        relevant_event_ids: list[uuid.UUID],
        language_code: str,
        db: AsyncSession,
        request_id: str,
        progress_callback: ProgressCallback | None = None,
    ) -> list[MergedEventGroupSchema]:
        """Merge related events using intelligent deduplication."""
        log_prefix = f"[RequestID: {request_id}] " if request_id else ""
        if progress_callback:
            await progress_callback.report(
                "Merging related events...",
                "event_merging_start",
                {"event_count": len(relevant_event_ids)},
                request_id,
            )

        # 1. Batch load all relevant Event objects with their associations
        # This is a key performance optimization to prevent N+1 queries later.
        events_from_db = await self.event_handler.get_events_by_ids_with_associations(
            relevant_event_ids, db=db
        )
        logger.info(
            f"{log_prefix}Loaded {len(events_from_db)} events with their details for merging"
        )

        # 2. Call EmbeddingEventMerger
        merger_service = EmbeddingEventMerger(user_lang=language_code)
        merge_instructions: list[
            MergedEventGroupOutput
        ] = await merger_service.get_merge_instructions(
            events_from_db, progress_callback, request_id
        )

        # 3. Convert the output of the merger service into our defined MergedEventGroupSchema
        merged_event_groups = []
        event_map = {event.id: event for event in events_from_db}

        for instruction in merge_instructions:
            # instruction is now a MergedEventGroupOutput Pydantic model
            representative_event = instruction.representative_event
            source_contributions = instruction.source_contributions

            if not representative_event or not source_contributions:
                logger.warning(
                    f"{log_prefix}Skipping instruction with no representative event or source contributions {representative_event} {source_contributions}"
                )
                continue

            # Reconstruct the list of source Event objects for the group
            source_event_ids = [
                uuid.UUID(contrib.event_data.id)
                for contrib in source_contributions
                if contrib.event_data.id
            ]
            source_events_for_group = [
                event_map[event_id]
                for event_id in source_event_ids
                if event_id in event_map
            ]

            if not source_events_for_group:
                continue

            # Check if the event was a simple group (not merged) or a result of merging
            is_merged = len(source_contributions) > 1

            if not is_merged:
                merged_event_groups.append(
                    MergedEventGroupSchema(
                        is_merged=False, source_events=source_events_for_group
                    )
                )
            else:
                # Directly access the typed data from the instruction object
                final_date_info = representative_event.date_info

                # Fallback: if no valid date_info object, try to parse from string.
                # This is kept for robustness in case the merger service cannot produce a date_info.
                if not final_date_info and representative_event.event_date_str:
                    logger.info(
                        f"{log_prefix}No valid date_info from merger. Parsing '{representative_event.event_date_str}' with LLM."
                    )
                    final_date_info = await parse_date_string_with_llm(
                        representative_event.event_date_str
                    )
                    if not final_date_info:
                        logger.error(
                            f"{log_prefix}Failed to parse date string '{representative_event.event_date_str}' with LLM. Event will have no date info."
                        )

                merged_event_groups.append(
                    MergedEventGroupSchema(
                        is_merged=True,
                        description=representative_event.description,
                        date_info=final_date_info,  # Directly pass the Pydantic object or None
                        source_events=source_events_for_group,
                    )
                )

        if progress_callback:
            await progress_callback.report(
                f"Merging complete. Found {len(merged_event_groups)} unique events.",
                "event_merging_complete",
                {"merged_group_count": len(merged_event_groups)},
                request_id,
            )
        return merged_event_groups

    async def _compute_embedding_for_merged_event(
        self, description: str, event_date_str: str, source_events: list[Event]
    ) -> list[float]:
        """
        Compute embedding vector for merged events using unified embedding service.

        Uses normalized data representation to ensure consistency with other parts of the system.

        Args:
            description: Merged event description
            event_date_str: Event date string
            source_events: List of source events

        Returns:
            list[float]: 768-dimensional embedding vector suitable for pgvector storage
        """
        # Use normalized data structure
        entities_list = []
        for source_event in source_events:
            if (
                hasattr(source_event, "entity_associations")
                and source_event.entity_associations
            ):
                for assoc in source_event.entity_associations:
                    if hasattr(assoc, "entity") and assoc.entity:
                        entity_name = getattr(assoc.entity, "entity_name", "")
                        entity_type = getattr(assoc.entity, "entity_type", "")
                        if entity_name.strip():
                            entities_list.append(
                                {
                                    "name": entity_name.strip(),
                                    "type": entity_type.strip() if entity_type else "",
                                }
                            )

        # Deduplicate entities
        seen_entities = set()
        unique_entities = []
        for entity in entities_list:
            entity_key = (entity["name"], entity["type"])
            if entity_key not in seen_entities:
                seen_entities.add(entity_key)
                unique_entities.append(entity)

        # Get source text snippet (from the first source event)
        source_snippet = None
        if source_events:
            first_event = source_events[0]
            if (
                hasattr(first_event, "raw_event_association_links")
                and first_event.raw_event_association_links
            ):
                first_raw_event = first_event.raw_event_association_links[0].raw_event
                if first_raw_event and hasattr(first_raw_event, "source_text_snippet"):
                    source_snippet = first_raw_event.source_text_snippet

        # Create normalized data
        canonical_data = CanonicalEventData(
            description=description or "",
            event_date_str=event_date_str or "",
            entities=unique_entities,
            source_snippet=source_snippet,
        )

        try:
            # Use normalized text representation
            event_text = canonical_data.to_embedding_text()
            logger.debug(f"Computing embedding for merged event: {event_text[:100]}...")

            # Use unified embedding service
            embedding = embedding_service.encode(
                event_text,
                convert_to_numpy=True,
                normalize_embeddings=True,
                add_query_prefix=True,  # Add "query: " prefix for Snowflake model
            )

            # Convert to list for pgvector storage
            embedding_list = embedding.tolist()
            logger.debug(
                f"Successfully computed embedding with {len(embedding_list)} dimensions"
            )

            return embedding_list

        except Exception as e:
            logger.error(
                f"Failed to compute embedding for merged event: {e}", exc_info=True
            )
            # Return zero vector as fallback (768 dimensions for Snowflake model)
            return [0.0] * 768

    @check_local_db
    async def _ensure_viewpoint_exists_for_task(
        self,
        task: Task,
        data_source_preference: str,
        request_id: str,
        *,
        db: AsyncSession = None,
        viewpoint_text_override: str | None = None,
        task_config: ArticleAcquisitionConfig | None = None,
    ) -> tuple[uuid.UUID | None, bool]:
        """Ensure viewpoint exists for task, reusing completed viewpoints when possible."""
        # Re-attach the detached task object to the current session
        # to ensure that any modifications to it are tracked and persisted.
        # Use merge to handle cases where the object might be from another session.
        task = await db.merge(task)

        viewpoint_text = viewpoint_text_override or task.topic_text.strip()

        # Use task-level reuse setting if available, otherwise fall back to global setting
        should_reuse = (
            task_config.reuse_composite_viewpoint
            if task_config
            else settings.reuse_composite_viewpoint
        )

        if should_reuse:
            # First, check if there's an existing completed viewpoint
            existing_viewpoint = await self.viewpoint_handler.get_by_attributes(
                topic=viewpoint_text,
                data_source_preference=data_source_preference,
                status="completed",
                db=db,
            )

            if existing_viewpoint:
                logger.info(
                    f"[RequestID: {request_id}] Found existing completed viewpoint {existing_viewpoint.id} for task {task.id} (reuse_composite_viewpoint={should_reuse})"
                )
                # Update task with existing viewpoint_id
                task.viewpoint_id = existing_viewpoint.id
                await db.flush()
                return existing_viewpoint.id, False

        # If no existing viewpoint, or reuse is disabled, create a new one
        logger.info(
            f"[RequestID: {request_id}] Creating new viewpoint for task {task.id}"
        )

        new_viewpoint = Viewpoint(
            topic=viewpoint_text,
            viewpoint_type="synthetic",
            status="processing",
            data_source_preference=data_source_preference,
        )
        db.add(new_viewpoint)
        await db.flush()  # Get the ID

        # Update task with new viewpoint_id
        task.viewpoint_id = new_viewpoint.id
        await db.flush()

        logger.info(
            f"[RequestID: {request_id}] Created new viewpoint {new_viewpoint.id} for task {task.id}"
        )
        return new_viewpoint.id, True

    @check_local_db
    async def _populate_existing_viewpoint_with_events(
        self,
        viewpoint_id: uuid.UUID,
        merged_event_groups: list[MergedEventGroupSchema],
        event_id_to_score: dict[uuid.UUID, float],
        request_id: str = "",
        progress_callback: ProgressCallback | None = None,
        *,
        db: AsyncSession = None,
    ) -> list[TimelineEventForAPI]:
        """Populate viewpoint with events from merged event groups."""
        log_prefix = f"[RequestID: {request_id}] " if request_id else ""

        # Retrieve and validate the target viewpoint
        # Note: Transaction management handled by @check_local_db decorator
        viewpoint = await self.viewpoint_handler.get(viewpoint_id, db=db)
        if not viewpoint:
            logger.error(f"{log_prefix}Viewpoint {viewpoint_id} not found")
            return []

        # Process each merged event group to create final viewpoint associations
        for group in merged_event_groups:
            final_event_for_viewpoint: Event

            if not group.is_merged:
                # Case A: Simple event association
                # Use existing event directly without modification
                final_event_for_viewpoint = group.source_events[0]
            else:
                # Case B: Complex merged event creation
                # Create new consolidated event representing multiple source events
                raw_date_str_from_llm = None
                date_info_obj = None

                if group.date_info:
                    # FIXED: Handle ParsedDateInfo object instead of dict
                    if hasattr(group.date_info, "original_text"):
                        # It's a ParsedDateInfo object
                        raw_date_str_from_llm = group.date_info.original_text
                    else:
                        # Fallback for dict format (shouldn't happen with new flow)
                        raw_date_str_from_llm = group.date_info.get(
                            "date_str"
                        ) or group.date_info.get("date")

                    # Date information processing and validation with robust error handling
                    try:
                        if isinstance(group.date_info, ParsedDateInfo):
                            parsed_date_info = group.date_info
                        else:
                            parsed_date_info = (
                                ParsedDateInfo(**group.date_info)
                                if group.date_info
                                else None
                            )

                        date_info_obj = (
                            parsed_date_info.to_date_range()
                            if parsed_date_info
                            else None
                        )
                    except Exception as e:
                        logger.warning(
                            f"{log_prefix}Failed to create ParsedDateInfo from group.date_info: {e}. "
                            f"date_info: {group.date_info}"
                        )
                        date_info_obj = None

                    # Event date string determination with multiple fallback strategies
                    event_date_str_for_new_event = None
                    if date_info_obj and date_info_obj.original_text:
                        event_date_str_for_new_event = date_info_obj.original_text
                    elif raw_date_str_from_llm:
                        event_date_str_for_new_event = raw_date_str_from_llm
                    else:
                        # Fallback: use date_str from first source event
                        if (
                            group.source_events
                            and group.source_events[0].event_date_str
                        ):
                            event_date_str_for_new_event = group.source_events[
                                0
                            ].event_date_str
                            logger.warning(
                                f"{log_prefix}Using fallback event_date_str from source event for merged event: {event_date_str_for_new_event}"
                            )
                        else:
                            # Last resort: generate a basic date string
                            if date_info_obj and date_info_obj.start_date:
                                event_date_str_for_new_event = str(
                                    date_info_obj.start_date.year
                                )
                                logger.warning(
                                    f"{log_prefix}Generated basic event_date_str from start_date: {event_date_str_for_new_event}"
                                )
                            else:
                                event_date_str_for_new_event = "Unknown"
                                logger.error(
                                    f"{log_prefix}Could not determine event_date_str for merged event, using 'Unknown'"
                                )

                    # Compute embedding vector for the merged event based on its actual description
                    # For short event descriptions, semantic accuracy is more important than marginal performance gains
                    description_vector = await self._compute_embedding_for_merged_event(
                        group.description,
                        event_date_str_for_new_event,
                        group.source_events,
                    )

                    new_merged_event = Event(
                        description=group.description,
                        event_date_str=event_date_str_for_new_event,
                        date_info=(
                            group.date_info.model_dump()
                            if isinstance(group.date_info, ParsedDateInfo)
                            else group.date_info
                        ),
                        description_vector=description_vector,  # Add the computed embedding
                    )

                db.add(new_merged_event)
                await db.flush()  # To get the ID

                # Provenance establishment and source tracking
                # Collect all RawEvents associated with the source events for complete lineage
                all_source_raw_events = set()
                for source_event in group.source_events:
                    for association in source_event.raw_event_association_links:
                        # Raw event associations were preloaded for performance
                        all_source_raw_events.add(association.raw_event)

                # Create associations between merged event and all source RawEvents
                # This preserves complete provenance and traceability
                for raw_event in all_source_raw_events:
                    db.add(
                        EventRawEventAssociation(
                            event_id=new_merged_event.id, raw_event_id=raw_event.id
                        )
                    )

                # Collect and associate all entities from source events
                all_source_entities = set()
                for source_event in group.source_events:
                    if source_event.entity_associations:
                        for assoc in source_event.entity_associations:
                            all_source_entities.add(assoc.entity_id)

                # Create entity associations for merged event
                for entity_id in all_source_entities:
                    db.add(
                        EventEntityAssociation(
                            event_id=new_merged_event.id, entity_id=entity_id
                        )
                    )

                final_event_for_viewpoint = new_merged_event

            # Create viewpoint-event association for the final event
            # This establishes the connection between viewpoint and its timeline events

            # Calculate relevance score for this event
            # For non-merged events, use the original score
            # For merged events, use the maximum score from source events
            relevance_score = 0.0
            if not group.is_merged:
                # Simple event - use its original relevance score
                relevance_score = event_id_to_score.get(
                    final_event_for_viewpoint.id, 0.0
                )
            else:
                # Merged event - use the maximum relevance score from source events
                source_scores = [
                    event_id_to_score.get(source_event.id, 0.0)
                    for source_event in group.source_events
                ]
                relevance_score = max(source_scores) if source_scores else 0.0

            db.add(
                ViewpointEventAssociation(
                    viewpoint_id=viewpoint_id,
                    event_id=final_event_for_viewpoint.id,
                    relevance_score=relevance_score,
                )
            )

        # Update viewpoint status based on processing results
        if merged_event_groups:
            viewpoint.status = "completed"
        else:
            # Handle edge case where no events are provided for population
            viewpoint.status = "failed"
            logger.warning(
                f"{log_prefix}Viewpoint {viewpoint_id} is being marked as failed as it has no events."
            )

        # Flush pending changes to ensure data consistency within transaction
        await db.flush()

        # Retrieve complete viewpoint details with populated timeline events
        viewpoint_details = (
            await self.viewpoint_handler.get_complete_viewpoint_details_by_id(
                viewpoint_id, db=db
            )
        )
        if viewpoint_details:
            final_events_for_api = viewpoint_details["timeline_events"]
        else:
            logger.error(
                f"{log_prefix}Could not retrieve details for viewpoint {viewpoint_id} after population"
            )
            final_events_for_api = []

        logger.info(
            f"{log_prefix}Successfully populated viewpoint {viewpoint_id} with {len(final_events_for_api)} events"
        )
        return final_events_for_api

    async def _run_generic_timeline_task(
        self,
        task: Task,
        task_config: ArticleAcquisitionConfig,
        progress_callback: ProgressCallback,
        request_id: str,
        *,
        # Processing mode parameters
        skip_keyword_extraction: bool = False,
        skip_article_acquisition: bool = False,
        skip_relevance_filtering: bool = False,
        # Data source parameters
        viewpoint_topic_override: str | None = None,
        effective_data_source_override: str | None = None,
        source_articles: list[SourceArticle] | None = None,
        keywords_extracted_override: list[str] | None = None,
        articles_processed_override: int | None = None,
    ) -> TimelineGenerationResult:
        """Generic timeline generation method that supports all task types with configurable pipeline stages."""
        log_prefix = f"[BG Task {task.id}] "

        # Determine effective parameters based on task type and overrides
        viewpoint_text = viewpoint_topic_override or task.topic_text.strip()

        # Stage 1: Data source preference determination
        if effective_data_source_override:
            effective_data_source = effective_data_source_override
        else:
            effective_data_source = "online_wikipedia"
            if task.config and task.config.get("data_source_preference"):
                ds_from_config = task.config["data_source_preference"]
                if ds_from_config.lower() != "none":
                    effective_data_source = ds_from_config

        # Stage 2: Viewpoint existence verification and creation
        viewpoint_id, needs_processing = await self._ensure_viewpoint_exists_for_task(
            task=task,
            data_source_preference=effective_data_source,
            request_id=request_id,
            viewpoint_text_override=viewpoint_text,
            task_config=task_config,
        )

        if not viewpoint_id:
            raise RuntimeError("Failed to create or find viewpoint for task")

        # Stage 3: Processing requirement assessment and optimization
        if not needs_processing:
            logger.info(
                f"{log_prefix}Found existing completed viewpoint {viewpoint_id}. Verifying event count..."
            )
            async with AppAsyncSessionLocal() as db:
                viewpoint_details = (
                    await self.viewpoint_handler.get_complete_viewpoint_details_by_id(
                        viewpoint_id, db=db
                    )
                )

            # If the viewpoint has events, reuse it.
            if viewpoint_details and viewpoint_details.get("timeline_events"):
                existing_events = viewpoint_details["timeline_events"]
                logger.info(
                    f"{log_prefix}Reusing existing viewpoint {viewpoint_id} with {len(existing_events)} events."
                )
                return TimelineGenerationResult(
                    events=existing_events,
                    viewpoint_id=viewpoint_id,
                    events_count=len(existing_events),
                    keywords_extracted=keywords_extracted_override or [],
                    articles_processed=articles_processed_override or 0,
                )
            else:
                # If viewpoint is empty, it needs processing.
                logger.warning(
                    f"{log_prefix}Existing viewpoint {viewpoint_id} is empty. Forcing reprocessing."
                )
                needs_processing = True

        # Stage 4: Processing pipeline execution
        if needs_processing:
            if skip_keyword_extraction and skip_article_acquisition and source_articles:
                # Direct processing mode for entity/document canonical tasks
                return await self._process_direct_articles_pipeline(
                    viewpoint_id=viewpoint_id,
                    viewpoint_text=viewpoint_text,
                    source_articles=source_articles,
                    effective_data_source=effective_data_source,
                    skip_relevance_filtering=skip_relevance_filtering,
                    progress_callback=progress_callback,
                    request_id=request_id,
                    task_config=task_config,
                    keywords_extracted_override=keywords_extracted_override,
                    articles_processed_override=articles_processed_override,
                )
            else:
                # Traditional synthetic viewpoint processing
                return await self._populate_existing_viewpoint_with_timeline(
                    viewpoint_id=viewpoint_id,
                    viewpoint_text=viewpoint_text,
                    data_source_preference=effective_data_source,
                    progress_callback=progress_callback,
                    request_id=request_id,
                    task_id=task.id,
                    task_config=task_config,
                )

    async def _process_direct_articles_pipeline(
        self,
        viewpoint_id: uuid.UUID,
        viewpoint_text: str,
        source_articles: list[SourceArticle],
        effective_data_source: str,
        skip_relevance_filtering: bool,
        progress_callback: ProgressCallback,
        request_id: str,
        task_config: ArticleAcquisitionConfig | None = None,
        keywords_extracted_override: list[str] | None = None,
        articles_processed_override: int | None = None,
    ) -> TimelineGenerationResult:
        """Process articles directly without keyword extraction and article acquisition stages."""
        log_prefix = f"[RequestID: {request_id}] "

        # Stage 1: Get canonical events from source articles
        all_canonical_event_ids = await self._get_canonical_events(
            articles=source_articles,
            data_source_preference=effective_data_source,
            request_id=request_id,
            progress_callback=progress_callback,
            task_config=task_config,
        )

        if not all_canonical_event_ids:
            logger.warning(f"{log_prefix}No canonical events found")
            await self.viewpoint_service.mark_viewpoint_failed_with_transaction(
                viewpoint_id
            )
            return TimelineGenerationResult(events=[])

        # Stage 2: Event processing pipeline
        async with AppAsyncSessionLocal() as db:
            # Handle relevance filtering based on configuration
            if skip_relevance_filtering:
                # No relevance filtering - all events are considered relevant
                event_id_to_score = dict.fromkeys(all_canonical_event_ids, 1.0)
            else:
                # Apply relevance filtering
                event_id_to_score = await self._filter_events_by_relevance(
                    all_canonical_event_ids,
                    viewpoint_text,
                    request_id,
                    progress_callback,
                    db=db,
                )

            if not event_id_to_score:
                logger.warning(f"{log_prefix}No relevant events found after filtering")
                await self.viewpoint_service.mark_viewpoint_failed_with_transaction(
                    viewpoint_id
                )
                return TimelineGenerationResult(events=[])

            # Stage 3: Event merging and deduplication
            merged_event_groups = await self._merge_events(
                relevant_event_ids=list(event_id_to_score.keys()),
                language_code="en",  # TODO: Make this configurable
                db=db,
                request_id=request_id,
                progress_callback=progress_callback,
            )

            # Stage 4: Final viewpoint population
            final_events = await self._populate_existing_viewpoint_with_events(
                viewpoint_id=viewpoint_id,
                merged_event_groups=merged_event_groups,
                event_id_to_score=event_id_to_score,
                request_id=request_id,
                progress_callback=progress_callback,
                db=db,
            )

            await db.commit()

        logger.info(f"{log_prefix}Processing completed with {len(final_events)} events")

        return TimelineGenerationResult(
            events=final_events,
            viewpoint_id=viewpoint_id,
            events_count=len(final_events),
            keywords_extracted=keywords_extracted_override or [],
            articles_processed=articles_processed_override or len(source_articles),
        )

    async def _prepare_entity_source_articles(
        self,
        entity_id: uuid.UUID,
        request_id: str,
        log_prefix: str,
    ) -> tuple[list[SourceArticle], str, str]:
        """Prepare source articles from entity documents."""
        # Get entity and its source documents
        entity = await self.entity_handler.get_entity_with_sources_by_id(entity_id)
        if not entity:
            logger.error(f"{log_prefix}Entity {entity_id} not found")
            return [], "", ""

        source_documents = entity.source_documents
        if not source_documents:
            logger.warning(
                f"{log_prefix}Entity '{entity.entity_name}' has no source documents"
            )
            return [], entity.entity_name, ""

        # Convert source documents to source articles with full content
        from app.services.article_acquisition import ArticleAcquisitionService

        article_acquisition_service = ArticleAcquisitionService()
        source_articles = []

        for doc in source_documents:
            source_article = await self._convert_document_to_source_article(
                doc,
                article_acquisition_service,
                request_id,
                log_prefix,
                entity_metadata={
                    "entity_name": entity.entity_name,
                    "entity_id": str(entity.id),
                },
            )
            source_articles.append(source_article)

        # Determine effective data source
        unique_source_types = list(
            {doc.source_type for doc in source_documents if doc.source_type}
        )
        effective_data_source = (
            ",".join(sorted(unique_source_types))
            if unique_source_types
            else "online_wikipedia"
        )

        logger.info(
            f"{log_prefix}Processing {len(source_articles)} source articles from {len(source_documents)} source documents"
        )

        return source_articles, entity.entity_name, effective_data_source

    async def _prepare_document_source_article(
        self,
        source_document_id: uuid.UUID,
        request_id: str,
        log_prefix: str,
    ) -> tuple[SourceArticle | None, str, str]:
        """Prepare source article from single document."""
        from app.db_handlers import SourceDocumentDBHandler
        from app.services.article_acquisition import ArticleAcquisitionService

        source_doc_handler = SourceDocumentDBHandler()
        source_document = await source_doc_handler.get(source_document_id)
        if not source_document:
            logger.error(f"{log_prefix}Source document {source_document_id} not found")
            return None, "", ""

        article_acquisition_service = ArticleAcquisitionService()
        source_article = await self._convert_document_to_source_article(
            source_document,
            article_acquisition_service,
            request_id,
            log_prefix,
            document_metadata={
                "document_title": source_document.title,
                "document_id": str(source_document.id),
            },
        )

        effective_data_source = source_document.source_type or "document_source"

        return source_article, source_document.title, effective_data_source

    async def _convert_document_to_source_article(
        self,
        doc,
        article_acquisition_service,
        request_id: str,
        log_prefix: str,
        entity_metadata: dict | None = None,
        document_metadata: dict | None = None,
    ) -> SourceArticle:
        """Convert source document to SourceArticle with full content."""
        # Create basic SourceArticle with metadata
        metadata = {
            "wikibase_item": doc.wikibase_item,
            **(entity_metadata or {}),
            **(document_metadata or {}),
        }

        basic_source_article = SourceArticle(
            source_name=doc.source_type or "online_wikipedia",
            source_url=doc.wikipedia_url,
            source_identifier=doc.wiki_pageid or str(doc.id),
            title=doc.title,
            text_content=doc.extract or "",  # Start with extract as fallback
            language=doc.language,
            metadata=metadata,
        )

        # Try to get full content using ArticleAcquisitionService
        if doc.source_type:
            try:
                # Prepare comprehensive query data for ArticleAcquisitionService
                query_data = {
                    "viewpoint_text": f"Processing: {doc.title}",
                    "keywords": [doc.title],
                    "target_lang": doc.language,
                    "user_language": doc.language,
                    "article_limit": 1,
                    "parent_request_id": request_id,
                    "data_source_preference": doc.source_type,  # This is crucial
                    "config": {},  # Empty config for basic operation
                }

                # Use ArticleAcquisitionService to get full articles
                full_articles = await article_acquisition_service.acquire_articles(
                    query_data
                )

                if full_articles and len(full_articles) > 0:
                    # Find the matching article by title or use the first one
                    matching_article = None
                    for article in full_articles:
                        if article.title == doc.title:
                            matching_article = article
                            break

                    # If no exact title match, use the first article
                    if not matching_article:
                        matching_article = full_articles[0]

                    # Update the content with full article text
                    basic_source_article.text_content = matching_article.text_content
                    logger.info(
                        f"{log_prefix}Got full content for {doc.title} ({doc.source_type}): {len(matching_article.text_content)} chars"
                    )
                else:
                    logger.warning(
                        f"{log_prefix}Could not get full content for {doc.title} ({doc.source_type}), using extract"
                    )

            except Exception as e:
                logger.error(
                    f"{log_prefix}Error getting full content for {doc.title} ({doc.source_type}): {e}",
                    exc_info=True,
                )
                logger.warning(
                    f"{log_prefix}Falling back to extract for {doc.title} ({doc.source_type})"
                )
        else:
            logger.info(
                f"{log_prefix}No valid source_type for {doc.title}, using extract content"
            )

        return basic_source_article
