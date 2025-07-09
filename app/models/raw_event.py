"""
Raw Event model for original, unprocessed event information from source documents.

This module preserves original, unprocessed event information extracted from
source documents before normalization and merging. Raw events provide data
fidelity and traceability throughout the processing pipeline, allowing for
audit trails and reprocessing with improved algorithms.

Architecture:
    SourceDocument → RawEvent → EventRawEventAssociation → Event

Key Features:
    - Original event information preservation
    - Source document traceability
    - Deduplication signature for fast duplicate detection
    - Data lineage tracking before normalization
    - Association with processed events
"""

from sqlalchemy import Column, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class RawEvent(Base, UUIDMixin, TimestampMixin):
    """
    Original, unprocessed event information from source documents.

    Preserves the raw format and content before normalization, providing data
    fidelity and traceability. Serves as the foundation for event processing
    and enables reprocessing with improved algorithms.
    """

    __tablename__ = "raw_events"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "deduplication_signature",
            name="uq_raw_events_source_sig",
        ),
        {"schema": SCHEMA_NAME},
    )

    deduplication_signature = Column(
        String(255),
        nullable=False,
        comment="Pre-computed signature for fast deduplication (e.g., SHA256 hash of content)",
    )

    original_description = Column(
        Text,
        nullable=False,
        comment="Original text description from source document before processing",
    )

    event_date_str = Column(
        String,
        nullable=False,
        comment="Original date string from source document before parsing",
    )

    date_info = Column(
        JSONB,
        nullable=True,
        comment="Original structured date information if provided by source, conforming to ParsedDateInfo schema",
    )

    source_document_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.source_documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="The source document this raw event was extracted from",
    )

    source_text_snippet = Column(
        Text,
        nullable=True,
        comment="Source text snippet providing context for the extracted event",
    )

    source_document = relationship(
        "SourceDocument",
        back_populates="raw_events",
        doc="The source document this raw event was extracted from",
    )

    event_association_links = relationship(
        "EventRawEventAssociation",
        back_populates="raw_event",
        cascade="all, delete-orphan",
        doc="Links to normalized events created from this raw event",
    )

    def __repr__(self):
        return (
            f"<RawEvent(id={self.id}, "
            f"source_document_id='{self.source_document_id}', "
            f"desc='{self.original_description[:30]}...')>"
        )
