"""
Task model for user-submitted timeline generation processing jobs.

This module represents the central orchestration unit that drives the entire
processing pipeline from raw text input to structured timeline output. Tasks
manage the lifecycle of timeline generation requests submitted by users.

Architecture:
    User → Task → Viewpoint → Events → Entities

Processing Pipeline:
    1. User submits topic_text for analysis
    2. Task status: pending → processing → completed/failed
    3. Processing generates a Viewpoint with structured timeline
    4. Results can be shared publicly or kept private

Key Features:
    - Lifecycle and status tracking
    - Performance monitoring
    - Public/private sharing configuration
    - Integration with viewpoint generation
"""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class Task(Base, UUIDMixin, TimestampMixin):
    """
    Timeline generation processing job submitted by a user.

    Manages the entire processing pipeline from raw text input to structured
    timeline output. Tracks status, performance, and configuration throughout
    the generation process.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_owner_id", "owner_id"),
        Index("ix_tasks_is_public", "is_public"),
        Index("ix_tasks_viewpoint_id", "viewpoint_id"),
        {"schema": SCHEMA_NAME},
    )

    topic_text = Column(
        Text,
        nullable=False,
        comment="Core input text for timeline generation and historical analysis",
    )

    owner_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.users.id", ondelete="CASCADE"),
        nullable=True,
        comment="Reference to the user who created this task (nullable for anonymous tasks)",
    )

    is_public = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether the task results are publicly accessible in the timeline gallery",
    )

    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="Current processing status: pending/processing/completed/failed",
    )

    processing_duration = Column(
        Float,
        nullable=True,
        comment="Total processing time in seconds (set when completed)",
    )

    config = Column(
        JSONB,
        nullable=True,
        comment="Task-specific configuration such as data source preferences and processing options",
    )

    notes = Column(
        Text,
        nullable=True,
        comment="Additional notes, error messages, or processing details",
    )

    processed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when task processing completed (successful or failed)",
    )

    viewpoint_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.viewpoints.id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to the generated viewpoint containing the timeline results",
    )

    owner = relationship(
        "User",
        back_populates="tasks",
        doc="User who created this task",
    )

    viewpoint = relationship(
        "Viewpoint",
        back_populates="tasks",
        doc="Generated viewpoint containing the structured timeline results",
    )

    def __repr__(self):
        return (
            f"<Task(id={self.id}, "
            f"status='{self.status}', "
            f"topic='{self.topic_text[:50]}...')>"
        )
