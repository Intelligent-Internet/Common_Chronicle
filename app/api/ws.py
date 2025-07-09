"""
WebSocket API Routes - Real-time task monitoring and progress updates.

Provides WebSocket endpoints for real-time monitoring of timeline generation tasks
with live progress updates and status changes.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosedOK

from app.db import AppAsyncSessionLocal, app_engine
from app.db_handlers import TaskDBHandler
from app.services.timeline_orchestrator import TimelineOrchestratorService
from app.utils.logger import setup_logger

logger = setup_logger("api")

router = APIRouter(prefix="/api")

# Global registry of active WebSocket connections indexed by request_id
active_websockets: dict[str, WebSocket] = {}


@router.websocket("/ws/timeline/from_task/{task_id}")
async def websocket_get_timeline_from_task(
    websocket: WebSocket,
    task_id: str,
    task_db_handler: TaskDBHandler = Depends(),
):
    """
    WebSocket endpoint for real-time task progress monitoring.

    Establishes a WebSocket connection to monitor timeline generation progress,
    sends historical progress, and handles task lifecycle management including
    starting background processing for pending tasks.
    """
    await websocket.accept()
    request_id = str(uuid.uuid4())
    logger.info(
        f"[WS RequestID: {request_id}] WebSocket connection established for task {task_id} monitoring."
    )

    # Register WebSocket for direct progress updates
    active_websockets[request_id] = websocket

    try:
        task_id = uuid.UUID(task_id)
        # Use a short-lived session for initial task validation and setup
        async with AppAsyncSessionLocal() as initial_db:
            task = await task_db_handler.get(task_id, db=initial_db)
            if not task:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Task {task_id} not found",
                        "request_id": request_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                await websocket.close()
                return

            # Send historical progress upon connection
            try:
                progress_steps = (
                    await task_db_handler.get_viewpoint_progress_steps_by_task_id(
                        task_id, db=initial_db
                    )
                )
                if progress_steps:
                    historical_payloads = [
                        {
                            "type": "status",
                            "message": step.get("message"),
                            "step": step.get("step_name"),
                            "data": {},
                            "request_id": request_id,
                            "timestamp": step.get("event_timestamp"),
                            "is_historical": True,
                        }
                        for step in progress_steps
                    ]
                    await websocket.send_json(
                        {
                            "type": "historical_progress",
                            "steps": historical_payloads,
                            "request_id": request_id,
                        }
                    )
                    logger.info(
                        f"[WS RequestID: {request_id}] Sent {len(progress_steps)} historical progress steps for task {task_id}."
                    )
            except Exception as e_hist:
                logger.error(
                    f"[WS RequestID: {request_id}] Error sending historical progress for task {task_id}: {e_hist}",
                    exc_info=True,
                )

            # Handle tasks that have already completed or failed
            if task.status == "completed":
                await websocket.send_json(
                    {
                        "type": "task_completed",
                        "message": f"Task {task_id} has already completed",
                        "task_id": str(task_id),
                        "request_id": request_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                await websocket.close()
                return

            elif task.status == "failed":
                await websocket.send_json(
                    {
                        "type": "task_failed",
                        "message": f"Task {task_id} has failed",
                        "task_id": str(task_id),
                        "error": task.notes,
                        "request_id": request_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                await websocket.close()
                return

            # Start background processing if task is in pending state
            if task.status == "pending":
                logger.info(
                    f"[WS RequestID: {request_id}] Starting background task for {task_id}"
                )
                orchestrator = TimelineOrchestratorService()
                asyncio.create_task(
                    orchestrator.run_timeline_generation_task(
                        task=task,
                        request_id=request_id,
                        websocket_callback=push_progress_to_websocket,
                    )
                )

        # Enter real-time monitoring mode for task status changes
        logger.info(
            f"[WS RequestID: {request_id}] Entering monitoring mode for task {task_id}"
        )

        while True:
            await asyncio.sleep(2.0)  # Poll task status every 2 seconds

            # Check if WebSocket is still connected before proceeding
            if websocket.client_state != WebSocketState.CONNECTED:
                logger.info(
                    f"[WS RequestID: {request_id}] WebSocket disconnected, stopping monitoring for task {task_id}"
                )
                # Remove disconnected connection from active registry
                active_websockets.pop(request_id, None)
                break

            # Use a fresh database session for each monitoring iteration
            async with AsyncSession(app_engine) as db:
                try:
                    # Retrieve current task status from database
                    current_task = await task_db_handler.get(id=task_id, db=db)
                    if not current_task:
                        logger.warning(
                            f"[WS RequestID: {request_id}] Task {task_id} disappeared from DB during monitoring."
                        )
                        break

                    if current_task.status == "completed":
                        # Verify WebSocket connection before sending notification
                        if websocket.client_state == WebSocketState.CONNECTED:
                            try:
                                await websocket.send_json(
                                    {
                                        "type": "task_completed",
                                        "message": f"Task {task_id} has completed successfully",
                                        "task_id": str(task_id),
                                        "request_id": request_id,
                                        "timestamp": datetime.now(UTC).isoformat(),
                                    }
                                )
                            except (
                                WebSocketDisconnect,
                                ConnectionClosedOK,
                                Exception,
                            ) as send_error:
                                logger.warning(
                                    f"[WS RequestID: {request_id}] Failed to send task completion message: {send_error}"
                                )
                                # Remove disconnected connection from active registry
                                active_websockets.pop(request_id, None)
                        else:
                            logger.info(
                                f"[WS RequestID: {request_id}] WebSocket disconnected, task {task_id} completed but client not notified"
                            )
                        break

                    elif current_task.status == "failed":
                        # Verify WebSocket connection before sending notification
                        if websocket.client_state == WebSocketState.CONNECTED:
                            try:
                                await websocket.send_json(
                                    {
                                        "type": "task_failed",
                                        "message": f"Task {task_id} has failed",
                                        "task_id": str(task_id),
                                        "error": current_task.notes,
                                        "request_id": request_id,
                                        "timestamp": datetime.now(UTC).isoformat(),
                                    }
                                )
                            except (
                                WebSocketDisconnect,
                                ConnectionClosedOK,
                                Exception,
                            ) as send_error:
                                logger.warning(
                                    f"[WS RequestID: {request_id}] Failed to send task failure message: {send_error}"
                                )
                                # Remove disconnected connection from active registry
                                active_websockets.pop(request_id, None)
                        else:
                            logger.info(
                                f"[WS RequestID: {request_id}] WebSocket disconnected, task {task_id} failed but client not notified"
                            )
                        break

                except Exception as e:
                    logger.error(
                        f"[WS RequestID: {request_id}] Unhandled error in monitoring loop: {e}",
                        exc_info=True,
                    )
                    break

    except ValueError as ve:
        logger.error(
            f"[WS RequestID: {request_id}] Invalid task_id format: {task_id}, error: {ve}"
        )
        await websocket.send_json(
            {
                "type": "error",
                "message": "Invalid task_id format",
                "request_id": request_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        await websocket.close()
    except WebSocketDisconnect:
        logger.info(
            f"[WS RequestID: {request_id}] Client disconnected during task {task_id} monitoring."
        )
        # Background task continues running independently of WebSocket connection
    except Exception as e:
        logger.error(
            f"[WS RequestID: {request_id}] Error monitoring task {task_id}: {e}",
            exc_info=True,
        )
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Task monitoring failed: {str(e)}",
                    "request_id": request_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except Exception:
            pass
    finally:
        logger.info(
            f"[WS RequestID: {request_id}] Closing WebSocket connection for task {task_id}."
        )
        # Remove WebSocket connection from active registry
        active_websockets.pop(request_id, None)

        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except Exception as e_close:
                logger.warning(
                    f"[WS RequestID: {request_id}] Error during WebSocket close: {e_close}"
                )


async def push_progress_to_websocket(message: str, step: str, data, request_id: str):
    """
    Push real-time progress updates to WebSocket connection.

    Callback function used by timeline orchestrator to send progress updates
    to connected WebSocket clients. Handles connection state verification
    and automatic cleanup of disconnected connections.
    """
    websocket = active_websockets.get(request_id)
    if websocket and websocket.client_state == WebSocketState.CONNECTED:
        try:
            await websocket.send_json(
                {
                    "type": "status",
                    "message": message,
                    "step": step,
                    "data": data or {},
                    "request_id": request_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except (WebSocketDisconnect, ConnectionClosedOK, Exception) as e:
            logger.warning(f"Failed to push progress to WebSocket {request_id}: {e}")
            # Remove disconnected WebSocket from registry
            active_websockets.pop(request_id, None)
    elif websocket:
        logger.debug(
            f"WebSocket {request_id} is not connected, removing from active connections"
        )
        # Remove disconnected WebSocket from registry
        active_websockets.pop(request_id, None)
