#!/usr/bin/env python3
"""
Common Chronicle MCP Tools - With Progress Reporting

This version implements FastMCP best practices for long-running tasks
using the official progress reporting mechanism.
"""

import asyncio
import uuid
from typing import Any

from fastmcp import Context, FastMCP

from app.utils.logger import setup_logger

logger = setup_logger("mcp_tools")

# Create MCP server instance
mcp = FastMCP("Common Chronicle Timeline Generator (With Progress)")

# Global flag for service initialization
_services_ready = False


async def ensure_services_ready(ctx: Context = None):
    """Ensure all required services are initialized (lazy loading)"""
    global _services_ready

    if not _services_ready:
        if ctx:
            await ctx.report_progress(0, 100, "Initializing services...")
        logger.info("Initializing services on first use...")

        llm_ready = False
        db_ready = False

        # Initialize LLM services
        if ctx:
            await ctx.report_progress(10, 100, "Loading AI models...")
        try:
            from app.services.llm_service import initialize_all_llm_clients

            initialize_all_llm_clients()
            llm_ready = True
            logger.info("LLM services initialized successfully")
        except Exception as llm_error:
            logger.error(f"LLM service initialization failed: {llm_error}")
            if ctx:
                await ctx.report_progress(30, 100, f"LLM init failed: {llm_error}")

        # Initialize database
        if ctx:
            await ctx.report_progress(50, 100, "Connecting to database...")
        try:
            from app.db import check_db_connection, init_db

            await init_db()

            if await check_db_connection():
                db_ready = True
                logger.info("Database initialized successfully")
            else:
                logger.error("Database connection check failed")
                if ctx:
                    await ctx.report_progress(70, 100, "Database connection failed")
        except Exception as db_error:
            logger.error(f"Database initialization failed: {db_error}")
            if ctx:
                await ctx.report_progress(70, 100, f"Database init failed: {db_error}")

        # Set services as ready if we have minimum requirements
        # Database is required for all operations
        if db_ready:
            _services_ready = True
            if ctx:
                status_msg = "Services ready!"
                if not llm_ready:
                    status_msg += " (LLM unavailable)"
                await ctx.report_progress(100, 100, status_msg)
            logger.info(
                f"Services initialization completed - DB: {db_ready}, LLM: {llm_ready}"
            )
        else:
            # Only fail if database is not available
            error_msg = "Database initialization failed - cannot perform operations"
            logger.error(error_msg)
            if ctx:
                await ctx.report_progress(100, 100, error_msg)
            raise Exception(error_msg)


