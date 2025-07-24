"""
Event model for normalized, unique historical events and occurrences.

This module represents the core structured data for timeline generation.
Events are normalized, unique records that correspond to real-world historical
occurrences, generated through processing, merging, and deduplication of raw
event data from various sources.

Architecture:
    RawEvent → EventRawEventAssociation → Event ←→ ViewpointEventAssociation ←→ Viewpoint
    Event ←→ EventEntityAssociation ←→ Entity

Key Features:
    - Normalized event descriptions and dates
    - Structured date information parsing
    - Vector embeddings for semantic similarity search
    - Associations with entities, viewpoints, and raw source events
    - Validation for required fields and data integrity
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, validates

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class Event(Base, UUIDMixin, TimestampMixin):
    """
    Normalized historical event with semantic search capabilities.

    Represents a unique historical occurrence derived from processing and
    deduplication of multiple raw events. Includes vector embeddings for
    semantic similarity search and structured date information.
    """

    __tablename__ = "events"
    __table_args__ = (
        Index(
            "ix_events_description_vector",
            "description_vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"description_vector": "vector_cosine_ops"},
        ),
        {"schema": SCHEMA_NAME},
    )

    event_date_str = Column(
        String,
        nullable=False,
        comment="Representative date description text for the event (e.g., 'December 2, 1805')",
    )

    description = Column(
        Text,
        nullable=False,
        comment="Normalized core description of the event content and significance",
    )

    date_info = Column(
        JSONB,
        nullable=True,
        comment="Structured date information conforming to ParsedDateInfo schema with precision and calendar details",
    )

    description_vector = Column(
        Vector(768),
        nullable=False,
        comment="Embedding vector for semantic similarity search and event clustering",
    )

    raw_event_association_links = relationship(
        "EventRawEventAssociation",
        back_populates="event",
        cascade="all, delete-orphan",
        doc="Association links to raw events that contributed to this normalized event",
    )

    entity_associations = relationship(
        "EventEntityAssociation",
        back_populates="event",
        cascade="all, delete-orphan",
        doc="Entities (people, places, organizations) involved in this event",
    )

    viewpoint_associations = relationship(
        "ViewpointEventAssociation",
        back_populates="event",
        cascade="all, delete-orphan",
        doc="Viewpoints that include this event in their timeline perspective",
    )

    @property
    def raw_events(self):
        """
        Get all RawEvent objects associated with this Event.
        """
        return [
            link.raw_event
            for link in self.raw_event_association_links
            if link.raw_event
        ]

    @validates("event_date_str")
    def validate_event_date_str(self, key, value):
        if value is None:
            current_description = getattr(self, "description", None)
            error_message = "event_date_str cannot be None. This is a required field."
            if current_description:
                error_message += f" (Event description starts with: '{current_description[:100]}...')"
            raise ValueError(error_message)

        if not isinstance(value, str):
            raise TypeError(
                f"event_date_str must be a string, but got type {type(value)}."
            )

        if not value.strip():
            current_description = getattr(self, "description", None)
            error_message = "event_date_str cannot be empty or contain only whitespace."
            if current_description:
                error_message += f" (Event description starts with: '{current_description[:100]}...')"
            raise ValueError(error_message)

        return value

    def __repr__(self):
        return (
            f"<Event(id={self.id}, "
            f"description='{self.description[:50]}...', "
            f"event_date_str='{self.event_date_str}')>"
        )
