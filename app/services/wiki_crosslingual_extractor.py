"""
Cross-lingual Wikipedia extraction utilities for multi-language entity information.

Provides functionality for finding Wikipedia pages across different languages
using interlanguage links with redirect handling and text extraction.
"""

import json
import urllib.parse
from typing import Any

import requests

from app.config import settings
from app.schemas import (
    CrosslingualWikiTextResponse,
    InterlanguageLinkResponse,
    WikiPageTextResponse,
)
from app.services.wiki_extractor import get_wiki_page_text
from app.utils.logger import setup_logger

logger = setup_logger("wiki_crosslingual_extractor")


def get_interlanguage_link(
    source_page_title: str, source_lang: str, target_lang: str
) -> InterlanguageLinkResponse:
    """
    Find the title of a Wikipedia page in a target language given a source page.
    Handles redirects on the source page and returns structured link information.
    """
    api_url = f"https://{source_lang}.wikipedia.org/w/api.php"

    current_source_page_title = source_page_title
    current_source_url = f"https://{source_lang}.wikipedia.org/wiki/{urllib.parse.quote(current_source_page_title.replace(' ', '_'))}"

    error_message_val: str | None = None
    target_link_title_val: str | None = None
    target_link_url_val: str | None = None
    source_redirect_info_val: dict[str, str] | None = None
    raw_response_data_val: dict[str, Any] | None = None

    params = {
        "action": "query",
        "format": "json",
        "titles": source_page_title,
        "prop": "langlinks",
        "lllang": target_lang,
        "lllimit": 1,
        "llprop": "url",
        "redirects": True,
        "maxlag": 5,
        "origin": "*",
    }

    headers = {"User-Agent": settings.wiki_api_user_agent}

    try:
        logger.info(
            f"Requesting langlink for '{source_page_title}' ({source_lang}) to {target_lang}. "
            f"User-Agent: {settings.wiki_api_user_agent}"
        )
        logger.debug(f"API URL: {api_url}, Params: {json.dumps(params)}")

        response = requests.get(
            api_url, params=params, headers=headers, timeout=(5, 30)
        )
        response.raise_for_status()

        data = response.json()
        raw_response_data_val = data  # Store raw data

        query_data = data.get("query", {})

        if "redirects" in query_data:
            redirect = query_data["redirects"][0]
            from_title = redirect.get("from")
            to_title = redirect.get("to")
            if from_title and to_title:  # Check if both are valid
                logger.info(
                    f"Source page '{from_title}' ({source_lang}) redirected to '{to_title}'."
                )
                source_redirect_info_val = {"from": from_title, "to": to_title}
                current_source_page_title = to_title

        if "normalized" in query_data:
            normalized_redirect = query_data["normalized"][0]
            from_normalized = normalized_redirect.get("from")
            to_normalized = normalized_redirect.get("to")
            if (
                from_normalized
                and to_normalized
                and from_normalized == current_source_page_title
            ):
                logger.info(
                    f"Source page title '{from_normalized}' ({source_lang}) normalized to '{to_normalized}'."
                )
                current_source_page_title = to_normalized

        # Update URL based on the potentially changed current_source_page_title
        current_source_url = f"https://{source_lang}.wikipedia.org/wiki/{urllib.parse.quote(current_source_page_title.replace(' ', '_'))}"

        pages = query_data.get("pages")
        if not pages:
            error_message_val = f"No 'pages' in API response for '{current_source_page_title}' ({source_lang})."
            logger.error(error_message_val)
            # Fall through to return statement

        if not error_message_val:  # Proceed only if no error so far
            for page_id, page_data in pages.items():
                # Update current_source_page_title if API indicates a different title for the page ID
                api_definitive_title = page_data.get("title")
                if (
                    api_definitive_title
                    and api_definitive_title != current_source_page_title
                ):
                    logger.info(
                        f"Source page title confirmed by API as '{api_definitive_title}' for langlinks."
                    )
                    current_source_page_title = api_definitive_title
                    current_source_url = f"https://{source_lang}.wikipedia.org/wiki/{urllib.parse.quote(current_source_page_title.replace(' ', '_'))}"

                if page_id == "-1" or "missing" in page_data:
                    error_message_val = (
                        f"Source page '{current_source_page_title}' ({source_lang}, URL: {current_source_url}) "
                        f"not found or is missing after potential redirect/normalization. Original request: '{source_page_title}'."
                    )
                    logger.error(error_message_val)
                    break  # Break from pages loop

                langlinks = page_data.get("langlinks")
                if langlinks:
                    link = langlinks[0]  # Expecting one due to lllimit=1
                    if link.get("lang") == target_lang:
                        target_link_title_val = link.get("*")
                        target_link_url_val = link.get("url")
                        logger.info(
                            f"Found langlink for '{current_source_page_title}' ({source_lang}) to "
                            f"{target_lang}: '{target_link_title_val}' (URL: {target_link_url_val})."
                        )
                        # Successfully found, break from pages loop (should be only one page anyway)
                        break

                if (
                    not target_link_title_val
                ):  # If after checking langlinks, it's still not found
                    error_message_val = (
                        f"No {target_lang} langlink found for source page "
                        f"'{current_source_page_title}' ({source_lang}, URL: {current_source_url})."
                    )
                    logger.warning(error_message_val)
                break  # Processed the first (and only expected) page item

    except requests.exceptions.RequestException as e:
        error_message_val = f"RequestException for langlink: '{source_page_title}' ({source_lang}) to {target_lang}. Error: {str(e)}"
        logger.error(error_message_val, exc_info=True)
    except json.JSONDecodeError as e:
        # raw_response_text might not be defined if error occurred before response.text
        raw_text_preview = (
            response.text[:500] + "..."
            if "response" in locals() and hasattr(response, "text")
            else "N/A"
        )
        error_message_val = (
            f"KeyError parsing langlink response for '{source_page_title}' ({source_lang}) to {target_lang}. "
            f"Missing key: {str(e)}. Response data (raw preview): {raw_text_preview}"
        )
        logger.error(error_message_val, exc_info=True)
    except KeyError as e:
        error_message_val = (
            f"KeyError parsing langlink response for '{source_page_title}' ({source_lang}) to {target_lang}. "
            f"Missing key: {str(e)}. Response data: {raw_response_data_val}"
        )
        logger.error(error_message_val, exc_info=True)
    except Exception as e:
        error_message_val = f"Unexpected error getting langlink for '{source_page_title}' ({source_lang}) to {target_lang}. Error: {type(e).__name__} - {str(e)}"
        logger.error(error_message_val, exc_info=True)

    return InterlanguageLinkResponse(
        source_title=current_source_page_title,
        source_url=current_source_url,
        target_title=target_link_title_val,
        target_url=target_link_url_val,
        error=error_message_val,
        source_redirect_info=source_redirect_info_val,
        raw_response_data=raw_response_data_val,
    )


