"""
Event-RawEvent association model for many-to-many relationships.

This module manages many-to-many relationships between normalized events and
raw events, tracking the source contributions that led to each processed event.
This provides essential traceability for the event processing pipeline and
enables data lineage preservation.

Architecture:
    Event ←→ EventRawEventAssociation ←→ RawEvent

Key Features:
    - Event processing traceability
    - Raw event source tracking
    - Data lineage preservation
    - Composite primary key for relationship uniqueness
    - Cascade deletion for data integrity
"""

from sqlalchemy import Column, ForeignKey, Index, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, TimestampMixin


class EventRawEventAssociation(Base, TimestampMixin):
    """
    Association between events and raw events for processing traceability.

    Tracks which raw events contributed to the formation of each normalized
    event, providing essential data lineage for the event processing pipeline.
    Uses a composite primary key to ensure relationship uniqueness.
    """

    __tablename__ = "event_raw_event_associations"
    __table_args__ = (
        PrimaryKeyConstraint("event_id", "raw_event_id"),
        Index("ix_erea_event_id", "event_id"),
        Index("ix_erea_raw_event_id", "raw_event_id"),
        {"schema": SCHEMA_NAME},
    )

    event_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.events.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the normalized event that uses this raw event as source material",
    )

    raw_event_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.raw_events.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the raw event being used as source material",
    )

    event = relationship(
        "Event",
        back_populates="raw_event_association_links",
        doc="The normalized event that uses this raw event as source material",
    )

    raw_event = relationship(
        "RawEvent",
        back_populates="event_association_links",
        doc="The raw event being used as source material",
    )

    def __repr__(self):
        return (
            f"<EventRawEventAssociation("
            f"event_id={self.event_id}, "
            f"raw_event_id={self.raw_event_id})>"
        )
