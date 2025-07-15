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
    if not text or not text.strip():
        return None

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

    # Try to parse as-is first
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # If direct parsing fails, try to fix truncated JSON
    # Find the last corresponding closing bracket to remove any trailing text
    last_brace = json_str.rfind("}")
    last_square = json_str.rfind("]")
    end_index = max(last_brace, last_square)

    if end_index != -1:
        json_str = json_str[: end_index + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # If still failing, try to repair common truncation patterns
    repaired_json = _attempt_json_repair(json_str)
    if repaired_json:
        try:
            return json.loads(repaired_json)
        except json.JSONDecodeError:
            pass

    return None


def _attempt_json_repair(json_str: str) -> str | None:
    """
    Attempt to repair truncated JSON by adding missing closing brackets.

    This function tries to fix common JSON truncation patterns by:
    1. Counting opening and closing brackets
    2. Adding missing closing brackets
    3. Removing incomplete last entries
    """
    if not json_str:
        return None

    # Remove any trailing incomplete content
    json_str = json_str.rstrip()

    # Count brackets to determine what's missing
    open_braces = json_str.count("{")
    close_braces = json_str.count("}")
    open_squares = json_str.count("[")
    close_squares = json_str.count("]")

    # If we have a reasonable amount of JSON content
    if open_braces > 0 or open_squares > 0:
        # Try to remove incomplete last item if it exists
        truncated_patterns = [
            r',\s*"[^"]*$',  # Incomplete key like: , "main
            r",\s*{[^}]*$",  # Incomplete object like: , {"name": "test
            r':\s*"[^"]*$',  # Incomplete value like: "name": "test
            r":\s*[^,}\]]*$",  # Incomplete value like: "type": "organ
        ]

        for pattern in truncated_patterns:
            if re.search(pattern, json_str):
                json_str = re.sub(pattern, "", json_str)
                break

        # Add missing closing brackets
        missing_braces = open_braces - close_braces
        missing_squares = open_squares - close_squares

        if missing_braces > 0:
            json_str += "}" * missing_braces
        if missing_squares > 0:
            json_str += "]" * missing_squares

        return json_str

    return None
