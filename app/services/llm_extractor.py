"""
LLM Extractor Service - Advanced Event Extraction and Processing

This module provides sophisticated LLM-powered functionality for extracting, parsing,
and processing historical events from text content. It serves as the core intelligence
layer for the Common Chronicle system's event extraction pipeline.
"""

import asyncio
import hashlib
import json
import time

import httpx
from openai import BadRequestError

from app.config import settings
from app.prompts import (
    ARTICLE_RELEVANCE_PROMPT,
    DATE_PARSING_BATCH_PROMPT,
    DATE_PARSING_PROMPT,
    EXTRACT_TIMELINE_EVENTS_PROMPT,
    LLM_LANG_DETECT_SYSTEM_PROMPT,
)
from app.schemas import ParsedDateInfo, ProcessedEvent, RawLLMEvent
from app.services.llm_interface import LLMInterface
from app.services.llm_service import get_llm_client
from app.utils.json_parser import extract_json_from_llm_response
from app.utils.logger import setup_logger

logger = setup_logger("llm_extractor", level="DEBUG")


async def extract_events_from_chunks(
    chunks: list[str],
    parent_request_id: str | None = None,
) -> list[ProcessedEvent]:
    """
    Extract events from multiple text chunks in parallel.

    This function processes text chunks concurrently to extract events,
    handling failures gracefully to ensure one chunk's failure doesn't
    affect others.

    Args:
        chunks: List of text chunks to process
        parent_request_id: Request ID for logging and tracking

    Returns:
        Combined list of all extracted events from all chunks
    """
    if not chunks:
        logger.warning(
            f"[ParentReqID: {parent_request_id}] No chunks provided for event extraction"
        )
        return []

    logger.info(
        f"[ParentReqID: {parent_request_id}] Starting parallel event extraction from {len(chunks)} chunks"
    )

    # Create async tasks for each chunk
    tasks = []
    for i, chunk in enumerate(chunks):
        task = _extract_events_from_single_chunk(
            chunk, i + 1, len(chunks), parent_request_id
        )
        tasks.append(task)

    # Execute all tasks concurrently
    chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results and collect all events
    all_events = []
    successful_chunks = 0
    failed_chunks = 0

    for i, result in enumerate(chunk_results):
        if isinstance(result, Exception):
            logger.error(
                f"[ParentReqID: {parent_request_id}] Chunk {i + 1} failed with exception: {result}",
                exc_info=False,
            )
            failed_chunks += 1
        elif isinstance(result, list):
            chunk_events = result
            all_events.extend(chunk_events)
            successful_chunks += 1
            logger.info(
                f"[ParentReqID: {parent_request_id}] Chunk {i + 1} extracted {len(chunk_events)} events"
            )
        else:
            logger.warning(
                f"[ParentReqID: {parent_request_id}] Chunk {i + 1} returned unexpected result type: {type(result)}"
            )
            failed_chunks += 1

    logger.info(
        f"[ParentReqID: {parent_request_id}] Parallel extraction complete: "
        f"{successful_chunks} successful, {failed_chunks} failed chunks. "
        f"Total events extracted: {len(all_events)}"
    )

    return all_events


async def _extract_events_from_single_chunk(
    chunk: str,
    chunk_number: int,
    total_chunks: int,
    parent_request_id: str | None = None,
) -> list[ProcessedEvent]:
    """
    Extract events from a single text chunk with error handling.

    This is a wrapper around extract_timeline_events_from_text that adds
    chunk-specific logging and error handling.

    Args:
        chunk: Text chunk to process
        chunk_number: Current chunk number (1-based)
        total_chunks: Total number of chunks being processed
        parent_request_id: Request ID for logging

    Returns:
        List of events extracted from the chunk
    """
    log_prefix = (
        f"[ParentReqID: {parent_request_id}] Chunk {chunk_number}/{total_chunks}"
    )

    try:
        logger.debug(
            f"{log_prefix} Starting event extraction (chunk length: {len(chunk)})"
        )

        # Call the existing event extraction function
        events = await extract_timeline_events_from_text(chunk)

        logger.debug(f"{log_prefix} Successfully extracted {len(events)} events")
        return events

    except Exception as e:
        logger.error(f"{log_prefix} Failed to extract events: {e}", exc_info=True)
        # Return empty list instead of raising exception to prevent
        # one chunk's failure from affecting others
        return []


