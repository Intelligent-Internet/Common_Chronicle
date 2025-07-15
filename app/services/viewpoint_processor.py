"""
Viewpoint processing utilities for keyword extraction and multi-language content retrieval.

This module handles the initial processing of user viewpoints (research questions or topics)
by extracting relevant keywords and gathering Wikipedia content in multiple languages.
It serves as the foundation for building comprehensive timelines from user input.
"""

import asyncio
import json
import time
from typing import Any

import httpx

from app.config import settings
from app.prompts import KEYWORD_EXTRACTION_SYSTEM_PROMPT
from app.schemas import KeywordExtractionResult
from app.services.llm_interface import LLMInterface
from app.services.llm_service import get_llm_client
from app.services.wiki_crosslingual_extractor import get_wiki_page_text_for_target_lang
from app.services.wiki_extractor import get_wiki_page_text
from app.utils.logger import setup_logger
from app.utils.wiki_optimization import (
    AdaptiveSemaphore,
    execute_with_retry_and_metrics,
)

logger = setup_logger("viewpoint_processor", level="DEBUG")


# Use adaptive semaphore for better performance
wiki_api_semaphore = AdaptiveSemaphore(
    initial_limit=settings.wiki_api_semaphore_limit,
    min_limit=max(1, settings.wiki_api_semaphore_limit // 3),
    max_limit=min(10, settings.wiki_api_semaphore_limit * 2),
)

DEFAULT_LLM_TIMEOUT_KEYWORD = 60  # Default value if not in config


async def _fetch_wiki_page_text_concurrently(
    keyword: str, lang: str, parent_request_id: str | None = None
):
    return await execute_with_retry_and_metrics(
        lambda: asyncio.to_thread(get_wiki_page_text, keyword, lang),
        operation_name=f"get_wiki_page_text({keyword}, {lang})",
        parent_request_id=parent_request_id,
    )


async def _fetch_wiki_page_text_for_target_lang_concurrently(
    source_page_title: str,
    source_lang: str,
    target_lang: str,
    parent_request_id: str | None = None,
):
    return await execute_with_retry_and_metrics(
        lambda: asyncio.to_thread(
            get_wiki_page_text_for_target_lang,
            source_page_title,
            source_lang,
            target_lang,
        ),
        operation_name=f"get_wiki_page_text_for_target_lang({source_page_title}, {source_lang}, {target_lang})",
        parent_request_id=parent_request_id,
    )


async def extract_keywords_from_viewpoint(
    viewpoint: str,
    parent_request_id: str | None = None,
) -> KeywordExtractionResult:
    # LLM-based keyword extraction with language detection and translation support
    log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""

    if not viewpoint or not viewpoint.strip():
        logger.warning(f"{log_prefix}Empty or whitespace-only viewpoint provided")
        return KeywordExtractionResult(error="Empty viewpoint provided")

    viewpoint_length = len(viewpoint)
    logger.info(
        f"{log_prefix}Starting keyword extraction and language detection from viewpoint: '{viewpoint[:100]}{'...' if viewpoint_length > 100 else ''}'"
    )
    logger.debug(f"{log_prefix}Full viewpoint text: {viewpoint}")

    # Get LLM client
    llm_client: LLMInterface | None = get_llm_client(settings.default_llm_provider)
    if not llm_client:
        error_msg = f"{log_prefix}Could not retrieve LLM client for keyword extraction"
        logger.error(error_msg)
        return KeywordExtractionResult(error="LLM service not available")

    logger.debug(f"{log_prefix}Using LLM provider: {settings.default_llm_provider}")

    try:
        messages = [
            {"role": "system", "content": KEYWORD_EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f'User Query: "{viewpoint}"\nExpected JSON Output:',
            },
        ]

        llm_call_start_time = time.monotonic()
        logger.info(f"{log_prefix}Making request to LLM API for keyword extraction.")

        chat_completion_response = await llm_client.generate_chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=max(
                2000, settings.llm_default_max_tokens
            ),  # Use configured default as minimum baseline
            response_format={"type": "json_object"},
        )

        llm_call_duration = time.monotonic() - llm_call_start_time
        logger.info(
            f"{log_prefix}LLM call for keyword extraction completed in {llm_call_duration:.2f}s"
        )
        if llm_call_duration > 30:
            logger.warning(
                f"{log_prefix}Slow LLM response for keyword extraction: {llm_call_duration:.2f}s"
            )

        raw_content = chat_completion_response["choices"][0]["message"]["content"]
        # logger.debug(f"{log_prefix}Raw LLM keyword response: {raw_content}")

        # Parse and validate the JSON response
        data = json.loads(raw_content)
        detected_language = data.get("detected_language", "und")
        original_keywords = data.get("original_keywords", [])
        english_keywords = data.get("english_keywords", [])
        translated_viewpoint = data.get("translated_viewpoint")

        if not isinstance(original_keywords, list) or not isinstance(
            english_keywords, list
        ):
            raise ValueError("Keywords are not lists in LLM response.")

        if len(original_keywords) != len(english_keywords):
            logger.warning(
                f"{log_prefix}Mismatch in keyword list lengths: "
                f"original ({len(original_keywords)}) vs english ({len(english_keywords)}). "
                "The lists will be cleared."
            )
            # Clearing lists because we can't trust the correspondence
            original_keywords = []
            english_keywords = []

        logger.info(
            f"{log_prefix}Successfully extracted {len(english_keywords)} keywords for detected language '{detected_language}'. "
            f"Original: {original_keywords}, English: {english_keywords}"
        )

        if translated_viewpoint:
            logger.info(
                f"{log_prefix}Successfully extracted translated viewpoint: '{translated_viewpoint[:100]}{'...' if len(translated_viewpoint) > 100 else ''}'"
            )

        return KeywordExtractionResult(
            original_keywords=original_keywords,
            english_keywords=english_keywords,
            viewpoint_language=detected_language,
            translated_viewpoint=translated_viewpoint,
        )

    except json.JSONDecodeError as e:
        logger.error(
            f"{log_prefix}Failed to decode JSON from LLM response: {e}. Raw response: '{raw_content}'",
            exc_info=True,
        )
        return KeywordExtractionResult(error="Invalid JSON response from LLM")
    except Exception as e:
        logger.error(
            f"{log_prefix}An unexpected error occurred during keyword extraction: {e}",
            exc_info=True,
        )
        return KeywordExtractionResult(error=f"An unexpected error occurred: {e}")


