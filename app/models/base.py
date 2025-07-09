"""
Base configurations and mixins for database models.

This module provides the foundation for all database models in the Common Chronicle application.
It includes essential base classes, mixins, and utilities that ensure consistent behavior
across all model implementations.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql.functions import now as db_now

from app.config import settings


class CustomBase:
    """
    Custom base class for SQLAlchemy models with enhanced serialization.

    This class provides a `to_dict` method that automatically converts
    model instances to dictionaries, handling special data types like
    UUID and datetime objects appropriately.
    """

    def to_dict(self) -> dict:
        d = {}
        if not self:
            return d
        for column in inspect(self).mapper.column_attrs:
            value = getattr(self, column.key)
            if isinstance(value, uuid.UUID):
                d[column.key] = str(value)
            elif isinstance(value, datetime):
                # Use isoformat() for timezone-aware datetime objects
                d[column.key] = value.isoformat()
            else:
                d[column.key] = value
        return d


# Create the base class for all models
Base = declarative_base(cls=CustomBase)


class TimestampMixin:
    """
    Mixin class that adds automatic timestamp management to models.

    Provides created_at and updated_at columns that are automatically
    managed by the database. The created_at timestamp is set when the
    record is first inserted, and updated_at is automatically updated
    whenever the record is modified.
    """

    created_at = Column(
        DateTime(timezone=True),
        server_default=db_now(),
        nullable=False,
        comment="Timestamp when the record was created",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=db_now(),
        onupdate=db_now(),
        nullable=False,
        comment="Timestamp when the record was last updated",
    )


class UUIDMixin:
    """
    Mixin class that adds UUID primary key to models.

    Provides a UUID-based primary key column that is automatically
    generated using uuid4() when new records are created. The UUID
    is indexed for performance and uses PostgreSQL's native UUID type.
    """

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
        comment="Primary key using UUID4 format",
    )


# Export schema name for use in models
# For backward compatibility
SCHEMA_NAME = settings.schema_name

__all__ = ["Base", "TimestampMixin", "UUIDMixin", "SCHEMA_NAME"]
