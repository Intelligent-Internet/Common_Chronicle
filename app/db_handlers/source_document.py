from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
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
        source_url = article_data.get("source_url", "")

        # 1. Query for existing source document using the unique constraint
        # URLs are now normalized at the data acquisition layer, so we can use them directly
        source_document = None

        # For Wikipedia sources, query by URL and source_type (the unique constraint)
        if source_url and source_type:
            source_document = await self.get_by_attributes(
                wikipedia_url=source_url, source_type=source_type, db=db
            )

            if source_document:
                logger.info(
                    f"{log_prefix}Found existing source document {source_document.id} by URL '{source_url}'"
                )
                return source_document

        # Additional fallback query by title and language
        if not source_document and title and language:
            source_document = await self.get_by_attributes(
                title=title, language=language, source_type=source_type, db=db
            )
            if source_document:
                logger.info(
                    f"{log_prefix}Found existing source document {source_document.id} by title/language '{title}'/'{language}'"
                )
                return source_document

        # 2. If not found, create it.
        logger.info(
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

            # Check for existing source document by entity_id
            existing_sd_by_entity = await self.get_by_attributes(
                db=db, entity_id=entity_id
            )
            if existing_sd_by_entity:
                logger.info(
                    f"{log_prefix}Found existing source document {existing_sd_by_entity.id} via entity_id {entity_id}."
                )
                return existing_sd_by_entity
        else:
            # Check if this is a Wikipedia source that should create entities
            is_wikipedia_source_flag = (
                "wikipedia.org" in source_url.lower()
                or "wikipedia" in source_type.lower()
            )

            if is_wikipedia_source_flag:
                logger.info(
                    f"{log_prefix}No entity found for '{title}'. Using EntityService to create entity with proper wikibase_item."
                )

                # Use EntityService to properly create entity with wikibase_item
                entity_service = AsyncEntityService()
                entity_requests = [(title, "UNKNOWN", language)]
                source_type_for_entity = source_type or "online_wikipedia"

                try:
                    entity_responses = (
                        await entity_service.batch_get_or_create_entities(
                            entity_requests, source_type_for_entity, db=db
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

        # 2b. Final check before creation - race condition protection
        if source_url and source_type:
            final_check = await self.get_by_attributes(
                wikipedia_url=source_url, source_type=source_type, db=db
            )
            if final_check:
                logger.info(
                    f"{log_prefix}Document created by another process during entity creation: {final_check.id}"
                )
                return final_check

        # 2c. Create the source document
        text_content = article_data.get("text_content")
        create_data = {
            "processing_status": "pending",
            "source_type": source_type,
            "title": title,
            "wikipedia_url": source_url,
            "language": language,
            "wiki_pageid": article_data.get("source_identifier"),
            "extract": text_content[:500] if text_content else None,
            "entity_id": entity_id,
        }

        try:
            new_source_document = await self.create(create_data, db=db)
            logger.info(
                f"{log_prefix}Created new source document {new_source_document.id} for article '{title}'."
            )
            return new_source_document
        except IntegrityError as e:
            # Handle the case where another process created the same document concurrently
            logger.warning(
                f"{log_prefix}IntegrityError when creating source document for '{title}'. "
                f"Attempting to fetch existing document. Error: {e}"
            )

            # Rollback the current transaction to clean state
            await db.rollback()

            # Try multiple query strategies to find the existing document
            existing_doc = None

            # Strategy 1: Query by unique constraint (URL + source_type)
            if source_url and source_type:
                existing_doc = await self.get_by_attributes(
                    wikipedia_url=source_url, source_type=source_type, db=db
                )

            # Strategy 2: Query by title + language + source_type
            if not existing_doc and title and language:
                existing_doc = await self.get_by_attributes(
                    title=title, language=language, source_type=source_type, db=db
                )

            # Strategy 3: Query by entity_id if we have one
            if not existing_doc and entity_id:
                existing_doc = await self.get_by_attributes(entity_id=entity_id, db=db)

            if existing_doc:
                logger.info(
                    f"{log_prefix}Found existing source document {existing_doc.id} after IntegrityError"
                )
                return existing_doc

            # If we still can't find it, re-raise the error
            logger.error(
                f"{log_prefix}Could not resolve IntegrityError for source document '{title}'. Re-raising."
            )
            raise