async def get_multilingual_wiki_texts_for_keyword_set(
    keywords: list[str],
    user_detected_lang: str,
    http_client: httpx.AsyncClient,
    parent_request_id: str | None = None,
) -> list[dict[str, Any]]:
    # Batch Wikipedia text fetching: user language + English with cross-lingual fallback
    # Returns dict format for backward compatibility
    log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
    logger.info(
        f"{log_prefix}Starting to fetch multilingual Wikipedia texts for {len(keywords)} keywords: {keywords}"
    )
    all_texts_data = []
    processed_eng_titles = (
        set()
    )  # To avoid fetching English text for the same title multiple times if keywords overlap

    # Phase 1: Fetch English texts for all unique keywords
    english_fetch_tasks = []
    keyword_map_for_eng_tasks = []  # To map results back

    for keyword in keywords:
        if keyword.lower() not in processed_eng_titles:
            # Use the new concurrent wrapper for English text fetching
            english_fetch_tasks.append(
                _fetch_wiki_page_text_concurrently(
                    keyword, "en", parent_request_id=parent_request_id
                )
            )
            keyword_map_for_eng_tasks.append(keyword)
            processed_eng_titles.add(keyword.lower())

    logger.info(
        f"{log_prefix}Fetching English Wikipedia texts for {len(keyword_map_for_eng_tasks)} unique keywords (concurrency limit: {settings.wiki_api_semaphore_limit}): {keyword_map_for_eng_tasks}"
    )
    english_results = await asyncio.gather(*english_fetch_tasks, return_exceptions=True)

    for i, eng_result_item in enumerate(english_results):
        original_keyword = keyword_map_for_eng_tasks[i]
        if isinstance(eng_result_item, Exception):
            logger.error(
                f"{log_prefix}Error fetching English text for keyword '{original_keyword}': {eng_result_item}"
            )
            continue
        if eng_result_item.error:
            logger.warning(
                f"{log_prefix}Error reported by get_wiki_page_text for English keyword '{original_keyword}': {eng_result_item.error}"
            )
            # We might still want to proceed to cross-lingual lookup even if English fetch had issues (e.g., page missing)
            # The cross-lingual lookup uses the original keyword as source.

        eng_text = eng_result_item.text
        eng_final_title = eng_result_item.title or original_keyword
        eng_actual_content_url = eng_result_item.url

        if eng_text:  # Only add if text was actually extracted
            all_texts_data.append(
                {
                    "keyword": original_keyword,
                    "text": eng_text,
                    "lang": "en",
                    "title": eng_final_title,
                    "url": eng_actual_content_url,  # For English, this is the same as actual_content_url
                    "actual_content_url": eng_actual_content_url,
                }
            )
            logger.info(
                f"{log_prefix}Successfully fetched English text for keyword '{original_keyword}' (Title: '{eng_final_title}', URL: {eng_actual_content_url}). Length: {len(eng_text)}"
            )
        else:
            logger.info(
                f"{log_prefix}No English text extracted for keyword '{original_keyword}' (Final title considered: '{eng_final_title}', URL: {eng_actual_content_url}). Error (if any): {eng_result_item.error}"
            )

    # Phase 2: If user_detected_lang is not English, attempt cross-lingual fetch for each original keyword
    if user_detected_lang != "en" and user_detected_lang not in [
        "und",
        "zxx",
    ]:  # also check for undetermined/no linguistic content
        logger.info(
            f"{log_prefix}User detected language is '{user_detected_lang}'. Attempting to fetch cross-lingual texts (concurrency limit: {settings.wiki_api_semaphore_limit})."
        )

        # Create tasks for fetching text in the target language for each keyword
        # Note: get_wiki_page_text_for_target_lang takes the *original English keyword* as source_page_title
        # and 'en' as source_lang.
        cross_lingual_fetch_tasks = [
            # Use the new concurrent wrapper for cross-lingual text fetching
            _fetch_wiki_page_text_for_target_lang_concurrently(
                source_page_title=keyword,
                source_lang="en",
                target_lang=user_detected_lang,
                parent_request_id=parent_request_id,
            )
            for keyword in keywords  # Iterate through all original keywords for cross-lingual lookup
        ]

        keyword_map_for_cross_tasks = keywords[:]  # To map results back

        logger.info(
            f"{log_prefix}Fetching '{user_detected_lang}' Wikipedia texts for {len(keywords)} keywords (source lang 'en', concurrency limit: {settings.wiki_api_semaphore_limit})."
        )
        cross_lingual_results = await asyncio.gather(
            *cross_lingual_fetch_tasks, return_exceptions=True
        )

        for i, cross_result_item in enumerate(cross_lingual_results):
            original_keyword_for_cross = keyword_map_for_cross_tasks[i]
            if isinstance(cross_result_item, Exception):
                logger.error(
                    f"{log_prefix}Exception during cross-lingual text fetch for source_keyword '{original_keyword_for_cross}' (en -> {user_detected_lang}): {cross_result_item}"
                )
                continue

            if cross_result_item.overall_status == "success":
                text = cross_result_item.text
                final_target_title = cross_result_item.link_search_outcome.target_title
                # This URL is the one for the page title in the target language, from langlink search
                interlang_url = cross_result_item.link_search_outcome.target_url
                # This is the crucial one: the URL from which text was actually extracted in the target language
                actual_content_url_cross = cross_result_item.url

                if (
                    text and actual_content_url_cross
                ):  # Ensure both text and its actual URL are present
                    all_texts_data.append(
                        {
                            "keyword": original_keyword_for_cross,  # The original English keyword
                            "text": text,
                            "lang": user_detected_lang,
                            "title": (
                                final_target_title if final_target_title else "N/A"
                            ),
                            "url": interlang_url,  # URL of the target lang page link
                            "actual_content_url": actual_content_url_cross,  # URL of the content source
                        }
                    )
                    logger.info(
                        f"{log_prefix}Successfully fetched text for '{original_keyword_for_cross}' (en) in '{user_detected_lang}'. "
                        f"Target Title: '{final_target_title}', Content URL: {actual_content_url_cross}. Length: {len(text)}"
                    )
                elif text and not actual_content_url_cross:
                    logger.warning(
                        f"{log_prefix}Text extracted for '{original_keyword_for_cross}' (en) in '{user_detected_lang}' (Title: {final_target_title}), but actual_content_url was missing. Skipping this entry."
                    )
                elif not text:
                    logger.info(
                        f"{log_prefix}Cross-lingual search for '{original_keyword_for_cross}' (en -> {user_detected_lang}) was successful in finding link, but no text extracted. "
                        f"Target Title: '{final_target_title}', Attempted URL: {actual_content_url_cross}, Error: {cross_result_item.error}"
                    )

            else:
                error_msg = cross_result_item.error or "Unknown error"
                status = cross_result_item.overall_status or "unknown_status"
                logger.info(
                    f"{log_prefix}Failed to get text for '{original_keyword_for_cross}' (en) in '{user_detected_lang}'. Status: {status}. Error: {error_msg}"
                )
    else:
        if user_detected_lang == "en":
            logger.info(
                f"{log_prefix}User detected language is 'en'. No cross-lingual fetch needed."
            )
        else:  # und or zxx
            logger.info(
                f"{log_prefix}User detected language is '{user_detected_lang}'. Skipping cross-lingual fetch."
            )

    # Deduplication based on actual_content_url before returning
    final_unique_texts_data = []
    seen_content_urls = set()
    for item in all_texts_data:
        content_url = item.get("actual_content_url")
        if content_url and content_url not in seen_content_urls:
            final_unique_texts_data.append(item)
            seen_content_urls.add(content_url)
            logger.debug(
                f"{log_prefix}Adding item with unique content URL: {content_url} (Keyword: {item['keyword']}, Lang: {item['lang']})"
            )
        elif content_url and content_url in seen_content_urls:
            logger.info(
                f"{log_prefix}Skipping duplicate content URL: {content_url} (Keyword: {item['keyword']}, Lang: {item['lang']})"
            )
        elif not content_url:
            # This case should ideally not happen if we successfully extracted text
            logger.warning(
                f"{log_prefix}Item found without actual_content_url, will be included if not otherwise duplicative based on other criteria (but primary key for dedupe is URL here). Item: {item.get('keyword')}, {item.get('lang')}"
            )
            final_unique_texts_data.append(item)

    logger.info(
        f"{log_prefix}Returning {len(final_unique_texts_data)} unique text items after processing {len(keywords)} keywords (user_lang: {user_detected_lang})."
    )
    return final_unique_texts_data
