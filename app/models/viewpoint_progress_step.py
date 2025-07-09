"""
Viewpoint Progress Step model for tracking progress during viewpoint generation.

This module provides granular monitoring and troubleshooting capabilities for
long-running viewpoint generation tasks. Each progress step represents a
significant milestone in the processing pipeline, enabling clear visibility
into task progression and detailed error diagnosis.

Architecture:
    Viewpoint → ViewpointProgressStep (one-to-many)

Key Features:
    - Progress tracking for viewpoint generation
    - Step-by-step monitoring capabilities
    - Debugging and troubleshooting information
    - Timestamp tracking for performance analysis
    - Detailed logging of processing stages
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class ViewpointProgressStep(Base, UUIDMixin, TimestampMixin):
    """
    Progress step tracking for viewpoint generation processes.

    Tracks significant milestones and stages in the viewpoint generation pipeline,
    providing granular monitoring for debugging and troubleshooting complex
    processing workflows.
    """

    __tablename__ = "viewpoint_progress_steps"
    __table_args__ = (
        UniqueConstraint(
            "viewpoint_id",
            "step_name",
            "message",
            name="uq_viewpoint_step_message",
        ),
        Index("ix_vps_viewpoint_id", "viewpoint_id"),
        Index("ix_vps_event_timestamp", "event_timestamp"),
        {"schema": SCHEMA_NAME},
    )

    viewpoint_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.viewpoints.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to the viewpoint this progress step belongs to",
    )

    step_name = Column(
        String(255),
        nullable=False,
        comment="Name/type of the progress step (e.g., 'source_extraction', 'event_normalization')",
    )

    event_timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when this progress step occurred",
    )

    message = Column(
        Text,
        nullable=True,
        comment="Detailed message about this step including status, counts, or error information",
    )

    viewpoint = relationship(
        "Viewpoint",
        back_populates="progress_steps",
        doc="The viewpoint this progress step belongs to",
    )

    def __repr__(self) -> str:
        return (
            f"<ViewpointProgressStep(id={self.id}, viewpoint_id={self.viewpoint_id}, "
            f"step_name='{self.step_name}', "
            f"event_timestamp={self.event_timestamp})>"
        )
