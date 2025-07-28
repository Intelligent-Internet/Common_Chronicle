"""
Viewpoint service for managing timeline perspectives and event associations.

This module provides comprehensive viewpoint management capabilities including
creation, event linking, entity processing, and database transaction handling.
Viewpoints represent coherent timeline perspectives that organize related events
around specific topics or themes.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings

# to avoid circular import
if TYPE_CHECKING:
    from app.services.process_callback import ProgressCallback

from app.db_handlers import (
    BaseDBHandler,
    EntityDBHandler,
    EventDBHandler,
    SourceDocumentDBHandler,
    ViewpointDBHandler,
    check_local_db,
)
from app.models import (
    EventEntityAssociation,
    EventRawEventAssociation,
    RawEvent,
    Viewpoint,
    ViewpointEventAssociation,
)
from app.models.raw_event_entity_association import RawEventEntityAssociation
from app.models.source_document import SourceDocument
from app.schemas import ProcessedEntityInfo, ProcessedEvent, SourceArticle
from app.services.canonical_event_service import CanonicalEventService
from app.services.embedding_event_merger import EmbeddingEventMerger
from app.services.entity_service import AsyncEntityService
from app.services.llm_extractor import (
    extract_events_from_chunks,
    extract_timeline_events_from_text,
)
from app.utils.logger import setup_logger
from app.utils.text_processing import split_text_into_chunks

logger = setup_logger("viewpoint_service", level="DEBUG")


class ViewpointService:
    """Service for managing viewpoints and their associated events."""

    def __init__(self):
        self.viewpoint_db_handler = ViewpointDBHandler()
        self.event_db_handler = EventDBHandler()
        self.raw_event_db_handler = BaseDBHandler(RawEvent)
        self.event_entity_assoc_handler = BaseDBHandler(EventEntityAssociation)
        self.raw_event_entity_assoc_handler = BaseDBHandler(RawEventEntityAssociation)
        self.event_source_assoc_handler = BaseDBHandler(EventRawEventAssociation)
        self.viewpoint_event_assoc_handler = BaseDBHandler(ViewpointEventAssociation)
        self.entity_db_handler = EntityDBHandler()
        self.entity_service = AsyncEntityService()
        # --- Service Instantiation with Dependency Injection ---
        embedding_merger = EmbeddingEventMerger()
        self.canonical_event_service = CanonicalEventService(
            embedding_merger=embedding_merger
        )

    async def _atomic_create_viewpoint_data(
        self,
        db: AsyncSession,
        source_document: SourceDocument,
        raw_events_data_with_entities: list[dict],
        data_source_preference: str,
        log_prefix: str = "",
    ) -> tuple[Viewpoint, list[uuid.UUID]]:
        """
        Atomically creates a viewpoint, its raw events, its base events,
        and all associated links in a single database transaction.
        """
        # 1. Create Viewpoint and mark its status as "populating"
        # We add a status field to the Viewpoint model
        new_viewpoint = await self.viewpoint_db_handler.create(
            {
                "topic": source_document.title,
                "viewpoint_type": "canonical",
                "canonical_source_id": source_document.id,
                "data_source_preference": data_source_preference,
                "status": "populating",  # Key point: initial status
            },
            db=db,
        )

        # 2. First perform deduplication at application level to avoid database constraint conflicts
        logger.info(
            f"{log_prefix}Starting deduplication of {len(raw_events_data_with_entities)} raw events from LLM"
        )

        # Use dictionary to track seen deduplication signatures, ensuring each signature is processed only once
        seen_signatures = {}
        deduplicated_events = []

        for i, event_data in enumerate(raw_events_data_with_entities):
            # Calculate deduplication signature
            deduplication_signature = hashlib.sha256(
                f"{source_document.id}-{event_data['description']}-{event_data['event_date_str']}".encode()
            ).hexdigest()

            # Check if same signature has already been processed
            if deduplication_signature in seen_signatures:
                logger.debug(
                    f"{log_prefix}Skipping duplicate event (signature: {deduplication_signature[:16]}...): "
                    f"'{event_data['description'][:100]}...'"
                )
                continue

            # Record this signature and add to deduplicated list
            seen_signatures[deduplication_signature] = i
            deduplicated_events.append(event_data)
            logger.debug(
                f"{log_prefix}Keeping event {i+1} (signature: {deduplication_signature[:16]}...): "
                f"'{event_data['description'][:100]}...'"
            )

        logger.info(
            f"{log_prefix}Deduplication complete: kept {len(deduplicated_events)} unique events "
            f"out of {len(raw_events_data_with_entities)} original events"
        )

        # 3. Iterate through deduplicated data and process raw events
        staged_data = []
        # In this first loop, we prepare all objects without committing.
        # This includes creating RawEvent objects and linking them to entities.
        for event_data in deduplicated_events:
            # a. Calculate deduplication signature (recalculate to ensure consistency)
            deduplication_signature = hashlib.sha256(
                f"{source_document.id}-{event_data['description']}-{event_data['event_date_str']}".encode()
            ).hexdigest()

            # b. Check if same RawEvent already exists (database level check)
            query = select(RawEvent).options(
                selectinload(RawEvent.entity_associations).selectinload(
                    RawEventEntityAssociation.entity
                )
            )
            existing_raw_event = await self.raw_event_db_handler.get_by_attributes(
                db=db,
                query=query,
                source_document_id=source_document.id,
                deduplication_signature=deduplication_signature,
            )

            raw_event_obj = None
            is_new_raw_event = False

            if existing_raw_event:
                # Use existing RawEvent
                raw_event_obj = existing_raw_event
                logger.debug(
                    f"{log_prefix}Reusing existing RawEvent {existing_raw_event.id} for deduplication_signature {deduplication_signature}"
                )
            else:
                # Create new RawEvent
                raw_event_obj = RawEvent(
                    original_description=event_data["description"],
                    event_date_str=event_data["event_date_str"],
                    date_info=event_data.get("date_info"),
                    deduplication_signature=deduplication_signature,
                    source_document_id=source_document.id,
                    source_text_snippet=event_data.get("source_text_snippet"),
                )
                db.add(raw_event_obj)
                is_new_raw_event = True

            # 4. For new raw events, we'll create entity associations after getting the RawEvent ID
            staged_data.append(
                {
                    "raw_event_obj": raw_event_obj,
                    "linked_entities": event_data.get("linked_entities", [])
                    if is_new_raw_event
                    else [],
                    "is_new_raw_event": is_new_raw_event,
                }
            )

        # Flush session to ensure all new RawEvents get IDs first
        await db.flush()
        logger.debug(
            f"{log_prefix}Flushed session to persist {len(staged_data)} raw events."
        )

        # Now create entity associations for new raw events
        for item in staged_data:
            raw_event_obj = item["raw_event_obj"]
            linked_entities = item["linked_entities"]
            is_new_raw_event = item["is_new_raw_event"]

            if is_new_raw_event and linked_entities:
                # Extract entity IDs from linked_entities
                entity_ids = [
                    entity_dict["entity_id"] for entity_dict in linked_entities
                ]

                # Verify entities exist and create associations only for valid entities
                for entity_id in entity_ids:
                    # Check if entity actually exists in database
                    entity = await self.entity_db_handler.get(entity_id, db=db)
                    if entity is not None:
                        association = RawEventEntityAssociation(
                            raw_event_id=raw_event_obj.id, entity_id=entity_id
                        )
                        db.add(association)
                    else:
                        logger.warning(
                            f"{log_prefix}Entity {entity_id} not found in database, skipping association for RawEvent {raw_event_obj.id}"
                        )

        # Final flush to persist all associations
        await db.flush()
        logger.debug(f"{log_prefix}Flushed session to persist entity associations.")

        # Extract just the raw_event objects for processing
        staged_data = [item["raw_event_obj"] for item in staged_data]

        # 5. Process all RawEvents to get or create canonical Events
        canonical_events = []
        for raw_event in staged_data:
            try:
                # The service now handles its own logic using persisted associations
                canonical_event = await self.canonical_event_service.process_raw_event(
                    db, raw_event
                )
                canonical_events.append(canonical_event)
                logger.debug(
                    f"{log_prefix}Processed RawEvent {raw_event.id} -> Event {canonical_event.id}"
                )
            except Exception as e:
                logger.error(
                    f"{log_prefix}Error processing RawEvent {raw_event.id}: {e}",
                    exc_info=True,
                )
                continue

        logger.info(
            f"{log_prefix}Processing completed: {len(staged_data)} raw events -> {len(canonical_events)} canonical events"
        )

        # Get unique event IDs, as semantic deduplication might reuse events
        event_ids = list({event.id for event in canonical_events})

        # 6. Associate unique Events with the Viewpoint
        if event_ids:
            # Create associations for all unique event IDs at once
            viewpoint_event_associations_to_create = []
            unique_viewpoint_event_pairs = set()

            for event_id in event_ids:
                vp_event_pair = (new_viewpoint.id, event_id)
                if vp_event_pair not in unique_viewpoint_event_pairs:
                    viewpoint_event_associations_to_create.append(
                        {"viewpoint_id": new_viewpoint.id, "event_id": event_id}
                    )
                    unique_viewpoint_event_pairs.add(vp_event_pair)

            if viewpoint_event_associations_to_create:
                stmt = pg_insert(ViewpointEventAssociation).values(
                    viewpoint_event_associations_to_create
                )
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["viewpoint_id", "event_id"]
                )
                await db.execute(stmt)
                logger.debug(
                    f"{log_prefix}Bulk inserted {len(viewpoint_event_associations_to_create)} viewpoint-event associations with ON CONFLICT"
                )

        # 7. Update Viewpoint status to "completed" and add to commit
        new_viewpoint.status = "completed"
        db.add(new_viewpoint)

        logger.info(
            f"{log_prefix}All objects and associations staged for commit. "
            f"Viewpoint {new_viewpoint.id} with {len(event_ids)} unique canonical events."
        )

        # Return created Viewpoint object and list of canonical Event IDs
        return new_viewpoint, event_ids

    @check_local_db
    async def get_or_create_canonical_viewpoint(
        self,
        article: SourceArticle,
        data_source_preference: str,
        request_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
        task_config=None,  # ArticleAcquisitionConfig | None = None, but avoid circular import
        db: AsyncSession = None,
    ) -> list[str]:
        log_prefix = f"[RequestID: {request_id}] " if request_id else ""
        logger.info(
            f"{log_prefix}Starting to get or create canonical viewpoint for {article.title}"
        )

        # ===== Preparation Phase =====
        # 1. Get or create source document
        source_document_handler = SourceDocumentDBHandler()
        source_document = await source_document_handler.get_or_create(
            article_data=article.model_dump(), log_prefix=log_prefix, db=db
        )

        # 2. Check if already processed (and if reuse is enabled)
        # Use task-level reuse setting if available, otherwise fall back to global setting
        should_reuse = (
            task_config.reuse_base_viewpoint
            if task_config and hasattr(task_config, "reuse_base_viewpoint")
            else settings.reuse_base_viewpoint
        )

        if should_reuse and source_document.processing_status == "completed":
            event_ids = await self.viewpoint_db_handler.get_viewpoint_related_event_ids(
                canonical_source_id=source_document.id,
                db=db,
                viewpoint_type="canonical",
            )
            if event_ids:
                logger.info(
                    f"{log_prefix}Found existing completed viewpoint for {article.title}."
                )

                # Report progress for cached article
                if progress_callback:
                    await progress_callback.report(
                        f"Article '{article.title}' already processed, using cached {len(event_ids)} events",
                        "article_processing_cached",
                        {
                            "article_title": article.title,
                            "event_count": len(event_ids),
                            "is_cached": True,
                        },
                        request_id,
                    )

                return event_ids

        # 3. Extract raw events from LLM with intelligent chunking
        text_content = article.text_content
        text_length = len(text_content) if text_content else 0

        # Determine if we need to use chunking strategy
        chunk_size_threshold = settings.text_chunk_size_threshold
        if text_length > chunk_size_threshold:
            logger.info(
                f"{log_prefix}Article text is long ({text_length} chars), using chunking strategy"
            )

            # Optimized chunking parameters for better event extraction
            # Smaller chunks with more overlap to prevent event splitting
            chunk_size = settings.text_chunk_size
            overlap = settings.text_chunk_overlap

            # Split text into chunks
            chunks = split_text_into_chunks(
                text_content, chunk_size=chunk_size, overlap=overlap
            )
            logger.info(
                f"{log_prefix}Split article into {len(chunks)} chunks (chunk_size={chunk_size}, overlap={overlap})"
            )

            # Extract events from chunks in parallel
            processed_events = await extract_events_from_chunks(
                chunks, parent_request_id=request_id
            )
            logger.info(
                f"{log_prefix}Extracted {len(processed_events)} events from {len(chunks)} chunks"
            )
        else:
            logger.info(
                f"{log_prefix}Article text is short ({text_length} chars), using single extraction"
            )
            # Use original single-pass extraction for shorter texts
            processed_events = await extract_timeline_events_from_text(text_content)

        if not processed_events:
            logger.warning(f"{log_prefix}No events extracted from {article.title}.")
            return []

        # 4. Link entities (depends on preprocessing)
        # Note: _link_entities_in_events internally needs to call EntityService
        raw_events_data_with_entities = await self._link_entities_in_events(
            processed_events, article.source_name, log_prefix, db=db
        )

        # ===== Execution Phase =====
        try:
            # 5. Use atomic method to complete all database writes in current transaction
            # Note: No need to start transaction again, as @check_local_db decorator already manages transaction
            new_viewpoint, event_ids = await self._atomic_create_viewpoint_data(
                db,
                source_document,
                raw_events_data_with_entities,
                data_source_preference,
                log_prefix,
            )

            # 6. Update source document status on success
            source_document.processing_status = "completed"
            await db.flush()  # Use flush instead of commit, as transaction is managed by decorator

            # 7. Directly use event_ids returned from _atomic_create_viewpoint_data
            logger.info(
                f"{log_prefix}Successfully created canonical viewpoint {new_viewpoint.id}"
            )

            # Report progress for successful processing
            if progress_callback:
                await progress_callback.report(
                    f"Article '{article.title}' successfully processed, extracted {len(event_ids)} events",
                    "article_processing_completed",
                    {
                        "article_title": article.title,
                        "viewpoint_id": str(new_viewpoint.id),
                        "event_count": len(event_ids),
                        "is_cached": False,
                    },
                    request_id,
                )

            return event_ids

        except Exception as e:
            # If atomic creation fails, mark source document as failed
            logger.error(
                f"{log_prefix}Error during atomic creation for {article.title}: {e}",
                exc_info=True,
            )
            source_document.processing_status = "failed"
            await db.flush()  # Use flush instead of commit
            raise

    async def _link_entities_in_events(
        self,
        processed_events: list[ProcessedEvent],
        source_type: str,
        log_prefix: str,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Links entities for a list of processed events."""
        logger.info(
            f"{log_prefix}Starting entity linking for {len(processed_events)} events"
        )

        entity_processing_start = time.time()

        # Step 1: Collect all unique entities from all events for batch processing
        all_entity_requests = []
        entity_request_map = {}  # Maps (name, type) to request index

        for _, event in enumerate(processed_events):
            if not event.main_entities:
                continue
            for entity_info in event.main_entities:
                entity_ref = (entity_info.name, entity_info.type)
                if entity_ref not in entity_request_map:
                    request_idx = len(all_entity_requests)
                    entity_request_map[entity_ref] = request_idx
                    all_entity_requests.append(
                        # name, entity_type, language
                        (entity_info.name, entity_info.type, entity_info.language)
                    )

        if not all_entity_requests:
            logger.info(
                f"{log_prefix}No entities found in events, skipping entity processing"
            )
            # Return events as-is, but convert to dict format
            final_events = []
            for event in processed_events:
                event_dict = event.model_dump(exclude_none=True)
                event_dict["linked_entities"] = []  # No entities to link
                final_events.append(event_dict)
            return final_events

        # Step 2: Call the entity service to batch get or create entities
        logger.info(
            f"{log_prefix}Processing {len(all_entity_requests)} unique entities"
        )
        entity_responses = await self.entity_service.batch_get_or_create_entities(
            all_entity_requests, source_type, db=db
        )

        entity_processing_end = time.time()
        logger.info(
            f"{log_prefix}Batch entity processing completed in {entity_processing_end - entity_processing_start:.2f}s for {len(all_entity_requests)} entities"
        )

        # Step 3: Reconstruct events with processed entities
        final_events = []
        for event in processed_events:
            processed_main_entities: list[ProcessedEntityInfo] = []
            linked_entities = []  # For database storage
            seen_entity_ids = set()  # Track entity IDs already added for this event

            if event.main_entities:
                for entity_info in event.main_entities:
                    entity_ref = (entity_info.name, entity_info.type)
                    request_index = entity_request_map.get(entity_ref)

                    if request_index is not None and request_index < len(
                        entity_responses
                    ):
                        entity_response = entity_responses[request_index]
                        processed_entity = ProcessedEntityInfo(
                            entity_id=entity_response.entity_id,
                            original_name=entity_info.name,
                            entity_type=entity_info.type,
                            status_code=entity_response.status_code,
                            message=entity_response.message,
                            disambiguation_options=entity_response.disambiguation_options,
                            is_verified_existent=entity_response.is_verified_existent,
                        )
                        processed_main_entities.append(processed_entity)

                        # If entity was successfully created/found, add to linked_entities
                        if (
                            entity_response.entity_id
                            and entity_response.entity_id not in seen_entity_ids
                        ):
                            linked_entities.append(
                                {
                                    "entity_id": entity_response.entity_id,
                                    "original_name": entity_info.name,
                                    "entity_type": entity_info.type,
                                }
                            )
                            seen_entity_ids.add(entity_response.entity_id)
                    else:
                        logger.error(
                            f"{log_prefix}Missing entity response for entity '{entity_info.name}'"
                        )
                        processed_main_entities.append(
                            ProcessedEntityInfo(
                                entity_id=None,
                                original_name=entity_info.name,
                                entity_type=entity_info.type,
                                status_code=500,
                                message="Entity processing failed - missing response",
                                disambiguation_options=None,
                                is_verified_existent=None,
                            )
                        )

            # Convert event to dict and add processed entities
            event_dict = event.model_dump(exclude_none=True)
            event_dict["main_entities"] = [
                entity.model_dump(exclude_none=True)
                for entity in processed_main_entities
            ]
            event_dict["linked_entities"] = linked_entities
            final_events.append(event_dict)

        total_processing_duration = time.time() - entity_processing_start
        logger.info(
            f"{log_prefix}Total entity processing completed in {total_processing_duration:.2f}s for {len(processed_events)} events"
        )

        return final_events

    async def mark_viewpoint_failed(
        self, viewpoint_id: uuid.UUID, db: AsyncSession
    ) -> None:
        """Mark a viewpoint as failed."""
        viewpoint = await self.viewpoint_db_handler.get(viewpoint_id, db=db)
        if viewpoint:
            viewpoint.status = "failed"
            await db.flush()

    @check_local_db
    async def mark_viewpoint_failed_with_transaction(
        self, viewpoint_id: uuid.UUID, *, db: AsyncSession = None
    ) -> None:
        """Mark a viewpoint as failed in its own transaction."""
        await self.mark_viewpoint_failed(viewpoint_id, db)

    async def mark_viewpoint_completed(
        self, viewpoint_id: uuid.UUID, db: AsyncSession
    ) -> None:
        """Mark a viewpoint as completed."""
        viewpoint = await self.viewpoint_db_handler.get(viewpoint_id, db=db)
        if viewpoint:
            viewpoint.status = "completed"
            await db.flush()

    @check_local_db
    async def mark_viewpoint_completed_with_transaction(
        self, viewpoint_id: uuid.UUID, *, db: AsyncSession = None
    ) -> None:
        """Mark a viewpoint as completed in its own transaction."""
        await self.mark_viewpoint_completed(viewpoint_id, db)
