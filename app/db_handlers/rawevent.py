from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db_handlers.base import BaseDBHandler, check_local_db
from app.models.raw_event import RawEvent
from app.models.raw_event_entity_association import RawEventEntityAssociation
from app.utils.logger import setup_logger

logger = setup_logger("db_handlers.rawevent")


class RawEventDBHandler(BaseDBHandler[RawEvent]):
    def __init__(self):
        super().__init__(RawEvent)

    @check_local_db
    async def get_by_attributes_with_entity_associations(
        self,
        source_document_id: uuid.UUID,
        deduplication_signature: str,
        *,
        db: AsyncSession = None,
    ) -> RawEvent | None:
        """Get raw event by attributes with entity associations preloaded."""
        try:
            stmt = (
                select(RawEvent)
                .options(
                    selectinload(RawEvent.entity_associations).selectinload(
                        RawEventEntityAssociation.entity
                    )
                )
                .where(
                    RawEvent.source_document_id == source_document_id,
                    RawEvent.deduplication_signature == deduplication_signature,
                )
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving raw event with entity associations: {e}")
            raise
