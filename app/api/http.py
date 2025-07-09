"""
HTTP API Routes - Main REST API endpoints for timeline generation tasks.

Handles timeline generation task management including creation, retrieval, status
monitoring, and sharing configuration.
"""


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_app_db
from app.db_handlers import TaskDBHandler
from app.dependencies.auth import get_current_user_optional
from app.dependencies.tasks import get_owned_task, get_task_with_authorization
from app.models import Task, User
from app.schemas import (
    CreateTaskRequest,
    TaskResponse,
    TaskResultDetailResponse,
    UpdateTaskSharingRequest,
)
from app.utils.logger import setup_logger

logger = setup_logger("api")

router = APIRouter(prefix="/api")


@router.get("/")
async def read_root():
    """API health check endpoint."""
    return {"message": "Timeline Project API is running!"}


@router.post("/tasks/", response_model=TaskResponse)
async def create_task(
    task_data: CreateTaskRequest,
    current_user: User | None = Depends(get_current_user_optional),
    task_db_handler: TaskDBHandler = Depends(),
):
    """
    Create a new timeline generation task.

    Anonymous users can only create public tasks. Authenticated users can create
    private tasks with configurable sharing settings.
    """
    try:
        # Anonymous users create public tasks, authenticated users default to private
        final_is_public: bool = True
        if current_user:
            final_is_public = (
                task_data.is_public if task_data.is_public is not None else False
            )
            log_piece = (
                f"registered user: {current_user.username} (ID: {current_user.id})"
            )
        else:
            log_piece = "anonymous/public user"

        task_dict = {
            "topic_text": task_data.topic_text,
            "config": task_data.config,
            "status": "pending",
            "owner_id": current_user.id if current_user else None,
            "is_public": final_is_public,
        }
        task_dict = await task_db_handler.create_task(obj_dict=task_dict)
        logger.info(f"Created new task: {task_dict.get('id')} for {log_piece}")
        return TaskResponse.model_validate(task_dict)

    except Exception as e:
        logger.error(f"Error creating task: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to create task: {str(e)}"
        ) from e


@router.get("/tasks/", response_model=list[TaskResponse])
async def get_tasks(
    status: str | None = None,
    owned_by_me: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_app_db),
    current_user: User | None = Depends(get_current_user_optional),
    task_db_handler: TaskDBHandler = Depends(),
):
    """
    Get timeline generation tasks with filtering and pagination.

    Anonymous users can only see public completed tasks. Authenticated users can
    see their own tasks plus public completed tasks.
    """
    logger.info(f"Fetching tasks with status='{status}', owned_by_me='{owned_by_me}'")
    try:
        query_dict = {
            "order_by": Task.created_at.desc(),
            "limit": limit,
            "offset": offset,
            "options": [selectinload(Task.owner)],  # Preload owner relationship
        }
        if status:
            query_dict["status"] = status
        # Get user's own tasks
        if owned_by_me is True:
            if not current_user:
                return []  # Or raise HTTPException(401, "Authentication required")
            query_dict["owner_id"] = current_user.id
        # Get public tasks (only completed public tasks can be accessed)
        elif owned_by_me is False:
            query_dict["is_public"] = True
            query_dict["status"] = "completed"

        tasks = await task_db_handler.get_tasks(db=db, **query_dict)
        logger.info(f"Found {len(tasks)} tasks matching criteria.")

        # Convert tasks to dictionaries to ensure proper type conversion
        task_dicts = []
        for task in tasks:
            task_dict = task.to_dict()
            # Add owner information if exists and is loaded
            if task.owner:
                task_dict["owner"] = task.owner.to_dict()
            else:
                task_dict["owner"] = None
            task_dicts.append(task_dict)

        return [TaskResponse.model_validate(task_dict) for task_dict in task_dicts]
    except Exception as e:
        logger.error(f"Failed to fetch tasks. Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch tasks") from e


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task: Task = Depends(get_task_with_authorization),
    db: AsyncSession = Depends(get_app_db),
    task_db_handler: TaskDBHandler = Depends(),
):
    """
    Retrieve detailed information about a specific task.

    Access is controlled based on task ownership and public/private status.
    """
    task_details = await task_db_handler.get_task_with_complete_viewpoint_details(
        task.id, db=db
    )
    if not task_details:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskResponse.model_validate(task_details)


@router.get("/tasks/{task_id}/result", response_model=TaskResultDetailResponse)
async def get_task_result(
    task: Task = Depends(get_task_with_authorization),
    db: AsyncSession = Depends(get_app_db),
    task_db_handler: TaskDBHandler = Depends(),
):
    """
    Retrieve the complete timeline results including all generated events and entities.

    Access is controlled based on task ownership and public/private status.
    """
    try:
        task_details = await task_db_handler.get_task_with_complete_viewpoint_details(
            task.id, db=db
        )
        if not task_details:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskResultDetailResponse.model_validate(task_details)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail="Invalid task_id format") from ve
    except Exception as e:
        logger.error(f"Error retrieving task result {task.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve task result: {str(e)}"
        ) from e


@router.patch("/tasks/{task_id}/sharing", response_model=TaskResultDetailResponse)
async def update_task_sharing(
    sharing_data: UpdateTaskSharingRequest,
    task: Task = Depends(get_owned_task),
    db: AsyncSession = Depends(get_app_db),
    task_db_handler: TaskDBHandler = Depends(),
):
    """
    Update task sharing settings (public/private).

    Only task owners can modify sharing settings. Returns updated task with complete results.
    """
    try:
        task.is_public = sharing_data.is_public
        await db.commit()
        await db.refresh(task)
        logger.info(
            f"Updated task {task.id} sharing status to is_public={task.is_public}"
        )

        # Return updated task with complete details
        task_details = await task_db_handler.get_task_with_complete_viewpoint_details(
            task.id, db=db
        )
        if not task_details:
            raise HTTPException(status_code=404, detail="Task not found after update")
        return TaskResultDetailResponse.model_validate(task_details)
    except Exception as e:
        await db.rollback()
        logger.error(
            f"Error updating task sharing status {task.id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to update task sharing status: {str(e)}"
        ) from e


@router.get("/public/timelines", response_model=list[TaskResponse])
async def get_public_timelines(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_app_db),
    task_db_handler: TaskDBHandler = Depends(),
):
    """
    Retrieve public completed timelines for gallery and archive display.

    Only returns public completed tasks that contain at least one event.
    """
    try:
        # Validate parameters
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=400, detail="Limit must be between 1 and 100"
            )
        if offset < 0:
            raise HTTPException(status_code=400, detail="Offset must be non-negative")

        tasks = await task_db_handler.get_public_completed_tasks_with_events(
            db=db, limit=limit, offset=offset
        )
        logger.info(f"Found {len(tasks)} public timelines with events.")
        return [TaskResponse.model_validate(task) for task in tasks]
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Failed to fetch public timelines. Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to fetch public timelines"
        ) from e
