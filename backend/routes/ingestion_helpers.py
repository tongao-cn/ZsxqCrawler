from __future__ import annotations

from typing import Any, Callable, Dict

from fastapi import BackgroundTasks, HTTPException

from backend.services.task_runtime import create_ingestion_task


INGESTION_CONFLICT_MESSAGE = "该群组已有采集或同步任务正在运行"
TASK_CREATED_MESSAGE = "任务已创建，正在后台执行"


def ingestion_conflict_detail(existing: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "message": INGESTION_CONFLICT_MESSAGE,
        "task_id": existing.get("task_id"),
        "type": existing.get("type"),
        "status": existing.get("status"),
    }


def raise_ingestion_conflict(existing: Dict[str, Any]) -> None:
    raise HTTPException(status_code=409, detail=ingestion_conflict_detail(existing))


def create_ingestion_task_or_raise(task_type: str, description: str, group_id: str) -> str:
    task_id, existing = create_ingestion_task(task_type, description, group_id)
    if existing:
        raise_ingestion_conflict(existing)
    return task_id


def enqueue_ingestion_task(
    background_tasks: BackgroundTasks,
    task_type: str,
    description: str,
    task_func: Callable[..., Any],
    group_id: str,
    *task_args: Any,
    message: str = TASK_CREATED_MESSAGE,
) -> Dict[str, str]:
    task_id = create_ingestion_task_or_raise(task_type, description, group_id)
    background_tasks.add_task(task_func, task_id, group_id, *task_args)
    return {"task_id": task_id, "message": message}
