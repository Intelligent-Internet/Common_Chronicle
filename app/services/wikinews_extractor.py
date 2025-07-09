"""
Wikinews content extraction utilities for news article processing.

This module provides functionality for searching and extracting content from Wikinews,
the collaborative news website that serves as a source of current events information.
It supports multi-language news content extraction for timeline generation.
"""

import json
import time

import requests

from app.schemas import WikinewsArticleCore, WikinewsSearchResponse
from app.utils.logger import setup_logger

logger = setup_logger("wikinews_extractor")

# Define a User-Agent string for Wikimedia API compliance
WIKINEWS_API_USER_AGENT = (
    "CommonChronicleProject/0.1 (WikinewsBot; contact: unavailable)"
)

# Constants for API calls
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3  # Retries for the main search operation and for each direct fetch
INITIAL_RETRY_DELAY = 1.0  # seconds
# CATEGORY_MEMBER_LIMIT = 10 # No longer directly used in main function if removing category logic
SEARCH_RESULT_LIMIT = 3  # Max articles to fetch content for from search results


# Helper function to fetch text for a single, non-category page (internal use)
def _fetch_direct_page_text_core(
    page_title: str,
    lang: str,
    api_url: str,
    headers: dict[str, str],
    parent_request_id: str | None = None,
) -> WikinewsArticleCore:
    """
    Core logic to fetch and extract text for a specific page title, without redirect or category handling.
    This function assumes the page_title is the one to fetch directly.
    """
    log_prefix = (
        f"[DirectFetch][ParentReqID: {parent_request_id}] "
        if parent_request_id
        else "[DirectFetch] "
    )

    params = {
        "action": "query",
        "format": "json",
        "titles": page_title,
        "prop": "extracts|info",
        "inprop": "url",
        "explaintext": True,
        # "redirects": 0, # No internal redirect resolution, assumed to be handled by caller or initial query
        "formatversion": 2,
    }

    logger.debug(
        f"{log_prefix}Requesting direct Wikinews page: '{page_title}' (lang: {lang}) with params: {json.dumps(params, ensure_ascii=False)}"
    )

    try:
        response = requests.get(
            api_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        response_data = response.json()
        # logger.debug(
        #     f"{log_prefix}Raw API response for '{page_title}': {json.dumps(response_data, ensure_ascii=False, indent=2)}"
        # )

        query = response_data.get("query", {})
        pages = query.get("pages", [])

        if not pages:
            return WikinewsArticleCore(
                text=None,
                title=page_title,
                url=None,
                error="No 'pages' array in direct fetch response.",
                status="error_no_pages_direct",
            )

        page_data = pages[0]
        if page_data.get("missing") or page_data.get("invalid"):
            reason = "missing" if page_data.get("missing") else "invalid"
            return WikinewsArticleCore(
                text=None,
                title=page_data.get("title", page_title),
                url=page_data.get("fullurl"),
                error=f"Page reported as {reason} by API in direct fetch.",
                status=f"error_page_{reason}_direct",
            )

        extracted_text = page_data.get("extract")
        final_title = page_data.get("title")
        final_url = page_data.get("fullurl")

        if not extracted_text:
            return WikinewsArticleCore(
                text=None,
                title=final_title,
                url=final_url,
                error="Page found but no text extracted in direct fetch (could be empty, redirect, or special page).",
                status="success_no_text_direct",
            )

        return WikinewsArticleCore(
            text=extracted_text,
            title=final_title,
            url=final_url,
            error=None,
            status="success_direct",
        )

    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTPError in direct fetch for '{page_title}': {e.response.status_code} - {e.response.text[:100]}"
        logger.warning(f"{log_prefix}{error_msg}")
        return WikinewsArticleCore(
            text=None,
            title=page_title,
            url=None,
            error=error_msg,
            status="error_http_direct",
        )
    except requests.exceptions.RequestException as e:
        error_msg = f"RequestException in direct fetch for '{page_title}': {type(e).__name__} - {str(e)}"
        logger.warning(f"{log_prefix}{error_msg}")
        return WikinewsArticleCore(
            text=None,
            title=page_title,
            url=None,
            error=error_msg,
            status="error_request_direct",
        )
    except json.JSONDecodeError as e:
        error_msg = f"JSONDecodeError in direct fetch for '{page_title}': {str(e)}"
        logger.error(f"{log_prefix}{error_msg}")
        return WikinewsArticleCore(
            text=None,
            title=page_title,
            url=None,
            error=error_msg,
            status="error_json_direct",
        )
    except Exception as e:
        error_msg = f"Unexpected error in direct fetch for '{page_title}': {type(e).__name__} - {str(e)}"
        logger.error(f"{log_prefix}{error_msg}", exc_info=True)
        return WikinewsArticleCore(
            text=None,
            title=page_title,
            url=None,
            error=error_msg,
            status="error_unexpected_direct",
        )


def get_wikinews_page_text(  # Renaming 'page_title' to 'search_query' to reflect its new role
    search_query: str,
    lang: str = "en",
    parent_request_id: str | None = None,
) -> WikinewsSearchResponse:
    """
    Searches Wikinews for articles matching the search_query and fetches content for the top N results.
    """
    log_prefix = (
        f"[WikinewsSearch][ParentReqID: {parent_request_id}] "
        if parent_request_id
        else "[WikinewsSearch] "
    )
    api_url = f"https://{lang}.wikinews.org/w/api.php"
    headers = {"User-Agent": WIKINEWS_API_USER_AGENT}

    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": search_query,
        "srnamespace": "0",  # Main namespace (articles)
        "srlimit": str(
            SEARCH_RESULT_LIMIT * 2
        ),  # Fetch a bit more initially in case some are not useful
        "sroffset": "0",
        "format": "json",
        "formatversion": 2,
    }

    logger.info(
        f"{log_prefix}Searching Wikinews for: '{search_query}' (lang: {lang}), limit (pref.): {SEARCH_RESULT_LIMIT}"
    )
    logger.debug(
        f"{log_prefix}Search API URL: {api_url}, Params: {json.dumps(search_params, ensure_ascii=False)}"
    )

    articles_results: list[WikinewsArticleCore] = []
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            search_response = requests.get(
                api_url,
                params=search_params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            search_response.raise_for_status()
            search_data = search_response.json()
            logger.debug(
                f"{log_prefix}Search API response for '{search_query}' (attempt {attempt + 1}): {json.dumps(search_data, ensure_ascii=False, indent=2)}"
            )

            if "error" in search_data:
                api_error_info = search_data["error"].get(
                    "info", "Unknown API error during search"
                )
                code = search_data["error"].get("code", "N/A")
                logger.error(
                    f"{log_prefix}API error during Wikinews search for '{search_query}': {code} - {api_error_info}"
                )
                # This is likely a fatal API error for the search itself, retry might not help if malformed.
                return WikinewsSearchResponse(
                    articles=[],
                    search_query=search_query,
                    error=f"API error during search: {code} - {api_error_info}",
                    status="error_api_search",
                )

            search_results = search_data.get("query", {}).get("search", [])

            if not search_results:
                logger.info(
                    f"{log_prefix}No Wikinews articles found matching search query: '{search_query}' (lang: {lang})"
                )
                return WikinewsSearchResponse(
                    articles=[],
                    search_query=search_query,
                    error=None,
                    status="success_search_no_results",
                )

            logger.info(
                f"{log_prefix}Found {len(search_results)} potential articles from search. Will attempt to fetch top {SEARCH_RESULT_LIMIT}."
            )

            titles_to_fetch = [
                result.get("title") for result in search_results if result.get("title")
            ]

            # Limit the number of articles for which content is fetched
            for i, title_to_fetch in enumerate(titles_to_fetch[:SEARCH_RESULT_LIMIT]):
                if not title_to_fetch:
                    logger.warning(
                        f"{log_prefix}Search result item {i} has no title, skipping."
                    )
                    continue

                logger.info(
                    f"{log_prefix}Fetching content for search result: '{title_to_fetch}' (lang: {lang})"
                )
                # Using _fetch_direct_page_text_core which has its own error handling per article
                article_data = _fetch_direct_page_text_core(
                    title_to_fetch,
                    lang,
                    api_url,
                    headers,
                    parent_request_id=f"{parent_request_id or ''}_sr{i}",
                )
                articles_results.append(article_data)

            return WikinewsSearchResponse(  # Successfully completed search and fetch attempts
                articles=articles_results,
                search_query=search_query,
                error=None,
                status="success_search_processed_results",
            )

        except requests.exceptions.HTTPError as e:
            last_exception = e
            error_msg = f"HTTPError during Wikinews search for '{search_query}' (attempt {attempt + 1}/{MAX_RETRIES}): {e.response.status_code} - {e.response.text[:200]}"
            logger.warning(f"{log_prefix}{error_msg}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(INITIAL_RETRY_DELAY * (2**attempt))
            else:
                logger.error(f"{log_prefix}Max retries reached for search. {error_msg}")
                return WikinewsSearchResponse(
                    articles=[],
                    search_query=search_query,
                    error=f"Max retries for search. Last HTTPError: {error_msg}",
                    status="error_http_search_max_retries",
                )
        except requests.exceptions.RequestException as e:
            last_exception = e
            error_msg = f"RequestException during Wikinews search for '{search_query}' (attempt {attempt + 1}/{MAX_RETRIES}): {type(e).__name__} - {str(e)}"
            logger.warning(f"{log_prefix}{error_msg}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(INITIAL_RETRY_DELAY * (2**attempt))
            else:
                logger.error(f"{log_prefix}Max retries reached for search. {error_msg}")
                return WikinewsSearchResponse(
                    articles=[],
                    search_query=search_query,
                    error=f"Max retries for search. Last RequestException: {error_msg}",
                    status="error_request_search_max_retries",
                )
        except json.JSONDecodeError as e:
            last_exception = e
            error_msg = f"JSONDecodeError during Wikinews search for '{search_query}' (attempt {attempt + 1}): {str(e)}"
            raw_text_snippet = "Could not get raw text from search response."
            if "search_response" in locals() and hasattr(search_response, "text"):
                raw_text_snippet = search_response.text[:200] + "...(truncated)"
            logger.error(
                f"{log_prefix}{error_msg}. Raw text snippet: {raw_text_snippet}"
            )
            # JSON errors usually mean unrecoverable response for this attempt, possibly for all.
            return WikinewsSearchResponse(
                articles=[],
                search_query=search_query,
                error=f"{error_msg}. Snippet: {raw_text_snippet}",
                status="error_json_decode_search",
            )
        except Exception as e:  # Catch any other unexpected errors
            last_exception = e
            error_msg = f"Unexpected error during Wikinews search for '{search_query}' (attempt {attempt + 1}): {type(e).__name__} - {str(e)}"
            logger.error(f"{log_prefix}{error_msg}", exc_info=True)
            return WikinewsSearchResponse(  # Return error immediately for unexpected issues
                articles=[],
                search_query=search_query,
                error=error_msg,
                status="error_unexpected_search",
            )

    # Fallback if loop finishes due to max_retries without specific return: (should ideally be covered by else clauses in try)
    fallback_error_msg = f"Failed to search Wikinews for '{search_query}' (lang: {lang}) after {MAX_RETRIES} retries. Last error: {str(last_exception)}"
    logger.error(f"{log_prefix}{fallback_error_msg}")
    return WikinewsSearchResponse(
        articles=[],
        search_query=search_query,
        error=fallback_error_msg,
        status="error_max_retries_fallback_search",
    )
