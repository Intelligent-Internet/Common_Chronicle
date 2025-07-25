from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db_handlers.base import BaseDBHandler, check_local_db
from app.models.event import Event
from app.models.event_entity_association import EventEntityAssociation
from app.models.event_raw_event_association import EventRawEventAssociation
from app.models.raw_event import RawEvent
from app.models.viewpoint import Viewpoint
from app.models.viewpoint_event_association import ViewpointEventAssociation
from app.schemas import EventSourceInfoForAPI, ProcessedEntityInfo, TimelineEventForAPI
from app.utils.logger import setup_logger

logger = setup_logger("viewpoint_db_handler")


class ViewpointDBHandler(BaseDBHandler[Viewpoint]):
    def __init__(self):
        super().__init__(Viewpoint)

    @check_local_db
    async def get_complete_viewpoint_details_by_id(
        self, viewpoint_id: uuid.UUID, *, db: AsyncSession = None
    ) -> dict[str, Any] | None:
        """Get viewpoint by ID with all related data eagerly loaded."""
        stmt = (
            select(Viewpoint)
            .options(
                selectinload(Viewpoint.event_associations)
                .selectinload(ViewpointEventAssociation.event)
                .selectinload(Event.raw_event_association_links)
                .selectinload(EventRawEventAssociation.raw_event)
                .selectinload(RawEvent.source_document),
                selectinload(Viewpoint.event_associations)
                .selectinload(ViewpointEventAssociation.event)
                .selectinload(Event.entity_associations)
                .selectinload(EventEntityAssociation.entity),
                selectinload(Viewpoint.progress_steps),
            )
            .where(Viewpoint.id == viewpoint_id)
        )
        result = await db.execute(stmt)
        viewpoint = result.unique().scalar_one_or_none()

        if not viewpoint:
            return None

        # Format timeline events with reference-based sources
        events_data = self._format_timeline_events(viewpoint)

        # Serialize progress steps
        progress_steps = [step.to_dict() for step in viewpoint.progress_steps]

        return {
            "viewpoint": viewpoint.to_dict(),
            "progress_steps": progress_steps,
            "sources": events_data["sources"],
            "timeline_events": events_data["timeline_events"],
        }

    def _format_timeline_events(self, viewpoint: Viewpoint) -> dict[str, Any]:
        """Format events from loaded Viewpoint into reference-based API structure."""
        sources_dict = {}
        final_event_api_objects = []

        logger.debug(
            f"[Format Timeline] Processing {len(viewpoint.event_associations)} event associations"
        )

        for association in viewpoint.event_associations:
            db_event = association.event
            if not db_event:
                continue

            logger.debug(f"[Format Timeline] Processing event {db_event.id}")
            logger.debug(
                f"[Format Timeline] Event {db_event.id} has {len(db_event.entity_associations)} entity associations"
            )

            # DEBUG: Add debug logging for raw_event_association_links
            logger.debug(
                f"[Format Timeline] Event {db_event.id} has {len(db_event.raw_event_association_links)} raw_event_association_links"
            )

            # Collect source snippets for this event (source_ref -> snippet mapping)
            source_snippets = {}
            for link in db_event.raw_event_association_links:
                contrib = link.raw_event
                if not contrib:
                    logger.debug(
                        f"[Format Timeline] Event {db_event.id} has link with no raw_event"
                    )
                    continue

                logger.debug(
                    f"[Format Timeline] Event {db_event.id} processing raw_event {contrib.id}, "
                    f"source_text_snippet length: {len(contrib.source_text_snippet) if contrib.source_text_snippet else 0}"
                )

                source_doc = contrib.source_document
                source_id = (
                    f"src_{source_doc.id}"
                    if source_doc
                    else f"src_unknown_{contrib.id}"
                )

                # Add to sources dictionary if not already present
                if source_id not in sources_dict:
                    sources_dict[source_id] = EventSourceInfoForAPI(
                        source_language=getattr(source_doc, "language", "unknown"),
                        source_page_title=getattr(source_doc, "title", None),
                        source_url=getattr(source_doc, "wikipedia_url", None),
                        source_document_id=str(source_doc.id) if source_doc else None,
                        source_type=getattr(source_doc, "source_type", None),
                    )

                # FIXED: Only add non-empty source snippets to avoid empty values in API response
                if contrib.source_text_snippet and contrib.source_text_snippet.strip():
                    source_snippets[source_id] = contrib.source_text_snippet
                    logger.debug(
                        f"[Format Timeline] Event {db_event.id} added source_snippet for {source_id}: "
                        f"'{contrib.source_text_snippet[:100]}...'"
                    )
                else:
                    logger.debug(
                        f"[Format Timeline] Event {db_event.id} skipping empty source_snippet for {source_id}"
                    )

            logger.debug(
                f"[Format Timeline] Event {db_event.id} final source_snippets count: {len(source_snippets)}"
            )

            # Format entities
            api_main_entities = []
            for entity_assoc in db_event.entity_associations:
                entity = entity_assoc.entity
                if not entity:
                    logger.debug(
                        f"[Format Timeline] Event {db_event.id} has entity association with no entity object"
                    )
                    continue

                logger.debug(
                    f"[Format Timeline] Event {db_event.id} processing entity {entity.id}: entity_name='{entity.entity_name}', entity_type='{entity.entity_type}'"
                )

                api_main_entities.append(
                    ProcessedEntityInfo(
                        entity_id=str(entity.id),
                        original_name=entity.entity_name,
                        entity_type=entity.entity_type,
                        is_verified_existent=entity.existence_verified,
                    )
                )

            logger.debug(
                f"[Format Timeline] Event {db_event.id} final api_main_entities count: {len(api_main_entities)}"
            )

            # Convert event date_info to proper format
            api_date_info = self._convert_date_info_to_parsed_format(
                db_event.date_info, db_event.event_date_str
            )

            final_event_api_objects.append(
                TimelineEventForAPI(
                    id=db_event.id,
                    event_date_str=db_event.event_date_str,
                    description=db_event.description,
                    main_entities=api_main_entities,
                    date_info=api_date_info,
                    is_merged=len(source_snippets) > 1,
                    source_snippets=source_snippets,
                    viewpoint_id=viewpoint.id,
                    relevance_score=association.relevance_score,
                )
            )

        logger.debug(
            f"[Format Timeline] Final result: {len(final_event_api_objects)} events formatted with {len(sources_dict)} unique sources"
        )

        return {
            "sources": sources_dict,
            "timeline_events": final_event_api_objects,
        }

    def _convert_date_info_to_parsed_format(
        self, date_info_dict: dict | None, fallback_date_str: str
    ) -> dict | None:
        """Convert database date_info to ParsedDateInfo-compatible format."""
        if not date_info_dict:
            return None

        # Check if it's already in the correct format
        required_fields = ["original_text", "display_text", "precision", "is_bce"]
        if all(field in date_info_dict for field in required_fields):
            return date_info_dict

        # Convert old format to new format
        date_str = date_info_dict.get("date_str", fallback_date_str or "unknown")

        return {
            "original_text": date_str,
            "display_text": date_str,
            "precision": "unknown",
            "is_bce": False,
            "start_year": None,
            "start_month": None,
            "start_day": None,
            "end_year": None,
            "end_month": None,
            "end_day": None,
        }

    @check_local_db
    async def get_viewpoint_related_event_ids(
        self,
        *,
        db: AsyncSession = None,
        canonical_source_id: str,
        viewpoint_type: str,
    ) -> list[str]:
        """Get event IDs related to viewpoint with specific source ID and type."""

        # Build the query to find the viewpoint
        stmt = (
            select(Viewpoint)
            .filter_by(
                canonical_source_id=canonical_source_id,
                viewpoint_type=viewpoint_type,
            )
            .options(selectinload(Viewpoint.event_associations))
        )

        # Execute query
        result = await db.execute(stmt)
        viewpoint = result.scalars().first()

        if not viewpoint:
            return []

        # Extract event IDs from associations
        event_ids = [assoc.event_id for assoc in viewpoint.event_associations]

        return event_ids
