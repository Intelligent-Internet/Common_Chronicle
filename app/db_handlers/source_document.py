from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db_handlers.base import BaseDBHandler, check_local_db
from app.db_handlers.entity import EntityDBHandler
from app.models.source_document import SourceDocument
from app.services.entity_service import AsyncEntityService
from app.utils.logger import setup_logger

logger = setup_logger("source_document_db_handler")


class SourceDocumentDBHandler(BaseDBHandler[SourceDocument]):
    def __init__(self):
        super().__init__(SourceDocument)

    @check_local_db
    async def get_or_create(
        self,
        article_data: dict[str, Any],
        log_prefix: str = "",
        *,
        db: AsyncSession = None,
    ) -> SourceDocument:
        """Get or create SourceDocument with associated Entity for Wikipedia sources."""
        title = article_data.get("title", "").strip()
        language = article_data.get("language", "").strip()
        source_type = article_data.get("source_name", "").strip()

        # 1. Build query to find existing source document
        query_data = {}
        if article_data.get("source_name"):
            query_data["source_type"] = article_data["source_name"]
        if title:
            query_data["title"] = title
        if article_data.get("source_url"):
            query_data["wikipedia_url"] = article_data["source_url"]
        if language:
            query_data["language"] = language
        if source_type:
            query_data["source_type"] = source_type

        if query_data:
            source_document = await self.get_by_attributes(db=db, **query_data)
            if source_document:
                logger.info(
                    f"{log_prefix}Found existing source document {source_document.id} for article '{title}'"
                )
                return source_document

        # 2. If not found, create it.
        logger.warning(
            f"{log_prefix}No source document found for article '{title}'({language}). Creating new one."
        )

        # 2a. Handle associated entity. Only Wikipedia sources should create entities.
        entity_id = None
        entity_db_handler = EntityDBHandler()

        # First try to find by source attributes (title, language)
        entity = await entity_db_handler.get_entity_by_source_attributes(
            title=title, language=language, db=db
        )

        if entity:
            entity_id = entity.id
            logger.info(f"{log_prefix}Found existing entity {entity_id} for '{title}'.")

            # Add check for existing source document by entity_id
            existing_sd_by_entity = await self.get_by_attributes(
                db=db, entity_id=entity_id
            )
            if existing_sd_by_entity:
                logger.info(
                    f"{log_prefix}Found existing source document {existing_sd_by_entity.id} via entity_id {entity_id}."
                )
                return existing_sd_by_entity
        else:
            source_url = article_data.get("source_url", "").lower()
            is_wikipedia_source = (
                "wikipedia.org" in source_url
                or "wikipedia" in article_data.get("source_name", "").lower()
            )

            if is_wikipedia_source:
                logger.warning(
                    f"{log_prefix}No entity found for '{title}'. Using EntityService to create entity with proper wikibase_item."
                )

                # Use EntityService to properly create entity with wikibase_item
                entity_service = AsyncEntityService()
                entity_requests = [(title, "UNKNOWN", language)]
                source_type = article_data.get("source_name", "wikipedia")

                try:
                    entity_responses = (
                        await entity_service.batch_get_or_create_entities(
                            entity_requests, source_type, db=db
                        )
                    )

                    if entity_responses and entity_responses[0].entity_id:
                        entity_id = entity_responses[0].entity_id
                        logger.info(
                            f"{log_prefix}Created new entity {entity_id} for '{title}' via EntityService."
                        )
                    else:
                        logger.warning(
                            f"{log_prefix}EntityService failed to create entity for '{title}': {entity_responses[0].message if entity_responses else 'No response'}"
                        )
                        # Continue without entity - create source document only

                except Exception as e:
                    logger.error(
                        f"{log_prefix}Error using EntityService to create entity for '{title}': {e}",
                        exc_info=True,
                    )
                    # Continue without entity - create source document only
            else:
                logger.info(
                    f"{log_prefix}Not creating entity for non-wikipedia source '{title}'."
                )

        # 2b. Create the source document
        text_content = article_data.get("text_content")
        create_data = {
            "processing_status": "pending",
            "source_type": source_type,
            "title": title,
            "wikipedia_url": article_data.get("source_url"),
            "language": language,
            "wiki_pageid": article_data.get("source_identifier"),
            "extract": text_content[:500] if text_content else None,
            "entity_id": entity_id,
        }

        new_source_document = await self.create(create_data, db=db)
        logger.info(
            f"{log_prefix}Created new source document {new_source_document.id} for article '{title}'."
        )

        return new_source_document