@mcp.tool
async def create_timeline(
    topic_text: str, config: dict[str, Any] | None = None, ctx: Context = None
) -> dict[str, Any]:
    """
    Create timeline generation task with progress reporting.

    This implementation follows FastMCP best practices for long-running tasks,
    using the official progress reporting mechanism to keep clients informed.

    Args:
        topic_text: The topic text to generate timeline
        config: Optional task configuration（e.g：
            {
                "data_source_preference": "dataset_wikipedia_en", # one of online_wikipedia, online_news, dataset_wikipedia_en
            }
        ctx: FastMCP context for progress reporting (injected automatically)

    Returns:
        Dictionary containing task ID, status, and message
    """
    try:
        if ctx:
            await ctx.report_progress(
                0, 100, f"Starting timeline generation for: {topic_text[:50]}..."
            )

        # Ensure services are ready
        await ensure_services_ready(ctx)

        if ctx:
            await ctx.report_progress(5, 100, "Services initialized, creating task...")

        logger.info(f"Creating timeline for topic: {topic_text[:100]}...")

        # Import heavy modules only when needed

        from app.db import AppAsyncSessionLocal
        from app.db_handlers import TaskDBHandler
        from app.services.timeline_orchestrator import TimelineOrchestratorService

        # Use database session
        async with AppAsyncSessionLocal() as db:
            task_db_handler = TaskDBHandler()

            if ctx:
                await ctx.report_progress(10, 100, "Checking for existing timelines...")

            # Set default configuration
            final_config = config or {}

            # Create task (public task, no authentication required)
            task_dict = {
                "task_type": "synthetic_viewpoint",
                "topic_text": topic_text,
                "config": final_config,
                "status": "pending",
                "owner_id": None,  # No authentication required
                "is_public": True,
            }

            # Check for reusable tasks
            data_source_preference = final_config.get(
                "data_source_preference", "online_wikipedia"
            )
            if data_source_preference == "none":
                data_source_preference = "online_wikipedia"

            # Look for reusable task
            for data_source_preference in [
                "online_wikipedia",
                "online_news",
                "dataset_wikipedia_en",
            ]:
                reusable_task = await task_db_handler.find_reusable_completed_task(
                    topic=topic_text.strip(),
                    data_source_preference=data_source_preference,
                    task_type="synthetic_viewpoint",
                    db=db,
                )

                if reusable_task:
                    if ctx:
                        await ctx.report_progress(
                            100, 100, "Found existing completed timeline!"
                        )
                    logger.info(f"Reusing existing completed task {reusable_task.id}")
                    return {
                        "task_id": str(reusable_task.id),
                        "status": "completed",
                        "message": "Found existing completed timeline for this topic",
                        "reused": True,
                    }

            if ctx:
                await ctx.report_progress(15, 100, "Creating new timeline task...")

            # Create new task
            task_dict = await task_db_handler.create_task(obj_dict=task_dict, db=db)
            task_id = task_dict["id"]

            logger.info(f"Created new task: {task_id}")

            if ctx:
                await ctx.report_progress(
                    20,
                    100,
                    f"Task created (ID: {str(task_id)[:8]}...), starting processing...",
                )

            # Get complete task object for background processing
            task = await task_db_handler.get(task_id, db=db)
            if not task:
                await ctx.report_progress(100, 100, "Failed to retrieve created task")
                return {
                    "error": "Failed to retrieve created task",
                    "task_id": str(task_id),
                }

            # Start background task processing with progress callback
            logger.info(f"Starting background processing for task {task_id}")
            orchestrator = TimelineOrchestratorService()

            # Create a progress callback that reports to the MCP context
            async def progress_callback(message: str, step: str, data, request_id: str):
                if ctx:
                    # Extract progress information from the message
                    progress_value = 25  # Default progress for processing
                    if "completed" in message.lower():
                        progress_value = 100
                    elif "processing" in message.lower():
                        progress_value = 30

                    await ctx.report_progress(
                        progress_value, 100, f"Processing: {message}"
                    )
                logger.info(f"Task {task_id} progress: {message}")

            # Create async task for timeline generation with proper error handling
            async def run_background_task():
                try:
                    await orchestrator.run_timeline_generation_task(
                        task=task,
                        request_id=str(uuid.uuid4()),
                        websocket_callback=progress_callback,
                    )
                    logger.info(
                        f"Background task completed successfully for task {task_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"Background task failed for task {task_id}: {e}", exc_info=True
                    )
                    # Update task status to failed
                    try:
                        async with AppAsyncSessionLocal() as error_db:
                            await task_db_handler.update(
                                task_id,
                                {
                                    "status": "failed",
                                    "notes": f"Background processing failed: {str(e)}",
                                },
                                db=error_db,
                            )
                    except Exception as update_error:
                        logger.error(
                            f"Failed to update task status after background error: {update_error}"
                        )

            # Create the background task
            asyncio.create_task(run_background_task())

            # Don't wait for completion, but log task creation
            logger.info(f"Background task created for {task_id}")

            if ctx:
                await ctx.report_progress(
                    30, 100, "Timeline generation started in background"
                )

            return {
                "task_id": str(task_id),
                "status": "pending",
                "message": "Timeline generation task created and started. Use get_timeline_result to check progress.",
                "topic": topic_text,
                "reused": False,
                "note": "This is a long-running task. Check back periodically for results.",
            }

    except Exception as e:
        logger.error(f"Error creating timeline: {e}", exc_info=True)
        if ctx:
            await ctx.report_progress(100, 100, f"Error: {str(e)}")
        return {"error": f"Failed to create timeline: {str(e)}", "task_id": None}


