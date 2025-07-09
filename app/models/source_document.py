"""
Source Document model for external information source metadata management.

This module manages metadata for all external information sources such as
Wikipedia articles, web crawls, and other reference materials. Source documents
serve as the foundation for raw event extraction and entity existence verification
throughout the processing pipeline.

Architecture:
    SourceDocument → RawEvent → Event
    SourceDocument ←→ Entity (verification source)
    SourceDocument → Viewpoint (canonical source)

Key Features:
    - External source metadata tracking
    - Processing status management
    - Multi-language source support
    - Entity existence verification
    - Raw event extraction foundation
    - Canonical viewpoint generation
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


class SourceDocument(Base, TimestampMixin, UUIDMixin):
    """
    External information source metadata with processing tracking.

    Stores metadata for external sources and tracks processing status throughout
    the extraction pipeline. Serves as the primary verification source for
    entity existence and foundation for raw event extraction.
    """

    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint(
            "wikipedia_url",
            "source_type",
            name="uq_source_documents_wikipedia_url_source_type",
        ),
        Index("ix_source_documents_processing_status", "processing_status"),
        Index("ix_source_documents_source_type", "source_type"),
        Index("ix_source_documents_title", "title"),
        Index("ix_source_documents_wikibase_item", "wikibase_item"),
        Index("ix_source_documents_wiki_pageid", "wiki_pageid"),
        Index("ix_source_documents_entity_id", "entity_id"),
        Index("ix_source_documents_type_lang", "source_type", "language"),
        {"schema": SCHEMA_NAME},
    )

    processing_status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="Processing status tracking (pending/processing_entities/processing_linking/completed)",
    )

    source_type = Column(
        String(50),
        nullable=True,
        comment="Type of source (wikipedia/web_crawl/news_article/etc.)",
    )

    title = Column(
        String(255),
        nullable=False,
        comment="Title of the source document (e.g., Wikipedia article title)",
    )

    wikipedia_url = Column(
        Text,
        nullable=True,
        comment="Wikipedia URL for Wikipedia sources (unique constraint prevents duplicates)",
    )

    language = Column(
        String(10),
        nullable=False,
        comment="Language code of the source document (e.g., 'en' for English)",
    )

    wikibase_item = Column(
        String(50),
        nullable=True,
        comment="Wikidata identifier (e.g., 'Q517') for canonical entity reference",
    )

    wiki_pageid = Column(
        String(50),
        nullable=True,
        comment="Wiki page ID for Wikipedia sources",
    )

    extract = Column(
        Text,
        nullable=True,
        comment="Summary or extract from the source document content",
    )

    source_document_version = Column(
        String,
        nullable=True,
        comment="Source document version identifier (e.g., Wikipedia revision_id)",
    )

    source_document_timestamp = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the source document itself (e.g., last modified date)",
    )

    entity_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.entities.id", ondelete="CASCADE"),
        nullable=True,
        comment="The entity this source document describes and verifies existence for",
    )

    entity = relationship(
        "Entity",
        back_populates="source_documents",
        doc="The entity this source document describes and verifies",
    )

    raw_events = relationship(
        "RawEvent",
        back_populates="source_document",
        cascade="all, delete-orphan",
        doc="All raw events extracted from this source document",
    )

    canonical_viewpoint = relationship(
        "Viewpoint",
        back_populates="canonical_source",
        uselist=False,
        cascade="all, delete-orphan",
        doc="The canonical viewpoint generated from this source document",
    )

    def __repr__(self):
        return (
            f"<SourceDocument(id={self.id}, "
            f"title='{self.title}', "
            f"language='{self.language}', "
            f"source_type='{self.source_type}'"
            f"entity_id='{self.entity_id}')>"
        )
