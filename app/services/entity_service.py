# Entity service for managing canonical entities with Wikipedia verification


from sqlalchemy.ext.asyncio import AsyncSession

from app.db_handlers import EntityDBHandler, check_local_db
from app.schemas import EntityServiceResponse
from app.services.wiki_extractor import get_wiki_page_info
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AsyncEntityService:
    # Batch processing with Wikipedia verification and canonical identifier management

    def __init__(self):
        self.db_handler = EntityDBHandler()

    # TODO: Add internal batch processing limit; if exceeded, process in batches.
    @check_local_db
    async def batch_get_or_create_entities(
        self,
        entity_requests: list[tuple[str, str, str]],  # (name, entity_type, language)
        source_type: str,
        *,
        db: AsyncSession = None,
    ) -> list[EntityServiceResponse]:
        # Batch processing: DB lookup → Wikipedia verification → entity creation
        # Maintains request order and handles partial failures gracefully
        if not entity_requests:
            return []

        logger.info(
            f"[ENTITY_SERVICE] Starting batch processing of {len(entity_requests)} entities"
        )

        # Keep track of original request order and data
        requests_map = {
            i: {"name": name, "entity_type": entity_type, "language": language}
            for i, (name, entity_type, language) in enumerate(entity_requests)
        }
        results = [None] * len(entity_requests)

        # --- Step 1: Fast Batch DB Read-Only Check by (title, language) ---
        still_to_process_indices = list(requests_map.keys())
        try:
            # Prepare lookup attributes for batch query
            lookup_attrs = [
                {
                    "title": requests_map[i]["name"],
                    "language": requests_map[i]["language"],
                }
                for i in still_to_process_indices
            ]

            found_map = await self.db_handler.batch_get_entities_by_source_attributes(
                lookup_attrs, db=db
            )

            remaining_indices = []
            updated_entities = []
            for i in still_to_process_indices:
                req_data = requests_map[i]
                key = (req_data["name"], req_data["language"])
                if key in found_map:
                    entity = found_map[key]

                    # Check if we need to update the entity type
                    new_entity_type = req_data["entity_type"]
                    if (
                        entity.entity_type.upper() == "UNKNOWN"
                        and new_entity_type.upper() != "UNKNOWN"
                        and new_entity_type.upper() != entity.entity_type.upper()
                    ):
                        logger.info(
                            f"[ENTITY_SERVICE] Updating entity {entity.wikibase_item} type from '{entity.entity_type}' to '{new_entity_type}'"
                        )
                        entity.entity_type = new_entity_type
                        updated_entities.append(entity)

                    results[i] = EntityServiceResponse(
                        entity_id=entity.id,
                        message=f"Found existing entity by '{req_data['name']}({req_data['language']})'.",
                        status_code=200,
                        is_verified_existent=True,
                    )
                else:
                    remaining_indices.append(i)

            # Flush updates if any entities were modified
            if updated_entities:
                await db.flush()
                logger.info(
                    f"[ENTITY_SERVICE] Updated {len(updated_entities)} entity types from UNKNOWN to more specific types"
                )
            still_to_process_indices = remaining_indices
        except Exception as e:
            logger.error(
                f"[ENTITY_SERVICE] Error in initial batch DB lookup: {e}", exc_info=True
            )
            # If this fails, we'll just try to process all of them via network.

        if not still_to_process_indices:
            return results

        logger.info(
            f"[ENTITY_SERVICE] {len(still_to_process_indices)} entities not found in DB, proceeding to network lookup."
        )

        # --- Step 2: Sequential Network Calls ---
        network_results = []
        for i in still_to_process_indices:
            req_data = requests_map[i]
            try:
                wiki_info = await get_wiki_page_info(
                    req_data["name"], req_data["language"]
                )
                network_results.append((i, wiki_info))
                logger.debug(
                    f"[ENTITY_SERVICE] Completed network call for '{req_data['name']}' ({req_data['language']})"
                )
            except Exception as e:
                logger.warning(
                    f"[ENTITY_SERVICE] MediaWiki API call for '{req_data['name']}' failed: {e}",
                    exc_info=True,
                )
                network_results.append((i, None))

        # --- Step 3: Process Network Results and Prepare for DB Write ---
        to_recheck_entities_info = {}  # index -> entity_dict

        for index, wiki_info in network_results:
            req_data = requests_map[index]
            if wiki_info and wiki_info.exists and not wiki_info.is_disambiguation:
                # Ensure wikibase_item exists - required for new architecture
                if not wiki_info.wikibase_item:
                    logger.warning(
                        f"[ENTITY_SERVICE] Skipping entity '{req_data['name']}' - no wikibase_item found"
                    )
                    results[index] = EntityServiceResponse(
                        entity_id=None,
                        message=f"Entity '{req_data['name']}' found but lacks required wikibase_item identifier.",
                        status_code=202,
                        is_verified_existent=False,
                    )
                    continue

                entity_dict = {
                    "title": wiki_info.title,
                    "language": req_data["language"],
                    "wikipedia_url": wiki_info.fullurl,
                    "wikibase_item": wiki_info.wikibase_item,
                    "wiki_pageid": wiki_info.pageid,
                    "entity_type": req_data["entity_type"],
                    "extract": wiki_info.extract,
                }
                to_recheck_entities_info[index] = entity_dict
            elif wiki_info and wiki_info.is_disambiguation:
                results[index] = EntityServiceResponse(
                    entity_id=None,
                    message=f"Disambiguation page found for '{req_data['name']}'.",
                    disambiguation_options=wiki_info.disambiguation_options,
                    status_code=300,
                    is_verified_existent=False,
                )
            else:
                if results[index] is None:
                    results[index] = EntityServiceResponse(
                        entity_id=None,
                        message=f"Could not verify entity '{req_data['name']}' via network.",
                        status_code=201,
                        is_verified_existent=False,
                    )

        if not to_recheck_entities_info:
            return [res for res in results if res is not None]

        # --- Step 4: Batch Re-check DB and Batch Create ---
        # The db_handler method is now more robust and handles transactions internally.
        # We let it raise exceptions on critical DB failures.
        processed_entities_map = (
            await self.db_handler.batch_get_or_create_verified_entities(
                to_recheck_entities_info, source_type, db=db
            )
        )

        # Map the results back to the original request indices
        for index, entity in processed_entities_map.items():
            req_data = requests_map[index]
            results[index] = EntityServiceResponse(
                entity_id=entity.id,
                message=f"Found or created verified entity for '{req_data['name']}({req_data['language']})'.",
                status_code=200,
                is_verified_existent=True,
            )

        # Fill any remaining None results with a generic error
        for i in range(len(results)):
            if results[i] is None:
                req_data = requests_map[i]
                results[i] = EntityServiceResponse(
                    entity_id=None,
                    message=f"ERROR_PROCESSING: An unknown error occurred for '{req_data['name']}'.",
                    status_code=500,
                    is_verified_existent=None,
                )

        return results
