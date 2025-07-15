"""
Text processing utilities for handling long text content.

This module provides text chunking capabilities for processing long articles
that exceed LLM token limits. It uses intelligent splitting based on natural
text boundaries while maintaining semantic coherence.
"""

import re

from app.utils.logger import setup_logger

logger = setup_logger("text_processing", level="DEBUG")


def split_text_into_chunks(
    text: str, chunk_size: int = 5000, overlap: int = 200
) -> list[str]:
    """
    Split text into chunks based on natural boundaries with overlap.

    This function intelligently splits text into manageable chunks while:
    1. Respecting paragraph and sentence boundaries
    2. Maintaining semantic coherence
    3. Creating overlap between chunks to prevent event loss

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
        # Split by sentence endings (., !, ?) followed by whitespace
        sentences = re.split(r"[.!?]+\s+", text)
        text_units = sentences
        logger.debug(
            f"No paragraph breaks found, using {len(sentences)} sentences as units"
        )
    else:
        text_units = paragraphs
        logger.debug(f"Found {len(paragraphs)} paragraphs as text units")

    chunks = []
    current_chunk = ""
    current_length = 0

    i = 0
    while i < len(text_units):
        unit = text_units[i].strip()
        unit_length = len(unit)

        # Handle units that are larger than chunk_size
        if unit_length > chunk_size:
            # If there's a current chunk, finalize it first
            if current_chunk:
                chunks.append(current_chunk.strip())
                logger.debug(
                    f"Created chunk {len(chunks)} with length {len(current_chunk)}"
                )
                current_chunk = ""
                current_length = 0

            # Add the oversized unit as its own chunk
            chunks.append(unit)
            logger.warning(
                f"Created oversized chunk {len(chunks)} with length {unit_length} (exceeds chunk_size {chunk_size})"
            )

            # Start next chunk with overlap from the oversized unit
            if overlap > 0:
                overlap_text = unit[-overlap:].strip()
                current_chunk = overlap_text
                current_length = len(overlap_text)
                logger.debug(
                    f"Started new chunk with overlap text of length {current_length}"
                )
            else:
                current_chunk = ""
                current_length = 0

            i += 1
            continue

        # If adding this unit would exceed chunk_size, finalize current chunk
        if current_length + unit_length > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            logger.debug(
                f"Created chunk {len(chunks)} with length {len(current_chunk)}"
            )

            # Start new chunk with overlap
            if overlap > 0 and current_chunk:
                # Take the last 'overlap' characters from current chunk
                overlap_text = current_chunk[-overlap:].strip()
                current_chunk = overlap_text
                current_length = len(overlap_text)
            else:
                current_chunk = ""
                current_length = 0

            # Don't increment i, try to add the same unit to the new chunk
            continue

        # Add unit to current chunk
        if current_chunk:
            current_chunk += "\n\n" + unit
            current_length += 2 + unit_length  # Account for the newlines
        else:
            current_chunk = unit
            current_length = unit_length

        i += 1

    # Add the final chunk if it has content
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
        logger.debug(
            f"Created final chunk {len(chunks)} with length {len(current_chunk)}"
        )

    logger.info(f"Text splitting complete: created {len(chunks)} chunks")

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
