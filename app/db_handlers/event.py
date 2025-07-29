from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db_handlers.base import BaseDBHandler, check_local_db
from app.models.event import Event
from app.models.event_entity_association import EventEntityAssociation
from app.models.event_raw_event_association import EventRawEventAssociation
from app.models.raw_event import RawEvent
from app.utils.logger import setup_logger

logger = setup_logger("db_handlers.event")


class EventDBHandler(BaseDBHandler[Event]):
    def __init__(self):
        super().__init__(Event)

    @check_local_db
    async def get_events_by_ids(
        self, event_ids: list[uuid.UUID], *, db: AsyncSession = None
    ) -> list[Event]:
        """Get multiple events by their IDs."""
        if not event_ids:
            return []

        try:
            stmt = select(Event).where(Event.id.in_(event_ids))
            result = await db.execute(stmt)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving events by IDs: {e}")
            raise

    @check_local_db
    async def get_events_by_ids_with_associations(
        self, event_ids: list[uuid.UUID], *, db: AsyncSession = None
    ) -> list[Event]:
        """Get multiple events by their IDs with all associations eagerly loaded."""
        if not event_ids:
            return []

        try:
            stmt = (
                select(Event)
                .options(
                    selectinload(Event.entity_associations).selectinload(
                        EventEntityAssociation.entity
                    ),
                    selectinload(Event.raw_event_association_links)
                    .selectinload(EventRawEventAssociation.raw_event)
                    .selectinload(RawEvent.source_document),
                )
                .where(Event.id.in_(event_ids))
            )
            result = await db.execute(stmt)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving events with associations by IDs: {e}")
            raise

    @check_local_db
    async def get_source_document_ids_for_event(
        self, event_id: uuid.UUID, *, db: AsyncSession = None
    ) -> set[uuid.UUID]:
        """Get all source document IDs associated with an event."""
        try:
            result = await db.execute(
                select(RawEvent.source_document_id)
                .join(EventRawEventAssociation)
                .where(EventRawEventAssociation.event_id == event_id)
                .distinct()
            )
            return {row[0] for row in result}
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving source document IDs for event {event_id}: {e}"
            )
            raise

    @check_local_db
    async def find_similar_events_by_vector(
        self,
        embedding: list[float],
        limit: int = 5,
        threshold: float = 0.80,
        *,
        db: AsyncSession = None,
    ) -> list[Event]:
        """Find events similar to the given embedding vector."""
        try:
            distance_threshold = 1 - threshold
            result = await db.execute(
                select(Event)
                .where(
                    Event.description_vector.cosine_distance(embedding)
                    < distance_threshold
                )
                .order_by(Event.description_vector.cosine_distance(embedding))
                .limit(limit)
            )
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Error finding similar events by vector: {e}")
            raise

    @check_local_db
    async def calculate_vector_distance(
        self, event_id: uuid.UUID, embedding: list[float], *, db: AsyncSession = None
    ) -> float | None:
        """Calculate cosine distance between event's vector and given embedding."""
        try:
            distance = await db.scalar(
                select(Event.description_vector.cosine_distance(embedding)).where(
                    Event.id == event_id
                )
            )
            return distance
        except SQLAlchemyError as e:
            logger.error(f"Error calculating vector distance for event {event_id}: {e}")
            raise