def get_wiki_page_text_for_target_lang(
    source_page_title: str, source_lang: str, target_lang: str
) -> CrosslingualWikiTextResponse:
    """
    Extract text content from a Wikipedia page in a target language via interlanguage links.

    First finds the target language page using interlanguage links, then extracts
    the full text content from that page.
    """
    overall_status_val: str = "pending"
    extracted_text_val: str | None = None
    error_message_val: str | None = None
    final_text_url_val: str | None = None
    final_text_title_val: str | None = None
    final_page_id_val: int | None = None
    text_extraction_outcome_val: WikiPageTextResponse | None = None

    logger.info(
        f"Attempting to get crosslingual text for '{source_page_title}' ({source_lang}) in {target_lang}."
    )

    link_info_result = get_interlanguage_link(
        source_page_title, source_lang, target_lang
    )

    if link_info_result.error:
        overall_status_val = "error_in_link_search"
        error_message_val = (
            f"Failed to find interlanguage link: {link_info_result.error}"
        )
        logger.error(error_message_val)

    elif not link_info_result.target_title:
        overall_status_val = "link_not_found"
        # Provide more context from link_info_result if the title is missing but no primary error was set
        error_detail = link_info_result.error or (
            f"No target language link title returned by get_interlanguage_link. "
            f"Source checked: '{link_info_result.source_title or 'N/A'}'"
        )
        error_message_val = f"No interlanguage link title found for '{source_page_title}' ({source_lang}) to {target_lang}. Detail: {error_detail}"
        logger.warning(error_message_val)

    else:  # Link found, proceed to get text
        target_title = link_info_result.target_title
        # Use .get for URL as it might be None if not found by API, though llprop=url should provide it
        target_linked_url = (
            link_info_result.target_url or "URL not provided in link info"
        )

        logger.info(
            f"Interlanguage link to '{target_lang}' found: Title='{target_title}', Linked_URL='{target_linked_url}'. "
            f"Now attempting to fetch content for this target page."
        )

        logger.info(f"Attempting to get text for '{target_title}' in {target_lang}.")
        text_extraction_outcome_val = get_wiki_page_text(
            page_title=target_title, lang=target_lang
        )

        if text_extraction_outcome_val.error:
            overall_status_val = "text_extraction_failed"
            error_message_val = f"Found link to '{target_title}' ({target_lang}) but failed to extract text: {text_extraction_outcome_val.error}"
            logger.error(error_message_val)
        else:
            extracted_text_val = text_extraction_outcome_val.text
            if extracted_text_val:
                overall_status_val = "success"
                final_text_url_val = text_extraction_outcome_val.url
                final_text_title_val = text_extraction_outcome_val.title
                final_page_id_val = text_extraction_outcome_val.page_id
                logger.info(
                    f"Successfully extracted crosslingual text for '{source_page_title}' ({source_lang}) -> '{target_title}' ({target_lang})."
                )
            else:
                overall_status_val = "text_extraction_failed"
                error_message_val = (
                    f"Found link to '{target_title}' ({target_lang}) and processed, but no text was extracted. "
                    f"Underlying reason: {text_extraction_outcome_val.error or 'No specific error, text content was empty.'}"
                )
                logger.warning(error_message_val)

    return CrosslingualWikiTextResponse(
        link_search_outcome=link_info_result,
        text_extraction_outcome=text_extraction_outcome_val,
        overall_status=overall_status_val,
        text=extracted_text_val,
        error=error_message_val,
        url=final_text_url_val,
        title=final_text_title_val,
        page_id=final_page_id_val,
    )
