"""
Viewpoint-Event association model for many-to-many relationships.

This module establishes many-to-many relationships between viewpoints and events,
enabling timeline organization with narrative sequencing capabilities. The core
functionality includes narrative sequencing through the sequence_order field,
enabling coherent timeline presentation.

Architecture:
    Viewpoint ←→ ViewpointEventAssociation ←→ Event

Key Features:
    - Timeline event organization
    - Narrative sequence ordering
    - Viewpoint-specific event collections
    - Unique constraint enforcement
    - Efficient timeline querying
"""

from sqlalchemy import Column, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, UUIDMixin


class ViewpointEventAssociation(Base, UUIDMixin):
    """
    Association between viewpoints and events for timeline organization.

    Organizes events under specific thematic perspectives with optional narrative
    sequencing. Enables coherent timeline presentation and supports multiple
    timeline perspectives of the same events.
    """

    __tablename__ = "viewpoint_event_associations"
    __table_args__ = (
        UniqueConstraint("viewpoint_id", "event_id", name="uq_viewpoint_event"),
        UniqueConstraint(
            "viewpoint_id", "sequence_order", name="uq_viewpoint_sequence"
        ),
        Index("ix_vea_viewpoint_id", "viewpoint_id"),
        Index("ix_vea_event_id", "event_id"),
        {"schema": SCHEMA_NAME},
    )

    viewpoint_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.viewpoints.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the viewpoint that includes this event",
    )

    event_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.events.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the event included in this viewpoint",
    )

    sequence_order = Column(
        Integer,
        nullable=True,
        comment="Optional sequence order for narrative presentation within the viewpoint",
    )

    viewpoint = relationship(
        "Viewpoint",
        back_populates="event_associations",
        doc="The viewpoint that includes this event",
    )

    event = relationship(
        "Event",
        back_populates="viewpoint_associations",
        doc="The event included in this viewpoint",
    )

    def __repr__(self):
        return (
            f"<ViewpointEventAssociation(id={self.id}, "
            f"viewpoint_id={self.viewpoint_id}, "
            f"event_id={self.event_id}, "
            f"sequence_order={self.sequence_order})>"
        )
