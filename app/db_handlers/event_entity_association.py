from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_handlers.base import BaseDBHandler, check_local_db
from app.models.event_entity_association import EventEntityAssociation
from app.utils.logger import setup_logger

logger = setup_logger("db_handlers.event_entity_association")


class EventEntityAssociationDBHandler(BaseDBHandler[EventEntityAssociation]):
    def __init__(self):
        super().__init__(EventEntityAssociation)

    @check_local_db
    async def bulk_create_associations(
        self, associations_data: list[dict], *, db: AsyncSession = None
    ) -> None:
        """Bulk create event-entity associations with conflict handling."""
        if not associations_data:
            return

        try:
            stmt = pg_insert(EventEntityAssociation).values(associations_data)
            stmt = stmt.on_conflict_do_nothing(index_elements=["event_id", "entity_id"])
            await db.execute(stmt)
            logger.debug(
                f"Bulk inserted {len(associations_data)} event-entity associations with ON CONFLICT"
            )
        except SQLAlchemyError as e:
            logger.error(f"Error bulk creating event-entity associations: {e}")
            raise
