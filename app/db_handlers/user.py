from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_handlers.base import BaseDBHandler, check_local_db
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger("db_handlers.user")


class UserDBHandler(BaseDBHandler[User]):
    def __init__(self):
        super().__init__(User)

    @check_local_db
    async def get_user_by_username(
        self, username: str, *, db: AsyncSession = None
    ) -> User | None:
        """Get a user by username."""
        try:
            stmt = select(User).filter(User.username == username)
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving user by username '{username}': {e}")
            raise
