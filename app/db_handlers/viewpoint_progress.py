from __future__ import annotations

from app.db_handlers.base import BaseDBHandler
from app.models.viewpoint_progress_step import ViewpointProgressStep
from app.utils.logger import setup_logger

logger = setup_logger("db_handlers.viewpoint_progress")


class ViewpointProgressStepDBHandler(BaseDBHandler[ViewpointProgressStep]):
    def __init__(self):
        super().__init__(ViewpointProgressStep)
