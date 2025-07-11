"""
LLM Validation Script: Article Relevance Scoring

This script tests the LLM's ability to score the relevance of multiple
articles against a given viewpoint text. It operates without a database.
"""


import pytest

from app.services.llm_extractor import score_articles_relevance
from app.services.llm_service import initialize_all_llm_clients

# The central topic or research question
TEST_VIEWPOINT_TEXT = (
    "The rise of personal computing and its impact on the software industry."
)

# A list of articles with varying degrees of relevance to the viewpoint
TEST_ARTICLES = [
    {
        "title": "The History of the Apple Macintosh",
        "text_content": (
            "The Macintosh, launched in 1984, was one of the first commercially "
            "successful personal computers to feature a graphical user interface (GUI) "
            "and a mouse. It fundamentally changed the way people interacted with "
            "computers and set the stage for modern operating systems."
        ),
    },
    {
        "title": "Microsoft's Dominance with Windows",
        "text_content": (
            "Microsoft Windows became the dominant operating system for personal computers "
            "in the 1990s, creating a massive ecosystem for software developers. "
            "The release of Windows 95 was a watershed moment for the PC industry."
        ),
    },
    {
        "title": "The Invention of the Transistor",
        "text_content": (
            "The transistor, invented at Bell Labs in 1947, is the fundamental "
            "building block of modern electronics. While not a personal computer itself, "
            "its invention was a critical precursor to the development of microprocessors."
        ),
    },
    {
        "title": "The Growth of the Video Game Market",
        "text_content": (
            "The video game market, while related to personal computing, focuses on "
            "entertainment software and dedicated console hardware. Companies like "
            "Nintendo and Sega competed for market share throughout the 80s and 90s."
        ),
    },
]


@pytest.fixture(scope="module", autouse=True)
def initialize_llm_services():
    """Initializes all configured LLM clients for the test module."""
    initialize_all_llm_clients()


@pytest.mark.asyncio
async def test_llm_article_relevance_scoring():
    """
    Tests the article relevance scoring functionality.

    This test provides a viewpoint and several articles to the LLM service,
    then prints the relevance scores assigned to each article.
    """
    print("\n--- Testing LLM Article Relevance Scoring ---")
    print("Viewpoint Text:")
    print(f"'{TEST_VIEWPOINT_TEXT}'")
    print("\nArticles to be scored:")
    for article in TEST_ARTICLES:
        print(f"- {article['title']}")

    # Call the LLM service to score the articles
    relevance_scores = await score_articles_relevance(
        viewpoint_text=TEST_VIEWPOINT_TEXT, articles=TEST_ARTICLES
    )

    print("\n" + "=" * 25 + " LLM Scoring Results " + "=" * 25)
    if not relevance_scores:
        print("No scores were returned.")
    else:
        # Sort by score for readability
        sorted_scores = sorted(
            relevance_scores.items(), key=lambda item: item[1], reverse=True
        )
        for title, score in sorted_scores:
            print(f"- Score: {score:.2f} | Article: '{title}'")
    print("\n" + "=" * 70)

    # Basic assertions
    assert relevance_scores is not None, "The scoring function returned None."
    assert isinstance(relevance_scores, dict), "The result should be a dictionary."
    assert len(relevance_scores) == len(
        TEST_ARTICLES
    ), "Should return a score for each article."

    print("\n--- LLM Article Relevance Scoring Test Complete ---")
