from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Generic, TypeVar

from asyncpg.exceptions import ConnectionDoesNotExistError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import tuple_

from app.db import AppAsyncSessionLocal
from app.models.base import Base
from app.utils.logger import setup_logger

logger = setup_logger("db_handlers")


# Define generic types for SQLAlchemy models and Pydantic schemas
ModelType = TypeVar("ModelType", bound=Base)


def check_local_db(func):
    """Database session decorator with transaction management and retry logic."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # If 'db' is already provided, we're in a nested call.
        # The outermost caller who created the session is responsible for the transaction.
        if kwargs.get("db"):
            # Even in a nested call, we might want retries, but the transaction
            # is managed externally. Let's assume for now retry is for new sessions.
            # A more complex implementation could handle nested retries differently.
            return await func(*args, **kwargs)

        # This is the outermost call, create a new session and manage the transaction.
        last_exception = None
        # Retry logic for transient connection errors
        for attempt in range(3):
            async with AppAsyncSessionLocal() as db:
                kwargs["db"] = db
                try:
                    result = await func(*args, **kwargs)
                    await db.commit()
                    return result
                except DBAPIError as e:
                    await db.rollback()
                    # Check if the error is a wrapper around a connection error
                    if isinstance(e.orig, ConnectionDoesNotExistError):
                        last_exception = e
                        logger.warning(
                            f"Connection error in {func.__name__} (attempt {attempt + 1}/3): {e}. Retrying..."
                        )
                        await asyncio.sleep(1 + attempt)  # Exponential backoff
                        continue
                    # It's a different DBAPIError, re-raise
                    logger.error(
                        f"DBAPIError in {func.__name__} (attempt {attempt + 1}/3): {e}",
                        exc_info=True,
                    )
                    raise
                except Exception as e:
                    await db.rollback()
                    logger.error(
                        f"Transaction failed in {func.__name__} (attempt {attempt + 1}/3): {e}",
                        exc_info=True,
                    )
                    raise  # Re-throw for non-DBAPIError exceptions

        # If all retries failed, raise the last captured exception
        logger.error(
            f"All retries failed for {func.__name__}. Last error: {last_exception}"
        )
        raise last_exception

    return wrapper


class BaseDBHandler(Generic[ModelType]):
    """Generic handler for database operations with basic CRUD methods."""

    def __init__(self, model: type[ModelType]):
        self.model = model

    @check_local_db
    async def create(
        self, obj_dict: dict[str, Any], *, db: AsyncSession = None
    ) -> ModelType:
        """Create a new record in the database."""

        db_obj = self.model(**obj_dict)
        try:
            db.add(db_obj)
            await db.commit()
            await db.refresh(db_obj)
            return db_obj
        except IntegrityError as e:
            await db.rollback()
            logger.warning(f"IntegrityError creating {self.model.__name__}: {e}")
            # Re-raise IntegrityError so calling code can handle it specifically
            raise
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"Error creating {self.model.__name__}: {e}", exc_info=True)
            raise

    @check_local_db
    async def get(self, id: Any, *, db: AsyncSession = None) -> ModelType | None:
        """Get a single record by its primary key."""
        stmt = select(self.model).where(self.model.id == id)
        result = await db.execute(stmt)
        return result.scalars().first()

    @check_local_db
    async def get_by_attributes(
        self, *, db: AsyncSession = None, query: select = None, **kwargs
    ) -> ModelType | None:
        """Get a single record by a set of attributes."""
        options_to_load = kwargs.pop("options", None)

        stmt = query if query is not None else select(self.model)
        stmt = stmt.filter_by(**kwargs)

        if options_to_load:
            stmt = stmt.options(*options_to_load)

        result = await db.execute(stmt)
        return result.scalars().first()

    @check_local_db
    async def get_id(self, *, db: AsyncSession = None, **kwargs) -> ModelType | None:
        """Get a single record ID by a set of attributes."""
        obj = self.get_by_attributes(**kwargs)
        if obj:
            return obj.id

    @check_local_db
    async def get_multi(
        self, *, db: AsyncSession = None, skip: int = 0, limit: int = 100
    ) -> list[ModelType]:
        """Get multiple records with pagination."""
        stmt = select(self.model).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    @check_local_db
    async def get_multi_by_attributes(
        self, *, db: AsyncSession = None, skip: int = 0, limit: int = 100, **kwargs
    ) -> list[ModelType]:
        """Get multiple records by a set of attributes with pagination."""
        # Pop special keys from kwargs, using function args as defaults
        final_limit = kwargs.pop("limit", limit)
        final_offset = kwargs.pop("offset", skip)
        # allow `skip` in kwargs as an alias for offset
        if "skip" in kwargs:
            final_offset = kwargs.pop("skip")

        order_by_clauses = kwargs.pop("order_by", None)
        options_to_load = kwargs.pop("options", None)

        # Remaining kwargs are for filtering
        filter_kwargs = kwargs

        stmt = select(self.model).filter_by(**filter_kwargs)

        # Eager load relationships if options are provided
        if options_to_load:
            stmt = stmt.options(*options_to_load)

        # Apply ordering if provided
        if order_by_clauses is not None:
            if isinstance(order_by_clauses, list):
                stmt = stmt.order_by(*order_by_clauses)
            else:
                stmt = stmt.order_by(order_by_clauses)

        stmt = stmt.offset(final_offset).limit(final_limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    @check_local_db
    async def update(
        self,
        db_obj: ModelType,
        update_data: dict[str, Any],
        *,
        db: AsyncSession = None,
    ) -> ModelType:
        """Update an existing record in the database."""

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        try:
            db.add(db_obj)
            await db.commit()
            await db.refresh(db_obj)
            return db_obj
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(
                f"Error updating {self.model.__name__} with id {db_obj.id}: {e}",
                exc_info=True,
            )
            raise

    @check_local_db
    async def remove(self, id: Any, *, db: AsyncSession = None) -> ModelType | None:
        """Remove a record from the database by its primary key."""
        obj = await self.get(id=id, db=db)
        if obj:
            try:
                await db.delete(obj)
                await db.commit()
                return obj
            except SQLAlchemyError as e:
                await db.rollback()
                logger.error(
                    f"Error removing {self.model.__name__} with id {id}: {e}",
                    exc_info=True,
                )
                raise
        return None

    @check_local_db
    async def batch_get_by_attributes(
        self, lookup_attrs: list[dict[str, Any]], *, db: AsyncSession = None
    ) -> dict[tuple, ModelType]:
        """Batch get records by their attributes."""
        if not lookup_attrs:
            return {}

        # Get the attribute names from the first dict
        attr_names = list(lookup_attrs[0].keys())
        if not attr_names:
            return {}

        # Create tuples of values for IN clause
        lookup_tuples = [
            tuple(attr_dict[name] for name in attr_names) for attr_dict in lookup_attrs
        ]

        # Build dynamic tuple_ comparison
        model_attrs = [getattr(self.model, name) for name in attr_names]
        stmt = select(self.model).where(tuple_(*model_attrs).in_(lookup_tuples))

        try:
            result = await db.execute(stmt)
            found_models = result.scalars().all()

            # Create return map using the same attributes as keys
            return {
                tuple(getattr(model, name) for name in attr_names): model
                for model in found_models
            }
        except SQLAlchemyError as e:
            logger.error(
                f"Error in batch_get_by_attributes for {self.model.__name__}: {e}",
                exc_info=True,
            )
            raise

    @check_local_db
    async def batch_create(
        self, obj_dicts: list[dict[str, Any]], *, db: AsyncSession = None
    ) -> list[ModelType]:
        """Create multiple records in a single transaction."""
        if not obj_dicts:
            return []

        try:
            # Create all model instances
            db_objs = [self.model(**obj_dict) for obj_dict in obj_dicts]

            # Add all to session
            db.add_all(db_objs)
            await db.commit()

            # Refresh all objects to get generated values
            for obj in db_objs:
                await db.refresh(obj)

            return db_objs
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(
                f"Error in batch_create for {self.model.__name__}: {e}", exc_info=True
            )
            raise

    @check_local_db
    async def batch_get_by_or_filters(
        self, filter_sets: list[dict[str, Any]], *, db: AsyncSession = None
    ) -> list[ModelType]:
        """Get records matching any of the provided filter sets."""
        if not filter_sets:
            return []

        try:
            # Create OR conditions from each filter set
            from sqlalchemy import or_

            conditions = []
            for filter_dict in filter_sets:
                # Create AND conditions for each filter set
                set_conditions = [
                    getattr(self.model, key) == value
                    for key, value in filter_dict.items()
                ]
                if set_conditions:
                    from sqlalchemy import and_

                    conditions.append(and_(*set_conditions))

            # Combine all conditions with OR
            stmt = select(self.model).where(or_(*conditions))
            result = await db.execute(stmt)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(
                f"Error in batch_get_by_or_filters for {self.model.__name__}: {e}",
                exc_info=True,
            )
            raise
