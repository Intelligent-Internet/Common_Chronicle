"""
Entity model for normalized, unique entities in the knowledge system.

This module represents the knowledge objects (people, places, organizations,
event types) that can be referenced across multiple events and timelines.
Entities provide canonical identification using Wikidata identifiers and
support multi-language information through source documents.

Architecture:
    Entity ←→ SourceDocument (verification source)
    Entity ←→ EventEntityAssociation ←→ Event

Key Features:
    - Canonical entity identification using Wikidata identifiers
    - Multi-language support through source documents
    - Entity type classification and categorization
    - Verification status for existence confirmation
"""

from sqlalchemy import Boolean, Column, Index, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class Entity(Base, TimestampMixin, UUIDMixin):
    """
    Normalized, unique knowledge object in the system.

    Represents people, organizations, places, and event types that can be
    referenced across multiple events. Each entity is canonically identified
    by its Wikidata identifier for cross-reference consistency.
    """

    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("wikibase_item", name="uq_entities_wikibase_item"),
        Index("ix_entities_entity_type", "entity_type"),
        Index("ix_entities_entity_name", "entity_name"),
        Index("ix_entities_wikibase_item", "wikibase_item"),
        {"schema": SCHEMA_NAME},
    )

    entity_name = Column(
        String(255),
        nullable=False,
        comment="Primary display name for the entity (can vary by language but represents same entity)",
    )

    entity_type = Column(
        String(50),
        nullable=False,
        comment="Entity classification type (e.g., 'PERSON', 'ORGANIZATION', 'LOCATION', 'EVENT_TYPE')",
    )

    wikibase_item = Column(
        String(50),
        nullable=False,
        comment="Wikidata identifier (e.g., 'Q517') serving as the canonical unique identifier",
    )

    existence_verified = Column(
        Boolean,
        nullable=False,
        server_default="f",
        comment="Whether the entity's existence is verified through canonical sources like Wikipedia",
    )

    # One-to-many relationship between entity and source documents; one entity can have multiple source documents in different languages
    source_documents = relationship(
        "SourceDocument",
        back_populates="entity",
        cascade="all, delete-orphan",
        doc="Source documents providing information about this entity in various languages",
    )

    # Many-to-many relationship between entity and events
    event_associations = relationship(
        "EventEntityAssociation",
        back_populates="entity",
        cascade="all, delete-orphan",
        doc="Events this entity is involved in or referenced by",
    )

    raw_event_associations = relationship(
        "RawEventEntityAssociation",
        back_populates="entity",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<Entity(id={self.id}, "
            f"entity_name='{self.entity_name}', "
            f"wikibase_item='{self.wikibase_item}', "
            f"entity_type='{self.entity_type}')>"
        )
