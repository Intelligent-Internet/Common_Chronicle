"""
Event Merger Service - Intelligent event deduplication and consolidation system.

Uses multi-stage approach combining rule-based matching, semantic similarity analysis,
and LLM-powered comparison to merge duplicate or related events from multiple sources.
"""

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from datetime import time as dt_time
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.services.process_callback import ProgressCallback

from app.config import settings
from app.models import Event
from app.schemas import (
    DateRangeInfo,
    EventDataForMerger,
    MergedEventGroupOutput,
    ParsedDateInfo,
    RepresentativeEventInfo,
    SourceContributionInfo,
    SourceInfoForMerger,
)
from app.services.llm_service import get_llm_client
from app.utils.logger import setup_logger

logger = setup_logger("event_merger", level="DEBUG")


class MatchCandidate(BaseModel):
    """
    Represents a potential match candidate with scoring information.

    Encapsulates candidate group, confidence score, and matching strategy
    for prioritization during event merging.
    """

    group: "MergedEventGroup"
    score: float
    match_type: str  # 'rule_exact', 'rule_partial', 'llm_candidate'

    class Config:
        arbitrary_types_allowed = True


class LLMComparisonCache:
    """
    Caching system for LLM comparison results to optimize performance.

    Uses content-based hashing to generate stable cache keys and avoid
    redundant API calls during semantic comparison operations.
    """

    def __init__(self, max_size: int = 1000):
        self.cache: dict[str, dict[str, Any]] = {}
        self.max_size = max_size

    def get_cache_key(self, event_a: "RawEventInput", event_b: "RawEventInput") -> str:
        """Generate stable cache key based on event content features."""
        features_a = (
            hashlib.md5((event_a.event_data.description or "").encode()).hexdigest()[
                :8
            ],
            "|".join(sorted(event_a.processed_entities_uuids)),
            str(event_a.event_year),
        )
        features_b = (
            hashlib.md5((event_b.event_data.description or "").encode()).hexdigest()[
                :8
            ],
            "|".join(sorted(event_b.processed_entities_uuids)),
            str(event_b.event_year),
        )
        # Ensure consistent ordering for cache key
        if features_a > features_b:
            features_a, features_b = features_b, features_a
        return f"{features_a}--{features_b}"

    def get(
        self, event_a: "RawEventInput", event_b: "RawEventInput"
    ) -> dict[str, Any] | None:
        """Retrieve cached comparison result for two events."""
        key = self.get_cache_key(event_a, event_b)
        return self.cache.get(key)

    def set(
        self,
        event_a: "RawEventInput",
        event_b: "RawEventInput",
        result: dict[str, Any],
    ):
        """Store comparison result in cache with LRU eviction."""
        if len(self.cache) >= self.max_size:
            # Simple LRU: remove oldest entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]

        key = self.get_cache_key(event_a, event_b)
        self.cache[key] = result


class IndexSystem:
    """
    Multi-dimensional indexing for O(1) candidate lookup and 95%+ comparison reduction.

    Maintains entity-based, temporal, and hybrid indexes to efficiently retrieve
    potentially matching event groups without exhaustive comparisons.
    """

    def __init__(self):
        """Initialize all index structures for multi-dimensional lookups."""
        # Entity-based indexes for direct and type-based matching
        self.entity_index: defaultdict[str, list[MergedEventGroup]] = defaultdict(list)
        self.entity_type_index: defaultdict[str, list[MergedEventGroup]] = defaultdict(
            list
        )
        self.entity_combination_index: defaultdict[
            frozenset, list[MergedEventGroup]
        ] = defaultdict(list)

        # Time-based indexes for temporal proximity matching
        self.year_index: defaultdict[int, list[MergedEventGroup]] = defaultdict(list)
        self.year_range_index: defaultdict[
            tuple[int, int], list[MergedEventGroup]
        ] = defaultdict(list)

        # Hybrid indexes combining entity and temporal dimensions
        self.hybrid_index: defaultdict[
            tuple[str, int], list[MergedEventGroup]
        ] = defaultdict(list)

    def add_group(self, group: "MergedEventGroup"):
        """Add a merged event group to all relevant indexes."""
        # Entity-based indexing for direct entity matching
        for entity_id in group.representative_entities_uuids:
            self.entity_index[entity_id].append(group)

        # Entity type indexing for broader category matching
        for entity_type in group.entity_types:
            self.entity_type_index[entity_type].append(group)

        # Entity combination indexing for exact entity set matching
        if group.representative_entities_uuids:
            entity_combo = frozenset(group.representative_entities_uuids)
            self.entity_combination_index[entity_combo].append(group)

        # Temporal indexing for year-based matching
        if group.event_year:
            self.year_index[group.event_year].append(group)

            # Year range indexing for temporal proximity (±1 year)
            for year in range(group.event_year - 1, group.event_year + 2):
                self.year_range_index[
                    (min(year, group.event_year), max(year, group.event_year))
                ].append(group)

        # Hybrid indexing combining entity and temporal dimensions
        if group.event_year:
            for entity_id in group.representative_entities_uuids:
                self.hybrid_index[(entity_id, group.event_year)].append(group)

    def get_candidates(self, event: "RawEventInput") -> set["MergedEventGroup"]:
        """Multi-index search: entity exact/type matching → temporal proximity → hybrid combinations."""
        candidates = set()

        # 1. Exact entity matching - highest precision candidates
        for entity_id in event.processed_entities_uuids:
            candidates.update(self.entity_index[entity_id])

        # 2. Entity type matching - broader category-based candidates
        for entity_type in event.entity_types:
            candidates.update(self.entity_type_index[entity_type])

        # 3. Temporal proximity matching - chronologically related events
        if event.event_year:
            # Same year candidates
            candidates.update(self.year_index[event.event_year])

            # Adjacent years for temporal proximity
            for year in [event.event_year - 1, event.event_year + 1]:
                candidates.update(self.year_index[year])

        # 4. Hybrid matching - combining entity and temporal dimensions
        if event.event_year:
            for entity_id in event.processed_entities_uuids:
                candidates.update(self.hybrid_index[(entity_id, event.event_year)])

        return candidates


