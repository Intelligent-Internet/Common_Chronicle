from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_handlers.base import BaseDBHandler, check_local_db
from app.models.event_raw_event_association import EventRawEventAssociation
from app.utils.logger import setup_logger

logger = setup_logger("db_handlers.event_rawevent_association")


class EventRawEventAssociationDBHandler(BaseDBHandler[EventRawEventAssociation]):
    def __init__(self):
        super().__init__(EventRawEventAssociation)

    @check_local_db
    async def check_association_exists(
        self, event_id: uuid.UUID, raw_event_id: uuid.UUID, *, db: AsyncSession = None
    ) -> bool:
        """Check if association between event and raw_event already exists."""
        try:
            existing_assoc = await db.scalar(
                select(EventRawEventAssociation).where(
                    EventRawEventAssociation.event_id == event_id,
                    EventRawEventAssociation.raw_event_id == raw_event_id,
                )
            )
            return existing_assoc is not None
        except SQLAlchemyError as e:
            logger.error(f"Error checking association existence: {e}")
            raise
