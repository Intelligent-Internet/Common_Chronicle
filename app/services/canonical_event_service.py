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
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_handlers.entity import EntityDBHandler
from app.db_handlers.event import EventDBHandler
from app.db_handlers.event_entity_association import EventEntityAssociationDBHandler
from app.db_handlers.event_rawevent_association import EventRawEventAssociationDBHandler
from app.models import Entity, Event, EventRawEventAssociation, RawEvent
from app.schemas import EventDataForMerger, SourceInfoForMerger
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

    def __init__(self, embedding_merger: EmbeddingEventMerger):
        """
        Initializes the service with its dependencies.
        Args:
            embedding_merger: An instance of EmbeddingEventMerger for computing embeddings.
        """
        self._embedding_merger = embedding_merger
        self.event_handler = EventDBHandler()
        self.entity_handler = EntityDBHandler()
        self.event_raw_event_assoc_handler = EventRawEventAssociationDBHandler()
        self.event_entity_assoc_handler = EventEntityAssociationDBHandler()
        logger.info("Initialized CanonicalEventService with injected embedding service")

    def _create_event_text_representation(
        self, raw_event: RawEvent, entities: list[Entity]
    ) -> str:
        """
        Create comprehensive text representation for embedding computation.
        Combines description, date, and entity information from persisted objects.
        """
        parts = []

        if raw_event.original_description:
            parts.append(raw_event.original_description)

        if raw_event.event_date_str:
            parts.append(f"Date: {raw_event.event_date_str}")

        if entities:
            entity_parts = [
                f"{entity.entity_name} ({entity.entity_type})" for entity in entities
            ]
            parts.append(f"Entities: {', '.join(entity_parts)}")

        if raw_event.source_text_snippet:
            snippet = raw_event.source_text_snippet[:200]
            parts.append(f"Context: {snippet}")

        return " | ".join(parts)

    async def _compute_embedding(
        self, raw_event: RawEvent, entities: list[Entity]
    ) -> np.ndarray:
        """
        Use the injected embedding service to compute the embedding vector for the raw event.
        """
        try:
            raw_event_input = self._convert_raw_event_to_input(raw_event, entities)
            embedding = self._embedding_merger.get_embedding_for_raw_event(
                raw_event_input
            )
            logger.debug(f"Computed embedding for raw event {raw_event.id}")
            return embedding
        except Exception as e:
            logger.error(
                f"Failed to compute embedding for raw event {raw_event.id}: {e}",
                exc_info=True,
            )
            return np.zeros(768)

    def _convert_raw_event_to_input(
        self, raw_event: RawEvent, entities: list[Entity]
    ) -> RawEventInput:
        """
        Convert a RawEvent object and its associated Entity objects to RawEventInput format.
        """
        main_entities = [
            {"original_name": entity.entity_name, "entity_type": entity.entity_type}
            for entity in entities
            if entity is not None  # Safety check to filter out None entities
        ]

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

    async def _get_dynamic_similarity_threshold(
        self, db: AsyncSession, current_raw_event: RawEvent, target_event: Event
    ) -> float:
        """
        Determine appropriate similarity threshold based on source context.
        - Higher threshold (0.95) for same-source deduplication.
        - Standard threshold (0.85) for cross-source merging.
        """
        try:
            current_source_doc_id = current_raw_event.source_document_id

            # Use handler to get all source document IDs for the target event
            target_source_doc_ids = (
                await self.event_handler.get_source_document_ids_for_event(
                    target_event.id, db=db
                )
            )

            if current_source_doc_id in target_source_doc_ids:
                logger.debug("Same source document detected, using high threshold 0.95")
                return 0.95
            else:
                logger.debug("Cross-source comparison, using standard threshold 0.85")
                return 0.85

        except Exception as e:
            logger.error(f"Error determining dynamic threshold: {e}", exc_info=True)
            return 0.85  # Fallback to standard threshold

    async def _create_new_event(
        self, db: AsyncSession, raw_event: RawEvent, embedding: np.ndarray
    ) -> Event:
        """
        Prepare a new Event record for creation.
        Does NOT commit the transaction.
        """
        new_event = Event(
            event_date_str=raw_event.event_date_str,
            description=raw_event.original_description,
            date_info=raw_event.date_info,
            description_vector=embedding.tolist(),
        )
        db.add(new_event)
        await db.flush()  # Flush to get the Event ID for association
        logger.info(f"Prepared new Event {new_event.id} from RawEvent {raw_event.id}")
        return new_event

    async def _associate_raw_event_to_event(
        self, db: AsyncSession, raw_event: RawEvent, event: Event
    ):
        """
        Prepare the association between a RawEvent and an Event.
        Does NOT commit the transaction.
        """
        # Check if association already exists to prevent duplicates
        association_exists = (
            await self.event_raw_event_assoc_handler.check_association_exists(
                event.id, raw_event.id, db=db
            )
        )
        if not association_exists:
            association = EventRawEventAssociation(
                event_id=event.id, raw_event_id=raw_event.id
            )
            db.add(association)
            logger.info(
                f"Prepared association: RawEvent {raw_event.id} -> Event {event.id}"
            )
        else:
            logger.debug(
                f"Association already exists: RawEvent {raw_event.id} -> Event {event.id}"
            )

    async def process_raw_event(self, db: AsyncSession, raw_event: RawEvent) -> Event:
        """
        Process a single RawEvent into a canonical Event record.
        This method is the core of the service and is transaction-agnostic.
        It adds objects to the session but does not commit.
        """
        start_time = time.time()
        logger.debug(
            f"Processing RawEvent {raw_event.id}: '{raw_event.original_description[:100]}...'"
        )

        # 1. Load entity associations using handler
        actual_entities = await self.entity_handler.get_entities_for_raw_event(
            raw_event.id, db=db
        )

        logger.debug(
            f"Loaded {len(actual_entities)} valid entities for RawEvent {raw_event.id}"
        )

        # 2. Compute embedding using the persisted entities
        embedding = await self._compute_embedding(raw_event, actual_entities)

        # 3. Find potential duplicates using a dynamic threshold
        potential_duplicate = await self._find_duplicate_with_dynamic_threshold(
            db, raw_event, embedding
        )

        # 4. Either associate with existing or create a new event
        if potential_duplicate:
            result_event = potential_duplicate
            logger.info(
                f"Found duplicate for RawEvent {raw_event.id}. Associating with existing Event {result_event.id}."
            )
        else:
            result_event = await self._create_new_event(db, raw_event, embedding)
            logger.info(
                f"No duplicate found for RawEvent {raw_event.id}. Created new Event {result_event.id}."
            )

        # 5. Associate the raw event with the chosen (new or existing) canonical event
        await self._associate_raw_event_to_event(db, raw_event, result_event)

        # 6. Associate the entities from the raw event with the canonical event
        if actual_entities:
            entity_associations_data = [
                {"event_id": result_event.id, "entity_id": entity.id}
                for entity in actual_entities
                if entity is not None and entity.id is not None  # Safety check
            ]

            await self.event_entity_assoc_handler.bulk_create_associations(
                entity_associations_data, db=db
            )

            logger.debug(
                f"Batch inserted {len(entity_associations_data)} entity associations for Event {result_event.id} with conflict resolution"
            )

        duration = time.time() - start_time
        logger.debug(
            f"Processed RawEvent {raw_event.id} in {duration:.3f}s. Session updated."
        )

        return result_event

    async def _find_duplicate_with_dynamic_threshold(
        self,
        db: AsyncSession,
        raw_event: RawEvent,
        embedding: np.ndarray,
    ) -> Event | None:
        """
        Two-stage duplicate detection using dynamic thresholds.
        """
        try:
            # Stage 1: Find candidate events using a conservative threshold
            conservative_threshold = 0.80
            embedding_list = embedding.tolist()

            candidates = await self.event_handler.find_similar_events_by_vector(
                embedding_list, limit=5, threshold=conservative_threshold, db=db
            )

            if not candidates:
                return None

            # Stage 2: Apply dynamic threshold to each candidate
            for candidate_event in candidates:
                actual_distance = await self.event_handler.calculate_vector_distance(
                    candidate_event.id, embedding_list, db=db
                )
                actual_similarity = 1 - (actual_distance or 1)

                dynamic_threshold = await self._get_dynamic_similarity_threshold(
                    db, raw_event, candidate_event
                )

                if actual_similarity >= dynamic_threshold:
                    logger.info(
                        f"Found duplicate Event {candidate_event.id} with similarity {actual_similarity:.3f} "
                        f"(threshold: {dynamic_threshold:.3f})"
                    )
                    return candidate_event

            return None

        except Exception as e:
            logger.error(
                f"Error during dynamic duplicate detection: {e}", exc_info=True
            )
            return None
