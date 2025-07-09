"""
Progress callback utilities for timeline generation processes.

Provides callback system for reporting progress during long-running operations
with multiple callback registration and error handling for callback failures.
"""

from collections.abc import Callable
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger("timeline_orchestrator", level="DEBUG")


class ProgressCallback:
    """
    Progress callback interface for timeline generation processes.

    Manages multiple callback functions for progress reporting. Provides error
    handling to ensure callback failures don't affect the main processing pipeline.
    """

    def __init__(self, callbacks: list[Callable] = None):
        self.callbacks = callbacks or []

    async def report(
        self,
        message: str,
        step: str,
        data: dict[str, Any] | None = None,
        request_id: str | None = None,
    ):
        """
        Report progress to all registered callbacks.

        If any callback fails, the error is logged but doesn't prevent other
        callbacks from being executed.
        """
        for callback in self.callbacks:
            try:
                await callback(message, step, data, request_id)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}", exc_info=False)
