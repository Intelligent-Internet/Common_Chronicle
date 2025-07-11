"""
LLM Validation Script: Event Extraction

This script tests the LLM's ability to extract structured event information
from a block of text. It operates without a database and is intended for
qualitative assessment of the event extraction process.
"""


import pytest

from app.services.llm_extractor import extract_timeline_events_from_text
from app.services.llm_service import initialize_all_llm_clients

# A sample text about the history of the internet for testing event extraction.
# This text contains various events, dates, and entities.
TEST_INPUT_TEXT = """
The history of the Internet has its origin in the efforts to build and
interconnect computer networks that arose from research and development
in the United States and involved international collaboration,
particularly with researchers in the United Kingdom and France.

The Advanced Research Projects Agency (ARPA) of the U.S. Department of
Defense funded research to build a fault-tolerant, distributed network.
This research produced the ARPANET, which was one of the first networks
to use the TCP/IP protocol suite. The first message on the ARPANET was
sent by UCLA student programmer Charley Kline on October 29, 1969.

In the 1980s, research at CERN in Switzerland by British computer scientist
Tim Berners-Lee resulted in the World Wide Web, linking hypertext documents
into an information system, accessible from any node on the network.
The first web browser was released in 1991. The Mosaic web browser,
created at the National Center for Supercomputing Applications (NCSA)
at the University of Illinois Urbana-Champaign, was released in 1993 and
was one of the first browsers to display images inline with text, which
helped popularize the web.
"""


@pytest.fixture(scope="module", autouse=True)
def initialize_llm_services():
    """Initializes all configured LLM clients for the test module."""
    initialize_all_llm_clients()


@pytest.mark.asyncio
async def test_llm_event_extraction():
    """
    Tests the timeline event extraction functionality.

    This test feeds a sample text to the LLM and prints the list of
    extracted structured events. Its purpose is to verify that the
    extraction process works and to allow for inspection of the output quality.
    """
    print("\n--- Testing LLM Event Extraction ---")
    print("Input Text Snippet:")
    print(TEST_INPUT_TEXT)

    # Call the LLM service to extract events
    extracted_events = await extract_timeline_events_from_text(TEST_INPUT_TEXT)

    print("\n" + "=" * 25 + " LLM Extraction Results " + "=" * 25)
    if not extracted_events:
        print("No events were extracted.")
    else:
        for i, event in enumerate(extracted_events, 1):
            print(f"\n--- Event {i} ---")
            print(f"  - Source Text Snippet: {event.source_text_snippet}")
            print(f"  - Description: {event.description}")
            print(f"  - Date String: '{event.event_date_str}'")
            if event.main_entities:
                # Extract just the names for clean printing.
                # event.main_entities contains Pydantic objects, not dicts.
                entity_names = [entity.name for entity in event.main_entities]
                print(f"  - Entities:    {', '.join(entity_names)}")
            if event.date_info:
                print("  - Parsed Date:")
                print(f"    - Display:   '{event.date_info.display_text}'")
                print(
                    f"    - Range:     From {event.date_info.start_year}-{event.date_info.start_month or '?'}-{event.date_info.start_day or '?'} to {event.date_info.end_year}-{event.date_info.end_month or '?'}-{event.date_info.end_day or '?'}"
                )
            else:
                print("  - Parsed Date: None")
    print("\n" + "=" * 70)

    # Basic assertions to ensure the function ran correctly
    assert extracted_events is not None, "The extraction function returned None."
    assert isinstance(extracted_events, list), "The result should be a list of events."
    assert len(extracted_events) > 0, "The extraction should find at least one event."

    print("\n--- LLM Event Extraction Test Complete ---")
