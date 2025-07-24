"""
Embedding-based Event Merger Service - High-performance event deduplication
using semantic embeddings with optional LLM fallback for edge cases.

This service integrates with the existing EventMergerService architecture while
providing significant performance improvements through embedding-based similarity.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import TYPE_CHECKING

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

if TYPE_CHECKING:
    from app.services.process_callback import ProgressCallback

from datetime import UTC

from app.config import settings
from app.models import Event
from app.schemas import (
    CanonicalEventData,
    EventDataForMerger,
    MergedEventGroupOutput,
    ParsedDateInfo,
    RepresentativeEventInfo,
    SourceContributionInfo,
    SourceInfoForMerger,
)
from app.services.embedding_service import embedding_service
from app.services.event_merger_service import LLMComparisonCache, RawEventInput
from app.utils.logger import setup_logger

logger = setup_logger("embedding_event_merger", level="DEBUG")


class EmbeddingCache:
    """
    LRU cache for event embeddings to avoid recomputation
    """

    def __init__(self, max_size: int = 10000):
        self.cache: dict[str, np.ndarray] = {}
        self.access_order: list[str] = []
        self.max_size = max_size

    def get(self, key: str) -> np.ndarray | None:
        """Get embedding from cache and update access order"""
        if key in self.cache:
            # Move to end (most recently used)
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None

    def set(self, key: str, embedding: np.ndarray):
        """Store embedding in cache with LRU eviction"""
        if key in self.cache:
            # Update existing
            self.cache[key] = embedding
            self.access_order.remove(key)
            self.access_order.append(key)
        else:
            # Add new
            if len(self.cache) >= self.max_size:
                # Evict least recently used
                oldest_key = self.access_order.pop(0)
                del self.cache[oldest_key]

            self.cache[key] = embedding
            self.access_order.append(key)

    def size(self) -> int:
        return len(self.cache)


class EmbeddingEventMerger:
    """
    High-performance event merger using embedding-based similarity
    with optional hybrid LLM fallback for uncertain cases.
    """

    def __init__(self, user_lang: str = None):
        self.user_lang = user_lang
        self.embedding_cache = EmbeddingCache(
            settings.event_merger_embedding_cache_size
        )
        self.llm_cache = LLMComparisonCache()

        # Performance statistics
        self._stats = {
            "total_events": 0,
            "embedding_cache_hits": 0,
            "embedding_cache_misses": 0,
            "embedding_computations": 0,
            "similarity_computations": 0,
            "llm_calls_made": 0,
            "llm_calls_saved": 0,
            "rule_based_merges": 0,
            "embedding_based_merges": 0,
            "hybrid_uncertain_pairs": 0,
        }

        logger.info(
            f"Initialized EmbeddingEventMerger with unified embedding service, hybrid_mode={settings.event_merger_hybrid_mode}"
        )

    # === Data Conversion Layer ===

    def _convert_raw_to_canonical(self, raw_event: RawEventInput) -> CanonicalEventData:
        entities_list = []

        if raw_event.event_data.main_entities:
            for entity in raw_event.event_data.main_entities:
                name = (
                    entity.get("original_name", "")
                    if isinstance(entity, dict)
                    else getattr(entity, "original_name", "")
                )
                entity_type = (
                    entity.get("entity_type", "")
                    if isinstance(entity, dict)
                    else getattr(entity, "entity_type", "")
                )

                if name.strip():
                    entities_list.append(
                        {
                            "name": name.strip(),
                            "type": entity_type.strip() if entity_type else "",
                        }
                    )

        return CanonicalEventData(
            description=raw_event.event_data.description or "",
            event_date_str=raw_event.event_data.event_date_str or "",
            entities=entities_list,
            source_snippet=raw_event.event_data.source_text_snippet,
        )

    def _convert_db_event_to_canonical(self, event: Event) -> CanonicalEventData:
        entities_list = []

        if hasattr(event, "entity_associations") and event.entity_associations:
            for assoc in event.entity_associations:
                if hasattr(assoc, "entity") and assoc.entity:
                    entity_name = getattr(assoc.entity, "entity_name", "")
                    entity_type = getattr(assoc.entity, "entity_type", "")

                    if entity_name.strip():
                        entities_list.append(
                            {
                                "name": entity_name.strip(),
                                "type": entity_type.strip() if entity_type else "",
                            }
                        )

        source_snippet = None
        if (
            hasattr(event, "raw_event_association_links")
            and event.raw_event_association_links
        ):
            first_raw_event = event.raw_event_association_links[0].raw_event
            if first_raw_event and hasattr(first_raw_event, "source_text_snippet"):
                source_snippet = first_raw_event.source_text_snippet

        return CanonicalEventData(
            description=event.description or "",
            event_date_str=event.event_date_str or "",
            entities=entities_list,
            source_snippet=source_snippet,
        )

    def _convert_event_to_raw_event_input(self, event: Event) -> RawEventInput:
        date_info_model = None
        if event.date_info and isinstance(event.date_info, dict):
            try:
                date_info_model = ParsedDateInfo(**event.date_info)
            except Exception as e:
                logger.warning(f"Failed to parse date_info for event {event.id}: {e}")

        source_snippet = None
        if (
            hasattr(event, "raw_event_association_links")
            and event.raw_event_association_links
        ):
            first_raw_event = event.raw_event_association_links[0].raw_event
            if first_raw_event and hasattr(first_raw_event, "source_text_snippet"):
                source_snippet = first_raw_event.source_text_snippet

        main_entities_list = []
        if hasattr(event, "entity_associations") and event.entity_associations:
            for assoc in event.entity_associations:
                entity_dict = {"entity_id": str(assoc.entity_id)}
                if hasattr(assoc, "entity") and assoc.entity:
                    entity_obj = assoc.entity
                    entity_dict.update(
                        {
                            "original_name": getattr(entity_obj, "entity_name", None),
                            "entity_type": getattr(entity_obj, "entity_type", None),
                        }
                    )
                main_entities_list.append(entity_dict)

        event_data = EventDataForMerger(
            id=str(event.id),
            description=event.description,
            event_date_str=event.event_date_str,
            date_info=date_info_model,
            main_entities=main_entities_list,
            source_text_snippet=source_snippet,
        )

        source_info = SourceInfoForMerger(
            language="en",
        )

        return RawEventInput(event_data=event_data, source_info=source_info)

    # === Core Embedding Layer===

    def _compute_embedding_from_canonical(
        self, canonical_data: CanonicalEventData
    ) -> np.ndarray:
        event_text = canonical_data.to_embedding_text()
        cache_key = hashlib.sha256(event_text.encode("utf-8")).hexdigest()
        # Try cache first
        cached_embedding = self.embedding_cache.get(cache_key)
        if cached_embedding is not None:
            self._stats["embedding_cache_hits"] += 1
            return cached_embedding

        # Compute embedding
        self._stats["embedding_cache_misses"] += 1
        self._stats["embedding_computations"] += 1

        try:
            embedding = embedding_service.encode(
                event_text,
                convert_to_numpy=True,
                normalize_embeddings=True,
                add_query_prefix=True,
            )

            # Store in cache
            self.embedding_cache.set(cache_key, embedding)

            logger.debug(f"Computed embedding for text: {event_text[:100]}...")
            return embedding

        except Exception as e:
            logger.error(f"Failed to compute embedding: {e}", exc_info=True)
            return np.zeros(768)

    def get_embedding_for_raw_event(self, raw_event: RawEventInput) -> np.ndarray:
        canonical_data = self._convert_raw_to_canonical(raw_event)
        return self._compute_embedding_from_canonical(canonical_data)

    def _get_embedding_for_db_event(self, event: Event) -> np.ndarray:
        """
        [Internal method] Get embedding for database Event (service stage two).

        All Events in the database must contain a valid description_vector field.

        Args:
            event: Database event object

        Returns:
            np.ndarray: 768-dimensional embedding vector

        Raises:
            ValueError: If Event is missing or contains invalid description_vector
        """
        # Events in database must contain description_vector
        if (
            not hasattr(event, "description_vector")
            or event.description_vector is None
            or len(event.description_vector) == 0
            or len(event.description_vector) != 768
        ):
            raise ValueError(f"Event {event.id} missing or invalid description_vector")

        # Use vector directly from database
        try:
            embedding = np.array(event.description_vector, dtype=np.float32)

            # Validate vector validity
            if embedding.shape != (768,) or np.isnan(embedding).any():
                raise ValueError(
                    f"Event {event.id} has invalid description_vector data"
                )

            self._stats["embedding_cache_hits"] += 1  # Count as cache hit
            logger.debug(f"Retrieved embedding from database for event {event.id}")
            return embedding

        except Exception as e:
            raise ValueError(
                f"Failed to load description_vector for event {event.id}: {e}"
            ) from e

    def _compute_similarity_matrix(self, events: list[Event]) -> np.ndarray:
        """
        Compute event similarity matrix.

        Directly uses description_vector from database to compute similarity matrix.

        Args:
            events: List of event objects

        Returns:
            np.ndarray: Similarity matrix
        """
        logger.info(f"Computing similarity matrix for {len(events)} events")

        # Get embedding vectors for all events
        embeddings = []
        for event in events:
            embedding = self._get_embedding_for_db_event(event)
            embeddings.append(embedding)

        # Convert to matrix for efficient computation
        embeddings_matrix = np.vstack(embeddings)

        # Compute cosine similarity matrix
        logger.info("Computing cosine similarity matrix...")
        self._stats["similarity_computations"] += 1
        similarity_matrix = cosine_similarity(embeddings_matrix)

        return similarity_matrix

    def _find_embedding_groups(
        self, events: list[Event], similarity_matrix: np.ndarray
    ) -> list[list[int]]:
        """
        Find event groups that should be merged based on embedding similarity.

        Args:
            events: List of event objects
            similarity_matrix: Similarity matrix

        Returns:
            list[list[int]]: List of event group indices
        """
        n_events = len(events)
        visited = [False] * n_events
        groups = []
        threshold = settings.event_merger_embedding_similarity_threshold

        for i in range(n_events):
            if visited[i]:
                continue

            # Start a new group
            current_group = [i]
            visited[i] = True

            # Find all events similar to this event
            for j in range(i + 1, n_events):
                if not visited[j] and similarity_matrix[i][j] >= threshold:
                    current_group.append(j)
                    visited[j] = True
                    logger.debug(
                        f"Grouped events {events[i].id} and {events[j].id} "
                        f"(similarity: {similarity_matrix[i][j]:.3f})"
                    )

            groups.append(current_group)

            if len(current_group) > 1:
                self._stats["embedding_based_merges"] += len(current_group) - 1

        return groups

    async def _hybrid_llm_verification(
        self, events: list[Event], similarity_matrix: np.ndarray
    ) -> list[list[int]]:
        """
        Hybrid approach: Use embeddings for batch grouping + LLM for uncertain cases.

        Args:
            events: List of event objects
            similarity_matrix: Similarity matrix

        Returns:
            list[list[int]]: List of event group indices
        """
        n_events = len(events)
        visited = [False] * n_events
        groups = []
        uncertain_pairs = []

        embedding_threshold = settings.event_merger_embedding_similarity_threshold
        llm_threshold = settings.event_merger_hybrid_llm_threshold

        # Stage 1: Group based on high-confidence embedding similarity
        for i in range(n_events):
            if visited[i]:
                continue

            current_group = [i]
            visited[i] = True

            for j in range(i + 1, n_events):
                if visited[j]:
                    continue

                similarity = similarity_matrix[i][j]

                if similarity >= llm_threshold:
                    # High confidence - merge directly
                    current_group.append(j)
                    visited[j] = True
                    logger.debug(
                        f"High-confidence merge: {similarity:.3f} >= {llm_threshold}"
                    )
                elif similarity >= embedding_threshold:
                    # Uncertain - requires LLM verification
                    uncertain_pairs.append((i, j, similarity))
                    logger.debug(f"Uncertain pair for LLM: {similarity:.3f}")

            groups.append(current_group)

        # Stage 2: LLM verification for uncertain pairs
        if uncertain_pairs:
            self._stats["hybrid_uncertain_pairs"] = len(uncertain_pairs)
            logger.info(
                f"Using LLM verification for {len(uncertain_pairs)} uncertain pairs"
            )

            # Use LLM to process uncertain pairs
            llm_verified_pairs = await self._verify_pairs_with_llm(
                events, uncertain_pairs
            )

            # Merge groups based on LLM verification results
            groups = self._merge_groups_with_llm_results(groups, llm_verified_pairs)

        return groups

    async def _verify_pairs_with_llm(
        self,
        events: list[Event],
        uncertain_pairs: list[tuple[int, int, float]],
    ) -> list[tuple[int, int, bool]]:
        """
        Use LLM to verify uncertain event pairs.

        Args:
            events: List of event objects
            uncertain_pairs: List of uncertain pairs (idx1, idx2, similarity)

        Returns:
            list[tuple[int, int, bool]]: LLM verification results (idx1, idx2, should_merge)
        """
        from app.services.event_merger_service import MergedEventGroup

        llm_results = []

        # 创建并发LLM任务（受并发窗口大小限制）
        window_size = settings.event_merger_concurrent_window_size

        for i in range(0, len(uncertain_pairs), window_size):
            window_pairs = uncertain_pairs[i : i + window_size]

            # 为此窗口创建LLM验证任务
            tasks = []
            for idx1, idx2, similarity in window_pairs:
                # 将Event转换为RawEventInput以兼容现有的MergedEventGroup
                raw_event1 = self._convert_event_to_raw_event_input(events[idx1])
                raw_event2 = self._convert_event_to_raw_event_input(events[idx2])

                # 创建临时组进行LLM比较
                group1 = MergedEventGroup(raw_event1)
                task = asyncio.create_task(
                    group1.llm_semantic_match(raw_event2, self.llm_cache)
                )
                tasks.append((task, idx1, idx2, similarity))

            # Execute window concurrently
            try:
                await asyncio.gather(
                    *[task for task, _, _, _ in tasks], return_exceptions=True
                )

                # Process results
                for task, idx1, idx2, similarity in tasks:
                    try:
                        if task.done() and not task.exception():
                            llm_result = task.result()
                            llm_results.append((idx1, idx2, llm_result))
                            self._stats["llm_calls_made"] += 1

                            if llm_result:
                                logger.debug(
                                    f"LLM confirmed merge for events {idx1}, {idx2} (similarity: {similarity:.3f})"
                                )
                            else:
                                logger.debug(
                                    f"LLM rejected merge for events {idx1}, {idx2} (similarity: {similarity:.3f})"
                                )
                        else:
                            logger.warning(
                                f"LLM verification failed for events {idx1}, {idx2}"
                            )
                            llm_results.append((idx1, idx2, False))
                    except Exception as e:
                        logger.error(
                            f"Error processing LLM result for events {idx1}, {idx2}: {e}",
                            exc_info=True,
                        )
                        llm_results.append((idx1, idx2, False))

            except Exception as e:
                logger.error(
                    f"Error in concurrent LLM verification: {e}", exc_info=True
                )
                # Fallback: assume no matches for this window
                for _, idx1, idx2, _ in tasks:
                    llm_results.append((idx1, idx2, False))

        return llm_results

    def _merge_groups_with_llm_results(
        self, groups: list[list[int]], llm_results: list[tuple[int, int, bool]]
    ) -> list[list[int]]:
        """
        Merge groups based on LLM verification results
        """
        # Create a mapping from event index to group index
        event_to_group = {}
        for group_idx, group in enumerate(groups):
            for event_idx in group:
                event_to_group[event_idx] = group_idx

        # Process LLM results and merge groups
        for idx1, idx2, should_merge in llm_results:
            if should_merge:
                group1_idx = event_to_group[idx1]
                group2_idx = event_to_group[idx2]

                if group1_idx != group2_idx:
                    # Merge group2 into group1
                    groups[group1_idx].extend(groups[group2_idx])

                    # Update mappings for all events in group2
                    for event_idx in groups[group2_idx]:
                        event_to_group[event_idx] = group1_idx

                    # Clear group2
                    groups[group2_idx] = []

        # Remove empty groups
        groups = [group for group in groups if group]

        return groups

    def _select_representative_event(
        self,
        group_events: list[Event],
        group_indices: list[int],
        similarity_matrix: np.ndarray,
    ) -> Event:
        """
        Select the most representative event from the group.

        Args:
            group_events: List of events in the group
            group_indices: List of event indices in the group
            similarity_matrix: Similarity matrix

        Returns:
            Event: The most representative event
        """
        if len(group_events) == 1:
            return group_events[0]

        # Find the event with highest average similarity to other events in the group
        best_event = group_events[0]
        best_score = 0

        for i, event in enumerate(group_events):
            if len(group_indices) > 1:
                # Calculate average similarity with other events in the group
                similarities = [
                    similarity_matrix[group_indices[i]][group_indices[j]]
                    for j in range(len(group_indices))
                    if i != j
                ]
                avg_similarity = np.mean(similarities) if similarities else 0
            else:
                avg_similarity = 1.0

            # Consider other factors like description completeness
            score = avg_similarity

            # Description completeness bonus
            if event.description:
                score += min(len(event.description) / 1000, 0.1)

            # Bonus for more entity associations
            if hasattr(event, "entity_associations") and event.entity_associations:
                score += min(len(event.entity_associations) / 10, 0.05)

            if score > best_score:
                best_score = score
                best_event = event

        return best_event

    def _create_merged_group_output(
        self, group_events: list[Event], representative_event: Event
    ) -> MergedEventGroupOutput:
        """
        Create output format for merged group.

        Args:
            group_events: List of events in the group
            representative_event: Representative event

        Returns:
            MergedEventGroupOutput: Merged group output object
        """
        # Create entity information for representative event
        main_entities_for_output = []
        if (
            hasattr(representative_event, "entity_associations")
            and representative_event.entity_associations
        ):
            for assoc in representative_event.entity_associations:
                if hasattr(assoc, "entity") and assoc.entity:
                    main_entities_for_output.append(
                        {
                            "entity_id": str(assoc.entity_id),
                            "original_name": getattr(assoc.entity, "entity_name", None),
                            "entity_type": getattr(assoc.entity, "entity_type", None),
                        }
                    )

        # Create timestamp from date information
        timestamp_for_db = None
        if representative_event.date_info and isinstance(
            representative_event.date_info, dict
        ):
            try:
                date_info_obj = ParsedDateInfo(**representative_event.date_info)
                date_range = date_info_obj.to_date_range()
                if date_range and date_range.start_date:
                    from datetime import datetime
                    from datetime import time as dt_time

                    timestamp_for_db = datetime.combine(
                        date_range.start_date,
                        dt_time.min,
                        tzinfo=UTC,
                    )
            except Exception as e:
                logger.warning(f"Failed to create timestamp from date_info: {e}")

        # Get source text snippet and URL information
        source_text_snippet = None
        source_url = None
        source_page_title = None
        source_language = None

        if (
            hasattr(representative_event, "raw_event_association_links")
            and representative_event.raw_event_association_links
        ):
            first_raw_event = representative_event.raw_event_association_links[
                0
            ].raw_event
            if first_raw_event:
                source_text_snippet = getattr(
                    first_raw_event, "source_text_snippet", None
                )
                source_url = getattr(first_raw_event, "page_url", None)
                source_page_title = getattr(first_raw_event, "page_title", None)
                source_language = getattr(first_raw_event, "language", None)

        representative_event_info = RepresentativeEventInfo(
            event_date_str=representative_event.event_date_str,
            description=representative_event.description,
            main_entities=main_entities_for_output,
            date_info=representative_event.date_info,
            timestamp=timestamp_for_db,
            source_text_snippet=source_text_snippet,
            source_url=source_url,
            source_page_title=source_page_title,
            source_language=source_language,
        )

        # Create source contribution information
        source_contributions = []
        for event in group_events:
            # Convert Event to format required by SourceContributionInfo
            raw_event_input = self._convert_event_to_raw_event_input(event)
            source_contributions.append(
                SourceContributionInfo(
                    event_data=raw_event_input.event_data,
                    source_info=raw_event_input.source_info,
                )
            )

        return MergedEventGroupOutput(
            representative_event=representative_event_info,
            source_contributions=source_contributions,
            original_id=str(representative_event.id),  # Use Event's ID
        )

    def _reset_stats(self):
        """Reset performance statistics"""
        for key in self._stats:
            self._stats[key] = 0

    # === Batch Merging Layer ===

    async def get_merge_instructions(
        self,
        events: list[Event],
        progress_callback: ProgressCallback | None = None,
        request_id: str = None,
    ) -> list[MergedEventGroupOutput]:
        """
        [Public interface] Main entry point for stage two batch merging.

        High-performance embedding-based event merging that directly processes Event object lists.

        Args:
            events: List of event objects
            progress_callback: Progress callback function
            request_id: Request ID

        Returns:
            list[MergedEventGroupOutput]: List of merged event groups
        """
        self._reset_stats()
        start_time = time.time()

        if not events:
            return []

        self._stats["total_events"] = len(events)

        logger.info(f"Starting embedding-based merge for {len(events)} events")

        if progress_callback:
            await progress_callback.report(
                f"Starting embedding-based event merging for {len(events)} events...",
                "embedding_merging_start",
                {"total_events": len(events)},
                request_id,
            )

        # Compute similarity matrix
        if progress_callback:
            await progress_callback.report(
                "Computing event embeddings and similarities...",
                "embedding_computation",
                {"events_processed": 0, "total_events": len(events)},
                request_id,
            )

        # Directly use description_vector from database to compute similarity matrix
        logger.info("Computing similarity matrix using database embeddings")
        similarity_matrix = self._compute_similarity_matrix(events)

        # Find groups based on method
        if settings.event_merger_hybrid_mode:
            logger.info("Using hybrid embedding + LLM approach")
            groups = await self._hybrid_llm_verification(events, similarity_matrix)
        else:
            logger.info("Using pure embedding approach")
            groups = self._find_embedding_groups(events, similarity_matrix)

        logger.info(f"Found {len(groups)} groups from {len(events)} events")

        # Create output format
        if progress_callback:
            await progress_callback.report(
                "Creating merged groups...",
                "group_creation",
                {"groups_found": len(groups)},
                request_id,
            )

        result_groups = []
        for group_indices in groups:
            # Use Event objects directly
            group_events = [events[i] for i in group_indices]
            representative_event = self._select_representative_event(
                group_events, group_indices, similarity_matrix
            )

            merged_group = self._create_merged_group_output(
                group_events, representative_event
            )
            result_groups.append(merged_group)

        # Sort by timestamp
        def get_sortable_timestamp(group):
            timestamp = group.representative_event.timestamp
            if timestamp:
                return timestamp
            from datetime import datetime

            return datetime.min.replace(tzinfo=UTC)

        result_groups.sort(key=get_sortable_timestamp)

        duration = time.time() - start_time

        # Log performance statistics
        logger.info(f"Embedding-based merge completed in {duration:.2f} seconds")
        logger.info(f"Performance: {len(events)/duration:.1f} events/second")
        logger.info(
            f"Cache efficiency: {self._stats['embedding_cache_hits']}/{self._stats['embedding_cache_hits'] + self._stats['embedding_cache_misses']} hits"
        )
        logger.info(
            f"LLM calls: {self._stats['llm_calls_made']} made, {self._stats['llm_calls_saved']} saved"
        )
        logger.info(
            f"Merges: {self._stats['rule_based_merges']} rule-based, {self._stats['embedding_based_merges']} embedding-based"
        )

        if progress_callback:
            await progress_callback.report(
                f"Embedding-based merging completed: {len(result_groups)} distinct events found",
                "embedding_merging_complete",
                {
                    "total_events": len(events),
                    "distinct_events": len(result_groups),
                    "duration_seconds": duration,
                    "performance_stats": self._stats,
                },
                request_id,
            )

        return result_groups
