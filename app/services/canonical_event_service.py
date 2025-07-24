"""
Canonical Event Service - Core service for creating unique historical events
from raw event data using semantic deduplication.

This service implements the core logic for converting RawEvents into unique Event
records, performing semantic deduplication at the Event creation stage rather than
post-creation merging.

Key features:
- Embedding-based semantic similarity detection
- pgvector integration for efficient similarity search
- Dynamic threshold strategies for different contexts
- Comprehensive logging and performance monitoring
"""

from __future__ import annotations

import time

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, RawEvent
from app.schemas import EventDataForMerger, ParsedDateInfo, SourceInfoForMerger
from app.services.embedding_event_merger import EmbeddingEventMerger
from app.services.event_merger_service import RawEventInput
from app.utils.logger import setup_logger

logger = setup_logger("canonical_event_service", level="DEBUG")


class CanonicalEventService:
    """
    Core service for creating canonical Event records from RawEvents.

    Implements semantic deduplication using embedding-based similarity search
    to ensure each Event represents a unique historical occurrence.
    """

    def __init__(self):
        self._stats = {
            "total_raw_events_processed": 0,
            "new_events_created": 0,
            "duplicates_found": 0,
            "embedding_computations": 0,
            "similarity_searches_performed": 0,
        }

        logger.info("Initialized CanonicalEventService with unified embedding service")

    def _create_event_text_representation(
        self, raw_event: RawEvent, entities: list = None
    ) -> str:
        """
        Create comprehensive text representation for embedding computation.

        Combines description, date, and entity information into a single
        text that captures the semantic essence of the event.

        Args:
            raw_event: The RawEvent object
            entities: Optional list of entity information for this event
        """
        parts = []

        # Add event description
        if raw_event.original_description:
            parts.append(raw_event.original_description)

        # Add date information
        if raw_event.event_date_str:
            parts.append(f"Date: {raw_event.event_date_str}")

        # Add entity information
        if entities:
            entity_parts = []
            for entity in entities:
                entity_text = (
                    entity.get("original_name", "") if isinstance(entity, dict) else ""
                )
                entity_type = (
                    entity.get("entity_type", "") if isinstance(entity, dict) else ""
                )
                if entity_type:
                    entity_text += f" ({entity_type})"
                if entity_text.strip():
                    entity_parts.append(entity_text.strip())

            if entity_parts:
                parts.append(f"Entities: {', '.join(entity_parts)}")

        # Add source context
        if raw_event.source_text_snippet:
            # Limit snippet length to avoid overwhelming the embedding
            snippet = raw_event.source_text_snippet[:200]
            parts.append(f"Context: {snippet}")

        return " | ".join(parts)

    async def _compute_embedding(
        self, raw_event: RawEvent, entities: list = None
    ) -> np.ndarray:
        """
        使用统一的嵌入服务为原始事件计算嵌入向量。

        现在使用EmbeddingEventMerger的规范化接口确保一致性。

        Args:
            raw_event: 原始事件对象
            entities: 可选的实体信息列表

        Returns:
            768维numpy数组，表示事件的语义内容
        """
        try:
            self._stats["embedding_computations"] += 1

            # 将RawEvent转换为RawEventInput格式
            raw_event_input = self._convert_raw_event_to_input(raw_event, entities)

            # 使用EmbeddingEventMerger的统一接口
            embedding_merger = EmbeddingEventMerger()
            embedding = embedding_merger.get_embedding_for_raw_event(raw_event_input)

            logger.debug(f"Computed embedding for raw event {raw_event.id}")
            return embedding

        except Exception as e:
            logger.error(
                f"Failed to compute embedding for raw event {raw_event.id}: {e}",
                exc_info=True,
            )
            # 返回零向量作为后备方案
            return np.zeros(768)

    def _convert_raw_event_to_input(
        self, raw_event: RawEvent, entities: list = None
    ) -> RawEventInput:
        """
        将RawEvent对象转换为RawEventInput格式。

        Args:
            raw_event: 原始事件对象
            entities: 可选的实体信息列表

        Returns:
            RawEventInput: 转换后的输入对象
        """
        # 处理实体信息
        main_entities = []
        if entities:
            for entity in entities:
                if isinstance(entity, dict):
                    main_entities.append(entity)
                else:
                    # 如果是其他格式，尝试转换
                    main_entities.append(
                        {
                            "original_name": getattr(entity, "name", str(entity)),
                            "entity_type": getattr(entity, "type", ""),
                        }
                    )

        event_data = EventDataForMerger(
            id=str(raw_event.id),
            description=raw_event.original_description or "",
            event_date_str=raw_event.event_date_str or "",
            date_info=raw_event.date_info,
            main_entities=main_entities,
            source_text_snippet=raw_event.source_text_snippet,
        )

        source_info = SourceInfoForMerger(
            language=getattr(raw_event, "language", "en"),
            page_url=getattr(raw_event, "page_url", None),
            page_title=getattr(raw_event, "page_title", None),
        )

        return RawEventInput(
            event_data=event_data,
            source_info=source_info,
            original_id=str(raw_event.id),
        )

    async def _find_duplicate_event_by_embedding(
        self,
        db: AsyncSession,
        embedding: np.ndarray,
        similarity_threshold: float = 0.95,
    ) -> Event | None:
        """
        Search for existing Event with similar embedding using pgvector.

        Args:
            db: Database session
            embedding: Event embedding vector
            similarity_threshold: Minimum cosine similarity for considering duplicate

        Returns:
            Existing Event if duplicate found, None otherwise
        """
        self._stats["similarity_searches_performed"] += 1

        try:
            # Convert cosine similarity threshold to distance threshold
            # pgvector cosine distance = 1 - cosine similarity
            distance_threshold = 1 - similarity_threshold

            result = await db.execute(
                select(Event)
                .where(
                    Event.description_vector.cosine_distance(embedding.tolist())
                    < distance_threshold
                )
                .order_by(Event.description_vector.cosine_distance(embedding.tolist()))
                .limit(1)
            )

            duplicate_event = result.scalar_one_or_none()

            if duplicate_event:
                # Calculate actual similarity for logging
                actual_distance = await db.scalar(
                    select(
                        Event.description_vector.cosine_distance(embedding.tolist())
                    ).where(Event.id == duplicate_event.id)
                )
                actual_similarity = (
                    1 - actual_distance if actual_distance is not None else 0
                )

                logger.info(
                    f"Found duplicate event {duplicate_event.id} with similarity {actual_similarity:.3f}"
                )
                self._stats["duplicates_found"] += 1

            return duplicate_event

        except Exception as e:
            logger.error(f"Error during similarity search: {e}", exc_info=True)
            return None

    def _get_similarity_threshold(self, raw_event: RawEvent) -> float:
        """
        Determine appropriate similarity threshold based on context.

        Uses dynamic thresholds:
        - Higher threshold (0.95) for same-source deduplication
        - Standard threshold (0.85) for cross-source merging
        """
        base_threshold = 0.85

        # For now, use base threshold - can be enhanced with source clustering logic
        return base_threshold

    async def _create_new_event(
        self, db: AsyncSession, raw_event: RawEvent, embedding: np.ndarray
    ) -> Event:
        """
        Create a new Event record from RawEvent with computed embedding.
        Also creates the EventRawEventAssociation link in the same transaction.
        """
        # Parse date info if available
        if raw_event.date_info and isinstance(raw_event.date_info, dict):
            try:
                ParsedDateInfo(**raw_event.date_info)
            except Exception as e:
                logger.warning(
                    f"Failed to parse date_info for raw event {raw_event.id}: {e}",
                    exc_info=True,
                )

        # Create new Event
        new_event = Event(
            event_date_str=raw_event.event_date_str,
            description=raw_event.original_description,
            date_info=raw_event.date_info,
            description_vector=embedding.tolist(),  # Store as list for pgvector
        )

        db.add(new_event)
        await db.flush()  # Flush to get the Event ID

        # FIXED: Create the EventRawEventAssociation for the new event in the same transaction
        from app.models import EventRawEventAssociation

        association = EventRawEventAssociation(
            event_id=new_event.id, raw_event_id=raw_event.id
        )
        db.add(association)

        # Commit both the Event and the association in a single transaction
        await db.commit()
        await db.refresh(new_event)

        self._stats["new_events_created"] += 1
        logger.info(
            f"Created new Event {new_event.id} from RawEvent {raw_event.id} with association"
        )

        return new_event

    async def _associate_raw_event_to_existing(
        self, db: AsyncSession, raw_event: RawEvent, existing_event: Event
    ) -> Event:
        """
        Associate RawEvent with existing Event record.

        Creates EventRawEventAssociation link and updates any necessary metadata.
        """
        from app.models import EventRawEventAssociation

        # Create association
        association = EventRawEventAssociation(
            event_id=existing_event.id, raw_event_id=raw_event.id
        )

        db.add(association)
        await db.commit()

        logger.info(
            f"Associated RawEvent {raw_event.id} with existing Event {existing_event.id}"
        )

        return existing_event

    async def create_or_merge_event(
        self, db: AsyncSession, raw_event: RawEvent, entities: list = None
    ) -> Event:
        """
        Core method: Create new Event or find existing duplicate for RawEvent.

        This is the main entry point for semantic deduplication at the Event level.

        Args:
            db: Database session
            raw_event: RawEvent to process
            entities: Optional list of entity information for this event

        Returns:
            Event record (either newly created or existing duplicate)
        """
        start_time = time.time()
        self._stats["total_raw_events_processed"] += 1

        logger.debug(
            f"Processing RawEvent {raw_event.id}: '{raw_event.original_description[:100]}...'"
        )

        # 1. Compute embedding for the raw event
        embedding = await self._compute_embedding(raw_event, entities)

        # 2. Search for potential duplicates
        similarity_threshold = self._get_similarity_threshold(raw_event)
        potential_duplicate = await self._find_duplicate_event_by_embedding(
            db, embedding, similarity_threshold
        )

        # 3. Either associate with existing or create new
        if potential_duplicate:
            result_event = await self._associate_raw_event_to_existing(
                db, raw_event, potential_duplicate
            )
        else:
            result_event = await self._create_new_event(db, raw_event, embedding)

        duration = time.time() - start_time
        logger.debug(f"Processed RawEvent {raw_event.id} in {duration:.3f}s")

        return result_event

    async def batch_process_raw_events(
        self, db: AsyncSession, raw_events: list[RawEvent]
    ) -> list[Event]:
        """
        Process multiple RawEvents efficiently with batch optimizations.

        Args:
            db: Database session
            raw_events: List of RawEvents to process

        Returns:
            List of Event records (deduplicated)
        """
        if not raw_events:
            return []

        start_time = time.time()
        logger.info(f"Starting batch processing of {len(raw_events)} raw events")

        processed_events = []

        for raw_event in raw_events:
            try:
                # Note: batch processing doesn't have entity information available
                event = await self.create_or_merge_event(db, raw_event)
                processed_events.append(event)
            except Exception as e:
                logger.error(
                    f"Error processing RawEvent {raw_event.id}: {e}", exc_info=True
                )
                continue

        duration = time.time() - start_time
        logger.info(
            f"Batch processing completed in {duration:.2f}s. "
            f"Processed {len(raw_events)} raw events -> {len({e.id for e in processed_events})} unique events. "
            f"Stats: {self._stats}"
        )

        return processed_events

    def get_stats(self) -> dict:
        """Return processing statistics for monitoring and optimization."""
        return self._stats.copy()

    def reset_stats(self):
        """Reset processing statistics."""
        for key in self._stats:
            self._stats[key] = 0