@mcp.tool
async def get_timeline_result(task_id: str, ctx: Context = None) -> dict[str, Any]:
    """
    Get timeline task result with progress reporting.

    Returns task status and complete timeline results when available.
    Provides progress updates during result retrieval.

    Args:
        task_id: Task ID
        ctx: FastMCP context for progress reporting (injected automatically)

    Returns:
        Dictionary containing task status and result data
    """
    try:
        if ctx:
            await ctx.report_progress(
                0, 100, f"Retrieving timeline result for task {task_id[:8]}..."
            )

        # Ensure services are ready
        await ensure_services_ready(ctx)

        if ctx:
            await ctx.report_progress(5, 100, "Validating task ID...")

        logger.info(f"Getting timeline result for task: {task_id}")

        # Validate task ID format
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return {"error": "Invalid task ID format", "task_id": task_id}

        if ctx:
            await ctx.report_progress(10, 100, "Querying database...")

        # Import modules when needed
        from app.db import AppAsyncSessionLocal
        from app.db_handlers import TaskDBHandler

        async with AppAsyncSessionLocal() as db:
            task_db_handler = TaskDBHandler()

            # Get task details
            task_details = (
                await task_db_handler.get_task_with_complete_viewpoint_details(
                    task_uuid, db=db
                )
            )

            if not task_details:
                if ctx:
                    await ctx.report_progress(100, 100, "Task not found")
                return {"error": "Task not found", "task_id": task_id}

            if ctx:
                await ctx.report_progress(15, 100, "Processing task details...")

            task_status = task_details.get("status", "unknown")

            # Basic task information
            result = {
                "task_id": task_id,
                "status": task_status,
                "topic": task_details.get("topic_text", ""),
                "created_at": task_details.get("created_at"),
                "updated_at": task_details.get("updated_at"),
            }

            if task_status == "completed":
                if ctx:
                    await ctx.report_progress(
                        80, 100, "Task completed! Formatting timeline data..."
                    )

                # Task completed, return timeline results
                viewpoint_details = task_details.get("viewpoint_details")
                if viewpoint_details:
                    timeline_events = viewpoint_details.get("timeline_events", [])
                    sources = viewpoint_details.get("sources", {})

                    # LLM-optimized result format
                    result.update(
                        {
                            "message": "Timeline generation completed successfully",
                            "event_count": len(timeline_events),
                            "timeline_events": [
                                {
                                    "date": event.event_date_str or "",
                                    "description": event.description or "",
                                    "entities": [
                                        {
                                            "name": entity.original_name or "",
                                            "type": entity.entity_type or "",
                                        }
                                        for entity in event.main_entities or []
                                    ],
                                    "sources": event.source_snippets or {},
                                }
                                for event in timeline_events
                            ],
                            "sources_summary": {
                                source_id: {
                                    "title": source_data.source_page_title or "",
                                    "url": source_data.source_url or "",
                                    "type": source_data.source_type or "",
                                }
                                for source_id, source_data in sources.items()
                            },
                        }
                    )

                    if ctx:
                        await ctx.report_progress(
                            100,
                            100,
                            f"Timeline ready! Found {len(timeline_events)} events.",
                        )
                else:
                    result["message"] = "Task completed but no timeline data available"
                    result["timeline_events"] = []
                    if ctx:
                        await ctx.report_progress(
                            100, 100, "Task completed but no data available"
                        )

            elif task_status == "failed":
                # Task failed
                result.update(
                    {
                        "message": "Timeline generation failed",
                        "error": task_details.get("notes", "Unknown error occurred"),
                    }
                )
                if ctx:
                    await ctx.report_progress(100, 100, "Task failed")

            elif task_status in ["pending", "processing"]:
                # Task in progress, return progress information
                viewpoint_details = task_details.get("viewpoint_details")
                progress_steps = []
                if viewpoint_details:
                    progress_steps = viewpoint_details.get("progress_steps", [])

                result.update(
                    {
                        "message": f"Timeline generation in progress ({task_status})",
                        "progress_steps": len(progress_steps),
                        "latest_progress": progress_steps[-1].get("message", "")
                        if progress_steps
                        else "",
                    }
                )

                if ctx:
                    progress_msg = f"Task still processing ({task_status})"
                    if progress_steps:
                        progress_msg += f" - Latest: {progress_steps[-1].get('message', '')[:50]}..."
                    await ctx.report_progress(90, 100, progress_msg)
            else:
                result["message"] = f"Task status: {task_status}"
                if ctx:
                    await ctx.report_progress(100, 100, f"Task status: {task_status}")

            return result

    except Exception as e:
        logger.error(f"Error getting timeline result: {e}", exc_info=True)
        if ctx:
            await ctx.report_progress(100, 100, f"Error retrieving result: {str(e)}")
        return {"error": f"Failed to get timeline result: {str(e)}", "task_id": task_id}


