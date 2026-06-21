from __future__ import annotations

from typing import Any, Callable, Dict

from fastapi import BackgroundTasks, HTTPException

from backend.services.task_launch import (
    INGESTION_CONFLICT_MESSAGE,
    TASK_CREATED_MESSAGE,
    TaskLaunchConflict,
    TaskLaunchRecipe,
    create_ingestion_task_or_raise as _create_ingestion_task_or_raise,
    ingestion_conflict_detail as _ingestion_conflict_detail,
    launch_task_recipe,
)


def ingestion_conflict_detail(existing: Dict[str, Any]) -> Dict[str, Any]:
    return _ingestion_conflict_detail(existing)


def raise_ingestion_conflict(existing: Dict[str, Any]) -> None:
    raise HTTPException(status_code=409, detail=ingestion_conflict_detail(existing))


def create_ingestion_task_or_raise(task_type: str, description: str, group_id: str) -> str:
    try:
        return _create_ingestion_task_or_raise(task_type, description, group_id)
    except TaskLaunchConflict as exc:
        raise_ingestion_conflict(exc.existing)


def enqueue_ingestion_task(
    background_tasks: BackgroundTasks,
    task_type: str,
    description: str,
    task_func: Callable[..., Any],
    group_id: str,
    *task_args: Any,
    message: str = TASK_CREATED_MESSAGE,
) -> Dict[str, str]:
    try:
        return launch_task_recipe(
            TaskLaunchRecipe.ingestion(
                task_type,
                description,
                task_func,
                group_id,
                *task_args,
                message=message,
            )
        )
    except TaskLaunchConflict as exc:
        raise_ingestion_conflict(exc.existing)
