"""
Dual Channel Progress Callback for timeline generation progress updates.

This module provides progress notifications through both WebSocket and A2A protocols.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger("dual_progress_callback", level="DEBUG")


class DualProgressCallback:
    """Dual Channel Progress Callback: Supports both WebSocket and A2A protocols"""

    def __init__(
        self,
        websocket_callback: Callable | None = None,
        a2a_callback=None,  # Use Any type to avoid import dependencies
        a2a_event_queue=None,  # A2A event queue
        a2a_context=None,  # A2A context
        request_id: str | None = None,
    ):
        """
        Initialize dual channel progress callback

        Args:
            websocket_callback: WebSocket callback function
            a2a_callback: A2A progress callback instance
            request_id: Request ID for logging
        """
        self.websocket_callback = websocket_callback
        self.a2a_callback = a2a_callback
        self.request_id = request_id

        # If A2A event queue and context are provided, create a direct sending callback
        if a2a_event_queue and a2a_context:
            try:
                from .a2a_progress_callback import A2AProgressCallback

                if hasattr(a2a_context, "context_id"):
                    logger.info(
                        f"Creating A2A progress callback with event queue type: {type(a2a_event_queue)}"
                    )
                    logger.info(f"Event queue instance: {id(a2a_event_queue)}")
                    self.a2a_callback = A2AProgressCallback(
                        event_queue=a2a_event_queue,  # Directly use the provided event queue
                        task_id=a2a_context.task_id,
                        context_id=a2a_context.context_id,
                    )
                    logger.info("Created direct A2A progress callback for event queue")
            except Exception as e:
                logger.warning(f"Failed to create direct A2A progress callback: {e}")

        # Record enabled channels
        enabled_channels = []
        if self.websocket_callback:
            enabled_channels.append("WebSocket")
        if self.a2a_callback:
            enabled_channels.append("A2A")

        logger.info(
            f"Initialized dual progress callback with channels: {', '.join(enabled_channels) or 'None'}"
        )

    async def report(
        self,
        message: str,
        step: str,
        data: dict[str, Any] | None,
        request_id: str | None = None,
    ):
        """
        Send progress information to available channels in parallel

        Args:
            message: Progress message
            step: Current step
            data: Progress data
            request_id: Request ID (overrides instance-level ID)
        """
        effective_request_id = request_id or self.request_id
        log_prefix = f"[{effective_request_id}] " if effective_request_id else ""

        tasks = []

        # WebSocket channel
        if self.websocket_callback:
            tasks.append(
                self._safe_websocket_report(message, step, data, effective_request_id)
            )

        # A2A channel
        if self.a2a_callback:
            tasks.append(self._safe_a2a_report(message, step, data))

        # Execute in parallel with exception isolation
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._log_report_results(results, log_prefix)
        else:
            logger.warning(f"{log_prefix}No progress channels available")

    async def _safe_websocket_report(
        self,
        message: str,
        step: str,
        data: dict[str, Any] | None,
        request_id: str | None,
    ):
        """Safe WebSocket progress report"""
        try:
            result = await self.websocket_callback(message, step, data, request_id)
            logger.debug(f"WebSocket progress sent: {step} - {message}")
            return result
        except Exception as e:
            logger.error(f"WebSocket progress report failed: {e}", exc_info=True)
            return None

    async def _safe_a2a_report(
        self, message: str, step: str, data: dict[str, Any] | None
    ):
        """Safe A2A progress report"""
        try:
            logger.debug(f"Attempting to send A2A progress: {step} - {message}")
            result = await self.a2a_callback.report_progress(message, step, data)
            logger.debug(f"A2A progress report result: {result}")
            return result
        except Exception as e:
            logger.error(f"A2A progress report failed: {e}", exc_info=True)
            return None

    def _log_report_results(self, results: list, log_prefix: str):
        """Log progress report results"""
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"{log_prefix}Progress report {i} failed: {result}")
            elif result is not None:
                logger.debug(f"{log_prefix}Progress report {i} succeeded")

    async def report_completion(
        self, final_message: str, final_data: dict[str, Any] | None = None
    ):
        """
        Report task completion

        Args:
            final_message: Completion message
            final_data: Final data
        """
        log_prefix = f"[{self.request_id}] " if self.request_id else ""
        logger.info(f"{log_prefix}Task completed: {final_message}")

        # Send completion event to A2A channel
        if self.a2a_callback:
            try:
                await self.a2a_callback.report_completion(final_message, final_data)
            except Exception as e:
                logger.error(f"{log_prefix}Failed to send A2A completion: {e}")

    async def report_error(
        self, error_message: str, error_data: dict[str, Any] | None = None
    ):
        """
        Report task error

        Args:
            error_message: Error message
            error_data: Error data
        """
        log_prefix = f"[{self.request_id}] " if self.request_id else ""
        logger.error(f"{log_prefix}Task failed: {error_message}")

        # Send error event to A2A channel
        if self.a2a_callback:
            try:
                await self.a2a_callback.report_error(error_message, error_data)
            except Exception as e:
                logger.error(f"{log_prefix}Failed to send A2A error: {e}")

    def has_websocket_channel(self) -> bool:
        """Check if WebSocket channel is available"""
        return self.websocket_callback is not None

    def has_a2a_channel(self) -> bool:
        """Check if A2A channel is available"""
        return self.a2a_callback is not None

    def get_enabled_channels(self) -> list[str]:
        """Get list of enabled channels"""
        channels = []
        if self.has_websocket_channel():
            channels.append("WebSocket")
        if self.has_a2a_channel():
            channels.append("A2A")
        return channels
