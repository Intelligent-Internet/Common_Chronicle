"""
Wikipedia Extractor Service - Advanced Wikipedia Content Extraction

This module provides comprehensive functionality for extracting and processing
Wikipedia content through the MediaWiki API. It serves as a robust interface
for retrieving structured information from Wikipedia pages across multiple languages.
"""

import json
import urllib.parse
from typing import Any

import requests
from async_lru import alru_cache
from bs4 import BeautifulSoup

from app.config import settings
from app.schemas import WikiPageInfoResponse, WikiPageTextResponse
from app.utils.logger import setup_logger
from app.utils.wiki_optimization import (
    WIKI_CACHE_CONFIG,
    create_optimized_http_client,
    execute_with_retry_and_metrics,
    get_dynamic_timeout,
    wiki_metrics,
)

logger = setup_logger("wiki_extractor")


def extract_disambiguation_options(summary: str) -> list[str]:
    options = []
    lines = summary.split("\n")
    for line in lines:
        if line.startswith("*"):  # Common pattern for disambiguation links
            # Try to extract link title (this is a heuristic method)
            link_text = line.lstrip("* ").split(",", 1)[0].split(" – ", 1)[0].strip()
            if link_text and len(link_text) < 100:  # Basic sanity check
                options.append(link_text)
    return options[:10]  # Limit number of options


@alru_cache(
    maxsize=WIKI_CACHE_CONFIG["page_info_cache_size"],
    ttl=WIKI_CACHE_CONFIG["cache_ttl"],
)
async def get_wiki_page_info(
    initial_title: str, lang: str = "en"
) -> WikiPageInfoResponse:
    # Cached Wikipedia page info lookup with Wikidata ID and disambiguation handling

    async def _fetch_page_info():
        logger.info(f"Fetching wiki page info for {initial_title}({lang})")
        client = create_optimized_http_client()
        try:
            api_url = f"https://{lang}.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "titles": initial_title,
                "prop": "info|extracts|pageprops",
                "ppprop": "wikibase_item|disambiguation",
                "inprop": "url",
                "exintro": True,
                "explaintext": True,
                "redirects": 1,
                "formatversion": 2,
            }

            timeout = get_dynamic_timeout(
                page_size_hint="small", is_text_extraction=False
            )
            headers = {"User-Agent": settings.wiki_api_user_agent}

            response = await client.get(
                api_url, params=params, headers=headers, timeout=timeout
            )
            response.raise_for_status()
            response_data = response.json()
            # logger.info("response_data: %s", response_data)

            query = response_data.get("query", {})
            pages = query.get("pages", [])
            if not pages:
                logger.warning(f"No pages found in API response for '{initial_title}'.")
                return WikiPageInfoResponse(
                    exists=False,
                    title=initial_title,
                )

            page_data = pages[0]

            if page_data.get("missing"):
                logger.info(
                    f"Page '{initial_title}' (lang: {lang}) is marked as missing by Wikipedia API."
                )
                return WikiPageInfoResponse(
                    exists=False,
                    title=initial_title,
                )

            is_disambiguation = page_data.get("pageprops", {}).get("disambiguation")
            extract = page_data.get("extract", "")

            # Handle disambiguation pages
            disambiguation_options = None
            if is_disambiguation and extract:
                disambiguation_options = extract_disambiguation_options(extract)

            return WikiPageInfoResponse(
                exists=True,
                is_redirect=(page_data.get("title") != initial_title),
                title=page_data.get("title", initial_title),
                fullurl=page_data.get("fullurl", ""),
                pagelanguage=page_data.get("pagelanguage", ""),
                touched=page_data.get("touched", ""),
                pageid=page_data.get("pageid", ""),
                wikibase_item=page_data.get("pageprops", {}).get("wikibase_item"),
                is_disambiguation=is_disambiguation,
                disambiguation_options=disambiguation_options,
                extract=extract.strip() if extract else None,
            )
        finally:
            await client.aclose()

    try:
        return await execute_with_retry_and_metrics(
            _fetch_page_info,
            operation_name=f"get_wiki_page_info_{initial_title}_{lang}",
        )
    except Exception as e:
        logger.error(
            f"Error fetching Wiki page info for '{initial_title}' (lang: {lang}): {e!r}",
            exc_info=True,
        )
        return WikiPageInfoResponse(
            exists=False,
            title=initial_title,
        )


