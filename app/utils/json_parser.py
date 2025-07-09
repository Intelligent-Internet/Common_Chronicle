"""
JSON parsing utilities for extracting structured data from LLM responses.

Handles JSON embedded in markdown code blocks or mixed with other text.
"""

import json
import re
from typing import Any


def extract_json_from_llm_response(text: str) -> Any | None:
    """
    Extract JSON from text that may contain markdown and other content.

    Handles common scenarios where LLM responses contain JSON data
    embedded in markdown code blocks or mixed with other text.
    Uses multi-step approach to locate and extract valid JSON.
    """
    # Extract content between ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)

    json_str = ""
    if match:
        json_str = match.group(1).strip()
    else:
        # If no markdown block, assume the whole string might contain the JSON
        json_str = text

    # Find the start of the first JSON object '{' or array '['
    # to remove any leading text that is not part of the JSON
    first_brace = json_str.find("{")
    first_square = json_str.find("[")

    start_index = -1
    if first_brace != -1 and first_square != -1:
        start_index = min(first_brace, first_square)
    elif first_brace != -1:
        start_index = first_brace
    else:
        start_index = first_square

    if start_index != -1:
        json_str = json_str[start_index:]

    # Find the last corresponding closing bracket to remove any trailing text
    last_brace = json_str.rfind("}")
    last_square = json_str.rfind("]")
    end_index = max(last_brace, last_square)

    if end_index != -1:
        json_str = json_str[: end_index + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None
