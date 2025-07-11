"""
LLM Validation Script: Date Parsing

This script is designed to test and validate the LLM's ability to parse
various natural language date strings into structured data. It does not
use a database and is intended to be run to observe the model's output.
"""

from pprint import pprint

import pytest

from app.services.llm_extractor import parse_date_strings_batch_with_llm
from app.services.llm_service import initialize_all_llm_clients

# List of challenging date strings to test the LLM's parsing capabilities
TEST_DATE_STRINGS = [
    "around the summer of 1994",
    "the first quarter of 2023",
    "late 2021",
    "Mid-June 1815",
    "the early 2000s",
    "a decade after the fall of the Berlin Wall",
    "the week of Thanksgiving, 1963",
    "Circa 480 BC",
    "the last day of the Heian period",
    "the beginning of the Meiji Restoration",
    "1950s",
    "the Spring of '88",
    "the Christmas season of 1999",
]


@pytest.fixture(scope="module", autouse=True)
def initialize_llm_services():
    """
    Fixture to initialize all configured LLM clients once per module.
    This ensures that API clients are ready before tests run.
    """
    initialize_all_llm_clients()


@pytest.mark.asyncio
async def test_llm_date_parsing_batch():
    """
    Tests the batch date parsing functionality of the LLM.

    This test sends a list of date strings to the LLM and prints the
    structured output. Its primary purpose is to verify that the LLM
    can be called and to allow for qualitative assessment of its parsing
    accuracy and format.
    """
    print("\n--- Testing LLM Batch Date Parsing ---")
    print("Input date strings:")
    pprint(TEST_DATE_STRINGS)

    # Prepare input for the batch function, which expects a list of dicts with an 'id'
    date_items_to_parse = [
        {"id": f"date_{i}", "date_str": date_str}
        for i, date_str in enumerate(TEST_DATE_STRINGS)
    ]

    # Call the LLM service
    parsed_dates_map = await parse_date_strings_batch_with_llm(date_items_to_parse)

    print("\n" + "=" * 25 + " LLM Parsing Results " + "=" * 25)
    # Sort by the original index for consistent output order
    sorted_items = sorted(
        parsed_dates_map.items(), key=lambda item: int(item[0].split("_")[1])
    )

    for key, parsed_info in sorted_items:
        original_string = next(
            (item["date_str"] for item in date_items_to_parse if item["id"] == key),
            "Unknown",
        )
        print(f"\n- Original:  '{original_string}'")
        if parsed_info:
            print(f"  - Display:   '{parsed_info.display_text}'")
            print(f"  - Precision: {parsed_info.precision}")
            print(
                f"  - Date Range: From {parsed_info.start_year}-{parsed_info.start_month or '?'}-{parsed_info.start_day or '?'} to {parsed_info.end_year}-{parsed_info.end_month or '?'}-{parsed_info.end_day or '?'}"
            )
        else:
            print("  - Failed to parse.")
    print("\n" + "=" * 70)

    # Basic assertion to ensure the process ran and returned something
    assert parsed_dates_map is not None, "The parsing function returned None."
    assert isinstance(parsed_dates_map, dict), "The result should be a dictionary."
    assert (
        len(parsed_dates_map) > 0
    ), "The parsing function should return at least one parsed date."

    print("\n--- LLM Batch Date Parsing Test Complete ---")
