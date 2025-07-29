from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_handlers.base import BaseDBHandler, check_local_db
from app.models.viewpoint_event_association import ViewpointEventAssociation
from app.utils.logger import setup_logger

logger = setup_logger("db_handlers.viewpoint_event_association")


class ViewpointEventAssociationDBHandler(BaseDBHandler[ViewpointEventAssociation]):
    def __init__(self):
        super().__init__(ViewpointEventAssociation)

    @check_local_db
    async def bulk_create_associations(
        self, associations_data: list[dict], *, db: AsyncSession = None
    ) -> None:
        """Bulk create viewpoint-event associations with conflict handling."""
        if not associations_data:
            return

        try:
            stmt = pg_insert(ViewpointEventAssociation).values(associations_data)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["viewpoint_id", "event_id"]
            )
            await db.execute(stmt)
            logger.debug(
                f"Bulk inserted {len(associations_data)} viewpoint-event associations with ON CONFLICT"
            )
        except SQLAlchemyError as e:
            logger.error(f"Error bulk creating viewpoint-event associations: {e}")
            raise
