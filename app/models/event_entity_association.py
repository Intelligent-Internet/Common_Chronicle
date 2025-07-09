"""
Event-Entity association model for many-to-many relationships.

This module establishes many-to-many relationships between events and entities,
enabling rich semantic connections in the timeline data model. It records
which entities are involved in which events, greatly enhancing the semantic
expressiveness of the system.

Architecture:
    Event ←→ EventEntityAssociation ←→ Entity

Key Features:
    - Event-entity relationship tracking
    - Enhanced semantic data modeling
    - Extensible design for future relationship metadata
    - Efficient querying with proper indexing
"""

from sqlalchemy import Column, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class EventEntityAssociation(Base, UUIDMixin, TimestampMixin):
    """
    Association between events and entities for many-to-many relationships.

    Records which entities are involved in which events. This is a rich object
    with its own ID and timestamps, allowing for future extensions to store
    additional relationship metadata.
    """

    __tablename__ = "event_entity_associations"
    __table_args__ = (
        UniqueConstraint("event_id", "entity_id", name="uq_event_entity"),
        Index("ix_eea_event_id", "event_id"),
        Index("ix_eea_entity_id", "entity_id"),
        {"schema": SCHEMA_NAME},
    )

    event_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.events.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the event in which this entity is involved",
    )

    entity_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.entities.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the entity involved in this event",
    )

    event = relationship(
        "Event",
        back_populates="entity_associations",
        doc="The event this entity is involved in",
    )

    entity = relationship(
        "Entity",
        back_populates="event_associations",
        foreign_keys=[entity_id],
        doc="The entity involved in this event",
    )

    def __repr__(self):
        return (
            f"<EventEntityAssociation(id={self.id}, "
            f"event_id={self.event_id}, "
            f"entity_id={self.entity_id})>"
        )