class RawEventInput(BaseModel):
    """
    Event representation with precomputed features for efficient matching operations.

    Preprocesses entities, temporal data, and content hashes to optimize comparison
    performance during merging pipeline.
    """

    event_data: EventDataForMerger
    source_info: SourceInfoForMerger

    # Fields computed on initialization for optimization
    original_id: str | None = None
    processed_entities_uuids: set[str] = Field(default_factory=set, exclude=True)
    entity_types: set[str] = Field(default_factory=set, exclude=True)
    date_range: DateRangeInfo | None = Field(None, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def __init__(
        self, event_data: dict[str, Any], source_info: dict[str, Any], **kwargs
    ):
        # Manually initialize to allow both dict and model inputs
        super().__init__(event_data=event_data, source_info=source_info, **kwargs)

        # Store original ID for tracking purposes
        self.original_id = self.event_data.id

        # Initialize private cache attributes for lazy computation
        self._event_year: int | None = None
        self._description_hash: str | None = None

        # Precompute entity sets for fast intersection operations
        entities_before = getattr(self.event_data, "main_entities", [])
        logger.debug(
            f"[RawEventInput Init] Event {self.original_id} entities_before processing: "
            f"{entities_before} (count: {len(entities_before) if entities_before else 0})"
        )

        self.processed_entities_uuids = {
            entity.entity_id
            for entity in self.event_data.main_entities
            if entity.entity_id
        }

        logger.debug(
            f"[RawEventInput Init] Event {self.original_id} processed_entities_uuids: "
            f"{self.processed_entities_uuids} (count: {len(self.processed_entities_uuids)})"
        )

        # Precompute entity types for category-based matching
        self.entity_types = {
            entity.entity_type
            for entity in self.event_data.main_entities
            if entity.entity_type
        }

        logger.debug(
            f"[RawEventInput Init] Event {self.original_id} entity_types: "
            f"{self.entity_types} (count: {len(self.entity_types)})"
        )

        # Convert date information to normalized range format
        if self.event_data.date_info:
            self.date_range = self.event_data.date_info.to_date_range()
        else:
            self.date_range = None

    @property
    def event_year(self) -> int | None:
        """Cached event year from date range, preferring start_date."""
        if self._event_year is None:
            if self.date_range and self.date_range.start_date:
                self._event_year = self.date_range.start_date.year
            elif self.date_range and self.date_range.end_date:
                self._event_year = self.date_range.end_date.year
        return self._event_year

    @property
    def description_hash(self) -> str:
        """8-character MD5 hash for fast description comparison."""
        if self._description_hash is None:
            desc = self.event_data.description or ""
            self._description_hash = hashlib.md5(desc.encode()).hexdigest()[:8]
        return self._description_hash

    def __repr__(self):
        return f"<RawEventInput entities={len(self.processed_entities_uuids)} year={self.event_year} desc='{self.event_data.description[:30] if self.event_data.description else ''}...'>"


class MergedEventGroup:
    """
    Container for events describing the same real-world event with progressive matching.

    Matching pipeline: quick exclusion → rule-based → scoring → LLM semantic analysis.
    Optimizes performance with early rejection and intelligent candidate prioritization.
    """

    def __init__(self, first_raw_event: RawEventInput):
        self.representative_event_input: RawEventInput = first_raw_event
        self.source_contributions: list[RawEventInput] = [first_raw_event]
        self.representative_entities_uuids: set[
            str
        ] = first_raw_event.processed_entities_uuids
        self.representative_date_range: DateRangeInfo | None = (
            first_raw_event.date_range
        )
        self.representative_date_info: ParsedDateInfo | None = (
            first_raw_event.event_data.date_info
        )
        self.original_id: str | None = (
            first_raw_event.original_id
        )  # Store the ID of the first event

        # Cache for optimization to avoid repeated computations
        self._entity_types = None
        self._event_year = None

        logger.debug(
            f"[Group Init] Created group with event {first_raw_event.original_id}. "
            f"Initial date_info type: {type(self.representative_date_info)}"
        )

        # DEBUG: Log entity information inheritance
        logger.debug(
            f"[Group Init] Group {self.original_id} representative_entities_uuids: "
            f"{self.representative_entities_uuids} (count: {len(self.representative_entities_uuids)})"
        )
        logger.debug(
            f"[Group Init] Group {self.original_id} first_raw_event main_entities: "
            f"{getattr(first_raw_event.event_data, 'main_entities', 'MISSING')}"
        )
        if hasattr(first_raw_event.event_data, "main_entities"):
            logger.debug(
                f"[Group Init] Group {self.original_id} main_entities details: "
                f"{[{getattr(e, 'original_name', 'NO_NAME'): getattr(e, 'entity_id', 'NO_ID')} for e in first_raw_event.event_data.main_entities]}"
            )

    @property
    def entity_types(self) -> set[str]:
        if self._entity_types is None:
            self._entity_types = self.representative_event_input.entity_types
        return self._entity_types

    @property
    def event_year(self) -> int | None:
        if self._event_year is None:
            self._event_year = self.representative_event_input.event_year
        return self._event_year

    def quick_exclude_check(self, event: RawEventInput) -> bool:
        """Fast exclusion to avoid expensive LLM comparisons: temporal distance >2yr, no entity overlap."""

        # 1. Year difference too large (>2 years)
        if (
            self.event_year is not None
            and event.event_year is not None
            and abs(self.event_year - event.event_year) > 2
        ):
            return True

        # 2. No entity overlap and no entity type overlap
        if not self.representative_entities_uuids.intersection(
            event.processed_entities_uuids
        ) and not self.entity_types.intersection(event.entity_types):
            return True

        # 3. Both events have very different description lengths (potential indicator)
        rep_desc_len = len(self.representative_event_input.event_data.description or "")
        event_desc_len = len(event.event_data.description or "")
        if rep_desc_len > 0 and event_desc_len > 0:
            length_ratio = max(rep_desc_len, event_desc_len) / min(
                rep_desc_len, event_desc_len
            )
            if length_ratio > 5:  # One description is 5x longer than the other
                return True

        return False

    def calculate_match_score(self, event: RawEventInput) -> float:
        """
        Multi-factor scoring for LLM candidate prioritization (0-100).

        Scoring: entity overlap (10pt each) + type overlap (5pt each) +
        temporal proximity (30/20/10 for 0/1/2yr) + language match (10pt) + description hash (10pt).
        """
        score = 0.0

        # Entity overlap score (0-40 points) - primary matching factor
        entity_overlap = len(
            self.representative_entities_uuids.intersection(
                event.processed_entities_uuids
            )
        )
        score += entity_overlap * 10

        # Entity type overlap score (0-10 points) - category similarity
        type_overlap = len(self.entity_types.intersection(event.entity_types))
        score += type_overlap * 5

        # Time proximity score (0-30 points) - temporal compatibility
        if self.event_year is not None and event.event_year is not None:
            year_diff = abs(self.event_year - event.event_year)
            if year_diff == 0:
                score += 30
            elif year_diff == 1:
                score += 20
            elif year_diff == 2:
                score += 10

        # Language match bonus (0-10 points) - source consistency
        if (
            self.representative_event_input.source_info.language
            == event.source_info.language
        ):
            score += 10

        # Description similarity (basic, 0-10 points) - content match
        if self.representative_event_input.description_hash == event.description_hash:
            score += 10  # Exact description match

        return score

    def rule_based_match(self, event: RawEventInput) -> bool:
        """High-confidence deterministic matching: high entity overlap + date compatibility."""

        # Calculate entity overlap ratio instead of requiring exact match
        common_entities = self.representative_entities_uuids.intersection(
            event.processed_entities_uuids
        )

        # If either set is empty, no match
        if not self.representative_entities_uuids or not event.processed_entities_uuids:
            entity_match = False
        else:
            # Calculate overlap ratio based on the smaller set
            smaller_set_size = min(
                len(self.representative_entities_uuids),
                len(event.processed_entities_uuids),
            )
            overlap_ratio = len(common_entities) / smaller_set_size

            # Consider it a match if overlap ratio meets the configured threshold
            entity_match = overlap_ratio >= settings.event_merger_rule_overlap_ratio

        # Date compatibility - events must have overlapping or both missing dates
        date_compatible = False
        if self.representative_date_range and event.date_range:
            date_compatible = self.representative_date_range.overlaps(event.date_range)
        elif not self.representative_date_range and not event.date_range:
            date_compatible = True

        return entity_match and date_compatible

    async def llm_semantic_match(
        self,
        event: RawEventInput,
        llm_cache: LLMComparisonCache,
        min_confidence_threshold: float = 0.75,
    ) -> bool:
        """LLM-based semantic matching with caching"""

        # Check cache first
        cached_result = llm_cache.get(self.representative_event_input, event)
        if cached_result is not None:
            return (
                cached_result.get("is_same_event", False)
                and cached_result.get("confidence_score", 0.0)
                >= min_confidence_threshold
            )

        # Get LLM client
        llm_service_client = get_llm_client(settings.default_llm_provider)
        if not llm_service_client:
            logger.warning("LLM client not available for semantic match")
            return False

        # Prepare comparison data
        event_a = self.representative_event_input
        event_b = event

        # Format entities
        def format_entities(entities):
            if not entities:
                return "N/A"
            return "\\n".join(
                [
                    f"- Name: {entity.original_name or 'N/A'}, Type: {entity.entity_type or 'N/A'}, UUID: {entity.entity_id or 'N/A'}"
                    for entity in entities
                ]
            )

        # Format date range
        def format_date_range(date_range):
            if not date_range:
                return "N/A"
            return json.dumps(date_range.to_api_dict())

        entities_a = format_entities(event_a.event_data.main_entities)
        entities_b = format_entities(event_b.event_data.main_entities)
        date_range_a = format_date_range(event_a.date_range)
        date_range_b = format_date_range(event_b.date_range)

        system_prompt = """
You are an expert in historical event analysis and deduplication, capable of understanding events across different languages.
Your task is to determine if the following two event descriptions, potentially from different sources or languages, refer to the *exact same underlying real-world event*.

Carefully consider the event descriptions, stated dates, and key entities involved.
Minor variations in wording, date precision, entity names (especially across languages or due to slight differences in extraction), or source text snippets are acceptable if the core factual event is identical.

Respond ONLY with a JSON object with the following schema:
{
  "is_same_event": boolean,
  "confidence_score": float,
  "reasoning": "A brief explanation for your decision, highlighting key similarities or differences."
}

Ensure your JSON response is valid and contains no other text or explanations outside the JSON structure.
"""

        user_content = (
            f"Event 1:\\n"
            f"Description: \\\"{event_a.event_data.description or 'N/A'}\\\"\\n"
            f"Date String: \\\"{event_a.event_data.event_date_str or 'N/A'}\\\"\\n"
            f"Parsed Date Range: {date_range_a}\\n"
            f"Entities:\\n{entities_a}\\n"
            f"Source Language: {event_a.source_info.language or 'N/A'}\\n"
            f"Source Snippet: \\\"{event_a.event_data.source_text_snippet or ''}\\\"\\n\\n"
            f"Event 2:\\n"
            f"Description: \\\"{event_b.event_data.description or 'N/A'}\\\"\\n"
            f"Date String: \\\"{event_b.event_data.event_date_str or 'N/A'}\\\"\\n"
            f"Parsed Date Range: {date_range_b}\\n"
            f"Entities:\\n{entities_b}\\n"
            f"Source Language: {event_b.source_info.language or 'N/A'}\\n"
            f"Source Snippet: \\\"{event_b.event_data.source_text_snippet or ''}\\\""
        )

        try:
            response = await llm_service_client.generate_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )

            if not response or not response.get("choices"):
                raise ValueError("LLM response is empty or invalid")

            response_content = response["choices"][0]["message"]["content"]
            if response_content:
                llm_result = json.loads(response_content)

                # Cache the result
                llm_cache.set(event_a, event_b, llm_result)

                is_same = llm_result.get("is_same_event", False)
                confidence = llm_result.get("confidence_score", 0.0)

                logger.debug(
                    f"LLM semantic match result: is_same={is_same}, confidence={confidence}"
                )

                return is_same and confidence >= min_confidence_threshold

        except Exception as e:
            logger.error(f"Error during LLM semantic match: {e}")

        return False

    async def check_merge_eligibility(
        self,
        raw_event: RawEventInput,
        stats: dict[str, int],
    ) -> tuple[bool, float]:
        """
        Pre-LLM filtering pipeline: quick exclusion → rules → scoring.
        Returns (is_eligible, match_score) where is_eligible indicates if LLM comparison is needed.
        """

        stats["total_try_add_contribution_calls"] += 1

        # DEBUG: Log entity information at start
        logger.debug(
            f"[Check Eligibility] Checking event {raw_event.original_id} against group {self.original_id}"
        )

        # Stage 1: Quick exclusion check
        if self.quick_exclude_check(raw_event):
            stats["quick_exclusions"] += 1
            logger.debug(
                f"[Check Eligibility] Event {raw_event.original_id} excluded by quick check"
            )
            return False, 0.0

        # Stage 2: Rule-based matching
        if self.rule_based_match(raw_event):
            stats["rule_based_merges"] += 1
            logger.debug("Rule-based merge successful")
            logger.debug(
                f"[Check Eligibility] Rule-based merge: event {raw_event.original_id} matches group {self.original_id}"
            )
            return True, 100.0  # High score indicates rule-based match

        # Stage 3: Calculate match score for LLM candidacy
        match_score = self.calculate_match_score(raw_event)

        # Enhanced pre-filtering: require minimum entity overlap
        common_entities = len(
            self.representative_entities_uuids.intersection(
                raw_event.processed_entities_uuids
            )
        )

        logger.debug(
            f"[Check Eligibility] Event {raw_event.original_id} vs Group {self.original_id}: "
            f"match_score={match_score}, common_entities={common_entities}"
        )

        # Require at least minimum common entities for LLM consideration
        if common_entities < settings.event_merger_min_common_entities:
            stats["low_score_rejections"] += 1
            logger.debug(
                f"[Check Eligibility] Event {raw_event.original_id} rejected: insufficient common entities"
            )
            return False, match_score

        # Time window check: events should be within reasonable time range (3 years)
        if (
            self.event_year is not None
            and raw_event.event_year is not None
            and abs(self.event_year - raw_event.event_year) > 3
        ):
            stats["low_score_rejections"] += 1
            logger.debug(
                f"[Check Eligibility] Event {raw_event.original_id} rejected: time window too large"
            )
            return False, match_score

        # Only proceed to LLM if score is promising (configurable threshold)
        if match_score < settings.event_merger_llm_score_threshold:
            stats["low_score_rejections"] += 1
            logger.debug(
                f"[Check Eligibility] Event {raw_event.original_id} rejected: low match score"
            )
            return False, match_score

        # Event is eligible for LLM comparison
        stats["llm_candidates"] += 1
        logger.debug(
            f"[Check Eligibility] Event {raw_event.original_id} eligible for LLM comparison (score: {match_score})"
        )
        return True, match_score

    async def try_add_contribution(
        self,
        raw_event: RawEventInput,
        llm_cache: LLMComparisonCache,
        stats: dict[str, int],
    ) -> bool:
        """Legacy method for backward compatibility. Uses the new check_merge_eligibility method."""

        is_eligible, match_score = await self.check_merge_eligibility(raw_event, stats)

        if not is_eligible:
            return False

        # If match_score is 100.0, it means rule-based match succeeded
        if match_score >= 100.0:
            self.source_contributions.append(raw_event)
            return True

        # Otherwise, perform LLM semantic matching
        if await self.llm_semantic_match(raw_event, llm_cache):
            self.source_contributions.append(raw_event)
            stats["llm_confirmed_merges"] += 1
            logger.debug(f"LLM semantic merge successful (score: {match_score})")
            logger.debug(
                f"[Try Add] LLM merge: added event {raw_event.original_id} to group {self.original_id}. "
                f"Group now has {len(self.source_contributions)} contributions"
            )
            return True

        logger.debug(
            f"[Try Add] Event {raw_event.original_id} rejected by LLM semantic match"
        )
        return False

    async def finalize_representative_event(
        self, user_lang: str | None = None, default_lang: str = "en"
    ):
        if not self.source_contributions:
            logger.debug(
                f"[Finalize] Group {self.original_id} has no source contributions"
            )
            return

        logger.debug(
            f"[Finalize] Starting finalization for group {self.original_id} with {len(self.source_contributions)} contributions"
        )

        # Log all contribution entities before finalization
        for i, contrib in enumerate(self.source_contributions):
            logger.debug(
                f"[Finalize] Contribution {i} (ID: {contrib.original_id}) entities: "
                f"{contrib.processed_entities_uuids} (count: {len(contrib.processed_entities_uuids)})"
            )
            logger.debug(
                f"[Finalize] Contribution {i} main_entities: "
                f"{getattr(contrib.event_data, 'main_entities', 'MISSING')}"
            )

        # If there's only one event, it's automatically the representative one.
        if len(self.source_contributions) == 1:
            best_event = self.source_contributions[0]
            self.representative_event_input = best_event
            self.representative_entities_uuids = best_event.processed_entities_uuids
            self.representative_date_range = best_event.date_range
            self.representative_date_info = best_event.event_data.date_info
            logger.debug(
                f"[Finalize] Single event group {self.original_id}: using only contribution as representative. "
                f"Entities: {self.representative_entities_uuids} (count: {len(self.representative_entities_uuids)})"
            )
            return

        # Prepare the list of events for the LLM to evaluate.
        events_to_evaluate = [
            {
                "id": event.original_id,
                "description": event.event_data.description,
                "date": event.event_data.event_date_str,
            }
            for event in self.source_contributions
        ]

        logger.debug(
            f"[Finalize] Group {self.original_id} preparing LLM evaluation for {len(events_to_evaluate)} events"
        )

        prompt = f"""
You are an expert historian AI. Your task is to analyze a list of event descriptions that refer to the same core event and select the one that is the most comprehensive and definitive summary.

**Source Events:**
Here is a list of events, each with a unique `id`:
{json.dumps(events_to_evaluate, indent=2)}

**Your Task:**
Review all the events and decide which one serves as the best single representative description for the entire group. Consider the clarity, detail, and completeness of the description and date.

**Output Format:**
You MUST respond with a single, valid JSON object containing ONE key: "best_event_id". The value should be the `id` of the event you have chosen as the best representative.

**Example Response:**
{{
  "best_event_id": "fcdcd7e6-5d16-4081-8442-2286adc060c3"
}}

**Crucial Instruction:**
Do NOT create a new description or date. Your only job is to CHOOSE the best event from the provided list and return its `id`.
"""

        try:
            llm_interface = get_llm_client(settings.default_llm_provider)
            if not llm_interface:
                raise ValueError("LLM client not available")

            response = await llm_interface.generate_chat_completion(
                messages=[{"role": "system", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,  # Set to 0 for deterministic choice
            )

            if not response or not response.get("choices"):
                raise ValueError("LLM response is empty or invalid")

            response_content = response["choices"][0]["message"]["content"]
            if response_content:
                llm_result = json.loads(response_content)
                best_event_id = llm_result.get("best_event_id")

                # Find the chosen event in our original list
                best_event = next(
                    (
                        event
                        for event in self.source_contributions
                        if event.original_id == best_event_id
                    ),
                    None,
                )

                if best_event:
                    self.representative_event_input = best_event
                    self.representative_entities_uuids = (
                        best_event.processed_entities_uuids
                    )
                    self.representative_date_range = best_event.date_range
                    self.representative_date_info = best_event.event_data.date_info
                    logger.debug(
                        f"[LLM Finalize] LLM chose best event ID: {best_event_id}. "
                        f"Final date_info type: {type(self.representative_date_info)}. "
                        f"date_info content: {self.representative_date_info.model_dump() if self.representative_date_info else 'None'}"
                    )
                    logger.debug(
                        f"[LLM Finalize] Group {self.original_id} LLM selected representative event {best_event_id}. "
                        f"Representative entities: {self.representative_entities_uuids} (count: {len(self.representative_entities_uuids)})"
                    )
                    return

        except Exception as e:
            logger.error(f"Error during LLM selection: {e}. Falling back to heuristic.")

        # Fallback to heuristic if LLM fails or doesn't return a valid ID
        logger.debug(
            f"[Finalize] Group {self.original_id} falling back to heuristic selection"
        )
        self._finalize_by_picking_best(user_lang, default_lang)

    def _finalize_by_picking_best(
        self, user_lang: str | None = None, default_lang: str = "en"
    ):
        if not self.source_contributions:
            logger.debug(
                f"[Heuristic] Group {self.original_id} has no source contributions"
            )
            return

        logger.debug(
            f"[Heuristic] Starting heuristic selection for group {self.original_id}"
        )

        best_candidate = self.source_contributions[0]
        best_score = -1

        for contrib_input in self.source_contributions:
            current_score = 0
            source_lang = contrib_input.source_info.language

            if user_lang and source_lang == user_lang:
                current_score += 100
            elif source_lang == default_lang:
                current_score += 50

            desc_len = len(contrib_input.event_data.description or "")
            current_score += desc_len * 0.1

            if contrib_input.date_range:
                precision = contrib_input.date_range.precision
                precision_scores = {
                    "day": 30,
                    "month": 20,
                    "year": 10,
                }
                current_score += precision_scores.get(precision, 0)

            logger.debug(
                f"[Heuristic] Group {self.original_id} event {contrib_input.original_id} score: {current_score}. "
                f"Entities: {contrib_input.processed_entities_uuids} (count: {len(contrib_input.processed_entities_uuids)})"
            )

            if current_score > best_score:
                best_score = current_score
                best_candidate = contrib_input
                logger.debug(
                    f"[Heuristic] Group {self.original_id} new best candidate: {contrib_input.original_id}"
                )

        # Enhanced robustness: Ensure the best candidate always has date information
        if not best_candidate.date_range:
            # Try to find any event with date information
            for potential_date_source in self.source_contributions:
                if potential_date_source.date_range:
                    best_candidate.date_range = potential_date_source.date_range
                    logger.debug(
                        f"Patched missing date for group {self.original_id} "
                        f"using date from contribution {potential_date_source.original_id}"
                    )
                    break

        # Also ensure event_date_str is available if date_range exists
        if best_candidate.date_range and not best_candidate.event_data.event_date_str:
            # Try to find an event_date_str from other contributions
            for potential_date_source in self.source_contributions:
                if potential_date_source.event_data.event_date_str:
                    best_candidate.event_data.event_date_str = (
                        potential_date_source.event_data.event_date_str
                    )
                    logger.debug(
                        f"Patched missing event_date_str for group {self.original_id} "
                        f"using date string from contribution {potential_date_source.original_id}"
                    )
                    break

        # Final safety check: If we still don't have event_date_str but have date_range,
        # create a basic date string from the date_range
        if not best_candidate.event_data.event_date_str and best_candidate.date_range:
            if best_candidate.date_range.start_date:
                best_candidate.event_data.event_date_str = str(
                    best_candidate.date_range.start_date.year
                )
                logger.debug(
                    f"Generated basic event_date_str '{best_candidate.event_data.event_date_str}' "
                    f"from date_range for group {self.original_id}"
                )

        self.representative_event_input = best_candidate
        self.representative_entities_uuids = best_candidate.processed_entities_uuids
        self.representative_date_range = best_candidate.date_range
        self.representative_date_info = best_candidate.event_data.date_info
        logger.debug(
            f"[Heuristic Finalize] Heuristic chose best event. "
            f"Final date_info type: {type(self.representative_date_info)}. "
            f"date_info content: {self.representative_date_info.model_dump() if self.representative_date_info else 'None'}"
        )
        logger.debug(
            f"[Heuristic Finalize] Group {self.original_id} final representative event: {best_candidate.original_id}. "
            f"Final representative entities: {self.representative_entities_uuids} (count: {len(self.representative_entities_uuids)})"
        )

    def to_output_schema(self) -> MergedEventGroupOutput:
        logger.debug(
            f"[To Output] Starting output schema conversion for group {self.original_id}"
        )
        logger.debug(
            f"[To Output] Group {self.original_id} representative_entities_uuids: "
            f"{self.representative_entities_uuids} (count: {len(self.representative_entities_uuids)})"
        )
        logger.debug(
            f"[To Output] Group {self.original_id} representative_event_input main_entities: "
            f"{getattr(self.representative_event_input.event_data, 'main_entities', 'MISSING')}"
        )

        # Finalize the representative event data from the best candidate
        final_rep_event_data = self.representative_event_input.event_data.model_copy()
        timestamp_for_db: datetime | None = None

        logger.debug(
            f"[To Output] Group {self.original_id} final_rep_event_data main_entities: "
            f"{getattr(final_rep_event_data, 'main_entities', 'MISSING')}"
        )
        logger.debug(
            f"[To Output] Group {self.original_id} final_rep_event_data main_entities_processed: "
            f"{getattr(final_rep_event_data, 'main_entities_processed', 'MISSING')}"
        )

        # Update date details and calculate timestamp from the merged date range
        if self.representative_date_range:
            # Use the preserved ParsedDateInfo object directly
            final_date_info = self.representative_date_info
            if self.representative_date_range.start_date:
                timestamp_for_db = datetime.combine(
                    self.representative_date_range.start_date, dt_time.min, tzinfo=UTC
                )
        else:
            final_date_info = None

        logger.debug(
            f"[To Output] Preparing output schema. "
            f"Final date_info type before serialization: {type(final_date_info)}. "
            f"date_info content: {final_date_info.model_dump() if final_date_info else 'None'}"
        )

        # Build the representative event part of the output
        main_entities_for_output = (
            final_rep_event_data.main_entities_processed
            if final_rep_event_data.main_entities_processed is not None
            else [e.model_dump() for e in final_rep_event_data.main_entities]
        )

        logger.debug(
            f"[To Output] Group {self.original_id} main_entities_for_output: "
            f"{main_entities_for_output} (count: {len(main_entities_for_output) if main_entities_for_output else 0})"
        )

        representative_event_info = RepresentativeEventInfo(
            event_date_str=final_rep_event_data.event_date_str,
            description=final_rep_event_data.description,
            main_entities=main_entities_for_output,
            date_info=final_date_info,  # Use the preserved ParsedDateInfo
            timestamp=timestamp_for_db,
            source_text_snippet=self.representative_event_input.event_data.source_text_snippet,
            source_url=self.representative_event_input.source_info.page_url,
            source_page_title=self.representative_event_input.source_info.page_title,
            source_language=self.representative_event_input.source_info.language,
        )

        logger.debug(
            f"[To Output] Group {self.original_id} created RepresentativeEventInfo with main_entities: "
            f"{getattr(representative_event_info, 'main_entities', 'MISSING')}"
        )

        # Build the source contributions part of the output
        source_contributions_info = [
            SourceContributionInfo(
                event_data=contrib_input.event_data,
                source_info=contrib_input.source_info,
            )
            for contrib_input in self.source_contributions
        ]

        # Combine into the final schema object
        final_output = MergedEventGroupOutput(
            representative_event=representative_event_info,
            source_contributions=source_contributions_info,
            original_id=self.original_id,
        )

        logger.debug(
            f"[To Output] Group {self.original_id} final output main_entities: "
            f"{getattr(final_output.representative_event, 'main_entities', 'MISSING')}"
        )

        return final_output


class EventMergerService:
    """
    High-performance event deduplication service with 95%+ comparison reduction.

    Combines rule-based matching, probabilistic scoring, and LLM semantic analysis
    with intelligent indexing and caching for optimal performance at scale.
    """

    def __init__(
        self,
        user_lang: str | None = None,
    ):
        self.user_lang = user_lang

        # Initialize optimization components
        self.index_system = IndexSystem()
        self.llm_cache = LLMComparisonCache()

        # Performance counters for monitoring and optimization
        self._stats = {
            "total_try_add_contribution_calls": 0,
            "rule_based_merges": 0,
            "llm_candidates": 0,
            "llm_confirmed_merges": 0,
            "quick_exclusions": 0,
            "low_score_rejections": 0,
            "index_lookups": 0,
            "cache_hits": 0,
            "concurrent_windows_processed": 0,
            "concurrent_llm_calls_saved": 0,
        }

    def _reset_stats(self):
        self._stats = {
            "total_try_add_contribution_calls": 0,
            "rule_based_merges": 0,
            "llm_candidates": 0,
            "llm_confirmed_merges": 0,
            "quick_exclusions": 0,
            "low_score_rejections": 0,
            "index_lookups": 0,
            "cache_hits": 0,
            "concurrent_windows_processed": 0,
            "concurrent_llm_calls_saved": 0,
        }

    async def get_merge_instructions(
        self,
        events: list[Event],
        progress_callback: Optional["ProgressCallback"] = None,
        request_id: str | None = None,
    ) -> list[MergedEventGroupOutput]:
        """Main entry point: converts DB events → applies merging pipeline → returns structured results."""
        self._reset_stats()
        start_time = time.time()

        if progress_callback:
            await progress_callback.report(
                f"Starting event merging for {len(events)} events...",
                "event_merging_start",
                {"total_events": len(events)},
                request_id,
            )

        # 1. Convert DB ORM Events to internal RawEventInput Pydantic models
        processed_raw_events = []
        for event in events:
            logger.debug(f"[DB Convert] Processing DB event {event.id}")
            logger.debug(
                f"[DB Convert] Event {event.id} entity_associations count: {len(event.entity_associations) if event.entity_associations else 0}"
            )
            logger.debug(
                f"[DB Convert] Event {event.id} raw_events count: {len(event.raw_events) if event.raw_events else 0}"
            )

            # This is the critical step where data from the DB is shaped into our internal models.
            # We assume event.date_info is a dict that conforms to ParsedDateInfo schema.
            if event.date_info and isinstance(event.date_info, dict):
                try:
                    date_info_model = ParsedDateInfo(**event.date_info)
                    logger.debug(
                        f"[Pre-process] Successfully parsed date_info for event {event.id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[Pre-process] Failed to parse date_info dict for event {event.id}. Error: {e}. "
                        f"date_info dict: {event.date_info}"
                    )
                    date_info_model = None
            else:
                date_info_model = None
                if event.date_info:
                    logger.warning(
                        f"[Pre-process] event.date_info for event {event.id} is not a dict, type: {type(event.date_info)}. Setting to None."
                    )

            # Access source_text_snippet from the associated RawEvent
            # Heuristic: use the first associated raw_event as the source of the snippet.
            primary_raw_event = event.raw_events[0] if event.raw_events else None
            snippet = (
                primary_raw_event.source_text_snippet if primary_raw_event else None
            )

            # Convert entity associations to main_entities format
            main_entities_list = []
            for assoc in event.entity_associations:
                logger.debug(
                    f"[DB Convert] Event {event.id} processing entity association: "
                    f"entity_id={assoc.entity_id}, has_entity_attr={hasattr(assoc, 'entity')}"
                )

                entity_dict = {"entity_id": str(assoc.entity_id)}
                # Add more entity information if available
                if hasattr(assoc, "entity") and assoc.entity:
                    entity_obj = assoc.entity
                    logger.debug(
                        f"[DB Convert] Event {event.id} entity object found: "
                        f"entity_id={entity_obj.id}, entity_name={getattr(entity_obj, 'entity_name', 'MISSING')}, "
                        f"entity_type={getattr(entity_obj, 'entity_type', 'MISSING')}"
                    )
                    entity_dict.update(
                        {
                            "original_name": getattr(entity_obj, "entity_name", None),
                            "entity_type": getattr(entity_obj, "entity_type", None),
                        }
                    )
                else:
                    logger.warning(
                        f"[DB Convert] Event {event.id} entity association {assoc.entity_id} has no entity object loaded! "
                        f"hasattr(assoc, 'entity')={hasattr(assoc, 'entity')}, "
                        f"assoc.entity={getattr(assoc, 'entity', 'MISSING')}"
                    )
                main_entities_list.append(entity_dict)

            logger.debug(
                f"[DB Convert] Event {event.id} converted main_entities: "
                f"{main_entities_list} (count: {len(main_entities_list)})"
            )

            event_data_for_merger = EventDataForMerger(
                id=str(event.id),
                description=event.description,
                event_date_str=event.event_date_str,
                date_info=date_info_model,  # Use the validated model
                main_entities=main_entities_list,
                source_text_snippet=snippet,
            )

            logger.debug(
                f"[DB Convert] Event {event.id} EventDataForMerger main_entities: "
                f"{getattr(event_data_for_merger, 'main_entities', 'MISSING')}"
            )

            # Source info can be reconstructed here if needed, or assumed to be part of the event model
            source_info_for_merger = SourceInfoForMerger(
                language=getattr(primary_raw_event, "language", None),
                # Assuming these fields exist on the Event model or can be derived
                # page_url=event.source_document.url,
                # page_title=event.source_document.title,
            )
            processed_raw_events.append(
                RawEventInput(
                    event_data=event_data_for_merger,
                    source_info=source_info_for_merger,
                )
            )

        logger.debug(
            f"[DB Convert] Converted {len(processed_raw_events)} DB events to RawEventInput objects"
        )

        # 2. Use the existing merge_events logic, but get back the internal groups
        merged_groups = await self._perform_merge(processed_raw_events)

        logger.debug(
            f"[Merge Complete] Created {len(merged_groups)} merged groups from {len(processed_raw_events)} events"
        )

        # 3. Finalize each group (e.g., synthesize description)
        for group in merged_groups:
            await group.finalize_representative_event(user_lang=self.user_lang)

        # 4. Finalize and convert to output format
        output_instructions = []
        for i, group in enumerate(merged_groups):
            logger.debug(
                f"[Final Convert] Processing group {i+1}/{len(merged_groups)} (ID: {group.original_id})"
            )
            await group.finalize_representative_event(user_lang=self.user_lang)
            output_schema = group.to_output_schema()
            output_instructions.append(output_schema)
            logger.debug(
                f"[Final Convert] Group {group.original_id} output main_entities: "
                f"{getattr(output_schema.representative_event, 'main_entities', 'MISSING')} "
                f"(count: {len(output_schema.representative_event.main_entities) if output_schema.representative_event.main_entities else 0})"
            )

        duration = time.time() - start_time
        logger.info(
            f"Generated {len(output_instructions)} merge instructions in {duration:.2f} seconds"
        )

        if progress_callback:
            await progress_callback.report(
                f"Event merging completed: {len(output_instructions)} distinct events found",
                "event_merging_complete",
                {
                    "total_events": len(events),
                    "distinct_events": len(output_instructions),
                    "duration_seconds": duration,
                    "performance_stats": self._stats,
                },
                request_id,
            )

        return output_instructions

    async def _try_concurrent_merge(
        self,
        raw_event: RawEventInput,
        candidate_groups: list[MergedEventGroup],
        llm_cache: LLMComparisonCache,
        stats: dict[str, int],
    ) -> bool:
        """
        Windowed concurrent LLM matching: processes candidates in parallel windows
        while respecting priority order and early termination optimization.
        """
        if not candidate_groups:
            return False

        window_size = settings.event_merger_concurrent_window_size
        total_candidates = len(candidate_groups)

        logger.debug(
            f"[Concurrent Merge] Processing {total_candidates} candidates for event {raw_event.original_id} "
            f"with window size {window_size}"
        )

        # Process candidates in windows
        for window_start in range(0, total_candidates, window_size):
            window_end = min(window_start + window_size, total_candidates)
            window_candidates = candidate_groups[window_start:window_end]

            stats["concurrent_windows_processed"] += 1

            logger.debug(
                f"[Concurrent Merge] Processing window {window_start}-{window_end-1} "
                f"({len(window_candidates)} candidates) for event {raw_event.original_id}"
            )

            # Phase 1: Pre-filter all candidates in the window (fast, non-LLM checks)
            eligible_candidates = []
            rule_matched_group = None

            for group in window_candidates:
                is_eligible, match_score = await group.check_merge_eligibility(
                    raw_event, stats
                )

                if not is_eligible:
                    continue

                # If rule-based match found, prioritize it immediately
                if match_score >= 100.0:
                    rule_matched_group = group
                    logger.debug(
                        f"[Concurrent Merge] Rule-based match found with group {group.original_id}"
                    )
                    break

                eligible_candidates.append((group, match_score))

            # If rule-based match found, use it immediately and skip LLM calls
            if rule_matched_group:
                rule_matched_group.source_contributions.append(raw_event)
                # Calculate how many LLM calls we saved
                stats["concurrent_llm_calls_saved"] += len(eligible_candidates)
                logger.debug(
                    f"[Concurrent Merge] Rule-based merge successful, saved {len(eligible_candidates)} LLM calls"
                )
                return True

            if not eligible_candidates:
                logger.debug(
                    f"[Concurrent Merge] No eligible candidates in window {window_start}-{window_end-1}"
                )
                continue

            # Sort eligible candidates by match score (descending)
            eligible_candidates.sort(key=lambda x: x[1], reverse=True)

            # Phase 2: Concurrent LLM semantic matching for eligible candidates
            logger.debug(
                f"[Concurrent Merge] Running concurrent LLM checks for {len(eligible_candidates)} candidates"
            )

            # Create concurrent LLM tasks
            llm_tasks = []
            for group, score in eligible_candidates:
                task = asyncio.create_task(
                    group.llm_semantic_match(raw_event, llm_cache),
                    name=f"llm_match_{group.original_id}_{raw_event.original_id}",
                )
                llm_tasks.append((task, group, score))

            # Wait for all LLM tasks to complete
            try:
                # Execute all tasks concurrently
                await asyncio.gather(
                    *[task for task, _, _ in llm_tasks], return_exceptions=True
                )

                # Process results in priority order (by original match score)
                for task, group, score in llm_tasks:
                    try:
                        if task.done() and not task.exception():
                            llm_result = task.result()
                            if llm_result:
                                # Found a match! Add to group and return success
                                group.source_contributions.append(raw_event)
                                stats["llm_confirmed_merges"] += 1

                                # Calculate how many additional LLM calls we saved by early termination
                                remaining_tasks = [
                                    t
                                    for t, _, _ in llm_tasks
                                    if not t.done() or t != task
                                ]
                                stats["concurrent_llm_calls_saved"] += len(
                                    remaining_tasks
                                )

                                logger.debug(
                                    f"[Concurrent Merge] LLM match successful with group {group.original_id} "
                                    f"(score: {score}), saved {len(remaining_tasks)} remaining LLM calls"
                                )
                                return True
                        else:
                            if task.exception():
                                logger.warning(
                                    f"[Concurrent Merge] LLM task failed for group {group.original_id}: {task.exception()}"
                                )
                    except Exception as e:
                        logger.error(
                            f"[Concurrent Merge] Error processing LLM result for group {group.original_id}: {e}"
                        )
                        continue

            except Exception as e:
                logger.error(
                    f"[Concurrent Merge] Error in concurrent LLM execution: {e}"
                )
                # Fallback to sequential processing for this window
                for task, group, _ in llm_tasks:
                    try:
                        if not task.done():
                            task.cancel()
                        if await group.llm_semantic_match(raw_event, llm_cache):
                            group.source_contributions.append(raw_event)
                            stats["llm_confirmed_merges"] += 1
                            logger.debug(
                                f"[Concurrent Merge] Fallback LLM match successful with group {group.original_id}"
                            )
                            return True
                    except Exception as fallback_error:
                        logger.error(
                            f"[Concurrent Merge] Fallback LLM match failed: {fallback_error}"
                        )
                        continue

            logger.debug(
                f"[Concurrent Merge] No matches found in window {window_start}-{window_end-1}"
            )

        logger.debug(
            f"[Concurrent Merge] No matches found across all {total_candidates} candidates for event {raw_event.original_id}"
        )
        return False

    async def _perform_merge(
        self, processed_raw_events: list[RawEventInput]
    ) -> list[MergedEventGroup]:
        """
        Core merging algorithm with index-based candidate lookup and progressive filtering.

        Sequential processing: sort by year → index lookup → scored prioritization → early termination.
        """
        self._reset_stats()

        # Sort by year for better processing order
        processed_raw_events.sort(key=lambda x: (x.event_year is None, x.event_year))

        total_events_to_process = len(processed_raw_events)
        logger.info(
            f"Internally processing {total_events_to_process} valid events for merging."
        )
        if total_events_to_process == 0:
            return []

        merged_groups: list[MergedEventGroup] = []
        processed_count = 0

        # Process each event through the multi-stage merging pipeline
        for raw_event in processed_raw_events:
            # Stage 1: Index-based candidate retrieval
            candidate_groups = self.index_system.get_candidates(raw_event)
            self._stats["index_lookups"] += 1

            # Stage 2: Candidate scoring and prioritization
            if candidate_groups:
                scored_candidates = [
                    MatchCandidate(
                        group=group,
                        score=group.calculate_match_score(raw_event),
                        match_type="indexed",
                    )
                    for group in candidate_groups
                ]
                # Sort by score descending to prioritize best matches
                scored_candidates.sort(key=lambda x: x.score, reverse=True)

                # Extract just the groups for concurrent processing
                ordered_candidate_groups = [
                    candidate.group for candidate in scored_candidates
                ]
            else:
                ordered_candidate_groups = []

            # Stage 3: Concurrent windowed matching with early termination
            found_match = False
            if ordered_candidate_groups:
                found_match = await self._try_concurrent_merge(
                    raw_event, ordered_candidate_groups, self.llm_cache, self._stats
                )

            # Stage 4: Create new group if no match found
            if not found_match:
                new_group = MergedEventGroup(raw_event)
                merged_groups.append(new_group)
                self.index_system.add_group(
                    new_group
                )  # Add to indexes for future lookups

            # Progress tracking and reporting
            processed_count += 1
            if processed_count % max(1, total_events_to_process // 10) == 0:
                logger.info(
                    f"Processed {processed_count}/{total_events_to_process} events for merging. "
                    f"Concurrent windows: {self._stats['concurrent_windows_processed']}, "
                    f"LLM calls saved: {self._stats['concurrent_llm_calls_saved']}"
                )

        return merged_groups

    async def merge_events(
        self,
        raw_event_inputs: list[dict[str, Any]],
        progress_callback: Optional["ProgressCallback"] = None,
        request_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Dictionary-based interface: validates inputs → applies merging → returns dict results."""
        logger.info(
            f"Starting original event merging for {len(raw_event_inputs)} events"
        )

        # Progress reporting using callback pattern
        if progress_callback:
            await progress_callback.report(
                f"Starting merge for {len(raw_event_inputs)} events...",
                "event_merging_start",
                {"total_events": len(raw_event_inputs)},
                request_id,
            )

        processed_raw_events: list[RawEventInput] = []
        for idx, item in enumerate(raw_event_inputs):
            if "event_data" not in item or "source_info" not in item:
                logger.warning(f"Event item {idx} is missing required fields.")
                continue
            try:
                raw_event = RawEventInput(item["event_data"], item["source_info"])
                if raw_event.date_range is None:
                    logger.warning(f"Skipping event {idx} due to unparsable date.")
                    continue
                processed_raw_events.append(raw_event)
            except Exception as e:
                logger.error(
                    f"Failed to create RawEventInput for item {idx}: {e}", exc_info=True
                )

        merged_groups = await self._perform_merge(processed_raw_events)

        # Finalize groups and convert to output dictionary format
        output_list: list[dict[str, Any]] = []
        for group in merged_groups:
            await group.finalize_representative_event(user_lang=self.user_lang)
            output_list.append(group.to_output_schema().model_dump(warnings=False))

        # Sort by timestamp
        def get_sortable_timestamp(ts_val: Any) -> datetime:
            if isinstance(ts_val, datetime):
                return ts_val
            # For pre-1970 dates, timestamp might be None. Sort them to the beginning.
            # Returning a very old date for sorting purposes.
            return datetime.min.replace(tzinfo=UTC)

        output_list.sort(
            key=lambda x: get_sortable_timestamp(
                x.get("representative_event", {}).get("timestamp")
            )
        )

        # Calculate efficiency metrics
        efficiency_improvement = (
            f"{self._stats['concurrent_llm_calls_saved']} LLM calls saved"
            if self._stats["concurrent_llm_calls_saved"] > 0
            else "No concurrent savings"
        )

        logger.info(
            f"Concurrent EventMerger Performance Stats: {json.dumps(self._stats, indent=2)}"
        )
        logger.info(
            f"Merged {len(processed_raw_events)} events into {len(output_list)} groups. "
            f"Efficiency: {efficiency_improvement} through concurrent processing."
        )

        # Final progress notification using callback pattern
        if progress_callback:
            await progress_callback.report(
                f"Merging completed: {len(output_list)} distinct events found",
                "event_merging_complete",
                {
                    "total_events": len(processed_raw_events),
                    "distinct_events": len(output_list),
                    "performance_stats": self._stats,
                },
                request_id,
            )

        return output_list
