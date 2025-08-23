import uuid
from datetime import UTC, datetime
from typing import override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    DataPart,
    Message,
    Part,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils import new_artifact, new_text_artifact

from app.a2a.agent import CommonChronicleA2AAgent
from app.db_handlers import TaskDBHandler
from app.services.timeline_orchestrator import TimelineOrchestratorService
from app.utils.logger import setup_logger

logger = setup_logger("a2a_executor")


class CommonChronicleAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = CommonChronicleA2AAgent()
        self.timeline_orchestrator = TimelineOrchestratorService()

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            logger.info(
                f"Setting A2A event queue in executor: {type(event_queue)}, instance: {id(event_queue)}"
            )
            self.timeline_orchestrator.set_a2a_event_queue(event_queue)

            query = context.get_user_input()
            if not query:
                raise Exception("No user input provided in request context")

            request_context = {}
            if context.message and hasattr(context.message, "content"):
                if hasattr(context.message.content, "get"):
                    request_context = context.message.content
                elif isinstance(context.message.content, str):
                    request_context = {"additional_context": context.message.content}

            logger.info(f"[A2A] Processing request: {query[:100]}...")

            try:
                ack_message = Message(
                    message_id=str(uuid.uuid4()),
                    role="agent",
                    parts=[
                        TextPart(
                            text=f"Request received. Starting processing...\n\n{query[:200]}"
                        )
                    ],
                    task_id=context.task_id,
                    context_id=context.context_id,
                )
                ack_status = TaskStatusUpdateEvent(
                    context_id=context.context_id,
                    task_id=context.task_id,
                    status=TaskStatus(
                        state=TaskState.working,
                        message=ack_message,
                        timestamp=datetime.now(UTC).isoformat(),
                    ),
                    final=False,
                )
                await event_queue.enqueue_event(ack_status)
            except Exception:
                pass

            async for event in self.agent.process_request(
                query,
                request_context,
                a2a_context=context,
                event_queue=event_queue,
            ):
                if event.get("error"):
                    error_artifact = new_text_artifact(
                        name="error", text=event["content"]
                    )
                    await event_queue.enqueue_event(
                        TaskArtifactUpdateEvent(
                            context_id=context.context_id,
                            task_id=context.task_id,
                            artifact=error_artifact,
                        )
                    )
                    break

                # Do not send duplicate progress artifacts here
                if not event.get("done"):
                    pass

                if event.get("done"):
                    final_parts: list[Part] = [
                        Part(root=TextPart(text=event["content"]))
                    ]
                    try:
                        handler = TaskDBHandler()
                        db_task_id_str = event.get("task_id") or context.task_id
                        task_uuid = uuid.UUID(str(db_task_id_str))
                        task_details = (
                            await handler.get_task_with_complete_viewpoint_details(
                                task_uuid
                            )
                        )
                        if task_details:
                            final_parts.append(Part(root=DataPart(data=task_details)))
                    except Exception:
                        pass

                    final_artifact = new_artifact(parts=final_parts, name="result")
                    await event_queue.enqueue_event(
                        TaskArtifactUpdateEvent(
                            context_id=context.context_id,
                            task_id=context.task_id,
                            artifact=final_artifact,
                        )
                    )
                    try:
                        completion_status = TaskStatusUpdateEvent(
                            context_id=context.context_id,
                            task_id=context.task_id,
                            status=TaskStatus(state=TaskState.completed),
                            final=True,
                        )
                        await event_queue.enqueue_event(completion_status)
                    except Exception:
                        pass
                    break

        except Exception as e:
            logger.error(f"[A2A] Error in execute: {e}", exc_info=True)
            try:
                error_artifact = new_text_artifact(
                    name="error", text=f"Execution error: {str(e)}"
                )
                await event_queue.enqueue_event(
                    TaskArtifactUpdateEvent(
                        context_id=context.context_id,
                        task_id=context.task_id,
                        artifact=error_artifact,
                    )
                )
            except Exception:
                pass

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info(f"[A2A] Cancelling task {context.task_id}")

        cancel_artifact = new_text_artifact(
            name="cancelled", text=f"Task {context.task_id} was cancelled."
        )
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                context_id=context.context_id,
                task_id=context.task_id,
                artifact=cancel_artifact,
            )
        )