def get_wiki_page_text(page_title: str, lang: str = "en") -> WikiPageTextResponse:
    # Extract plain text from Wikipedia page HTML with redirect handling
    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    original_formatted_title = urllib.parse.quote(page_title.replace(" ", "_"))
    original_page_url = f"https://{lang}.wikipedia.org/wiki/{original_formatted_title}"

    current_page_title = page_title
    current_page_url = original_page_url
    extracted_text: str | None = None
    error_message: str | None = None
    redirect_info_for_return: dict[str, Any] | None = None

    # Parameters for action=parse to get HTML content
    params_parse = {
        "action": "parse",
        "page": page_title,  # For action=parse, use 'page' instead of 'titles'
        "format": "json",
        "prop": "text|redirects",  # Get main HTML content and redirect information
        "disabletoc": True,  # Optionally disable table of contents in the HTML
        "disableeditsection": True,  # Optionally disable edit section links
        "wrapoutputclass": "mw-parser-output",  # Ensures the main content is wrapped
        "maxlag": 5,
        "origin": "*",
    }

    headers = {"User-Agent": settings.wiki_api_user_agent}

    raw_response_text_for_error_parsing: str = ""

    try:
        logger.info(
            "Making request (action=parse) to %s Wikipedia API for page: '%s' (URL: %s) with User-Agent: %s",
            lang,
            page_title,
            original_page_url,
            settings.wiki_api_user_agent,
        )
        logger.debug("Request API URL: %s", api_url)
        logger.debug("Request params: %s", json.dumps(params_parse, ensure_ascii=False))

        response = requests.get(
            api_url,
            params=params_parse,
            headers=headers,
            timeout=settings.wiki_api_timeout,
        )
        response.raise_for_status()

        raw_response_text = response.text
        raw_response_text_for_error_parsing = (
            raw_response_text  # Store for potential use in JSONDecodeError block
        )
        data = response.json()

        # Handle redirects with action=parse
        if "parse" in data and "redirects" in data["parse"]:
            redirects = data["parse"]["redirects"]
            if redirects:
                redirect = redirects[0]  # API usually returns the final target
                from_title = page_title  # The original request title
                to_title = redirect.get("to")
                if to_title:  # Ensure 'to' exists
                    logger.info(
                        f"Page '{from_title}' redirected to '{to_title}' on {lang}.wikipedia.org"
                    )
                    redirect_info_for_return = {
                        "from": from_title,
                        "to": to_title,
                        "to_fragment": redirect.get("tofragment"),
                    }

                    current_page_title = to_title
                    current_formatted_title = urllib.parse.quote(
                        current_page_title.replace(" ", "_")
                    )
                    current_page_url = (
                        f"https://{lang}.wikipedia.org/wiki/{current_formatted_title}"
                    )

                    # If redirected, we might need to make a new request for the *parsed content* of the redirected page.
                    # The 'text' field in the current response might be for the redirect page itself, not the target.
                    # For simplicity in this step, we'll assume the API gives content of final page or we re-fetch.
                    # A robust solution would re-fetch parse data for `to_title`.
                    # However, `action=parse` with `page=...` and `redirects=true` (implicit) should handle this.
                    # The `title` in `data['parse']['title']` should be the final title.
                    if (
                        "title" in data["parse"]
                        and data["parse"]["title"] != current_page_title
                    ):
                        logger.warning(
                            f"Redirect target title mismatch. API title: {data['parse']['title']}, Calculated: {current_page_title}. Using API title."
                        )
                        current_page_title = data["parse"]["title"]
                        current_formatted_title = urllib.parse.quote(
                            current_page_title.replace(" ", "_")
                        )
                        current_page_url = f"https://{lang}.wikipedia.org/wiki/{current_formatted_title}"

        logger.info(
            "Received response with status code: %d for %s original page: '%s' (Final page considered: '%s', URL: %s)",
            response.status_code,
            lang,
            page_title,
            current_page_title,  # This should be the title after potential redirect
            current_page_url,
        )

        if "error" in data:
            error_info_api = data["error"]
            error_message = f"API error for '{current_page_title}' (lang: {lang}): {error_info_api.get('code')} - {error_info_api.get('info')}"
            logger.warning(error_message)
            return WikiPageTextResponse(
                title=current_page_title,
                url=current_page_url,
                page_id=None,
                text=None,
                error=error_message,
                redirect_info=redirect_info_for_return,
            )

        parsed_data = data.get("parse", {})
        if (
            not parsed_data
            or "text" not in parsed_data
            or "*" not in parsed_data["text"]
        ):
            # Check if it's a "missing" page based on pageid
            if "pageid" not in parsed_data:  # Or specific missing indicators
                error_message = f"Page '{current_page_title}' (lang: {lang}, URL: {current_page_url}) not found or is missing (no pageid or specific missing indicators). Original request was for '{page_title}'."
                logger.error(error_message)
                return WikiPageTextResponse(
                    title=current_page_title,
                    url=current_page_url,
                    page_id=None,
                    text=None,
                    error=error_message,
                    redirect_info=redirect_info_for_return,
                )

            error_message = f"No 'text' found in API parse response for '{current_page_title}' (lang: {lang}). Parsed data: {parsed_data}"
            logger.error(error_message)
            return WikiPageTextResponse(
                title=current_page_title,
                url=current_page_url,
                page_id=None,
                text=None,
                error=error_message,
                redirect_info=redirect_info_for_return,
            )

        # Update final page details from the parse data if available and more accurate
        api_page_title = parsed_data.get("title", current_page_title)
        api_page_id = parsed_data.get("pageid")  # Extract pageid

        if api_page_title != current_page_title:
            logger.info(
                f"Updating current_page_title from '{current_page_title}' to '{api_page_title}' based on parse data."
            )
            current_page_title = api_page_title
            current_formatted_title = urllib.parse.quote(
                current_page_title.replace(" ", "_")
            )
            current_page_url = (
                f"https://{lang}.wikipedia.org/wiki/{current_formatted_title}"
            )

        # Standardize the URL to the permanent link format if pageid is available
        if api_page_id:
            current_page_url = f"https://{lang}.wikipedia.org/wiki?curid={api_page_id}"
            logger.info(
                f"Standardized URL for '{current_page_title}' to permanent link: {current_page_url}"
            )

        html_content = parsed_data["text"]["*"]

        if not html_content:
            error_message = f"Page '{current_page_title}' (lang: {lang}, URL: {current_page_url}) was found, but HTML content is empty. Original request: '{page_title}'."
            logger.warning(error_message)
            # Extracted text will be None or empty
        else:
            logger.info(
                f"Successfully fetched HTML for page: '{current_page_title}' (lang: {lang}, URL: {current_page_url}). Length: {len(html_content)}. Original request: '{page_title}'."
            )
            # Use BeautifulSoup to parse HTML and extract text
            soup = BeautifulSoup(html_content, "html.parser")

            # Attempt to find the main content div. Wikipedia main content is often in a div with class 'mw-parser-output'.
            # If your 'wrapoutputclass' param was successful, this should be the main container.
            content_div = soup.find("div", class_="mw-parser-output")

            if content_div:
                # Remove known non-content elements if necessary (e.g., tables of contents, edit links, navboxes, categories)
                # This part can be quite heuristic and might need refinement based on observed HTML structure.

                # Remove references section(s) first
                for references_section in content_div.find_all(
                    "ol", class_="references"
                ):
                    logger.debug("Removing <ol class='references'> section.")
                    references_section.decompose()
                for reflist_div in content_div.find_all("div", class_="reflist"):
                    logger.debug("Removing <div class='reflist'> section.")
                    reflist_div.decompose()
                # Sometimes references are under a heading and not in a specific class-named div/ol
                # This is a more complex case, for now, targeting common explicit structures.
                # Example: Find <h2> with "References" and remove its next sibling if it's a list/div.
                # for heading in content_div.find_all(['h2', 'h3']):
                #    if heading.get_text(strip=True).lower() in ["references", "notes", "footnotes"]:
                #        # This needs careful handling to remove the correct subsequent elements
                #        pass

                for unwanted_class in [
                    "metadata",
                    "nomobile",
                    "noprint",
                    "ambox",
                    "vertical-navbox",
                    "navbox",
                    "catlinks",
                    "printfooter",
                    "infobox",
                ]:  # Common classes to remove
                    for tag in content_div.find_all(class_=unwanted_class):
                        tag.decompose()  # Removes the tag and its content

                # Remove specific tags if they are problematic and not caught by classes
                for unwanted_tag_name in [
                    "style",
                    "script",
                    "table",
                    "sup",
                    "span",
                ]:  # Example: remove reference superscripts like [1], tables
                    # Be careful with removing generic tags like 'span' or 'table' if they might contain desired text.
                    # For 'sup' with class 'reference', it's safer. For general 'sup', it might remove other things.
                    # For 'table', some tables might contain relevant text.
                    # This is a trade-off between completeness and cleanliness.
                    if (
                        unwanted_tag_name == "sup"
                    ):  # Specifically target reference superscripts
                        for tag in content_div.find_all(
                            unwanted_tag_name, class_="reference"
                        ):
                            tag.decompose()
                    elif (
                        unwanted_tag_name == "span"
                    ):  # Example: remove IPA pronunciation spans if not needed
                        for tag in content_div.find_all(
                            unwanted_tag_name, class_="IPA"
                        ):  # Example
                            tag.decompose()
                        for tag in content_div.find_all(
                            unwanted_tag_name, class_="rt-comment"
                        ):  # Example for ruby text comments
                            tag.decompose()
                    # elif unwanted_tag_name == "table": # Decide if tables should be globally removed or parsed differently
                    #     for tag in content_div.find_all(unwanted_tag_name):
                    #         tag.decompose()
                    else:
                        for tag in content_div.find_all(unwanted_tag_name):
                            # A more conservative approach for general tags: extract text then remove if empty, or just leave them.
                            # For now, let's be aggressive for 'style' and 'script'.
                            if unwanted_tag_name in ["style", "script"]:
                                tag.decompose()

                extracted_text = content_div.get_text(
                    separator="\\n", strip=True
                )  # Get text, try to preserve line breaks somewhat
            else:
                # Fallback if 'mw-parser-output' is not found - parse the whole body
                logger.warning(
                    "Could not find 'div.mw-parser-output'. Parsing text from the whole HTML body. This might include unwanted elements."
                )
                extracted_text = soup.get_text(separator="\\n", strip=True)

            log_message_suffix = (
                "and text was extracted from HTML."
                if extracted_text
                else "but text was NOT extracted from HTML (or extracted text is empty)."
            )
            logger.info(
                f"Successfully processed HTML for page: '{current_page_title}' (lang: {lang}, URL: {current_page_url}), {log_message_suffix}. Original request: '{page_title}'."
            )

            if extracted_text:
                logger.debug(
                    "First 500 chars of text extracted from HTML for '%s': %s",
                    current_page_title,
                    extracted_text[:500],
                )
            else:
                logger.debug(
                    "Extracted text from HTML is empty or None for page: '%s' (URL: %s)",
                    current_page_title,
                    current_page_url,
                )

        return WikiPageTextResponse(
            title=current_page_title,
            url=current_page_url,
            page_id=api_page_id,
            text=extracted_text,
            error=error_message,  # Will be None if no error during html processing
            redirect_info=redirect_info_for_return,
        )

    except requests.HTTPStatusError as e:
        error_message = f"Error fetching Wiki page (action=parse). Original request: '{page_title}' (lang: {lang}, URL: {original_page_url}). Error: {str(e)}"
        logger.error(error_message)
        return WikiPageTextResponse(
            title=current_page_title,  # Use current_page_title which might have been updated by redirect
            url=current_page_url,  # Use current_page_url
            page_id=None,
            text=None,
            error=error_message,
            redirect_info=redirect_info_for_return,
        )
    except json.JSONDecodeError as e:
        error_message = f"Error parsing Wiki API JSON response (action=parse). Original request: '{page_title}' (lang: {lang}, URL: {original_page_url}). Error: {str(e)}. Response text was: {raw_response_text_for_error_parsing[:500]}..."
        logger.error(error_message)
        return WikiPageTextResponse(
            title=current_page_title,
            url=current_page_url,
            page_id=None,
            text=None,
            error=error_message,
            redirect_info=redirect_info_for_return,
        )
    except ImportError:
        error_message = "BeautifulSoup4 library is not installed. Please install it (e.g., pip install beautifulsoup4) to parse HTML."
        logger.error(error_message)
        return WikiPageTextResponse(
            title=current_page_title,
            url=current_page_url,
            page_id=None,
            text=None,
            error=error_message,
            redirect_info=redirect_info_for_return,
        )
    except Exception as e:
        error_message = f"An unexpected error occurred (action=parse). Original request: '{page_title}' (lang: {lang}, URL: {original_page_url}). Error: {type(e).__name__}: {str(e)}"
        logger.error(
            error_message, exc_info=True
        )  # Log full traceback for unexpected errors
        return WikiPageTextResponse(
            title=current_page_title,
            url=current_page_url,
            page_id=None,
            text=None,
            error=error_message,
            redirect_info=redirect_info_for_return,
        )


@alru_cache(
    maxsize=WIKI_CACHE_CONFIG["page_text_cache_size"],
    ttl=WIKI_CACHE_CONFIG["cache_ttl"],
)
async def cached_get_wiki_page_text(
    page_title: str, lang: str = "en"
) -> WikiPageTextResponse:
    """
    Cached version of get_wiki_page_text for better performance
    """
    import time

    start_time = time.time()

    try:
        # Call the synchronous function in a thread pool
        import asyncio

        result = await asyncio.to_thread(get_wiki_page_text, page_title, lang)

        # Record cache miss metrics
        response_time = time.time() - start_time
        wiki_metrics.record_request(
            success=True, response_time=response_time, from_cache=False
        )

        return result
    except Exception as e:
        # Record error metrics
        response_time = time.time() - start_time
        from app.utils.wiki_optimization import classify_wiki_error

        error_type = classify_wiki_error(e)
        wiki_metrics.record_request(
            success=False, response_time=response_time, error_type=error_type
        )
        raise