async def parse_date_string_with_llm(
    date_str: str,
) -> ParsedDateInfo | None:
    """
    Uses a dedicated LLM call to parse a single date string into a structured object.
    """
    logger.debug(f"Parsing date string: '{date_str}'")
    llm_service_client: LLMInterface | None = get_llm_client(
        settings.default_llm_provider
    )
    if not llm_service_client:
        logger.error("LLM client not available for date parsing.")
        return None

    try:
        completion = await llm_service_client.generate_chat_completion(
            messages=[
                {"role": "system", "content": DATE_PARSING_PROMPT},
                {"role": "user", "content": date_str},
            ],
            temperature=0.0,
            extra_body={"timeout": 30.0},
        )

        raw_content = (
            completion.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        if not raw_content:
            logger.warning(
                f"LLM returned empty content for date parsing of '{date_str}'"
            )
            return None

        parsed_json = extract_json_from_llm_response(raw_content)
        if not parsed_json:
            logger.error(
                f"Failed to extract JSON from date parsing response for '{date_str}'. Content: {raw_content}"
            )
            return None

        return ParsedDateInfo(**parsed_json)

    except Exception as e:
        logger.error(
            f"Error during LLM date parsing for '{date_str}': {e}", exc_info=True
        )
        return None


async def parse_date_strings_batch_with_llm(
    date_items: list[dict[str, str]],
) -> dict[str, ParsedDateInfo]:
    """
    Uses a single, optimized LLM call to parse a batch of date strings.
    """
    if not date_items:
        return {}

    logger.info(f"Starting batch date parsing for {len(date_items)} items.")
    llm_service_client: LLMInterface | None = get_llm_client(
        settings.default_llm_provider
    )
    if not llm_service_client:
        logger.error("LLM client not available for batch date parsing.")
        return {}

    # The input to the prompt is a JSON string of the list of items
    prompt_input = json.dumps(date_items, indent=2)

    try:
        completion = await llm_service_client.generate_chat_completion(
            messages=[
                {"role": "system", "content": DATE_PARSING_BATCH_PROMPT},
                {"role": "user", "content": prompt_input},
            ],
            temperature=0.0,
            extra_body={"timeout": 120.0},  # Increased timeout for batch jobs
        )

        raw_content = (
            completion.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        if not raw_content:
            logger.warning("LLM returned empty content for batch date parsing.")
            return {}

        parsed_json = extract_json_from_llm_response(raw_content)
        if not isinstance(parsed_json, list):
            logger.error(
                f"Batch date parsing did not return a list. Content: {raw_content}"
            )
            return {}

        # Convert the list of results into a dictionary for easy lookup
        results_map: dict[str, ParsedDateInfo] = {}
        for item in parsed_json:
            try:
                item_id = item.get("id")
                parsed_info = item.get("parsed_info")
                if item_id and parsed_info:
                    results_map[item_id] = ParsedDateInfo(**parsed_info)
            except Exception as e:
                logger.error(
                    f"Failed to parse item in batch response: {item}. Error: {e}",
                    exc_info=True,
                )
                continue

        logger.info(f"Successfully parsed {len(results_map)} items in batch.")
        return results_map

    except Exception as e:
        logger.error(f"Error during LLM batch date parsing: {e}", exc_info=True)
        return {}


def _deduplicate_extracted_events(events: list[ProcessedEvent]) -> list[ProcessedEvent]:
    """
    Remove duplicate events from the extracted events list.

    This function uses the same deduplication logic as the database layer
    to prevent constraint violations during batch insertion.
    """
    if not events:
        return events

    seen_signatures = set()
    unique_events = []

    for event in events:
        # Generate the same signature that will be used in the database
        signature_input = f"{event.description}-{event.event_date_str}"
        deduplication_signature = hashlib.sha256(signature_input.encode()).hexdigest()

        if deduplication_signature not in seen_signatures:
            seen_signatures.add(deduplication_signature)
            unique_events.append(event)
        else:
            logger.debug(
                f"Filtered duplicate event: '{event.description[:100]}...' "
                f"with date '{event.event_date_str}'"
            )

    duplicates_removed = len(events) - len(unique_events)
    if duplicates_removed > 0:
        logger.info(f"Removed {duplicates_removed} duplicate events during extraction")

    return unique_events


async def extract_timeline_events_from_text(
    input_text: str,
) -> list[ProcessedEvent]:
    """
    Uses a two-step LLM process to extract structured timeline event data from text.
    1. Extracts raw events (description, date string, entities).
    2. Parses the extracted date string into a structured ParsedDateInfo object.
    """
    logger.info(
        f"ENTERING extract_timeline_events_from_text for text length: {len(input_text) if input_text else 0}"
    )

    llm_service_client: LLMInterface | None = get_llm_client(
        settings.default_llm_provider
    )
    if not llm_service_client:
        logger.error("Could not retrieve LLM client. Aborting event extraction.")
        return []

    try:
        # --- Step 1: Extract Raw Events ---
        logger.info("Step 1: Extracting raw events from text.")

        # Estimate the number of tokens needed for the response
        # Based on text length, estimate number of events and calculate required tokens
        text_length = len(input_text) if input_text else 0
        estimated_events = max(
            1, text_length // 800
        )  # More conservative: 1 event per 800 chars instead of 1000

        # Each event JSON structure needs approximately 300-500 tokens
        # Include buffer for safety - increase based on real-world observations
        estimated_tokens_per_event = (
            1200  # Increased from 800 to 1200 for better safety
        )
        base_tokens = 3000  # Increased from 2000 to 3000 for JSON structure overhead

        # Calculate estimated tokens, but use default max_tokens as minimum baseline
        estimated_tokens = base_tokens + (estimated_events * estimated_tokens_per_event)

        # Add additional safety buffer for complex JSON structures
        safety_multiplier = 1.5  # 50% safety buffer
        estimated_tokens_with_buffer = int(estimated_tokens * safety_multiplier)

        estimated_max_tokens = min(
            settings.llm_event_extraction_max_tokens,
            max(
                settings.llm_default_max_tokens,  # Use default as minimum baseline
                estimated_tokens_with_buffer,
            ),
        )

        logger.debug(
            f"Text length: {text_length}, estimated events: {estimated_events}, base estimated tokens: {estimated_tokens}, with buffer: {estimated_tokens_with_buffer}, max_tokens: {estimated_max_tokens} (min baseline: {settings.llm_default_max_tokens})"
        )

        chat_completion_response = await llm_service_client.generate_chat_completion(
            messages=[
                {"role": "system", "content": EXTRACT_TIMELINE_EVENTS_PROMPT},
                {
                    "role": "user",
                    "content": f"Please extract timeline events from the following text: \n\n{input_text}",
                },
            ],
            temperature=0.1,
            max_tokens=estimated_max_tokens,
            extra_body={"timeout": settings.llm_timeout_extract},
        )

        raw_content = (
            chat_completion_response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not raw_content:
            logger.warning("Step 1: Empty content in LLM response for raw extraction.")
            return []

        logger.debug(f"Step 1: Raw LLM response length: {len(raw_content)} characters")

        parsed_raw_events_json = extract_json_from_llm_response(raw_content)
        if not isinstance(parsed_raw_events_json, list):
            logger.error(f"Step 1: Parsed JSON is not a list. Content: {raw_content}")

            # Enhanced truncation detection - check for multiple indicators
            is_truncated = False
            truncation_indicators = [
                # Common JSON truncation patterns
                (",", "{", '["', '"'),  # Original patterns
                # Additional patterns for field names and values
                ('name":', 'type":', 'language":', '"zh'),
                # Incomplete JSON structures
                ('event_description":', 'event_date_str":', "main_entities"),
                # Partial closing patterns
                ("]", "}]", "}]}"),
                # Any text that doesn't end with complete JSON
                ("```", "```json"),
            ]

            # Check for incomplete JSON structure
            trimmed_content = raw_content.rstrip()

            # Check if content ends with any truncation indicators
            for indicator_group in truncation_indicators:
                if any(
                    trimmed_content.endswith(pattern) for pattern in indicator_group
                ):
                    is_truncated = True
                    break

            # Additional check: if JSON parsing failed and content is substantial, likely truncated
            if not is_truncated and len(raw_content) > 1000:
                # Try to detect if it looks like incomplete JSON
                if (
                    raw_content.count("[") != raw_content.count("]")
                    or raw_content.count("{") != raw_content.count("}")
                    or raw_content.count('"') % 2 != 0
                ):
                    is_truncated = True
                    logger.info(
                        "Step 1: Detected JSON truncation based on unmatched brackets/quotes"
                    )

            if is_truncated:
                logger.warning(
                    "Step 1: JSON appears to be truncated, attempting retry with higher max_tokens"
                )

                # Retry with increased max_tokens
                retry_estimated_tokens = estimated_tokens_with_buffer * 2
                retry_max_tokens = min(
                    settings.llm_event_extraction_retry_max_tokens,
                    max(
                        settings.llm_default_max_tokens,  # Use default as minimum baseline
                        retry_estimated_tokens,
                    ),
                )
                logger.info(
                    f"Step 1: Retrying with increased max_tokens: {retry_max_tokens} (retry estimated: {retry_estimated_tokens}, min baseline: {settings.llm_default_max_tokens})"
                )

                try:
                    retry_response = await llm_service_client.generate_chat_completion(
                        messages=[
                            {
                                "role": "system",
                                "content": EXTRACT_TIMELINE_EVENTS_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": f"Please extract timeline events from the following text: \n\n{input_text}",
                            },
                        ],
                        temperature=0.1,
                        max_tokens=retry_max_tokens,
                        extra_body={"timeout": settings.llm_timeout_extract},
                    )

                    retry_content = (
                        retry_response.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )

                    if retry_content:
                        logger.info(
                            f"Step 1: Retry response length: {len(retry_content)} characters"
                        )
                        parsed_raw_events_json = extract_json_from_llm_response(
                            retry_content
                        )

                        if isinstance(parsed_raw_events_json, list):
                            logger.info("Step 1: Retry successful, got valid JSON list")
                            raw_content = retry_content  # Update for logging
                        else:
                            logger.error(
                                "Step 1: Retry also failed to produce valid JSON list"
                            )

                            # If first retry fails, try with maximum tokens
                            if (
                                retry_max_tokens
                                < settings.llm_event_extraction_retry_max_tokens
                            ):
                                logger.warning(
                                    "Step 1: Attempting final retry with maximum tokens"
                                )
                                final_retry_response = await llm_service_client.generate_chat_completion(
                                    messages=[
                                        {
                                            "role": "system",
                                            "content": EXTRACT_TIMELINE_EVENTS_PROMPT,
                                        },
                                        {
                                            "role": "user",
                                            "content": f"Please extract timeline events from the following text: \n\n{input_text}",
                                        },
                                    ],
                                    temperature=0.1,
                                    max_tokens=settings.llm_event_extraction_retry_max_tokens,
                                    extra_body={
                                        "timeout": settings.llm_timeout_extract
                                    },
                                )

                                final_retry_content = (
                                    final_retry_response.get("choices", [{}])[0]
                                    .get("message", {})
                                    .get("content", "")
                                )

                                if final_retry_content:
                                    logger.info(
                                        f"Step 1: Final retry response length: {len(final_retry_content)} characters"
                                    )
                                    parsed_raw_events_json = (
                                        extract_json_from_llm_response(
                                            final_retry_content
                                        )
                                    )

                                    if isinstance(parsed_raw_events_json, list):
                                        logger.info(
                                            "Step 1: Final retry successful, got valid JSON list"
                                        )
                                        raw_content = final_retry_content
                                    else:
                                        logger.error(
                                            "Step 1: Final retry also failed, giving up"
                                        )
                                        return []
                                else:
                                    logger.error(
                                        "Step 1: Final retry returned empty content"
                                    )
                                    return []
                            else:
                                return []
                    else:
                        logger.error("Step 1: Retry returned empty content")
                        return []

                except Exception as e:
                    logger.error(f"Step 1: Retry failed with exception: {e}")
                    return []
            else:
                return []

        if not isinstance(parsed_raw_events_json, list):
            logger.error(
                f"Step 1: Final parsed JSON is not a list. Content: {raw_content}"
            )
            return []

        logger.info(f"Step 1: LLM extracted {len(parsed_raw_events_json)} raw events.")

        # --- Step 1.5: Data Quality Check ---
        logger.info("Step 1.5: Filtering events with missing required fields.")

        # Filter out events with missing required fields
        valid_events = []
        skipped_count = 0

        for i, event_data in enumerate(parsed_raw_events_json):
            # Check for required fields
            if not event_data.get("event_date_str"):
                logger.debug(
                    f"Skipping event {i} (missing event_date_str): "
                    f"description={event_data.get('event_description', 'N/A')[:50]}..."
                )
                skipped_count += 1
                continue

            if not event_data.get("event_description"):
                logger.debug(
                    f"Skipping event {i} (missing event_description): "
                    f"date_str={event_data.get('event_date_str', 'N/A')}"
                )
                skipped_count += 1
                continue

            valid_events.append(event_data)

        if skipped_count > 0:
            logger.warning(
                f"Filtered out {skipped_count} events with missing required fields."
            )

        # Update the events list to use only valid events
        parsed_raw_events_json = valid_events

        if not parsed_raw_events_json:
            logger.warning("No valid events remaining after data quality check.")
            return []

        logger.info(
            f"Step 1.5: {len(parsed_raw_events_json)} valid events remaining after quality check."
        )

        # --- Step 2: Batch Parse Date for All Events ---
        logger.info("Step 2: Batch parsing date strings for all extracted events.")

        # Prepare data for batch parsing
        date_parsing_requests = []
        # Use a temporary mapping from a unique ID to the original raw_event
        raw_events_map = {}

        for i, event_data in enumerate(parsed_raw_events_json):
            try:
                logger.debug(f"Raw event data: {event_data}")

                # Data normalization - ensure optional fields have default values
                # (Required fields are already validated in Step 1.5)
                if not isinstance(event_data.get("main_entities"), list):
                    logger.debug(f"Setting empty main_entities list for event {i}")
                    event_data["main_entities"] = []

                # FIXED: Don't set empty string for source_text_snippet if it's missing from LLM
                # Let RawLLMEvent validation handle this - it's a required field
                if not event_data.get("source_text_snippet"):
                    logger.warning(
                        f"Event {i} missing source_text_snippet from LLM response. "
                        f"This should not happen as it's a required field in the prompt. "
                        f"Event description: {event_data.get('event_description', 'N/A')[:100]}..."
                    )
                    # Skip this event if it doesn't have source_text_snippet
                    continue

                raw_event = RawLLMEvent(**event_data)
                event_id = f"event_{i}"

                # Build date string for parsing: combine original and enhanced if available
                if raw_event.enhanced_event_date_str:
                    # Format: "original_date(enhanced_date)"
                    date_str_for_parsing = f"{raw_event.event_date_str}({raw_event.enhanced_event_date_str})"
                    logger.debug(
                        f"Using combined date for parsing: '{date_str_for_parsing}'"
                    )
                else:
                    # Use original date string only
                    date_str_for_parsing = raw_event.event_date_str
                    logger.debug(
                        f"Using original date for parsing: '{raw_event.event_date_str}'"
                    )

                date_parsing_requests.append(
                    {"id": event_id, "date_str": date_str_for_parsing}
                )
                raw_events_map[event_id] = raw_event
            except Exception as e:
                logger.error(
                    f"Failed to parse raw event data, skipping: {e}", exc_info=True
                )
                continue

        # Perform the single batch call
        parsed_dates_map = await parse_date_strings_batch_with_llm(
            date_parsing_requests
        )

        # --- Step 3: Combine Results ---
        logger.info("Step 3: Combining raw events with parsed dates.")
        processed_events: list[ProcessedEvent] = []
        for event_id, date_info in parsed_dates_map.items():
            logger.debug(f"event_id: {event_id}, date_info: {date_info}")
            raw_event = raw_events_map.get(event_id)
            if not raw_event:
                logger.warning(
                    f"Could not find original raw event for parsed date id: {event_id}"
                )
                continue

            try:
                processed_event = ProcessedEvent(
                    description=raw_event.event_description,
                    event_date_str=raw_event.event_date_str,
                    date_info=date_info,
                    main_entities=raw_event.main_entities,
                    source_text_snippet=raw_event.source_text_snippet,
                )
                processed_events.append(processed_event)
            except Exception as e:
                logger.error(
                    f"Failed to create ProcessedEvent for id {event_id}: {e}",
                    exc_info=True,
                )
                continue

        logger.info(
            f"Successfully created {len(processed_events)} processed events after batch date parsing."
        )

        # --- Step 4: Deduplicate Events ---
        if processed_events:
            logger.info("Step 4: Deduplicating processed events.")
            deduplicated_events = _deduplicate_extracted_events(processed_events)
            logger.info(
                f"Event deduplication complete: kept {len(deduplicated_events)} unique events."
            )
            processed_events = deduplicated_events

        logger.info("EXITING extract_timeline_events_from_text (Success path)")
        return processed_events

    except httpx.TimeoutException as e:
        error_msg = f"LLM call for event extraction timed out after {settings.llm_timeout_extract}s: {e}"
        logger.error(error_msg, exc_info=True)
        logger.info(
            "EXITING extract_timeline_events_from_text (Error: httpx.TimeoutException)"
        )
        return []

    except BadRequestError as e:
        # Attempt to parse the error response body
        try:
            error_body = e.response.json()
            error_message = error_body.get("error", {}).get("message", "")
        except json.JSONDecodeError:
            error_message = e.response.text

        if "Content Exists Risk" in error_message:
            logger.warning(
                f"Skipping article due to content filter risk: {error_message}"
            )
            return []
        else:
            logger.error(f"BadRequestError during event extraction: {e}", exc_info=True)
            raise e

    except Exception as e:
        error_msg = f"Unexpected error in extract_timeline_events_from_text: {e}"
        logger.error(error_msg, exc_info=True)
        logger.info(
            "EXITING extract_timeline_events_from_text (Error: General Exception)"
        )
        return []


async def detect_language_with_llm(
    text: str,
    parent_request_id: str | None = None,
    timeout_seconds: int = 30,
) -> str:
    log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
    logger.debug(f"{log_prefix}Detecting language for text: {text[:100]}...")

    # Get LLM client from the service
    llm_service_client: LLMInterface | None = get_llm_client(
        settings.default_llm_provider
    )
    if not llm_service_client:
        logger.error(
            f"{log_prefix}Could not retrieve OpenAI client. Language detection via LLM failed."
        )
        return "und"  # Undetermined

    try:
        llm_call_start_time = time.monotonic()
        logger.info(
            f"{log_prefix}Making request to LLM API, timeout: {timeout_seconds}s) for language detection."
        )
        # Use the new service client
        chat_completion_response = await llm_service_client.generate_chat_completion(
            messages=[
                {"role": "system", "content": LLM_LANG_DETECT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0,
            extra_body={
                "timeout": timeout_seconds
            },  # Pass OpenAI-specific timeout via extra_body for openai-python v1.x
        )
        llm_call_duration = time.monotonic() - llm_call_start_time

        if not chat_completion_response or not chat_completion_response.get("choices"):
            logger.error(
                f"{log_prefix}LLM response for language detection is empty or invalid."
            )
            return "und"

        lang_code = (
            chat_completion_response["choices"][0]["message"]["content"].strip().lower()
        )
        logger.info(
            f"{log_prefix}LLM call for language detection completed in {llm_call_duration:.2f} seconds. Detected language: {lang_code}"
        )
        return lang_code
    except (
        httpx.TimeoutException
    ) as e:  # This might be specific to httpx, OpenAI client might raise its own TimeoutError
        logger.error(
            f"{log_prefix}LLM call for language detection timed out after {timeout_seconds}s: {e}"
        )
        return "und"
    except (
        Exception
    ) as e:  # Catch more general exceptions from the llm_service_client call
        logger.error(
            f"{log_prefix}Error detecting language with LLM: {e}", exc_info=True
        )
        return "und"


async def score_articles_relevance(
    viewpoint_text: str,
    articles: list[
        dict[str, str]
    ],  # Expects a list of dicts with "title" and "text_content"
    parent_request_id: str | None = None,
    timeout_seconds: int = 120,
) -> dict[str, float]:
    # LLM-based relevance scoring: returns dict mapping article titles to scores (0.0-1.0)
    log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
    logger.info(
        f"{log_prefix}Starting article relevance scoring for viewpoint: '{viewpoint_text[:100]}...'"
    )

    if not articles:
        logger.warning(f"{log_prefix}No articles provided for relevance scoring.")
        return {}

    llm_service_client: LLMInterface | None = get_llm_client(
        settings.default_llm_provider
    )
    if not llm_service_client:
        logger.error(
            f"{log_prefix}Could not retrieve LLM client. Aborting relevance scoring."
        )
        return {}

    # Prepare article data for the prompt, truncating content to be safe.
    # Use more content for better relevance assessment, but still within reasonable limits
    articles_for_prompt = [
        {
            "title": article.get("title", "No Title"),
            "content": article.get("text_content", "")[:1500]
            + (
                "..." if len(article.get("text_content", "")) > 1500 else ""
            ),  # Increased from 500 to 1500 chars
        }
        for article in articles
    ]
    articles_json = json.dumps(articles_for_prompt, indent=2)

    prompt = ARTICLE_RELEVANCE_PROMPT.format(
        viewpoint_text=viewpoint_text, articles_json=articles_json
    )

    try:
        llm_call_start_time = time.monotonic()
        logger.info(
            f"{log_prefix}Making request to LLM API (timeout: {timeout_seconds}s) for article relevance scoring."
        )

        chat_completion_response = await llm_service_client.generate_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that provides relevance scores in JSON format.",
                },  # A simple system message
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            extra_body={"timeout": timeout_seconds},
        )
        llm_call_duration = time.monotonic() - llm_call_start_time
        logger.info(
            f"{log_prefix}LLM call for relevance scoring completed in {llm_call_duration:.2f}s"
        )

        if not chat_completion_response:
            logger.error(
                f"{log_prefix}LLM returned None response for relevance scoring."
            )
            return {}

        choices = chat_completion_response.get("choices", [])
        if not choices:
            logger.error(
                f"{log_prefix}No choices found in LLM response for relevance scoring."
            )
            return {}

        raw_content = choices[0].get("message", {}).get("content", "")
        if not raw_content:
            logger.warning(
                f"{log_prefix}Empty content in LLM response for relevance scoring."
            )
            return {}

        parsed_scores = extract_json_from_llm_response(raw_content)

        if not parsed_scores or not isinstance(parsed_scores, dict):
            logger.error(
                f"{log_prefix}Failed to extract a valid JSON object from LLM response. Content: {raw_content}"
            )
            return {}

        # Validate that values are floats
        validated_scores = {}
        for title, score in parsed_scores.items():
            try:
                validated_scores[title] = float(score)
            except (ValueError, TypeError):
                logger.warning(
                    f"{log_prefix}Invalid score value for title '{title}': {score}. Skipping."
                )
                continue

        logger.info(
            f"{log_prefix}Successfully scored {len(validated_scores)} articles for relevance."
        )
        return validated_scores

    except httpx.TimeoutException as e:
        logger.error(
            f"{log_prefix}LLM call for relevance scoring timed out after {timeout_seconds}s: {e}"
        )
        return {}
    except Exception as e:
        logger.error(
            f"{log_prefix}Unexpected error during article relevance scoring: {e}",
            exc_info=True,
        )
        return {}
