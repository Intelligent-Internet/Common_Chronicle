"""
Event Relevance Service - Intelligent Event Filtering and Relevance Scoring

This service provides sophisticated filtering capabilities for extracted events,
evaluating their relevance to the user's original research viewpoint. It ensures
that only highly relevant events are included in the final timeline results.
"""

import json
import time
from typing import Any

from app.config import settings
from app.prompts import (
    EVENT_RELEVANCE_BATCH_SYSTEM_PROMPT,
    EVENT_RELEVANCE_SYSTEM_PROMPT,
)
from app.services.llm_interface import LLMInterface
from app.services.llm_service import get_llm_client
from app.utils.logger import setup_logger

logger = setup_logger("event_relevance_service", level="DEBUG")


class EventRelevanceService:
    """
    Service for evaluating the relevance of extracted events to the user's original viewpoint.

    This service filters out events that are not sufficiently related to the user's research intent,
    improving the quality and focus of the final timeline results.

    The service supports both single-event and batch processing modes:
    - Single-event mode: Each event is evaluated individually (default when batch_size=1)
    - Batch mode: Multiple events are evaluated in a single LLM call (when batch_size>1)
    """

    def __init__(self, relevance_threshold: float = 0.6, batch_size: int = 10):
        self.relevance_threshold = relevance_threshold
        self.batch_size = max(1, batch_size)

    async def filter_relevant_events(
        self,
        all_extracted_events: list[dict[str, Any]],
        original_viewpoint: str,
        parent_request_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Filter events based on their relevance to the original user viewpoint.
        Supports both single-event and batch processing modes.
        """

        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""

        if not all_extracted_events:
            logger.warning(f"{log_prefix}No events provided for relevance filtering")
            return [], {"total_events": 0, "relevant_events": 0, "filter_rate": 0.0}

        if not original_viewpoint or not original_viewpoint.strip():
            logger.warning(
                f"{log_prefix}Empty original viewpoint provided, returning all events"
            )
            return all_extracted_events, {
                "total_events": len(all_extracted_events),
                "relevant_events": len(all_extracted_events),
                "filter_rate": 0.0,
            }

        logger.info(
            f"{log_prefix}Starting relevance filtering for {len(all_extracted_events)} events "
            f"against viewpoint: '{original_viewpoint[:100]}...'"
        )

        # Get LLM client
        llm_client: LLMInterface | None = get_llm_client(settings.default_llm_provider)
        if not llm_client:
            logger.error(
                f"{log_prefix}Could not retrieve LLM client for relevance evaluation. Returning all events."
            )
            return all_extracted_events, {
                "total_events": len(all_extracted_events),
                "relevant_events": len(all_extracted_events),
                "filter_rate": 0.0,
                "error": "LLM service not available",
            }

        relevant_events = []
        processing_start_time = time.monotonic()
        successful_evaluations = 0
        failed_evaluations = 0
        batch_successes = 0
        batch_failures = 0

        # Process events in batches if batch_size > 1
        if self.batch_size > 1:
            logger.info(
                f"{log_prefix}Using batch processing mode with size {self.batch_size}"
            )

            # Split events into batches
            for i in range(0, len(all_extracted_events), self.batch_size):
                batch = all_extracted_events[i : i + self.batch_size]
                batch_number = (i // self.batch_size) + 1

                try:
                    # Try batch processing first
                    batch_results = await self._evaluate_events_batch(
                        original_viewpoint=original_viewpoint,
                        events_batch=batch,
                        llm_client=llm_client,
                        parent_request_id=parent_request_id,
                        batch_number=batch_number,
                    )

                    if batch_results:
                        # Batch processing succeeded
                        batch_successes += 1
                        for event_idx, score in batch_results.items():
                            event_wrapper = batch[event_idx]
                            event_wrapper["relevance_score"] = score

                            if score >= self.relevance_threshold:
                                relevant_events.append(event_wrapper)
                                successful_evaluations += 1
                            else:
                                logger.debug(
                                    f"{log_prefix}Event {i + event_idx + 1} filtered out "
                                    f"(batch score: {score:.2f})"
                                )
                    else:
                        # Batch processing failed, fallback to individual processing
                        batch_failures += 1
                        logger.warning(
                            f"{log_prefix}Batch {batch_number} processing failed, "
                            "falling back to individual processing"
                        )
                        await self._process_events_individually(
                            batch,
                            original_viewpoint,
                            llm_client,
                            parent_request_id,
                            i,
                            relevant_events,
                            successful_evaluations,
                            failed_evaluations,
                        )

                except Exception as e:
                    batch_failures += 1
                    logger.error(
                        f"{log_prefix}Error processing batch {batch_number}: {e}",
                        exc_info=True,
                    )
                    # Fallback to individual processing
                    await self._process_events_individually(
                        batch,
                        original_viewpoint,
                        llm_client,
                        parent_request_id,
                        i,
                        relevant_events,
                        successful_evaluations,
                        failed_evaluations,
                    )
        else:
            # Process events individually (original mode)
            logger.info(f"{log_prefix}Using individual processing mode")
            await self._process_events_individually(
                all_extracted_events,
                original_viewpoint,
                llm_client,
                parent_request_id,
                0,
                relevant_events,
                successful_evaluations,
                failed_evaluations,
            )

        processing_duration = time.monotonic() - processing_start_time
        total_events = len(all_extracted_events)
        relevant_count = len(relevant_events)
        filter_rate = (
            ((total_events - relevant_count) / total_events * 100)
            if total_events > 0
            else 0.0
        )

        logger.info(
            f"{log_prefix}Relevance filtering completed in {processing_duration:.2f}s. "
            f"Results: {relevant_count}/{total_events} events relevant "
            f"(filtered {filter_rate:.1f}%). "
            f"Successful evaluations: {successful_evaluations}, Failed: {failed_evaluations}"
        )

        if self.batch_size > 1:
            logger.info(
                f"{log_prefix}Batch processing stats - "
                f"Successful batches: {batch_successes}, Failed batches: {batch_failures}"
            )

        statistics = {
            "total_events": total_events,
            "relevant_events": relevant_count,
            "filtered_events": total_events - relevant_count,
            "filter_rate": filter_rate,
            "successful_evaluations": successful_evaluations,
            "failed_evaluations": failed_evaluations,
            "processing_duration": processing_duration,
            "relevance_threshold": self.relevance_threshold,
            "batch_size": self.batch_size,
            "batch_successes": batch_successes,
            "batch_failures": batch_failures,
        }

        return relevant_events, statistics

    async def _process_events_individually(
        self,
        events: list[dict[str, Any]],
        original_viewpoint: str,
        llm_client: LLMInterface,
        parent_request_id: str | None,
        start_index: int,
        relevant_events: list[dict[str, Any]],
        successful_evaluations: int,
        failed_evaluations: int,
    ) -> None:
        """
        Process a list of events individually using the single-event evaluation method.
        This is used both as the default processing mode and as a fallback when batch processing fails.
        """
        for i, event_wrapper in enumerate(events):
            try:
                event_data = event_wrapper.get("event_data", {})
                event_description = event_data.get("description", "")

                if not event_description:
                    logger.warning(
                        f"Event {start_index + i + 1} has no description, skipping relevance check"
                    )
                    failed_evaluations += 1
                    continue

                relevance_score = await self._evaluate_event_relevance(
                    original_viewpoint=original_viewpoint,
                    event_description=event_description,
                    llm_client=llm_client,
                    parent_request_id=parent_request_id,
                    event_index=start_index + i + 1,
                )

                if relevance_score is not None:
                    successful_evaluations += 1
                    event_wrapper["relevance_score"] = relevance_score

                    if relevance_score >= self.relevance_threshold:
                        relevant_events.append(event_wrapper)
                else:
                    failed_evaluations += 1

            except Exception as e:
                failed_evaluations += 1
                logger.error(
                    f"Error evaluating relevance for event {start_index + i + 1}: {e}",
                    exc_info=True,
                )

    # TODO: Add batch size limits, automatically split if exceeded
    async def _evaluate_events_batch(
        self,
        original_viewpoint: str,
        events_batch: list[dict[str, Any]],
        llm_client: LLMInterface,
        parent_request_id: str | None = None,
        batch_number: int = 1,
    ) -> dict[int, float] | None:
        """
        Evaluate the relevance of multiple events in a single LLM call.
        """
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""

        try:
            llm_call_start_time = time.monotonic()

            # Prepare the batch evaluation prompt
            events_list = []
            for i, event_wrapper in enumerate(events_batch, 1):
                event_data = event_wrapper.get("event_data", {})
                event_description = event_data.get("description", "")
                if event_description:
                    events_list.append(f"{i}. {event_description}")

            if not events_list:
                logger.warning(f"{log_prefix}No valid events in batch {batch_number}")
                return None

            user_prompt = f"""
Original Viewpoint: "{original_viewpoint}"

Events to Evaluate:
{chr(10).join(events_list)}

Relevance Scores:"""

            # Estimate the required tokens for the response.
            # Each entry is approx. '{"event_index": 12, "relevance_score": 0.25},' -> ~40-50 tokens
            # We add a buffer.
            estimated_tokens_per_event = 50
            max_output_tokens = (len(events_batch) * estimated_tokens_per_event) + 100

            try:
                chat_completion_response = await llm_client.generate_chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": EVENT_RELEVANCE_BATCH_SYSTEM_PROMPT,
                        },
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=max_output_tokens,
                    extra_body={
                        "timeout": 60
                    },  # Increased timeout for batch processing
                )
            except Exception as e:
                logger.error(
                    f"{log_prefix}LLM API call failed during batch evaluation: {e}"
                )
                return None

            llm_call_duration = time.monotonic() - llm_call_start_time

            if not chat_completion_response or not chat_completion_response.get(
                "choices"
            ):
                logger.error(
                    f"{log_prefix}LLM returned empty response for batch {batch_number}"
                )
                return None

            # Extract and parse the batch results
            content = chat_completion_response["choices"][0]["message"][
                "content"
            ].strip()

            # TODO: Should be wrapped in json parser instead of special handling here
            try:
                # Clean up potential markdown code fences from the LLM response
                if "```" in content:
                    # Extract content between the first and last triple backticks
                    parts = content.split("```")
                    if len(parts) >= 2:
                        content = parts[1]
                        # If the block is labeled (e.g., ```json), remove the label
                        if content.lower().startswith("json"):
                            content = content[4:].strip()

                results = json.loads(content)
                if not isinstance(results, list):
                    logger.error(
                        f"{log_prefix}Invalid JSON format in batch {batch_number}: not a list"
                    )
                    return None

                # Convert to internal 0-based indices and validate scores
                processed_results = {}
                for result in results:
                    if not isinstance(result, dict):
                        continue

                    event_index = result.get("event_index")
                    score = result.get("relevance_score")

                    if event_index is None or score is None:
                        continue

                    # Convert 1-based index from LLM to 0-based index for internal use
                    internal_index = event_index - 1

                    # Validate the index is within range
                    if 0 <= internal_index < len(events_batch):
                        # Validate and clamp the score to [0.0, 1.0]
                        processed_results[internal_index] = max(
                            0.0, min(1.0, float(score))
                        )

                if processed_results:
                    logger.debug(
                        f"{log_prefix}Batch {batch_number} evaluated in {llm_call_duration:.2f}s: "
                        f"{len(processed_results)} valid results"
                    )
                    return processed_results
                else:
                    logger.warning(
                        f"{log_prefix}No valid results in batch {batch_number} response"
                    )
                    return None

            except json.JSONDecodeError as e:
                logger.error(
                    f"{log_prefix}Failed to parse JSON from batch {batch_number}: {e}. "
                    f"Raw response: '{content}'"
                )
                return None
            except (ValueError, TypeError) as e:
                logger.error(
                    f"{log_prefix}Error processing batch {batch_number} results: {e}"
                )
                return None

        except Exception as e:
            logger.error(
                f"{log_prefix}Exception during batch {batch_number} evaluation: {e}",
                exc_info=True,
            )
            return None

    async def _evaluate_event_relevance(
        self,
        original_viewpoint: str,
        event_description: str,
        llm_client: LLMInterface,
        parent_request_id: str | None = None,
        event_index: int = 0,
    ) -> float | None:
        """
        Evaluate the relevance of a single event to the original viewpoint using LLM.
        """
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""

        try:
            llm_call_start_time = time.monotonic()

            # Prepare the evaluation prompt
            user_prompt = f"""
Original Viewpoint: "{original_viewpoint}"

Event to Evaluate: "{event_description}"

Relevance Score:"""

            # Make LLM call for relevance evaluation
            chat_completion_response = await llm_client.generate_chat_completion(
                messages=[
                    {"role": "system", "content": EVENT_RELEVANCE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,  # Low temperature for consistent scoring
                max_tokens=10,  # We only need a single number
                extra_body={
                    "timeout": 30
                },  # 30 second timeout for individual evaluations
            )

            llm_call_duration = time.monotonic() - llm_call_start_time

            if not chat_completion_response or not chat_completion_response.get(
                "choices"
            ):
                logger.error(
                    f"{log_prefix}LLM returned empty response for event {event_index} relevance evaluation"
                )
                return None

            # Extract and parse the relevance score
            content = chat_completion_response["choices"][0]["message"][
                "content"
            ].strip()

            try:
                relevance_score = float(content)

                # Validate score is in expected range
                if 0.0 <= relevance_score <= 1.0:
                    logger.debug(
                        f"{log_prefix}Event {event_index} relevance evaluated in {llm_call_duration:.2f}s: "
                        f"score = {relevance_score:.2f}"
                    )
                    return relevance_score
                else:
                    logger.warning(
                        f"{log_prefix}Event {event_index} relevance score out of range (0.0-1.0): {relevance_score}. "
                        f"Raw response: '{content}'"
                    )
                    return None

            except (ValueError, TypeError) as e:
                logger.warning(
                    f"{log_prefix}Failed to parse relevance score for event {event_index}: '{content}'. Error: {e}"
                )
                return None

        except Exception as e:
            logger.error(
                f"{log_prefix}Exception during relevance evaluation for event {event_index}: {e}",
                exc_info=True,
            )
            return None
