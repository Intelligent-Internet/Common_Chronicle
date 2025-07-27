"""
Defines the association table for the many-to-many relationship
between RawEvent and Entity.

This table directly links a raw, unprocessed event to the entities
that were identified within its original context. This allows for
consistent entity-based processing before the creation of a canonical
Event.
"""

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class RawEventEntityAssociation(Base, UUIDMixin, TimestampMixin):
    """
    Association object linking a RawEvent to an Entity.
    """

    __tablename__ = "raw_event_entity_association"
    __table_args__ = (
        UniqueConstraint(
            "raw_event_id", "entity_id", name="uq_raw_event_entity_association"
        ),
        {
            "schema": SCHEMA_NAME,
            "comment": "Joins raw events to the entities they mention.",
        },
    )

    raw_event_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.raw_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="The ID of the associated raw event.",
    )
    entity_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="The ID of the associated entity.",
    )

    # Relationships
    raw_event = relationship("RawEvent", back_populates="entity_associations")
    entity = relationship("Entity", back_populates="raw_event_associations")

    def __repr__(self) -> str:
        return f"<RawEventEntityAssociation(raw_event_id='{self.raw_event_id}', entity_id='{self.entity_id}')>"
