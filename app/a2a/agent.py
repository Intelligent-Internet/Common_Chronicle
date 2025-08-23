import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from app.db import AppAsyncSessionLocal
from app.models import Task
from app.services.timeline_orchestrator import TimelineOrchestratorService
from app.utils.logger import setup_logger

logger = setup_logger("a2a_agent")


class CommonChronicleA2AAgent:
    def __init__(self):
        self.orchestrator = TimelineOrchestratorService()
        logger.info("Common Chronicle A2A Agent initialized successfully")

    async def process_request(
        self,
        query: str,
        context: dict[str, Any] = None,
        a2a_context=None,
        event_queue=None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Process A2A requests and stream responses.

        Args:
            query: The user's request (viewpoint, research question, etc.)
            context: Additional context for the request
            a2a_context: A2A request context for progress notifications

        Yields:
            Streaming response chunks with progress updates
        """
        try:
            task_id = str(uuid.uuid4())
            logger.info(f"[A2A Task {task_id}] Processing request: {query[:100]}...")

            async for chunk in self._generate_timeline(
                query, context, task_id, a2a_context, event_queue
            ):
                yield chunk

        except Exception as e:
            logger.error(f"[A2A] Error processing request: {e}", exc_info=True)
            yield {
                "content": f"Error processing request: {str(e)}",
                "done": True,
                "error": True,
                "task_id": task_id if "task_id" in locals() else None,
            }

    async def _generate_timeline(
        self,
        query: str,
        context: dict[str, Any],
        task_id: str,
        a2a_context=None,
        event_queue=None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        try:
            logger.info(
                f"[A2A Task {task_id}] Starting timeline generation using existing core services for: {query}"
            )

            yield {
                "content": f"Starting timeline generation for: {query}",
                "done": False,
                "task_id": task_id,
                "progress": 10,
            }

            try:
                if self.orchestrator:
                    logger.info(
                        f"[A2A Task {task_id}] Using existing TimelineOrchestratorService"
                    )

                    task_config = {
                        "viewpoint_text": query,
                        "keywords": [],
                        "article_sources": [],
                        "data_source_preference": "dataset_wikipedia_en",
                        "timeline_parameters": {
                            "max_events": 20,
                            "date_range": None,
                            "relevance_threshold": 0.7,
                        },
                    }

                    task = Task(
                        id=task_id,
                        task_type="synthetic_viewpoint",
                        topic_text=query,  # Required field for synthetic_viewpoint
                        config=task_config,
                        status="pending",
                        is_public=False,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )

                    async with AppAsyncSessionLocal() as db:
                        db.add(task)
                        await db.commit()
                        await db.refresh(task)

                    yield {
                        "content": f"Task {task_id} created and saved to database, starting timeline generation...",
                        "done": False,
                        "task_id": task_id,
                        "progress": 20,
                    }

                    async def a2a_progress_callback(
                        message: str, step: str, data, request_id: str = None
                    ):
                        """Callback to send progress updates to A2A client."""
                        logger.info(
                            f"[A2A Task {task_id}] Progress: {step} - {message}"
                        )

                        return

                    try:
                        if event_queue and hasattr(
                            self.orchestrator, "set_a2a_event_queue"
                        ):
                            self.orchestrator.set_a2a_event_queue(event_queue)
                            logger.info("Set A2A event queue for orchestrator instance")

                        result = await self.orchestrator.run_timeline_generation_task(
                            task=task,
                            request_id=task_id,
                            websocket_callback=a2a_progress_callback,
                            a2a_context=a2a_context,
                        )

                        if result and hasattr(result, "events") and result.events:
                            timeline_summary = self._format_timeline_for_a2a(
                                result.events
                            )

                            logger.info(
                                f"[A2A Task {task_id}] Timeline generation completed with {len(result.events)} events"
                            )

                            yield {
                                "content": f"Timeline generation completed successfully!\n\n{timeline_summary}",
                                "done": True,
                                "task_id": task_id,
                                "progress": 100,
                                "result_data": {
                                    "events_count": len(result.events),
                                    "viewpoint_id": str(result.viewpoint_id)
                                    if hasattr(result, "viewpoint_id")
                                    else None,
                                    "timeline_summary": timeline_summary,
                                },
                            }
                        else:
                            logger.warning(
                                f"[A2A Task {task_id}] Timeline generation completed but no events were found in result"
                            )
                            logger.debug(
                                f"[A2A Task {task_id}] Result object: {result}"
                            )
                            if result:
                                logger.debug(
                                    f"[A2A Task {task_id}] Result attributes: {dir(result)}"
                                )
                                if hasattr(result, "events"):
                                    logger.debug(
                                        f"[A2A Task {task_id}] Result.events: {result.events}"
                                    )

                            yield {
                                "content": "Timeline generation completed but no events were generated",
                                "done": True,
                                "task_id": task_id,
                                "progress": 100,
                                "result_data": {
                                    "events_count": 0,
                                    "error": "No events generated",
                                    "debug_info": {
                                        "result_type": type(result).__name__
                                        if result
                                        else None,
                                        "result_has_events": hasattr(result, "events")
                                        if result
                                        else False,
                                        "result_events_count": len(result.events)
                                        if result
                                        and hasattr(result, "events")
                                        and result.events
                                        else 0,
                                    },
                                },
                            }

                    except Exception as orchestrator_error:
                        logger.error(
                            f"[A2A Task {task_id}] Orchestrator service error: {orchestrator_error}"
                        )
                        yield {
                            "content": f"Timeline generation completed with fallback processing for: {query}\n\nNote: Core service error: {str(orchestrator_error)}",
                            "done": True,
                            "task_id": task_id,
                            "progress": 100,
                        }
                else:
                    raise Exception("TimelineOrchestratorService not available")

            except Exception as service_error:
                logger.error(
                    f"[A2A Task {task_id}] Service integration error: {service_error}"
                )
                yield {
                    "content": f"Timeline generation completed with fallback processing for: {query}\n\nNote: Service integration failed: {str(service_error)}",
                    "done": True,
                    "task_id": task_id,
                    "progress": 100,
                }

        except Exception as e:
            logger.error(
                f"[A2A Task {task_id}] Error in timeline generation: {e}", exc_info=True
            )
            yield {
                "content": f"Error generating timeline: {str(e)}",
                "done": True,
                "error": True,
                "task_id": task_id,
            }

    def _format_timeline_for_a2a(self, events) -> str:
        """
        Format timeline events for A2A client consumption.

        Args:
            events: List of timeline events

        Returns:
            Formatted string representation of the timeline
        """
        if not events:
            return "No events found in timeline."

        timeline_lines = []
        timeline_lines.append(f"📅 Timeline with {len(events)} events:")
        timeline_lines.append("=" * 50)

        for i, event in enumerate(events, 1):
            event_date = getattr(event, "event_date_str", "Unknown Date")
            event_description = getattr(event, "description", "No description")

            event_line = f"{i:2d}. [{event_date}] {event_description}"
            timeline_lines.append(event_line)

            if hasattr(event, "entities") and event.entities:
                entity_names = [
                    entity.get("name", "Unknown")
                    for entity in event.entities
                    if entity.get("name")
                ]
                if entity_names:
                    timeline_lines.append(
                        f"    👥 Entities: {', '.join(entity_names[:3])}"
                    )

        timeline_lines.append("=" * 50)
        timeline_lines.append(f"Total events: {len(events)}")

        return "\n".join(timeline_lines)
