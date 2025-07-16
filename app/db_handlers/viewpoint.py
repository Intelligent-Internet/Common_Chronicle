from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


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

        # Format timeline events - always return all events with their relevance scores
        timeline_events = self._format_timeline_events(viewpoint)

        # Serialize progress steps
        progress_steps = [step.to_dict() for step in viewpoint.progress_steps]

        return {
            "viewpoint": viewpoint.to_dict(),
            "progress_steps": progress_steps,
            "timeline_events": timeline_events,
        }

    def _format_timeline_events(
        self, viewpoint: Viewpoint
    ) -> list[TimelineEventForAPI]:
        """Format events from loaded Viewpoint into API models."""
        final_event_api_objects: list[TimelineEventForAPI] = []

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

            # Format source contributions
            source_contributions_for_api = []
            for link in db_event.raw_event_association_links:
                contrib = link.raw_event
                if not contrib:
                    continue

                # Convert source contribution date_info to proper format
                parsed_contrib_date_info = self._convert_date_info_to_parsed_format(
                    contrib.date_info, contrib.event_date_str
                )

                source_doc = contrib.source_document
                source_contributions_for_api.append(
                    EventSourceInfoForAPI(
                        original_description=contrib.original_description,
                        event_date_str=contrib.event_date_str,
                        date_info=parsed_contrib_date_info,
                        source_language=getattr(source_doc, "language", "unknown"),
                        source_page_title=getattr(source_doc, "title", None),
                        source_url=getattr(source_doc, "wikipedia_url", None),
                        source_text_snippet=contrib.source_text_snippet,
                    )
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
                        status_code=200,
                        message=None,
                        disambiguation_options=None,
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

            first_source = (
                source_contributions_for_api[0]
                if source_contributions_for_api
                else None
            )

            final_event_api_objects.append(
                TimelineEventForAPI(
                    id=db_event.id,
                    # TODO:changed to display text
                    event_date_str=db_event.event_date_str,
                    description=db_event.description,
                    main_entities=api_main_entities,
                    date_info=api_date_info,
                    is_merged=len(source_contributions_for_api) > 1,
                    sources=source_contributions_for_api,
                    viewpoint_id=viewpoint.id,
                    source_text_snippet=(
                        first_source.source_text_snippet
                        if first_source
                        else db_event.description
                    ),
                    source_url=(first_source.source_url if first_source else None),
                    source_page_title=(
                        first_source.source_page_title
                        if first_source
                        else "Aggregated Event"
                    ),
                    source_language=(
                        first_source.source_language if first_source else None
                    ),
                    relevance_score=association.relevance_score,
                )
            )

        logger.debug(
            f"[Format Timeline] Final result: {len(final_event_api_objects)} events formatted"
        )
        return final_event_api_objects

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
