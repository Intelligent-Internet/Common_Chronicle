from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db_handlers.base import (
    BaseDBHandler,
    ViewpointProgressStepDBHandler,
    check_local_db,
)
from app.db_handlers.viewpoint import ViewpointDBHandler
from app.models import Event, Viewpoint, ViewpointEventAssociation

# Assuming your SQLAlchemy models inherit from a declarative base located in app.models.base
# If not, you might need to adjust the bound of ModelType
from app.models.task import Task
from app.models.viewpoint_progress_step import ViewpointProgressStep
from app.utils.logger import setup_logger

logger = setup_logger("task_db_handler")


class TaskDBHandler(BaseDBHandler[Task]):
    def __init__(self):
        super().__init__(Task)

    @check_local_db
    async def create_task(
        self, obj_dict: dict[str, Any], *, db: AsyncSession = None
    ) -> dict[str, Any]:
        """Create a new task and return as dict."""
        task = await super().create(obj_dict, db=db)
        return task.to_dict()

    @check_local_db
    async def get_tasks(self, *, db: AsyncSession = None, **kwargs) -> list[Task]:
        """Get tasks by attributes."""
        return await super().get_multi_by_attributes(db=db, **kwargs)

    @check_local_db
    async def update_task_status(
        self,
        task_id: uuid.UUID,
        status: str,
        processing_duration: float | None = None,
        notes: str | None = None,
        *,
        db: AsyncSession = None,
    ) -> Task | None:
        """Update task status and related information."""
        try:
            task = await self.get(task_id, db=db)
            if not task:
                logger.warning(f"Task {task_id} not found for status update")
                return None
            updated_data = {"status": status}

            if processing_duration is not None:
                updated_data["processing_duration"] = processing_duration
            if notes:
                updated_data["notes"] = notes
            if status in ["completed", "failed"]:
                updated_data["processed_at"] = datetime.now(UTC)
            return await self.update(task, updated_data, db=db)
        except Exception as e:
            # The caller should handle the rollback.
            logger.error(f"Error preparing task {task_id} for status update: {e}")
            raise

    @check_local_db
    async def get_pending_tasks(
        self, limit: int = 10, *, db: AsyncSession = None
    ) -> list[Task]:
        try:
            stmt = (
                select(Task)
                .where(Task.status == "pending")
                .order_by(Task.created_at)
                .limit(limit)
            )
            result = await db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error retrieving pending tasks: {e}")
            raise

    @check_local_db
    async def get_task_with_complete_viewpoint_details(
        self, task_id: uuid.UUID, *, db: AsyncSession = None
    ) -> dict[str, Any] | None:
        """Get task with complete associated viewpoint details."""
        try:
            stmt = (
                select(Task).where(Task.id == task_id).options(selectinload(Task.owner))
            )
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()

            if not task:
                return None

            # Convert task to dict and manually add owner information
            task_dict = task.to_dict()

            # Add owner information if exists and is loaded
            if task.owner:
                task_dict["owner"] = task.owner.to_dict()
            else:
                task_dict["owner"] = None

            if task.viewpoint_id:
                viewpoint_handler = ViewpointDBHandler()
                viewpoint_details = (
                    await viewpoint_handler.get_complete_viewpoint_details_by_id(
                        task.viewpoint_id, db=db
                    )
                )
                task_dict["viewpoint_details"] = viewpoint_details
            else:
                task_dict["viewpoint_details"] = None

            return task_dict
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving task with complete viewpoint for task {task_id}: {e}",
                exc_info=True,
            )
            raise

    @check_local_db
    async def create_viewpoint_progress_step(
        self,
        task_id: uuid.UUID,
        step_name: str,
        message: str,
        event_timestamp: str,
        request_id: str = "",
        *,
        db: AsyncSession = None,
    ) -> ViewpointProgressStep | None:
        """Create a progress step for viewpoint associated with task."""
        try:
            # First, get the task to find its associated viewpoint
            task = await self.get(task_id, db=db)
            if not task or not task.viewpoint_id:
                logger.warning(
                    f"Cannot create progress step: Task {task_id} not found or has no associated viewpoint"
                )
                return None

            try:
                timestamp_dt = datetime.fromisoformat(
                    event_timestamp.replace("Z", "+00:00")
                )
            except ValueError:
                timestamp_dt = datetime.now(UTC)

            # Create the progress step
            progress_step_handler = ViewpointProgressStepDBHandler()
            progress_step_data = {
                "viewpoint_id": task.viewpoint_id,
                "step_name": step_name,
                "message": message,
                "event_timestamp": timestamp_dt,
            }

            try:
                return await progress_step_handler.create(progress_step_data, db=db)
            except SQLAlchemyError as db_error:
                # Handle unique constraint violation for duplicate progress steps
                if (
                    "uq_viewpoint_step_message" in str(db_error)
                    or "duplicate key" in str(db_error).lower()
                ):
                    logger.debug(
                        f"Progress step already exists for task {task_id}, step '{step_name}': {message}"
                    )
                    # Find and return the existing progress step
                    existing_step = await progress_step_handler.get_by_attributes(
                        viewpoint_id=task.viewpoint_id,
                        step_name=step_name,
                        message=message,
                        db=db,
                    )
                    return existing_step
                else:
                    # Re-raise other database errors
                    raise

        except Exception as e:
            logger.error(
                f"Error creating viewpoint progress step for task {task_id}: {e}",
                exc_info=True,
            )
            raise

    @check_local_db
    async def get_viewpoint_progress_steps_by_task_id(
        self,
        task_id: uuid.UUID,
        *,
        db: AsyncSession = None,
    ) -> list[dict[str, Any]]:
        """Get progress steps for task via its associated viewpoint."""
        try:
            # Get the task to find its associated viewpoint
            task = await self.get(task_id, db=db)
            if not task or not task.viewpoint_id:
                logger.warning(
                    f"Cannot get progress steps: Task {task_id} not found or has no associated viewpoint"
                )
                return []

            # Use the viewpoint handler to get complete details
            viewpoint_handler = ViewpointDBHandler()
            viewpoint_details = (
                await viewpoint_handler.get_complete_viewpoint_details_by_id(
                    task.viewpoint_id, db=db
                )
            )

            if not viewpoint_details:
                return []

            # Return the progress steps from viewpoint details
            return viewpoint_details.get("progress_steps", [])

        except Exception as e:
            logger.error(
                f"Error getting viewpoint progress steps for task {task_id}: {e}",
                exc_info=True,
            )
            return []

    async def get_public_completed_tasks_with_events(
        self, db: AsyncSession, limit: int = 50, offset: int = 0
    ) -> list[Task]:
        """Fetch public completed tasks with at least one event."""
        stmt = (
            select(Task)
            .join(Task.viewpoint)
            .join(Viewpoint.event_associations)
            .join(ViewpointEventAssociation.event)
            .where(Task.is_public.is_(True), Task.status == "completed")
            .group_by(Task.id)
            .having(func.count(Event.id) > 0)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(Task.owner))  # Avoid N+1 for owner info
        )
        result = await db.execute(stmt)
        tasks = result.scalars().unique().all()
        return tasks

    @check_local_db
    async def get_task_with_owner(
        self, task_id: uuid.UUID, *, db: AsyncSession = None
    ) -> Task | None:
        """Get task by ID with owner information loaded."""
        try:
            stmt = (
                select(Task).options(selectinload(Task.owner)).where(Task.id == task_id)
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving task with owner for task {task_id}: {e}")
            raise

    @check_local_db
    async def get_owned_task_by_user(
        self, task_id: uuid.UUID, user_id: uuid.UUID, *, db: AsyncSession = None
    ) -> Task | None:
        """Get task by ID that belongs to specific user."""
        try:
            stmt = (
                select(Task)
                .options(selectinload(Task.owner))
                .where(Task.id == task_id, Task.owner_id == user_id)
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving owned task {task_id} for user {user_id}: {e}"
            )
            raise
