"""
Wikipedia URL normalization utilities for consistent source document deduplication.

This module provides functions to normalize Wikipedia URLs to a consistent format
based on page IDs, ensuring that different URL formats pointing to the same page
are treated as identical sources.
"""

import re
from urllib.parse import parse_qs, urlparse

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def normalize_wikipedia_url(
    url: str, wiki_pageid: str | None = None, language: str | None = None
) -> str:
    """
    Normalize Wikipedia URL to consistent curid format for deduplication.

    This function converts various Wikipedia URL formats to the standard
    curid format: https://{lang}.wikipedia.org/wiki?curid={pageid}

    Args:
        url: Original Wikipedia URL (any format)
        wiki_pageid: Page ID if known (extracted from URL if not provided)
        language: Language code if known (extracted from URL if not provided)

    Returns:
        Normalized URL in curid format, or original URL if normalization fails

    Examples:
        >>> normalize_wikipedia_url("https://en.wikipedia.org/wiki/Li_Xiaolai", "68212824", "en")
        "https://en.wikipedia.org/wiki?curid=68212824"

        >>> normalize_wikipedia_url("https://en.wikipedia.org/wiki?curid=68212824")
        "https://en.wikipedia.org/wiki?curid=68212824"
    """
    if not url or not isinstance(url, str):
        logger.warning(f"Invalid URL provided for normalization: {url}")
        return url

    try:
        parsed_url = urlparse(url.strip())

        # Extract language from hostname if not provided
        if not language:
            hostname_match = re.match(
                r"^([a-z]{2,3})\.wikipedia\.org$", parsed_url.netloc
            )
            if hostname_match:
                language = hostname_match.group(1)
            else:
                logger.warning(f"Could not extract language from URL: {url}")
                return url

        # Extract pageid if not provided
        if not wiki_pageid:
            # Try to extract from curid parameter first
            query_params = parse_qs(parsed_url.query)
            if "curid" in query_params:
                wiki_pageid = query_params["curid"][0]
            else:
                logger.warning(
                    f"No wiki_pageid provided and could not extract curid from URL: {url}"
                )
                return url

        # Validate that we have the required components
        if not wiki_pageid or not language:
            logger.warning(
                f"Missing required components for normalization - pageid: {wiki_pageid}, language: {language}"
            )
            return url

        # Generate normalized URL
        normalized_url = f"https://{language}.wikipedia.org/wiki?curid={wiki_pageid}"

        if normalized_url != url:
            logger.debug(f"Normalized URL from '{url}' to '{normalized_url}'")

        return normalized_url

    except Exception as e:
        logger.error(f"Error normalizing Wikipedia URL '{url}': {e}", exc_info=True)
        return url


def extract_pageid_from_wikipedia_url(url: str) -> str | None:
    """
    Extract page ID from Wikipedia URL if present.

    Args:
        url: Wikipedia URL to extract page ID from

    Returns:
        Page ID as string if found, None otherwise
    """
    if not url or not isinstance(url, str):
        return None

    try:
        parsed_url = urlparse(url.strip())
        query_params = parse_qs(parsed_url.query)

        if "curid" in query_params:
            return query_params["curid"][0]

    except Exception as e:
        logger.debug(f"Could not extract pageid from URL '{url}': {e}")

    return None


def is_wikipedia_source(source_type: str, url: str = "") -> bool:
    """
    Check if a source is a Wikipedia source that should be normalized.

    Args:
        source_type: The source type identifier
        url: Optional URL to check for wikipedia.org domain

    Returns:
        True if this is a Wikipedia source that should be normalized
    """
    if not source_type:
        return False

    # Check source_type for Wikipedia indicators
    source_type_lower = source_type.lower()
    if "wikipedia" in source_type_lower:
        return True

    # Check URL for Wikipedia domain as fallback
    if url:
        url_lower = url.lower()
        if "wikipedia.org" in url_lower:
            return True

    return False
