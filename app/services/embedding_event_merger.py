"""
Embedding-based Event Merger Service - High-performance event deduplication
using semantic embeddings with optional LLM fallback for edge cases.

This service integrates with the existing EventMergerService architecture while
providing significant performance improvements through embedding-based similarity.
"""

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
    EventDataForMerger,
    MergedEventGroupOutput,
    ParsedDateInfo,
    RepresentativeEventInfo,
    SourceContributionInfo,
    SourceInfoForMerger,
)
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

        # Lazy initialization of embedding model
        self._embedding_model = None

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
            f"Initialized EmbeddingEventMerger with hybrid_mode={settings.event_merger_hybrid_mode}"
        )

    @property
    def embedding_model(self):
        """Lazy initialization of SentenceTransformer model"""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info(
                    f"Loading embedding model: {settings.event_merger_embedding_model}"
                )
                self._embedding_model = SentenceTransformer(
                    settings.event_merger_embedding_model
                )
                logger.info("Embedding model loaded successfully")
            except ImportError:
                logger.error(
                    "sentence_transformers not installed. Please install: pip install sentence_transformers"
                )
                raise
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise
        return self._embedding_model

    def _create_event_text_representation(self, raw_event: RawEventInput) -> str:
        """
        Create a comprehensive text representation of an event for embedding.

        This combines description, date, and entity information into a single
        text that captures the semantic meaning of the event.
        """
        parts = []

        # Add event description
        if raw_event.event_data.description:
            parts.append(raw_event.event_data.description)

        # Add date information
        if raw_event.event_data.event_date_str:
            parts.append(f"Date: {raw_event.event_data.event_date_str}")

        # Add entity information
        if raw_event.event_data.main_entities:
            entity_parts = []
            for entity in raw_event.event_data.main_entities:
                entity_text = (
                    entity.get("original_name", "")
                    if isinstance(entity, dict)
                    else getattr(entity, "original_name", "")
                )
                entity_type = (
                    entity.get("entity_type", "")
                    if isinstance(entity, dict)
                    else getattr(entity, "entity_type", "")
                )
                if entity_type:
                    entity_text += f" ({entity_type})"
                if entity_text.strip():
                    entity_parts.append(entity_text.strip())

            if entity_parts:
                parts.append(f"Entities: {', '.join(entity_parts)}")

        # Add source context if available
        if raw_event.event_data.source_text_snippet:
            # Limit snippet length to avoid overwhelming the embedding
            snippet = raw_event.event_data.source_text_snippet[:200]
            parts.append(f"Context: {snippet}")

        return " | ".join(parts)

    def _get_event_embedding(self, raw_event: RawEventInput) -> np.ndarray:
        """
        Get or compute embedding for an event with caching
        """
        # Create cache key based on event content
        event_text = self._create_event_text_representation(raw_event)
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
            embedding = self.embedding_model.encode(event_text, convert_to_numpy=True)

            # Store in cache
            self.embedding_cache.set(cache_key, embedding)

            logger.debug(
                f"Computed embedding for event {raw_event.original_id}: {event_text[:100]}..."
            )
            return embedding

        except Exception as e:
            logger.error(
                f"Failed to compute embedding for event {raw_event.original_id}: {e}"
            )
            # Return zero vector as fallback
            return np.zeros(384)  # all-MiniLM-L6-v2 has 384 dimensions

    def _compute_similarity_matrix(self, raw_events: list[RawEventInput]) -> np.ndarray:
        """
        Compute pairwise cosine similarity matrix for all events
        """
        logger.info(f"Computing embeddings for {len(raw_events)} events...")

        # Compute all embeddings
        embeddings = []
        for raw_event in raw_events:
            embedding = self._get_event_embedding(raw_event)
            embeddings.append(embedding)

        # Convert to matrix for efficient computation
        embeddings_matrix = np.vstack(embeddings)

        # Compute cosine similarity matrix
        logger.info("Computing similarity matrix...")
        self._stats["similarity_computations"] += 1
        similarity_matrix = cosine_similarity(embeddings_matrix)

        return similarity_matrix

    def _find_embedding_groups(
        self, raw_events: list[RawEventInput], similarity_matrix: np.ndarray
    ) -> list[list[int]]:
        """
        Find groups of events that should be merged based on embedding similarity
        """
        n_events = len(raw_events)
        visited = [False] * n_events
        groups = []
        threshold = settings.event_merger_embedding_similarity_threshold

        for i in range(n_events):
            if visited[i]:
                continue

            # Start a new group
            current_group = [i]
            visited[i] = True

            # Find all events similar to this one
            for j in range(i + 1, n_events):
                if not visited[j] and similarity_matrix[i][j] >= threshold:
                    current_group.append(j)
                    visited[j] = True
                    logger.debug(
                        f"Grouped events {raw_events[i].original_id} and {raw_events[j].original_id} "
                        f"(similarity: {similarity_matrix[i][j]:.3f})"
                    )

            groups.append(current_group)

            if len(current_group) > 1:
                self._stats["embedding_based_merges"] += len(current_group) - 1

        return groups

    async def _hybrid_llm_verification(
        self, raw_events: list[RawEventInput], similarity_matrix: np.ndarray
    ) -> list[list[int]]:
        """
        Hybrid approach: Use embedding for bulk grouping + LLM for uncertain cases
        """
        n_events = len(raw_events)
        visited = [False] * n_events
        groups = []
        uncertain_pairs = []

        embedding_threshold = settings.event_merger_embedding_similarity_threshold
        llm_threshold = settings.event_merger_hybrid_llm_threshold

        # Phase 1: Group by high-confidence embedding similarity
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
                    # Uncertain - needs LLM verification
                    uncertain_pairs.append((i, j, similarity))
                    logger.debug(f"Uncertain pair for LLM: {similarity:.3f}")

            groups.append(current_group)

        # Phase 2: LLM verification for uncertain pairs
        if uncertain_pairs:
            self._stats["hybrid_uncertain_pairs"] = len(uncertain_pairs)
            logger.info(
                f"Using LLM verification for {len(uncertain_pairs)} uncertain pairs"
            )

            # Process uncertain pairs with LLM
            llm_verified_pairs = await self._verify_pairs_with_llm(
                raw_events, uncertain_pairs
            )

            # Merge groups based on LLM verification
            groups = self._merge_groups_with_llm_results(groups, llm_verified_pairs)

        return groups

    async def _verify_pairs_with_llm(
        self,
        raw_events: list[RawEventInput],
        uncertain_pairs: list[tuple[int, int, float]],
    ) -> list[tuple[int, int, bool]]:
        """
        Use LLM to verify uncertain event pairs
        """
        from app.services.event_merger_service import MergedEventGroup

        llm_results = []

        # Create concurrent LLM tasks (limited by concurrent window size)
        window_size = settings.event_merger_concurrent_window_size

        for i in range(0, len(uncertain_pairs), window_size):
            window_pairs = uncertain_pairs[i : i + window_size]

            # Create LLM verification tasks for this window
            tasks = []
            for idx1, idx2, similarity in window_pairs:
                # Create temporary groups for LLM comparison
                group1 = MergedEventGroup(raw_events[idx1])
                task = asyncio.create_task(
                    group1.llm_semantic_match(raw_events[idx2], self.llm_cache)
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
                            f"Error processing LLM result for events {idx1}, {idx2}: {e}"
                        )
                        llm_results.append((idx1, idx2, False))

            except Exception as e:
                logger.error(f"Error in concurrent LLM verification: {e}")
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
        group_events: list[RawEventInput],
        group_indices: list[int],
        similarity_matrix: np.ndarray,
    ) -> RawEventInput:
        """
        Select the most representative event from a group
        """
        if len(group_events) == 1:
            return group_events[0]

        # Find event with highest average similarity to others in the group
        best_event = group_events[0]
        best_avg_similarity = 0

        for i, event in enumerate(group_events):
            if len(group_indices) > 1:
                # Calculate average similarity to other events in the group
                similarities = [
                    similarity_matrix[group_indices[i]][group_indices[j]]
                    for j in range(len(group_indices))
                    if i != j
                ]
                avg_similarity = np.mean(similarities) if similarities else 0
            else:
                avg_similarity = 1.0

            # Also consider other factors like language preference and description length
            score = avg_similarity

            # Language preference bonus
            if self.user_lang and event.source_info.language == self.user_lang:
                score += 0.1

            # Description completeness bonus
            if event.event_data.description:
                score += min(len(event.event_data.description) / 1000, 0.1)

            if score > best_avg_similarity:
                best_avg_similarity = score
                best_event = event

        return best_event

    def _create_merged_group_output(
        self, group_events: list[RawEventInput], representative_event: RawEventInput
    ) -> MergedEventGroupOutput:
        """
        Create the output format for a merged group
        """
        # Create representative event info
        main_entities_for_output = []
        if representative_event.event_data.main_entities_processed:
            main_entities_for_output = (
                representative_event.event_data.main_entities_processed
            )
        else:
            main_entities_for_output = [
                {
                    "entity_id": entity.get("entity_id")
                    if isinstance(entity, dict)
                    else getattr(entity, "entity_id", None),
                    "original_name": entity.get("original_name")
                    if isinstance(entity, dict)
                    else getattr(entity, "original_name", None),
                    "entity_type": entity.get("entity_type")
                    if isinstance(entity, dict)
                    else getattr(entity, "entity_type", None),
                }
                for entity in representative_event.event_data.main_entities
            ]

        # Create timestamp from date info
        timestamp_for_db = None
        if (
            hasattr(representative_event, "date_range")
            and representative_event.date_range
            and representative_event.date_range.start_date
        ):
            from datetime import datetime
            from datetime import time as dt_time

            timestamp_for_db = datetime.combine(
                representative_event.date_range.start_date,
                dt_time.min,
                tzinfo=UTC,
            )

        representative_event_info = RepresentativeEventInfo(
            event_date_str=representative_event.event_data.event_date_str,
            description=representative_event.event_data.description,
            main_entities=main_entities_for_output,
            date_info=representative_event.event_data.date_info,
            timestamp=timestamp_for_db,
            source_text_snippet=representative_event.event_data.source_text_snippet,
            source_url=representative_event.source_info.page_url,
            source_page_title=representative_event.source_info.page_title,
            source_language=representative_event.source_info.language,
        )

        # Create source contributions
        source_contributions = [
            SourceContributionInfo(
                event_data=event.event_data,
                source_info=event.source_info,
            )
            for event in group_events
        ]

        return MergedEventGroupOutput(
            representative_event=representative_event_info,
            source_contributions=source_contributions,
            original_id=representative_event.original_id,
        )

    def _reset_stats(self):
        """Reset performance statistics"""
        for key in self._stats:
            self._stats[key] = 0

    async def get_merge_instructions(
        self,
        events: list[Event],
        progress_callback: "ProgressCallback" | None = None,
        request_id: str = None,
    ) -> list[MergedEventGroupOutput]:
        """
        Main entry point: High-performance embedding-based event merging
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

        # Convert DB events to RawEventInput format (reuse existing logic)
        processed_raw_events = []
        for event in events:
            # Reuse the conversion logic from the original EventMergerService
            if event.date_info and isinstance(event.date_info, dict):
                try:
                    date_info_model = ParsedDateInfo(**event.date_info)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse date_info for event {event.id}: {e}"
                    )
                    date_info_model = None
            else:
                date_info_model = None

            # Get source text snippet
            primary_raw_event = event.raw_events[0] if event.raw_events else None
            snippet = (
                primary_raw_event.source_text_snippet if primary_raw_event else None
            )

            # Convert entity associations
            main_entities_list = []
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

            event_data_for_merger = EventDataForMerger(
                id=str(event.id),
                description=event.description,
                event_date_str=event.event_date_str,
                date_info=date_info_model,
                main_entities=main_entities_list,
                source_text_snippet=snippet,
            )

            source_info_for_merger = SourceInfoForMerger(
                language=getattr(primary_raw_event, "language", None)
                if primary_raw_event
                else None,
            )

            processed_raw_events.append(
                RawEventInput(
                    event_data=event_data_for_merger,
                    source_info=source_info_for_merger,
                )
            )

        logger.info(
            f"Converted {len(processed_raw_events)} DB events to RawEventInput objects"
        )

        # Compute similarity matrix
        if progress_callback:
            await progress_callback.report(
                "Computing event embeddings and similarities...",
                "embedding_computation",
                {"events_processed": 0, "total_events": len(events)},
                request_id,
            )

        similarity_matrix = self._compute_similarity_matrix(processed_raw_events)

        # Find groups based on approach
        if settings.event_merger_hybrid_mode:
            logger.info("Using hybrid embedding + LLM approach")
            groups = await self._hybrid_llm_verification(
                processed_raw_events, similarity_matrix
            )
        else:
            logger.info("Using pure embedding approach")
            groups = self._find_embedding_groups(
                processed_raw_events, similarity_matrix
            )

        logger.info(
            f"Found {len(groups)} groups from {len(processed_raw_events)} events"
        )

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
            group_events = [processed_raw_events[i] for i in group_indices]
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
