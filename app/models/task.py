"""
Task model for user-submitted timeline generation processing jobs.

This module represents the central orchestration unit that drives the entire
processing pipeline from raw text input to structured timeline output. Tasks
manage the lifecycle of timeline generation requests submitted by users.

Architecture:
    User → Task → Viewpoint → Events → Entities

Processing Pipeline:
    1. User submits topic_text for analysis (synthetic viewpoint)
       OR submits entity_id/source_document_id for canonical processing
    2. Task status: pending → processing → completed/failed
    3. Processing generates a Viewpoint with structured timeline
    4. Results can be shared publicly or kept private

Key Features:
    - Lifecycle and status tracking
    - Performance monitoring
    - Public/private sharing configuration
    - Integration with viewpoint generation
    - Support for multiple task types (synthetic, entity_canonical, document_canonical)
"""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship, validates

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class Task(Base, UUIDMixin, TimestampMixin):
    """
    Timeline generation processing job submitted by a user.

    Manages the entire processing pipeline from raw text input to structured
    timeline output. Tracks status, performance, and configuration throughout
    the generation process. Supports multiple task types:

    - synthetic_viewpoint: Traditional topic-based timeline generation
    - entity_canonical: Generate timeline from specific entity's source documents
    - document_canonical: Generate timeline from specific source document
    """

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_owner_id", "owner_id"),
        Index("ix_tasks_is_public", "is_public"),
        Index("ix_tasks_viewpoint_id", "viewpoint_id"),
        Index("ix_tasks_task_type", "task_type"),
        Index("ix_tasks_entity_id", "entity_id"),
        Index("ix_tasks_source_document_id", "source_document_id"),
        {"schema": SCHEMA_NAME},
    )

    task_type = Column(
        String(30),
        nullable=False,
        default="synthetic_viewpoint",
        comment="Type of task: synthetic_viewpoint (default), entity_canonical, or document_canonical",
    )

    topic_text = Column(
        Text,
        nullable=True,  # Changed to nullable since canonical tasks don't require topic_text
        comment="Core input text for timeline generation and historical analysis (required for synthetic_viewpoint tasks)",
    )

    entity_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.entities.id", ondelete="CASCADE"),
        nullable=True,
        comment="Reference to entity for entity_canonical tasks",
    )

    source_document_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.source_documents.id", ondelete="CASCADE"),
        nullable=True,
        comment="Reference to source document for document_canonical tasks",
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

    entity = relationship(
        "Entity",
        doc="Entity referenced by entity_canonical tasks",
    )

    source_document = relationship(
        "SourceDocument",
        doc="Source document referenced by document_canonical tasks",
    )

    @validates("task_type")
    def validate_task_type_requirements(self, key, value):
        """Validate task_type and perform cross-field validation safely."""
        # First validate the task_type enum
        if value not in [
            "synthetic_viewpoint",
            "entity_canonical",
            "document_canonical",
        ]:
            raise ValueError(f"Invalid task_type: {value}")

        # For cross-field validation, only check when we're confident
        # other fields are already set (skip during object construction)
        if hasattr(self, "_sa_instance_state") and self._sa_instance_state.persistent:
            # Object is being updated, perform full validation
            self._validate_requirements_for_type(value)

        return value

    def _validate_requirements_for_type(self, task_type):
        """Helper method to validate requirements for a specific task type."""
        if task_type == "synthetic_viewpoint":
            if not getattr(self, "topic_text", None):
                raise ValueError("topic_text is required for synthetic_viewpoint tasks")
        elif task_type == "entity_canonical":
            if not getattr(self, "entity_id", None):
                raise ValueError("entity_id is required for entity_canonical tasks")
        elif task_type == "document_canonical":
            if not getattr(self, "source_document_id", None):
                raise ValueError(
                    "source_document_id is required for document_canonical tasks"
                )

    def __init__(self, **kwargs):
        """Initialize Task with proper validation after all fields are set."""
        super().__init__(**kwargs)
        # Perform validation after object is fully constructed
        if hasattr(self, "task_type") and self.task_type:
            self._validate_requirements_for_type(self.task_type)

    def __repr__(self):
        if self.task_type == "synthetic_viewpoint":
            detail = (
                f"topic='{self.topic_text[:50]}...'"
                if self.topic_text
                else "topic=None"
            )
        elif self.task_type == "entity_canonical":
            detail = f"entity_id='{self.entity_id}'"
        elif self.task_type == "document_canonical":
            detail = f"source_document_id='{self.source_document_id}'"
        else:
            detail = f"type='{self.task_type}'"

        return (
            f"<Task(id={self.id}, "
            f"status='{self.status}', "
            f"task_type='{self.task_type}', "
            f"{detail})>"
        )
