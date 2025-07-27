"""
Text processing utilities for handling long text content.

This module provides text chunking capabilities for processing long articles
that exceed LLM token limits. It uses intelligent splitting based on natural
text boundaries while maintaining semantic coherence.
"""

import re

from app.utils.logger import setup_logger

logger = setup_logger("text_processing", level="DEBUG")


def split_text_into_chunks(text, chunk_size=5000, overlap=200):
    """
    Split text into chunks based on natural boundaries with overlap.

    This function intelligently splits text into manageable chunks while:
    1. Respecting paragraph and sentence boundaries
    2. Maintaining semantic coherence
    3. Creating overlap between chunks to prevent event loss
    4. Preventing infinite loops through simple progress validation

    Args:
        text: The input text to be split
        chunk_size: Target size for each chunk in characters
        overlap: Number of characters to overlap between adjacent chunks

    Returns:
        List of text chunks with appropriate overlap
    """
    if not text or not text.strip():
        logger.warning("Empty or whitespace-only text provided for chunking")
        return []

    # Input validation
    if chunk_size <= 0:
        logger.error(f"Invalid chunk_size: {chunk_size}. Must be positive.")
        raise ValueError("chunk_size must be positive")

    if overlap < 0:
        logger.error(f"Invalid overlap: {overlap}. Must be non-negative.")
        raise ValueError("overlap must be non-negative")

    if overlap >= chunk_size:
        logger.warning(
            f"overlap ({overlap}) is >= chunk_size ({chunk_size}). Reducing overlap to {chunk_size // 2}"
        )
        overlap = chunk_size // 2

    if overlap < 100:
        logger.warning(f"overlap ({overlap}) is < 100. Increasing overlap to 100")
        overlap = 100

    if overlap > 1000:
        logger.warning(f"overlap ({overlap}) is > 1000. Reducing overlap to 1000")
        overlap = 1000

    text = text.strip()
    text_length = len(text)

    # If text is shorter than chunk_size, return as single chunk
    if text_length <= chunk_size:
        logger.info(
            f"Text length ({text_length}) is within chunk_size ({chunk_size}), returning single chunk"
        )
        return [text]

    logger.info(
        f"Splitting text of length {text_length} into chunks of size {chunk_size} with overlap {overlap}"
    )

    # Split text into paragraphs first (double newline)
    paragraphs = re.split(r"\n\s*\n", text)

    # If no paragraph breaks found, split by sentences
    if len(paragraphs) == 1:
        text_units = re.split(r"[.!?]+\s+", text)
    else:
        text_units = paragraphs

    processed_units = []
    for unit in text_units:
        unit = unit.strip()
        if not unit:
            continue
        if len(unit) > chunk_size:
            pieces = [unit[i : i + chunk_size] for i in range(0, len(unit), chunk_size)]
            processed_units.extend(pieces)
        else:
            processed_units.append(unit)

    chunks = []
    current_chunk = ""

    for i, unit in enumerate(processed_units):
        logger.debug(
            f"Processing unit {i} of {len(processed_units)}; current_chunk: {len(current_chunk)}"
        )
        if len(current_chunk) == 0:
            current_chunk = unit
        if len(current_chunk) + 2 + len(unit) <= chunk_size:
            current_chunk += "\n\n" + unit
        else:
            chunks.append(current_chunk)

            if len(current_chunk) <= overlap + 200:
                overlap = max(overlap // 2, 100)
                logger.warning(f"Reducing overlap to {overlap}")

            if len(current_chunk) > overlap:
                current_chunk = current_chunk[-overlap:] + "\n\n" + unit
            else:
                current_chunk = unit

    if current_chunk:
        chunks.append(current_chunk)

    # Log chunk size distribution for debugging
    chunk_sizes = [len(chunk) for chunk in chunks]
    if chunk_sizes:
        avg_size = sum(chunk_sizes) / len(chunk_sizes)
        min_size = min(chunk_sizes)
        max_size = max(chunk_sizes)
        logger.debug(
            f"Chunk size stats - Min: {min_size}, Max: {max_size}, Avg: {avg_size:.1f}"
        )

    return chunks


def estimate_chunk_count(text: str, chunk_size: int = 5000) -> int:
    """
    Estimate the number of chunks that will be created from text.

    Args:
        text: The input text
        chunk_size: Target chunk size in characters

    Returns:
        Estimated number of chunks
    """
    if not text or not text.strip():
        return 0

    text_length = len(text.strip())
    if text_length <= chunk_size:
        return 1

    # Rough estimate accounting for overlap
    return max(1, (text_length // chunk_size) + 1)
