import uuid

from fastapi import Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_app_db
from app.db_handlers.task import TaskDBHandler
from app.dependencies.auth import get_current_user_optional
from app.models import Task, User


async def get_task_with_authorization(
    task_id: str = Path(..., description="The ID of the task to retrieve"),
    db: AsyncSession = Depends(get_app_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> Task:
    """
    Dependency to get a task and check if the current user has permission to view it.

    Permission is granted if:
    1. The task is public (`is_public` is True).
    2. The user is the owner of the task.

    Raises HTTPException 404 if the task is not found.
    Raises HTTPException 403 if the user is not authorized.
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid task_id format") from e

    task_handler = TaskDBHandler()
    task = await task_handler.get_task_with_owner(task_uuid, db=db)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check for authorization
    is_owner = current_user and task.owner_id == current_user.id
    if not task.is_public and not is_owner:
        raise HTTPException(
            status_code=403, detail="Not authorized to access this task"
        )

    return task


async def get_owned_task(
    task_id: str = Path(..., description="The ID of the task to modify"),
    db: AsyncSession = Depends(get_app_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> Task:
    """
    Dependency to get a task, ensuring the current user is the owner.

    This is a stricter check for operations that should only be performed by the owner,
    such as deleting or changing sharing status.

    Raises HTTPException 404 if the task is not found.
    Raises HTTPException 401 if the user is not authenticated.
    Raises HTTPException 403 if the user is not the owner.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid task_id format") from e

    task_handler = TaskDBHandler()
    task = await task_handler.get_owned_task_by_user(task_uuid, current_user.id, db=db)

    if not task:
        raise HTTPException(
            status_code=404, detail="Task not found or not owned by current user"
        )

    return task
