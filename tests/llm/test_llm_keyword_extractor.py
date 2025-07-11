"""
LLM Validation Script: Keyword and Language Extraction

This script tests the LLM's ability to extract relevant keywords and detect
the language from a given viewpoint text. It operates without a database.
"""


import pytest

from app.services.llm_service import initialize_all_llm_clients
from app.services.viewpoint_processor import extract_keywords_from_viewpoint

# A sample viewpoint text for testing keyword extraction.
TEST_VIEWPOINT_TEXT = (
    "I want to understand the full history of the Crusades, "
    "focusing on the major military campaigns and their "
    "long-term impact on relations between Christians and Muslims."
)


@pytest.fixture(scope="module", autouse=True)
def initialize_llm_services():
    """Initializes all configured LLM clients for the test module."""
    initialize_all_llm_clients()


@pytest.mark.asyncio
async def test_llm_keyword_extraction():
    """
    Tests the keyword extraction and language detection functionality.

    This test sends a viewpoint text to the service and prints the
    resulting structured data, which includes original and English keywords,
    and the detected language.
    """
    print("\n--- Testing LLM Keyword Extraction ---")
    print("Input Viewpoint Text:")
    print(TEST_VIEWPOINT_TEXT)

    # Call the service to extract keywords and detect language
    extraction_result = await extract_keywords_from_viewpoint(TEST_VIEWPOINT_TEXT)

    print("\n" + "=" * 25 + " LLM Keyword Results " + "=" * 25)
    if extraction_result:
        print(f"- Detected Language:      {extraction_result.viewpoint_language}")
        print(
            f"- Original Keywords:      {', '.join(extraction_result.original_keywords)}"
        )
        print(
            f"- English Keywords:       {', '.join(extraction_result.english_keywords)}"
        )
        if extraction_result.translated_viewpoint:
            print(f"- Translated Viewpoint: '{extraction_result.translated_viewpoint}'")
    else:
        print("No keywords or language detected.")
    print("\n" + "=" * 70)

    # Basic assertions to ensure the function ran correctly
    assert extraction_result is not None, "The extraction function returned None."
    assert extraction_result.viewpoint_language, "Should have detected a language."
    assert (
        extraction_result.english_keywords
    ), "Should have extracted at least one keyword."

    print("\n--- LLM Keyword Extraction Test Complete ---")
