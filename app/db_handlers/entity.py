from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db_handlers.base import BaseDBHandler, check_local_db
from app.models.entity import Entity
from app.models.source_document import SourceDocument
from app.utils.logger import setup_logger

logger = setup_logger(__name__, level="DEBUG")


class EntityDBHandler(BaseDBHandler[Entity]):
    def __init__(self):
        super().__init__(Entity)

    @check_local_db
    async def get_entity_by_source_attributes(
        self,
        title: str,
        language: str,
        *,
        db: AsyncSession = None,
    ) -> Entity:
        """Find entity by its associated source document title and language."""
        # Use SourceDocument as the query starting point to avoid circular imports
        # Create a temporary BaseDBHandler for SourceDocument
        source_doc_handler = BaseDBHandler(SourceDocument)
        source_doc = await source_doc_handler.get_by_attributes(
            title=title,
            language=language,
            options=[selectinload(SourceDocument.entity)],
            db=db,
        )

        # Return the associated entity if source document exists
        return source_doc.entity if source_doc else None

    @check_local_db
    async def get_entity_by_wikibase_item(
        self,
        wikibase_item: str,
        *,
        db: AsyncSession = None,
    ) -> Entity:
        """Find entity by its wikibase_item identifier."""
        return await self.get_by_attributes(
            wikibase_item=wikibase_item,
            options=[selectinload(Entity.source_documents)],
            db=db,
        )

    @check_local_db
    async def batch_get_entities_by_source_attributes(
        self,
        lookup_attrs: list[dict],
        *,
        db: AsyncSession = None,
    ) -> dict:
        """Batch find entities by their associated source document attributes."""
        if not lookup_attrs:
            return {}

        # Build OR conditions for all title/language pairs
        conditions = []
        for attrs in lookup_attrs:
            conditions.append(
                (SourceDocument.title == attrs["title"])
                & (SourceDocument.language == attrs["language"])
            )

        # Single JOIN query for efficiency in batch operations
        stmt = (
            select(Entity, SourceDocument.title, SourceDocument.language)
            .join(SourceDocument)
            .where(or_(*conditions))
        )

        result = await db.execute(stmt)
        found_map = {}

        for entity, title, language in result:
            found_map[(title, language)] = entity

        return found_map

    @check_local_db
    async def batch_get_or_create_verified_entities(
        self,
        entities_to_process: dict[int, dict[str, Any]],
        source_type: str,
        *,
        db: AsyncSession = None,
    ) -> dict[int, Entity]:
        """Batch process verified entities using wikibase_item as primary key."""
        results: dict[int, Entity] = {}
        if not entities_to_process:
            return results

        # Validate input: ensure all entities have wikibase_item
        for index, info in entities_to_process.items():
            if not info.get("wikibase_item"):
                raise ValueError(
                    f"Entity at index {index} missing required 'wikibase_item' field"
                )

        # --- Step 1: Group by wikibase_item to identify unique entities ---
        wikibase_to_indices = {}  # wikibase_item -> list of original indices
        for index, info in entities_to_process.items():
            wikibase_item = info["wikibase_item"]
            if wikibase_item not in wikibase_to_indices:
                wikibase_to_indices[wikibase_item] = []
            wikibase_to_indices[wikibase_item].append(index)

        # --- Step 2: Batch lookup existing entities by wikibase_item ---
        wikibase_items = list(wikibase_to_indices.keys())
        stmt = select(Entity).where(Entity.wikibase_item.in_(wikibase_items))
        result = await db.execute(stmt)
        existing_entities = {
            entity.wikibase_item: entity for entity in result.scalars()
        }

        # Map existing entities to all their associated indices
        for wikibase_item, indices in wikibase_to_indices.items():
            if wikibase_item in existing_entities:
                entity = existing_entities[wikibase_item]
                for index in indices:
                    results[index] = entity

        # --- Step 3: Create new entities for missing wikibase_items ---
        missing_wikibase_items = [
            wikibase_item
            for wikibase_item in wikibase_items
            if wikibase_item not in existing_entities
        ]

        if missing_wikibase_items:
            new_entities = {}
            for wikibase_item in missing_wikibase_items:
                # Use the first occurrence to determine entity attributes
                sample_index = wikibase_to_indices[wikibase_item][0]
                sample_info = entities_to_process[sample_index]

                logger.info(
                    f"Creating new entity for {wikibase_item} with attributes: {sample_info}"
                )

                entity = Entity(
                    entity_name=sample_info["title"],
                    entity_type=sample_info.get("entity_type", "unknown"),
                    wikibase_item=wikibase_item,
                    existence_verified=bool(sample_info.get("wikipedia_url")),
                )
                new_entities[wikibase_item] = entity

            # Batch insert new entities
            db.add_all(new_entities.values())
            await db.flush()  # Get IDs for new entities

            # Map new entities to all their associated indices
            for wikibase_item, indices in wikibase_to_indices.items():
                if wikibase_item in new_entities:
                    entity = new_entities[wikibase_item]
                    for index in indices:
                        results[index] = entity

        # --- Step 4: Create SourceDocuments for all input data ---
        # Identify all unique URLs from the input to check against the database
        urls_to_check = {
            info["wikipedia_url"]
            for info in entities_to_process.values()
            if info.get("wikipedia_url")
        }

        # Fetch all existing (url, source_type) pairs from the DB for the given URLs
        existing_docs_keys = set()
        if urls_to_check:
            stmt = select(
                SourceDocument.wikipedia_url, SourceDocument.source_type
            ).where(SourceDocument.wikipedia_url.in_(urls_to_check))
            result = await db.execute(stmt)
            existing_docs_keys = set(result)

        # Create SourceDocuments, avoiding duplicates using the (url, source_type) key
        source_docs_to_create = []
        processed_keys_in_batch = set()
        for index, info in entities_to_process.items():
            entity = results[index]
            wikipedia_url = info.get("wikipedia_url")

            if not wikipedia_url:
                continue

            # The unique key is the combination of wikipedia_url and source_type
            doc_key = (wikipedia_url, source_type)

            # Skip if this key already exists in the DB or has been processed in this batch
            if doc_key in existing_docs_keys:
                continue
            if doc_key in processed_keys_in_batch:
                continue

            source_docs_to_create.append(
                SourceDocument(
                    title=info["title"],
                    language=info.get("language", "en"),
                    wikipedia_url=wikipedia_url,
                    wikibase_item=info.get("wikibase_item"),
                    wiki_pageid=(
                        str(info["wiki_pageid"]) if info.get("wiki_pageid") else None
                    ),
                    extract=info.get("extract"),
                    source_type=source_type,
                    processing_status="pending",
                    entity_id=entity.id,  # Associate with the correct entity
                )
            )
            processed_keys_in_batch.add(doc_key)

        if source_docs_to_create:
            db.add_all(source_docs_to_create)

        await db.flush()

        return results

    @check_local_db
    async def batch_get_entities_by_wikibase_items(
        self,
        wikibase_items: list[str],
        *,
        db: AsyncSession = None,
    ) -> dict[str, Entity]:
        """Batch find entities by their wikibase_item identifiers."""
        if not wikibase_items:
            return {}

        stmt = (
            select(Entity)
            .where(Entity.wikibase_item.in_(wikibase_items))
            .options(selectinload(Entity.source_documents))
        )

        result = await db.execute(stmt)
        return {entity.wikibase_item: entity for entity in result.scalars()}
