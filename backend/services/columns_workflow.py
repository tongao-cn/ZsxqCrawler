from __future__ import annotations

from typing import Any

from backend.services.columns_fetch_task_service import run_columns_fetch_task
from backend.services.task_launch import TaskLaunchRecipe, launch_task_recipe
from backend.services.task_runtime import update_task


COLUMNS_FETCH_CREATED_MESSAGE = "专栏采集任务已启动"
COLUMNS_FETCH_RUNNING_MESSAGE = "正在采集专栏内容..."


def create_columns_fetch_task(group_id: str, request: Any) -> dict[str, Any]:
    response = launch_task_recipe(
        TaskLaunchRecipe.ingestion(
            "columns_fetch",
            f"采集专栏内容 (群组: {group_id})",
            run_columns_fetch_task,
            group_id,
            request,
            message=COLUMNS_FETCH_CREATED_MESSAGE,
            on_created=lambda task_id: update_task(task_id, "running", COLUMNS_FETCH_RUNNING_MESSAGE),
        )
    )
    return {"success": True, **response}
