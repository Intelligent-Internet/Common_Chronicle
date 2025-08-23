"""
A2A Protocol Progress Callback for timeline generation progress updates.

This module provides A2A-standard progress notifications using TaskStatusUpdateEvent.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger("a2a_progress_callback", level="DEBUG")


class A2AProgressCallback:
    """A2A Protocol Progress Notification Callback"""

    def __init__(self, event_queue, task_id: str, context_id: str):
        """
        Initialize A2A Progress Callback

        Args:
            event_queue: A2A Event Queue
            task_id: Task ID
            context_id: Context ID
        """
        self.event_queue = event_queue
        self.task_id = task_id
        self.context_id = context_id

        # Delay import of A2A dependencies to avoid startup errors
        self._a2a_available = self._check_a2a_availability()

        if not self._a2a_available:
            logger.warning("A2A modules not available, A2A progress will be disabled")

    def _check_a2a_availability(self) -> bool:
        """Check if A2A related modules are available"""
        try:
            # Try to import necessary A2A modules
            pass

            return True
        except ImportError:
            logger.debug("A2A modules not available")
            return False

    async def report_progress(
        self, message: str, step: str, data: dict[str, Any] | None
    ):
        """
        Send A2A standard progress event

        Args:
            message: Progress message
            step: Current step
            data: Progress data
        """
        if not self._a2a_available:
            logger.debug("A2A progress disabled, skipping progress report")
            return

        try:
            # Delay import of A2A types and tools
            from a2a.types import (
                Message,
                TaskState,
                TaskStatus,
                TaskStatusUpdateEvent,
                TextPart,
            )

            # Create progress status update event (using correct A2A protocol)
            progress_message = Message(
                message_id=str(uuid.uuid4()),
                role="agent",
                parts=[
                    TextPart(
                        text=f"[{step}] {message}",
                        metadata={"step": step, "progress_data": data},
                    )
                ],
                task_id=self.task_id,
                context_id=self.context_id,
            )

            progress_event = TaskStatusUpdateEvent(
                context_id=self.context_id,
                task_id=self.task_id,
                status=TaskStatus(
                    state=TaskState.working,  # Use working state
                    message=progress_message,
                    timestamp=datetime.now(UTC).isoformat(),
                ),
                final=False,  # Not final state
            )

            # Send to A2A event queue
            logger.info(
                f"About to enqueue A2A progress event to queue: {type(self.event_queue)}"
            )
            logger.info(
                f"Event details: context_id={self.context_id}, task_id={self.task_id}, state=working, text=[{step}] {message}"
            )

            # Log complete event object information
            logger.info(f"Progress event type: {type(progress_event)}")
            logger.info(
                f"Progress event kind: {getattr(progress_event, 'kind', 'N/A')}"
            )
            logger.info(
                f"Progress event fields: {[attr for attr in dir(progress_event) if not attr.startswith('_')]}"
            )

            # Try to get JSON representation of the event
            try:
                event_dict = (
                    progress_event.model_dump()
                    if hasattr(progress_event, "model_dump")
                    else progress_event.__dict__
                )
                logger.info(f"Progress event data: {event_dict}")
            except Exception as e:
                logger.warning(f"Could not serialize progress event: {e}")

            # Log detailed information before sending
            logger.info(
                f"About to send progress event to queue: {type(self.event_queue)}"
            )
            logger.info(f"Queue instance ID: {id(self.event_queue)}")

            # Try to send the event
            result = await self.event_queue.enqueue_event(progress_event)
            logger.info(f"Event enqueue result: {result}")
            logger.info(
                f"A2A progress sent: {step} - {message}"
            )  # Changed to INFO level

        except Exception as e:
            logger.error(f"Failed to send A2A progress event: {e}", exc_info=True)

    async def report_completion(
        self, final_message: str, final_data: dict[str, Any] | None = None
    ):
        """
        Send task completion event

        Args:
            final_message: Completion message
            final_data: Final data
        """
        if not self._a2a_available:
            return

        try:
            from a2a.types import (
                Message,
                TaskState,
                TaskStatus,
                TaskStatusUpdateEvent,
                TextPart,
            )

            # Create completion status update event (using correct A2A protocol)
            completion_message = Message(
                message_id=str(uuid.uuid4()),
                role="agent",
                parts=[
                    TextPart(
                        text=f"Completed: {final_message}",
                        metadata={"completion_data": final_data},
                    )
                ],
                task_id=self.task_id,
                context_id=self.context_id,
            )

            completion_event = TaskStatusUpdateEvent(
                context_id=self.context_id,
                task_id=self.task_id,
                status=TaskStatus(
                    state=TaskState.completed,  # Use completed state
                    message=completion_message,
                    timestamp=datetime.now(UTC).isoformat(),
                ),
                final=True,  # This is the final state
            )

            await self.event_queue.enqueue_event(completion_event)
            logger.debug(f"A2A completion sent: {final_message}")

        except Exception as e:
            logger.error(f"Failed to send A2A completion event: {e}", exc_info=True)

    async def report_error(
        self, error_message: str, error_data: dict[str, Any] | None = None
    ):
        """
        Send error event

        Args:
            error_message: Error message
            error_data: Error data
        """
        if not self._a2a_available:
            return

        try:
            from a2a.types import (
                Message,
                TaskState,
                TaskStatus,
                TaskStatusUpdateEvent,
                TextPart,
            )

            # Create error status update event (using correct A2A protocol)
            error_message = Message(
                message_id=str(uuid.uuid4()),
                role="agent",
                parts=[
                    TextPart(
                        text=f"Error: {error_message}",
                        metadata={"error_data": error_data},
                    )
                ],
                task_id=self.task_id,
                context_id=self.context_id,
            )

            error_event = TaskStatusUpdateEvent(
                context_id=self.context_id,
                task_id=self.task_id,
                status=TaskStatus(
                    state=TaskState.failed,  # Use failed state
                    message=error_message,
                    timestamp=datetime.now(UTC).isoformat(),
                ),
                final=True,  # This is the final state
            )

            await self.event_queue.enqueue_event(error_event)
            logger.debug(f"A2A error sent: {error_message}")

        except Exception as e:
            logger.error(f"Failed to send A2A error event: {e}", exc_info=True)