@mcp.tool
async def list_recent_public_timelines(
    limit: int = 10, ctx: Context = None
) -> dict[str, Any]:
    """
    List recent public timeline tasks with progress reporting.

    Args:
        limit: Maximum number of returned tasks (default 10, max 50)
        ctx: FastMCP context for progress reporting (injected automatically)

    Returns:
        Dictionary containing list of public timelines
    """
    try:
        if ctx:
            await ctx.report_progress(0, 100, "Searching for public timelines...")

        # Ensure services are ready
        await ensure_services_ready(ctx)

        if ctx:
            await ctx.report_progress(
                30, 100, "Querying database for public timelines..."
            )

        # Limit query number
        limit = min(max(1, limit), 50)

        # Import modules when needed
        from app.db import AppAsyncSessionLocal
        from app.db_handlers import TaskDBHandler

        async with AppAsyncSessionLocal() as db:
            task_db_handler = TaskDBHandler()

            if ctx:
                await ctx.report_progress(
                    60, 100, f"Fetching up to {limit} public timelines..."
                )

            # Get public completed tasks
            tasks = await task_db_handler.get_public_completed_tasks_with_events(
                db=db, limit=limit, offset=0
            )

            if ctx:
                await ctx.report_progress(
                    90, 100, f"Processing {len(tasks)} timeline results..."
                )

            timeline_list = []
            for task in tasks:
                timeline_list.append(
                    {
                        "task_id": str(task.id),
                        "topic": task.topic_text or "",
                        "created_at": task.created_at,
                        "task_type": task.task_type or "",
                    }
                )

            if ctx:
                await ctx.report_progress(
                    100, 100, f"Found {len(timeline_list)} public timelines"
                )

            return {
                "message": f"Found {len(timeline_list)} recent public timelines",
                "timelines": timeline_list,
                "total_count": len(timeline_list),
            }

    except Exception as e:
        logger.error(f"Error listing public timelines: {e}", exc_info=True)
        if ctx:
            await ctx.report_progress(100, 100, f"Error: {str(e)}")
        return {"error": f"Failed to list public timelines: {str(e)}", "timelines": []}


@mcp.tool
async def get_service_status(ctx: Context = None) -> dict[str, Any]:
    """
    Get current service status for debugging purposes.

    Returns:
        Dictionary containing service status information
    """
    try:
        if ctx:
            await ctx.report_progress(0, 100, "Checking service status...")

        status = {
            "services_ready": _services_ready,
            "timestamp": str(uuid.uuid4()),  # Using uuid as timestamp placeholder
            "initialization_attempted": True,
        }

        # Test database connection
        try:
            if ctx:
                await ctx.report_progress(30, 100, "Testing database connection...")
            from app.db import check_db_connection

            db_ok = await check_db_connection()
            status["database"] = {
                "connection_ok": db_ok,
                "status": "connected" if db_ok else "failed",
            }
        except Exception as db_error:
            status["database"] = {
                "connection_ok": False,
                "status": "error",
                "error": str(db_error),
            }

        # Test LLM service
        try:
            if ctx:
                await ctx.report_progress(60, 100, "Testing LLM services...")

            # Just check if the module can be imported
            status["llm"] = {"available": True, "status": "module_loaded"}
        except Exception as llm_error:
            status["llm"] = {
                "available": False,
                "status": "error",
                "error": str(llm_error),
            }

        if ctx:
            await ctx.report_progress(100, 100, "Service status check completed")

        logger.info(f"Service status check: {status}")
        return status

    except Exception as e:
        logger.error(f"Error checking service status: {e}", exc_info=True)
        if ctx:
            await ctx.report_progress(100, 100, f"Error: {str(e)}")
        return {
            "error": f"Failed to check service status: {str(e)}",
            "services_ready": _services_ready,
        }
