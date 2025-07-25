"""
Viewpoint model for organizing events into thematic timeline perspectives.

This module provides timeline organization capabilities through the Viewpoint model,
which serves as the final output of the event processing pipeline. Viewpoints
represent coherent narratives that organize collections of events around specific
topics or themes.

Architecture:
    Task → Viewpoint → Events (via ViewpointEventAssociation)

Key Concepts:
    - Canonical viewpoints: Derived from single authoritative sources
    - Synthetic viewpoints: Synthesized from multiple sources for custom tasks
    - Data source preferences: Influence content and perspective generation
    - Progress tracking: Monitored through ViewpointProgressStep records
"""

from sqlalchemy import Column, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class Viewpoint(Base, UUIDMixin, TimestampMixin):
    """
    Timeline perspective that organizes events around a specific topic.

    Serves as the final output of event processing, providing structured
    timeline results to users. Supports both canonical (single-source) and
    synthetic (multi-source) timeline generation.
    """

    __tablename__ = "viewpoints"
    __table_args__ = (
        Index("ix_viewpoints_status", "status"),
        Index("ix_viewpoints_viewpoint_type", "viewpoint_type"),
        Index("ix_viewpoints_data_source_preference", "data_source_preference"),
        Index("ix_viewpoints_canonical_source_id", "canonical_source_id"),
        {"schema": SCHEMA_NAME},
    )

    status = Column(
        String(50),
        nullable=False,
        default="populating",
        comment="Processing status of the viewpoint (populating/completed/failed)",
    )

    topic = Column(
        Text,
        nullable=False,
        comment="Topic or theme of the viewpoint timeline (e.g., article title or user query)",
    )

    viewpoint_type = Column(
        String(50),
        nullable=False,
        comment="Viewpoint classification: 'canonical' for single-source or 'synthetic' for multi-source timelines",
    )

    data_source_preference = Column(
        String(255),
        nullable=False,
        comment="Preferred data source for content generation (dataset_wikipedia_en/online_wikipedia/online_wikinews)",
    )

    canonical_source_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.source_documents.id"),
        nullable=True,
        comment="Source document reference for canonical viewpoints (null for synthetic viewpoints)",
    )

    canonical_source = relationship(
        "SourceDocument",
        back_populates="canonical_viewpoint",
        doc="Source document providing the canonical content for this viewpoint",
    )

    tasks = relationship(
        "Task",
        back_populates="viewpoint",
        doc="Tasks that generated or are associated with this viewpoint",
    )

    event_associations = relationship(
        "ViewpointEventAssociation",
        back_populates="viewpoint",
        cascade="all, delete-orphan",
        doc="Events that constitute this timeline perspective",
    )

    progress_steps = relationship(
        "ViewpointProgressStep",
        back_populates="viewpoint",
        cascade="all, delete-orphan",
        doc="Processing steps for viewpoint generation progress tracking",
    )

    def __repr__(self):
        return (
            f"<Viewpoint(id={self.id}, "
            f"type='{self.viewpoint_type}', "
            f"topic='{self.topic}')>"
        )
