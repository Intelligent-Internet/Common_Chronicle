"""
Article Acquisition Strategies - Comprehensive Multi-Source Content Retrieval

This module implements various strategies for acquiring articles from different sources,
each optimized for specific use cases and data sources. The strategies follow a common
interface but provide specialized implementations for different content acquisition needs.

All strategies implement the DataAcquisitionStrategy abstract base class, ensuring
consistent behavior while allowing for source-specific optimizations. The module
supports both online and offline acquisition methods with sophisticated error handling
and performance optimization.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any

import httpx
import requests

from app.config import settings
from app.schemas import SourceArticle, WikinewsSearchResponse
from app.services.article_acquisition.components import SemanticSearchComponent
from app.services.wiki_crosslingual_extractor import get_wiki_page_text_for_target_lang
from app.services.wiki_extractor import get_wiki_page_text
from app.services.wikinews_extractor import get_wikinews_page_text
from app.utils.logger import setup_logger
from app.utils.wiki_optimization import (
    AdaptiveSemaphore,
    WikiErrorType,
    classify_wiki_error,
    create_optimized_http_client,
    get_retry_delay,
    should_retry_error,
    wiki_metrics,
)

logger = setup_logger("article_acquisition_strategies")


class DataAcquisitionStrategy(ABC):
    @abstractmethod
    async def get_articles(
        self,
        query_data: dict[str, Any],
        # config: Optional[Dict[str, Any]] = None # Strategy-specific config if needed later
    ) -> list[SourceArticle]:
        # Abstract method: fetch articles based on query data (keywords, language, etc.)
        """
        Fetches articles based on the query data.
        """


class OnlineWikipediaStrategy(DataAcquisitionStrategy):
    # Live Wikipedia article fetching with multilingual and cross-lingual support

    def __init__(self, semaphore_limit: int = settings.wiki_api_semaphore_limit):
        # Use adaptive semaphore for better performance
        self.adaptive_semaphore = AdaptiveSemaphore(
            initial_limit=semaphore_limit,
            min_limit=max(2, semaphore_limit // 3),
            max_limit=min(15, semaphore_limit * 2),
        )

    async def _execute_wiki_api_call_with_retry(
        self,
        func,  # The synchronous wiki function to call
        keyword_or_title: str,
        lang: str,
        http_client: httpx.AsyncClient,  # Moved before optional arguments
        target_lang_for_crosslingual: str
        | None = None,  # Only for get_wiki_page_text_for_target_lang
        parent_request_id: str | None = None,
    ) -> dict[str, Any]:
        # Adaptive retry wrapper for wiki API calls with metrics and error classification
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
        func_name_for_log = func.__name__

        # Adjusting args based on the function being called
        if func is get_wiki_page_text_for_target_lang:
            args_for_log = (keyword_or_title, lang, target_lang_for_crosslingual)
            current_args = (keyword_or_title, lang, target_lang_for_crosslingual)
        else:  # for get_wiki_page_text
            args_for_log = (keyword_or_title, lang)
            current_args = (keyword_or_title, lang)

        last_exception = None

        # Use adaptive semaphore
        async with self.adaptive_semaphore:
            for attempt in range(settings.max_wiki_retries):
                try:
                    # Run synchronous function in a separate thread
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, func, *current_args)

                    # result is a Pydantic model (e.g., WikiPageTextResponse). Use attribute access.
                    if result.error and not result.text:
                        error_type = classify_wiki_error(
                            Exception(result.error), result.model_dump()
                        )

                        logger.warning(
                            f"{log_prefix}{func_name_for_log}{args_for_log} reported error (attempt {attempt+1}/{settings.max_wiki_retries}): {result.error} (type: {error_type.value})"
                        )

                        # Check if we should retry based on error type
                        if not should_retry_error(error_type, attempt):
                            return result.model_dump()  # Return dict for consistency

                    elif not result.text and not result.error:
                        # This case might occur if a page exists but no content could be extracted (e.g. disambiguation)
                        logger.info(
                            f"{log_prefix}{func_name_for_log}{args_for_log} returned no text and no error (attempt {attempt+1}/{settings.max_wiki_retries}). Assuming non-retryable."
                        )
                        return result.model_dump()  # Return dict for consistency

                    return result.model_dump()  # Success: return dict for consistency

                except requests.exceptions.RequestException as e:
                    last_exception = e
                    error_type = classify_wiki_error(e)

                    logger.warning(
                        f"{log_prefix}RequestException for {func_name_for_log}{args_for_log} (attempt {attempt+1}/{settings.max_wiki_retries}): {e!r} (type: {error_type.value}). Retrying..."
                    )

                    if not should_retry_error(error_type, attempt):
                        break

                    if attempt < settings.max_wiki_retries - 1:
                        delay = get_retry_delay(attempt, error_type)
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{log_prefix}Max retries for {func_name_for_log}{args_for_log}. Error: {e!r}"
                        )
                        break

                except Exception as e:  # Catch any other unexpected errors
                    logger.error(
                        f"{log_prefix}Unexpected error in _execute_wiki_api_call_with_retry for {func_name_for_log}{args_for_log} (attempt {attempt+1}): {e!r}",
                        exc_info=True,
                    )
                    last_exception = e
                    break  # Break on unexpected errors

        # If all retries failed
        error_type = (
            classify_wiki_error(last_exception)
            if last_exception
            else WikiErrorType.UNKNOWN
        )
        error_message = f"{log_prefix}Failed {func_name_for_log}{args_for_log} after {settings.max_wiki_retries} retries. Last error: {str(last_exception)} (type: {error_type.value})"
        logger.error(error_message)

        # Record error metrics
        wiki_metrics.record_request(
            success=False, response_time=0, error_type=error_type
        )

        # Return a consistent error structure
        final_title_val = keyword_or_title  # Fallback
        final_url_val = ""  # Fallback

        return {
            "error": error_message,
            "text": None,
            "title": final_title_val,
            "url": final_url_val,
            "redirect_info": None,
            "status": (
                error_type.value if error_type else "unknown_error"
            ),  # Include error type info
        }

    async def _fetch_english_article(
        self,
        keyword: str,
        http_client: httpx.AsyncClient,
        parent_request_id: str | None = None,
    ) -> SourceArticle | None:
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
        logger.info(
            f"{log_prefix}Fetching English Wikipedia text for keyword: '{keyword}'"
        )

        eng_result_item = await self._execute_wiki_api_call_with_retry(
            get_wiki_page_text,
            keyword,
            "en",
            http_client,  # Pass http_client here
            parent_request_id=parent_request_id,
        )

        if eng_result_item.get("error") and not eng_result_item.get("text"):
            logger.warning(
                f"{log_prefix}Error reported by get_wiki_page_text for English keyword '{keyword}': {eng_result_item.get('error')}"
            )
            return None

        eng_text = eng_result_item.get("text")
        eng_final_title = eng_result_item.get("title") or keyword
        eng_actual_content_url = eng_result_item.get("url") or ""
        # Use page_id as the definitive unique identifier for Wikipedia articles
        eng_page_id = eng_result_item.get("page_id")

        if eng_text and eng_actual_content_url and eng_page_id:
            logger.info(
                f"{log_prefix}Successfully fetched English text for keyword '{keyword}' (Title: '{eng_final_title}', URL: {eng_actual_content_url}, PageID: {eng_page_id}). Length: {len(eng_text)}"
            )
            return SourceArticle(
                source_name="online_wikipedia",
                source_url=eng_actual_content_url,
                source_identifier=str(
                    eng_page_id
                ),  # Use pageid as the unique identifier
                title=eng_final_title,
                text_content=eng_text,
                language="en",
                metadata={
                    "original_keyword": keyword,
                    "retrieved_title": eng_final_title,
                    "retrieved_url": eng_actual_content_url,
                    "page_id": eng_page_id,
                },
            )
        else:
            logger.info(
                f"{log_prefix}No English text extracted for keyword '{keyword}' or missing URL/PageID. (Final title considered: '{eng_final_title}', URL: {eng_actual_content_url}). Error (if any): {eng_result_item.get('error')}"
            )
            return None

    async def _fetch_target_lang_article(
        self,
        keyword: str,
        target_lang: str,
        http_client: httpx.AsyncClient,
        parent_request_id: str | None = None,
    ) -> SourceArticle | None:
        """Fetches a Wikipedia article directly in the specified target language."""
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
        logger.info(
            f"{log_prefix}Fetching Wikipedia text for keyword: '{keyword}' in language: '{target_lang}'"
        )

        result_item = await self._execute_wiki_api_call_with_retry(
            get_wiki_page_text,
            keyword,
            target_lang,  # Use the target_lang parameter
            http_client,
            parent_request_id=parent_request_id,
        )

        if isinstance(result_item, Exception):
            logger.error(
                f"{log_prefix}Unhandled exception fetching text for keyword '{keyword}' in lang '{target_lang}': {result_item}"
            )
            return None

        if result_item.get("error") and not result_item.get("text"):
            logger.warning(
                f"{log_prefix}Error reported by get_wiki_page_text for keyword '{keyword}' in lang '{target_lang}': {result_item.get('error')}"
            )
            return None

        text_content = result_item.get("text")
        final_title = result_item.get("title") or keyword
        actual_content_url = result_item.get("url") or ""
        page_id = result_item.get("page_id")

        if text_content and actual_content_url and page_id:
            logger.info(
                f"{log_prefix}Successfully fetched text for keyword '{keyword}' in lang '{target_lang}' (Title: '{final_title}', URL: {actual_content_url}, PageID: {page_id}). Length: {len(text_content)}"
            )
            return SourceArticle(
                source_name="online_wikipedia",
                source_url=actual_content_url,
                source_identifier=str(page_id),  # Use pageid as the unique identifier
                title=final_title,
                text_content=text_content,
                language=target_lang,
                metadata={
                    "original_keyword": keyword,
                    "retrieved_title": final_title,
                    "retrieved_url": actual_content_url,
                    "fetch_language": target_lang,
                    "page_id": page_id,
                },
            )
        else:
            logger.info(
                f"{log_prefix}No text extracted for keyword '{keyword}' in lang '{target_lang}' or missing URL/PageID. (Final title considered: '{final_title}', URL: {actual_content_url}). Error (if any): {result_item.get('error')}"
            )
            return None

    async def _fetch_crosslingual_article(
        self,
        english_keyword: str,
        target_lang: str,
        http_client: httpx.AsyncClient,
        parent_request_id: str | None = None,
    ) -> SourceArticle | None:
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
        logger.info(
            f"{log_prefix}Fetching cross-lingual Wikipedia text for English keyword '{english_keyword}' -> target lang '{target_lang}'"
        )

        cross_result_item = await self._execute_wiki_api_call_with_retry(
            get_wiki_page_text_for_target_lang,
            english_keyword,  # source_page_title
            "en",  # source_lang
            http_client,  # Pass http_client here
            target_lang_for_crosslingual=target_lang,
            parent_request_id=parent_request_id,
        )

        if isinstance(cross_result_item, Exception):  # Should not happen
            logger.error(
                f"{log_prefix}Unhandled exception during cross-lingual text fetch for source_keyword '{english_keyword}' (en -> {target_lang}): {cross_result_item}"
            )
            return None

        if cross_result_item.get("status") == "success":
            text = cross_result_item.get("text")
            # actual_content_url_cross is the URL from which text was actually extracted in the target language
            actual_content_url_cross = cross_result_item.get("url")
            final_page_id = cross_result_item.get("page_id")

            # Determine the best title for the cross-lingual article
            final_target_title = None
            text_extraction_outcome = cross_result_item.get("text_extraction_outcome")
            link_search_outcome = cross_result_item.get("link_search_outcome")

            if text_extraction_outcome and text_extraction_outcome.get("title"):
                final_target_title = text_extraction_outcome.get("title")
            elif link_search_outcome and link_search_outcome.get("target_title"):
                final_target_title = link_search_outcome.get("target_title")

            interlang_url = (
                link_search_outcome.get("target_url") if link_search_outcome else None
            )

            if text and actual_content_url_cross and final_page_id:
                logger.info(
                    f"{log_prefix}Successfully fetched text for '{english_keyword}' (en) in '{target_lang}'. "
                    f"Target Title: '{final_target_title}', Content URL: {actual_content_url_cross}, PageID: {final_page_id}. Length: {len(text)}"
                )
                return SourceArticle(
                    source_name="online_wikipedia",
                    source_url=actual_content_url_cross,
                    source_identifier=str(
                        final_page_id
                    ),  # Use pageid as the unique identifier
                    title=final_target_title if final_target_title else "N/A",
                    text_content=text,
                    language=target_lang,
                    metadata={
                        "original_keyword": english_keyword,
                        "target_language": target_lang,
                        "retrieved_title": final_target_title,
                        "retrieved_url": actual_content_url_cross,
                        "interlanguage_link_url": interlang_url,
                        "page_id": final_page_id,
                    },
                )
            elif text and not actual_content_url_cross:
                logger.warning(
                    f"{log_prefix}Text extracted for '{english_keyword}' (en) in '{target_lang}' (Title: {final_target_title}), but actual_content_url_cross was missing. Skipping this entry."
                )
                return None
            elif not text:
                logger.info(
                    f"{log_prefix}Cross-lingual search for '{english_keyword}' (en -> {target_lang}) successful in finding link, but no text extracted. "
                    f"Target Title: '{final_target_title}', Attempted URL: {actual_content_url_cross}, Error: {cross_result_item.get('error')}"
                )
                return None
        else:
            error_msg = cross_result_item.get("error") or "Unknown error"
            status = cross_result_item.get("status") or "unknown_status"
            logger.info(
                f"{log_prefix}Failed to get text for '{english_keyword}' (en) in '{target_lang}'. Status: {status}. Error: {error_msg}"
            )
            return None
        return None

    async def get_articles(
        self,
        query_data: dict[str, Any],
    ) -> list[SourceArticle]:
        log_prefix = (
            f"[ParentReqID: {query_data.get('parent_request_id')}] "
            if query_data.get("parent_request_id")
            else ""
        )

        keywords: list[str] = query_data.get("keywords", [])
        english_keywords: list[str] = query_data.get("english_keywords", [])
        user_language: str = query_data.get("user_language", "en")
        http_client: httpx.AsyncClient | None = query_data.get("http_client")
        parent_request_id: str | None = query_data.get("parent_request_id")

        if not user_language or user_language.lower() in ["und", "zxx"]:
            logger.warning(
                f"{log_prefix}OnlineWikipediaStrategy received invalid user_language='{user_language}'. Defaulting to 'en'."
            )
            user_language = "en"

        logger.info(
            f"{log_prefix}OnlineWikipediaStrategy starting. Original keywords: {keywords} (lang: {user_language}), English keywords: {english_keywords} (lang: en)"
        )

        if not http_client:
            logger.info(
                f"{log_prefix}No http_client provided, creating optimized client."
            )
            http_client = create_optimized_http_client()
            should_close_client = True
        else:
            should_close_client = False

        if not keywords and not english_keywords:
            logger.info(f"{log_prefix}No keywords provided to OnlineWikipediaStrategy.")
            return []

        try:
            tasks = []
            processed_keys = set()  # To avoid duplicate processing

            # 1. Fetch articles for original keywords in their native language
            if user_language != "en" and keywords:
                for keyword in keywords:
                    if (keyword, user_language) not in processed_keys:
                        tasks.append(
                            self._fetch_target_lang_article(
                                keyword, user_language, http_client, parent_request_id
                            )
                        )
                        processed_keys.add((keyword, user_language))

            # 2. Fetch articles for English keywords in English
            # This handles both English users and the English version for non-English users
            keywords_to_fetch_in_english = (
                english_keywords if user_language != "en" else keywords
            )
            if keywords_to_fetch_in_english:
                for keyword in keywords_to_fetch_in_english:
                    if (keyword, "en") not in processed_keys:
                        tasks.append(
                            self._fetch_english_article(
                                keyword, http_client, parent_request_id
                            )
                        )
                        processed_keys.add((keyword, "en"))

            if not tasks:
                logger.warning(
                    f"{log_prefix}No fetch tasks were created. Check keyword lists and language."
                )
                return []

            logger.info(f"{log_prefix}Created {len(tasks)} fetching tasks.")

            # Execute all fetch tasks concurrently
            results: list[SourceArticle | None] = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            articles: list[SourceArticle] = []
            for result in results:
                if isinstance(result, SourceArticle):
                    articles.append(result)
                elif isinstance(result, Exception):
                    logger.error(
                        f"{log_prefix}Error during article fetching task: {result}",
                        exc_info=result,
                    )

            logger.info(
                f"{log_prefix}OnlineWikipediaStrategy finished, returning {len(articles)} raw articles (before service-level deduplication)."
            )
            return articles

        finally:
            if should_close_client and http_client:
                await http_client.aclose()


class OnlineWikinewsStrategy(DataAcquisitionStrategy):
    # Live Wikinews article search and extraction with keyword-based filtering

    def __init__(self, semaphore_limit: int = settings.wiki_api_semaphore_limit):
        # Use adaptive semaphore for better performance
        self.adaptive_semaphore = AdaptiveSemaphore(
            initial_limit=semaphore_limit,
            min_limit=max(2, semaphore_limit // 3),
            max_limit=min(15, semaphore_limit * 2),
        )

        # Ensure get_wikinews_page_text is available
        if not callable(get_wikinews_page_text):
            logger.critical(
                "get_wikinews_page_text is not callable! OnlineWikinewsStrategy will not work."
            )

    async def _execute_wikinews_api_call_with_retry(
        self,
        func,  # Should be get_wikinews_page_text
        search_keyword: str,  # Changed from page_title to search_keyword for clarity
        lang: str,
        http_client: httpx.AsyncClient,
        parent_request_id: str | None = None,
    ) -> WikinewsSearchResponse:
        """
        Helper to execute a synchronous Wikinews API call with adaptive semaphore, intelligent retry, and metrics.
        """
        log_prefix = (
            f"[WikinewsAPI][ParentReqID: {parent_request_id}] "
            if parent_request_id
            else "[WikinewsAPI] "
        )
        func_name_for_log = func.__name__  # Should be 'get_wikinews_page_text'

        args_for_log = (search_keyword, lang)  # func now takes search_keyword
        current_args = (
            search_keyword,  # Passed as search_query to get_wikinews_page_text
            lang,
            parent_request_id,
        )  # Pass parent_request_id to underlying function

        last_exception = None

        # Use adaptive semaphore
        async with self.adaptive_semaphore:
            for attempt in range(settings.max_wiki_retries):
                try:
                    loop = asyncio.get_event_loop()
                    # Run synchronous function in a separate thread
                    result = await loop.run_in_executor(None, func, *current_args)

                    # Based on the new structure of get_wikinews_page_text's return value
                    overall_status = result.status
                    if "error" in overall_status:
                        error_type = classify_wiki_error(
                            Exception(result.error or ""), result
                        )

                        logger.warning(
                            f"{log_prefix}{func_name_for_log}{args_for_log} reported overall error (attempt {attempt+1}/{settings.max_wiki_retries}): {result.error}, Status: {overall_status} (type: {error_type.value})"
                        )

                        # Check if we should retry based on error type
                        if not should_retry_error(error_type, attempt):
                            return (
                                result.model_dump()
                            )  # Return immediately for non-retryable errors

                    # If overall_status is success but no articles, it's a valid non-retryable outcome.
                    if overall_status == "success_search_no_results":
                        logger.info(
                            f"{log_prefix}{func_name_for_log}{args_for_log} found no articles (attempt {attempt+1}/{settings.max_wiki_retries}). Status: {overall_status}"
                        )
                        return result.model_dump()

                    # If it's success_search_processed_results, it means search was ok
                    return result.model_dump()

                except requests.exceptions.RequestException as e:
                    last_exception = e
                    error_type = classify_wiki_error(e)

                    logger.warning(
                        f"{log_prefix}RequestException for {func_name_for_log}{args_for_log} (attempt {attempt+1}/{settings.max_wiki_retries}): {e!r} (type: {error_type.value}). Retrying..."
                    )

                    if not should_retry_error(error_type, attempt):
                        break

                    if attempt < settings.max_wiki_retries - 1:
                        delay = get_retry_delay(attempt, error_type)
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{log_prefix}Max retries for {func_name_for_log}{args_for_log}. Error: {e!r}"
                        )
                        break

                except Exception as e:
                    logger.error(
                        f"{log_prefix}Unexpected error in _execute_wikinews_api_call_with_retry for {func_name_for_log}{args_for_log} (attempt {attempt+1}): {e!r}",
                        exc_info=True,
                    )
                    last_exception = e
                    break  # Break on unexpected errors

        # If all retries failed for the search operation
        error_type = (
            classify_wiki_error(last_exception)
            if last_exception
            else WikiErrorType.UNKNOWN
        )
        error_message = f"{log_prefix}Failed {func_name_for_log}{args_for_log} after {settings.max_wiki_retries} retries. Last error: {str(last_exception)} (type: {error_type.value})"
        logger.error(error_message)

        # Record error metrics
        wiki_metrics.record_request(
            success=False, response_time=0, error_type=error_type
        )

        return WikinewsSearchResponse(
            articles=[],
            search_query=search_keyword,
            error=error_message,
            status="error_in_retry_wrapper_wikinews_search_failed",
        ).model_dump()

    async def _fetch_wikinews_articles_for_keyword(
        self,
        keyword: str,
        lang: str,
        http_client: httpx.AsyncClient,  # Passed but not directly used by get_wikinews_page_text
        parent_request_id: str | None = None,
    ) -> list[
        SourceArticle
    ]:  # Changed return type from Optional[SourceArticle] to List[SourceArticle]
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
        logger.info(
            f"{log_prefix}Fetching Wikinews articles for keyword: '{keyword}' (lang: {lang})"
        )

        # Ensure get_wikinews_page_text is callable before using it
        if not callable(get_wikinews_page_text):
            logger.error(
                f"{log_prefix}get_wikinews_page_text is not available. Cannot fetch for '{keyword}'."
            )
            return []

        # get_wikinews_page_text is synchronous, run it in executor
        wikinews_result_data = await self._execute_wikinews_api_call_with_retry(
            get_wikinews_page_text,  # This is the refactored function
            keyword,  # This keyword is now treated as a search_query by get_wikinews_page_text
            lang,
            http_client,
            parent_request_id=parent_request_id,
        )

        found_articles: list[SourceArticle] = []

        if not wikinews_result_data:
            logger.error(
                f"{log_prefix}Invalid or empty result from _execute_wikinews_api_call_with_retry for keyword '{keyword}'."
            )
            return []

        # Check overall status first
        overall_status = wikinews_result_data.get("status")
        if "error" in overall_status:
            logger.warning(
                f"{log_prefix}Overall error reported by get_wikinews_page_text for keyword '{keyword}': {wikinews_result_data.get('error')} (Status: {overall_status})"
            )
            return []  # If overall status is an error, no articles to process

        articles_data = wikinews_result_data.get("articles", [])
        search_query_actually_used = wikinews_result_data.get("search_query")

        # Log based on search results
        if not articles_data and "success_search_no_results" == overall_status:
            logger.info(
                f"{log_prefix}Search for '{search_query_actually_used}' yielded no Wikinews articles."
            )
        elif articles_data:
            logger.info(
                f"{log_prefix}Search for '{search_query_actually_used}' yielded {len(articles_data)} article entries to process."
            )

        for i, article_content in enumerate(articles_data):
            text_content = article_content.get("text")
            final_title = article_content.get("title")
            final_url = article_content.get("url")
            article_status = article_content.get("status")
            article_error = article_content.get("error")

            if article_status and "error" in article_status and not text_content:
                logger.warning(
                    f"{log_prefix}Error for article '{final_title or f'(part of {keyword})'}' (item {i+1}): {article_error}. Status: {article_status}"
                )
                continue  # Skip this article

            if text_content and final_url and final_title:
                logger.info(
                    f"{log_prefix}Successfully processed Wikinews article '{final_title}' (URL: {final_url}). Length: {len(text_content)}"
                )
                article_obj = SourceArticle(
                    source_name="online_wikinews",
                    source_url=final_url,
                    source_identifier=keyword,  # Original keyword for query context
                    title=final_title,
                    text_content=text_content,
                    language=lang,  # Assuming lang of the query is lang of the article
                    metadata={
                        "original_keyword": keyword,  # The keyword that initiated this specific fetch flow
                        "search_query_used_for_article_group": search_query_actually_used,  # The query string that resulted in this group of articles
                        "retrieved_title": final_title,
                        "retrieved_url": final_url,
                        # "category_source": None, # No longer directly available from extractor
                        # "redirect_info": None,   # No longer directly available from extractor
                        "fetch_status": article_status,
                    },
                )
                found_articles.append(article_obj)
            elif final_title:
                logger.info(
                    f"{log_prefix}No text extracted for Wikinews article '{final_title}' (item {i+1} for keyword '{keyword}'). Status: {article_status}, Error: {article_error}"
                )
            else:
                logger.warning(
                    f"{log_prefix}Skipping item {i+1} for keyword '{keyword}' due to missing title or URL. Status: {article_status}, Error: {article_error}"
                )

        # Updated logging for clarity when no articles are found after processing search results
        if (
            not found_articles
            and "success_search_processed_results" == overall_status
            and articles_data
        ):
            logger.info(
                f"{log_prefix}Search for '{search_query_actually_used}' found {len(articles_data)} items, but none yielded extractable articles."
            )
        elif not found_articles and "success_search_no_results" == overall_status:
            pass  # Already logged above
        elif not found_articles:
            logger.info(
                f"{log_prefix}No articles successfully extracted for original keyword '{keyword}' (Searched with: '{search_query_actually_used}'). Overall status: {overall_status}"
            )

        return found_articles

    async def get_articles(
        self,
        query_data: dict[str, Any],
    ) -> list[SourceArticle]:
        keywords: list[str] = query_data.get("keywords", [])
        user_language: str = query_data.get("user_language", "en")
        http_client: httpx.AsyncClient = query_data["http_client"]
        parent_request_id: str | None = query_data.get("request_id")
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""

        # Add check for invalid language codes like 'und'
        if not user_language or user_language.lower() == "und":
            logger.warning(
                f"{log_prefix}OnlineWikinewsStrategy received invalid user_language='{user_language}'. Defaulting to 'en'."
            )
            user_language = "en"

        if not keywords:
            logger.warning(f"{log_prefix}OnlineWikinewsStrategy received no keywords.")
            return []

        if not callable(get_wikinews_page_text):
            logger.error(
                f"{log_prefix}get_wikinews_page_text is not available. OnlineWikinewsStrategy cannot proceed."
            )
            return []

        logger.info(
            f"{log_prefix}OnlineWikinewsStrategy: Processing {len(keywords)} keywords for lang '{user_language}'."
        )

        all_gathered_articles: list[SourceArticle] = []

        # Create tasks for all keywords to run concurrently
        tasks = []
        for keyword in keywords:
            # For Wikinews, we typically use the user's language directly.
            # If cross-lingual lookup was needed for Wikinews (e.g. English keyword to German Wikinews),
            # that logic would need to be added here or in the _fetch_ method.
            # For now, assuming keyword is in user_language or directly usable.
            tasks.append(
                self._fetch_wikinews_articles_for_keyword(
                    keyword=keyword,
                    lang=user_language,  # Use user_language for Wikinews query lang
                    http_client=http_client,
                    parent_request_id=parent_request_id,
                )
            )

        # Gather results from all tasks
        # List[List[SourceArticle]] - each inner list is from one keyword
        results_from_keywords: list[list[SourceArticle]] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        for i, keyword_results in enumerate(results_from_keywords):
            keyword = keywords[i]
            if isinstance(keyword_results, Exception):
                logger.error(
                    f"{log_prefix}Exception while fetching Wikinews articles for keyword '{keyword}': {keyword_results}",
                    exc_info=keyword_results,  # Log with stack trace
                )
            elif isinstance(keyword_results, list):  # It should be List[SourceArticle]
                if keyword_results:  # If the list is not empty
                    logger.info(
                        f"{log_prefix}Keyword '{keyword}' yielded {len(keyword_results)} Wikinews articles."
                    )
                    all_gathered_articles.extend(keyword_results)  # Flatten the list
                else:
                    logger.info(
                        f"{log_prefix}Keyword '{keyword}' yielded no Wikinews articles."
                    )
            else:
                logger.warning(
                    f"{log_prefix}Unexpected result type for keyword '{keyword}': {type(keyword_results)}. Expected List[SourceArticle]. Result: {keyword_results}"
                )

        logger.info(
            f"{log_prefix}OnlineWikinewsStrategy finished. Total articles gathered: {len(all_gathered_articles)} from {len(keywords)} keywords."
        )
        return all_gathered_articles


class DatasetWikipediaEnStrategy(DataAcquisitionStrategy):
    """
    Fetches articles from a pre-processed English Wikipedia dataset (or 'chunk store').
    This strategy is optimized for semantic search on English content.
    """

    def __init__(
        self,
        semantic_search_component: SemanticSearchComponent | None = None,
        article_limit: int = settings.default_article_limit,
    ):
        # Allow component to be injected, or create a default one
        self.component = semantic_search_component or SemanticSearchComponent()
        self.article_limit = article_limit
        logger.info(
            f"Initialized DatasetWikipediaEnStrategy with article limit: {self.article_limit}"
        )

    async def _get_articles_from_full_documents(
        self, query_data: dict[str, Any]
    ) -> list[SourceArticle]:
        """
        [DEPRECATED but kept for reference]
        Fetches full articles based on semantic search results. This is inefficient.
        """
        parent_request_id = query_data.get("parent_request_id")
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""
        viewpoint_text = query_data.get("viewpoint_text", "")
        if not viewpoint_text:
            logger.warning(
                f"{log_prefix}No viewpoint_text provided for semantic search. Cannot proceed."
            )
            return []

        if not self.component or not self.component.is_ready():
            logger.error(
                f"{log_prefix}SemanticSearchComponent is not ready (model or DB not loaded). Cannot perform search."
            )
            return []

        logger.info(
            f"{log_prefix}Performing semantic search with viewpoint: '{viewpoint_text[:100]}...'"
        )

        try:
            # Semantic search returns a list of unique parent document IDs
            doc_ids = await self.component.perform_semantic_search(
                query_text=viewpoint_text, limit=self.article_limit
            )

            if not doc_ids:
                logger.info(f"{log_prefix}Semantic search returned no document IDs.")
                return []

            logger.info(
                f"{log_prefix}Semantic search found {len(doc_ids)} unique document IDs: {doc_ids}"
            )

            # Retrieve full documents based on IDs
            full_documents = await self.component.get_documents_by_ids(doc_ids)

            articles: list[SourceArticle] = []
            for doc_data in full_documents:
                doc_id = doc_data.get("doc_id")
                content = doc_data.get("text")
                metadata = doc_data.get("metadata", {})
                title = metadata.get("title", f"Document {doc_id}")
                url = metadata.get("url", "")

                if content:
                    articles.append(
                        SourceArticle(
                            source_name="dataset_wikipedia_en",
                            source_identifier=str(doc_id),
                            title=title,
                            text_content=content,
                            language="en",
                            metadata=metadata,
                            source_url=url,
                        )
                    )
            logger.info(
                f"{log_prefix}Successfully retrieved {len(articles)} full articles from dataset."
            )
            return articles

        except Exception as e:
            logger.error(
                f"{log_prefix}An error occurred during semantic search or document retrieval: {e}",
                exc_info=True,
            )
            return []

    async def _get_articles_from_chunks(
        self, search_text: str, query_data: dict[str, Any]
    ) -> list[SourceArticle]:
        """
        Performs semantic search on article chunks and reconstructs articles.
        """
        parent_request_id = query_data.get("parent_request_id")
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""

        if not search_text:
            logger.warning(
                f"{log_prefix}Search text is empty, cannot perform semantic search."
            )
            return []

        try:
            logger.info(
                f"{log_prefix}Searching article chunks with text: '{search_text}'"
            )
            relevant_chunks = await self.component.search_article_chunks(
                query_text=search_text,
                limit=20,  # Fetch more chunks initially to allow for consolidation
            )

            if not relevant_chunks:
                logger.info(
                    f"{log_prefix}Semantic search returned no relevant chunks for query: '{search_text}'"
                )
                return []

            logger.info(
                f"{log_prefix}Retrieved {len(relevant_chunks)} relevant chunks from semantic search."
            )

            # Consolidate chunks back into articles, preserving order of relevance
            consolidated_articles: dict[str, SourceArticle] = {}
            for chunk in relevant_chunks:
                # Extract the doc_id (which is the Wikipedia pageid) from chunk
                chunk_doc_id = chunk.get("doc_id")
                chunk_url = chunk.get("url", "")
                chunk_title = chunk.get("title", "")
                chunk_text = chunk.get("chunk_text", "")
                chunk_similarity = chunk.get("similarity", 0.0)

                if len(consolidated_articles) >= self.article_limit:
                    if chunk_url not in consolidated_articles:
                        logger.debug(
                            f"{log_prefix}SourceArticle limit ({self.article_limit}) reached. Skipping new article from chunk for URL: {chunk_url}"
                        )
                        continue  # Skip chunks for new articles if limit is reached

                if chunk_url in consolidated_articles:
                    # Append text to existing article if it's not already there
                    if (
                        chunk_text
                        and chunk_text
                        not in consolidated_articles[chunk_url].text_content
                    ):
                        consolidated_articles[
                            chunk_url
                        ].text_content += f"\n\n... {chunk_text}"
                        logger.debug(
                            f"{log_prefix}Appended chunk to existing article: {chunk_url}"
                        )
                else:
                    # Create a new article from the chunk
                    logger.debug(
                        f"{log_prefix}Creating new article from chunk: {chunk_url} (PageID: {chunk_doc_id})"
                    )
                    new_article = SourceArticle(
                        source_name="dataset_wikipedia_en",
                        source_url=chunk_url,
                        source_identifier=str(
                            chunk_doc_id
                        ),  # Use pageid as the unique identifier
                        title=chunk_title,
                        text_content=chunk_text or "",
                        language="en",
                        metadata={
                            "retrieval_method": "semantic_chunk_search",
                            "initial_relevance_score": chunk_similarity,
                            "pageid": chunk_doc_id,  # Store pageid in metadata for reference
                        },
                    )
                    consolidated_articles[chunk_url] = new_article

            final_articles = list(consolidated_articles.values())
            logger.info(
                f"{log_prefix}Consolidated chunks into {len(final_articles)} final articles."
            )
            return final_articles

        except Exception as e:
            logger.error(
                f"{log_prefix}An error occurred while getting articles from chunks: {e}",
                exc_info=True,
            )
            return []

    async def get_articles(
        self,
        query_data: dict[str, Any],
    ) -> list[SourceArticle]:
        """
        Selects the best query text based on available data and then fetches articles.
        This strategy has autonomous decision-making logic with the following priority:
        1. English original text (if user_language is 'en')
        2. Complete English translation of the viewpoint (if available)
        3. English keywords list (if available)
        4. Non-English original text (fallback)
        """
        user_language = query_data.get("user_language")
        english_keywords = query_data.get("english_keywords", [])
        translated_viewpoint = query_data.get("translated_viewpoint")
        viewpoint_text = query_data.get("viewpoint_text", "")
        parent_request_id = query_data.get("parent_request_id")
        log_prefix = f"[ParentReqID: {parent_request_id}] " if parent_request_id else ""

        search_text = ""
        search_method = ""

        # Strategy's internal decision logic with enhanced priority system
        if user_language == "en":
            # Priority 1: English original text -> Use the original, full-semantic query
            search_text = viewpoint_text
            search_method = "original_english_viewpoint"
            logger.info(
                f"{log_prefix}Using original English viewpoint text for semantic search (Priority 1)."
            )
        elif translated_viewpoint and translated_viewpoint.strip():
            # Priority 2: Complete English translation -> Use full translated semantic query
            search_text = translated_viewpoint
            search_method = "translated_english_viewpoint"
            logger.info(
                f"{log_prefix}Using complete English translation for semantic search (Priority 2): '{search_text[:100]}{'...' if len(search_text) > 100 else ''}'"
            )
        elif english_keywords:
            # Priority 3: English keywords -> Use translated keywords
            search_text = ", ".join(english_keywords)
            search_method = "english_keywords"
            logger.info(
                f"{log_prefix}Using English keywords for semantic search (Priority 3): '{search_text}'"
            )
        else:
            # Priority 4: Fallback -> Use original non-English text
            search_text = viewpoint_text
            search_method = "fallback_original_text"
            logger.warning(
                f"{log_prefix}Fallback: Using original non-English viewpoint text for search (Priority 4). Results may be suboptimal."
            )

        # Log the decision for debugging and analytics
        logger.info(
            f"{log_prefix}DatasetWikipediaEnStrategy decision: method='{search_method}', user_language='{user_language}', search_text_length={len(search_text)}"
        )

        # Once the search text is decided, execute the search
        return await self._get_articles_from_chunks(search_text, query_data)
