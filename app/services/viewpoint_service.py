"""
Viewpoint service for managing timeline perspectives and event associations.

This module provides comprehensive viewpoint management capabilities including
creation, event linking, entity processing, and database transaction handling.
Viewpoints represent coherent timeline perspectives that organize related events
around specific topics or themes.
"""

import hashlib
import time
import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.event import Event
from app.models.source_document import SourceDocument
from app.schemas import ProcessedEntityInfo, ProcessedEvent, SourceArticle
from app.services.entity_service import AsyncEntityService
from app.services.llm_extractor import extract_timeline_events_from_text
from app.utils.logger import setup_logger

logger = setup_logger("viewpoint_service", level="DEBUG")


class ViewpointService:
    """Service for managing viewpoints and their associated events."""

    def __init__(self):
        self.viewpoint_db_handler = ViewpointDBHandler()
        self.event_db_handler = EventDBHandler()
        self.event_entity_assoc_handler = BaseDBHandler(EventEntityAssociation)
        self.event_source_contrib_handler = BaseDBHandler(RawEvent)
        self.event_source_assoc_handler = BaseDBHandler(EventRawEventAssociation)
        self.viewpoint_event_assoc_handler = BaseDBHandler(ViewpointEventAssociation)
        self.entity_db_handler = EntityDBHandler()
        self.entity_service = AsyncEntityService()

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

        # 3. Prepare all RawEvent and Event objects to be created in memory
        staged_data = []
        for event_data in deduplicated_events:
            # a. Calculate deduplication signature (recalculate to ensure consistency)
            deduplication_signature = hashlib.sha256(
                f"{source_document.id}-{event_data['description']}-{event_data['event_date_str']}".encode()
            ).hexdigest()

            # b. Check if same RawEvent already exists (database level check)
            existing_raw_event = (
                await self.event_source_contrib_handler.get_by_attributes(
                    source_document_id=source_document.id,
                    deduplication_signature=deduplication_signature,
                    db=db,
                )
            )

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

            # c. Prepare corresponding "base" Event
            event_obj = Event(
                description=event_data["description"],
                event_date_str=event_data["event_date_str"],
                date_info=event_data.get("date_info"),
            )

            staged_data.append(
                {
                    "raw_event_obj": raw_event_obj,
                    "event_obj": event_obj,
                    "linked_entities": event_data.get("linked_entities", []),
                    "is_existing_raw_event": existing_raw_event is not None,
                }
            )

        # 4. Add only new RawEvents and all Events to session
        new_raw_events = [
            item["raw_event_obj"]
            for item in staged_data
            if not item["is_existing_raw_event"]
        ]
        all_events = [item["event_obj"] for item in staged_data]

        if new_raw_events:
            db.add_all(new_raw_events)
            logger.debug(
                f"{log_prefix}Adding {len(new_raw_events)} new RawEvent objects to session"
            )

        db.add_all(all_events)
        logger.debug(f"{log_prefix}Adding {len(all_events)} Event objects to session")

        # 5. Flush to get IDs of all new objects (but transaction not yet committed)
        await db.flush()

        # After flushing, the event objects now have IDs.
        event_ids = [
            item["event_obj"].id
            for item in staged_data
            if item["event_obj"].id is not None
        ]

        # 6. Prepare all "association" objects in memory
        all_associations = []
        unique_event_entity_pairs = set()  # Track unique (event_id, entity_id) pairs

        for item in staged_data:
            raw_event = item["raw_event_obj"]
            event = item["event_obj"]

            # a. Viewpoint <-> Event
            all_associations.append(
                ViewpointEventAssociation(
                    viewpoint_id=new_viewpoint.id, event_id=event.id
                )
            )
            # b. Event <-> RawEvent
            all_associations.append(
                EventRawEventAssociation(event_id=event.id, raw_event_id=raw_event.id)
            )
            # c. Event <-> Entity
            for entity_dict in item["linked_entities"]:
                entity_id = entity_dict.get("entity_id")
                if entity_id:
                    pair = (event.id, entity_id)
                    if pair not in unique_event_entity_pairs:
                        all_associations.append(
                            EventEntityAssociation(
                                event_id=event.id, entity_id=entity_id
                            )
                        )
                        unique_event_entity_pairs.add(pair)
                    else:
                        logger.debug(
                            f"{log_prefix}Skipping duplicate entity association: event_id={event.id}, entity_id={entity_id}"
                        )

        # 7. Batch add all association objects to session
        db.add_all(all_associations)

        # 8. Update Viewpoint status to "completed" and add to commit
        new_viewpoint.status = "completed"
        db.add(new_viewpoint)

        logger.info(f"{log_prefix}All objects and associations staged for commit.")

        # Return created Viewpoint object and list of new Event IDs
        return new_viewpoint, event_ids

    @check_local_db
    async def get_or_create_canonical_viewpoint(
        self,
        article: SourceArticle,
        data_source_preference: str,
        request_id: str | None = None,
        progress_callback: Optional["ProgressCallback"] = None,
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
        if (
            settings.REUSE_BASE_VIEWPOINT
            and source_document.processing_status == "completed"
        ):
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

        # 3. Extract raw events from LLM
        processed_events = await extract_timeline_events_from_text(article.text_content)
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
