"""
User Management API Routes - Personal workspace and task ownership management.

Provides API endpoints for authenticated users to manage their personal workspace
and task ownership with proper authorization checks.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_app_db
from app.db_handlers import TaskDBHandler
from app.dependencies.auth import get_current_user
from app.models import Task, User
from app.schemas import TaskResponse, TaskResultDetailResponse

router = APIRouter(prefix="/api/users", tags=["User Management"])


@router.get("/me/tasks", response_model=list[TaskResponse])
async def get_my_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
    status_filter: str | None = Query(None, description="Filter tasks by status"),
    limit: int = Query(50, le=100, description="Maximum number of tasks to return"),
    offset: int = Query(0, ge=0, description="Number of tasks to skip"),
    task_db_handler: TaskDBHandler = Depends(),
):
    """
    Retrieve all tasks owned by the current authenticated user.

    Returns tasks created by the current user with filtering and pagination.
    Access is restricted to task owners only.
    """
    query_params = {
        "owner_id": current_user.id,
        "limit": limit,
        "offset": offset,
        "options": [selectinload(Task.owner)],
        "order_by": [Task.created_at.desc()],
    }

    if status_filter:
        valid_statuses = ["pending", "processing", "completed", "failed"]
        if status_filter not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter. Must be one of: {valid_statuses}",
            )
        query_params["status"] = status_filter

    tasks = await task_db_handler.get_tasks(db=db, **query_params)
    return [TaskResponse.model_validate(task) for task in tasks]


@router.get("/me/tasks/{task_id}", response_model=TaskResultDetailResponse)
async def get_my_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
    task_db_handler: TaskDBHandler = Depends(),
):
    """
    Retrieve complete details and results for a specific task owned by the current user.

    Returns comprehensive task information including all generated events and entities.
    Access is restricted to task owners only with automatic ownership verification.
    """
    task_details = await task_db_handler.get_task_with_complete_viewpoint_details(
        task_id, db=db
    )

    if not task_details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )

    # Authorization check: Ensure the task belongs to the current user
    owner_info = task_details.get("owner")
    if not owner_info or owner_info.get("id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return TaskResultDetailResponse.model_validate(task_details)
