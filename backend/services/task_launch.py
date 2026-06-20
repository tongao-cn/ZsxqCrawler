from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from backend.services.task_runtime import (
    create_ingestion_task,
    create_task,
    enqueue_runtime_task,
)
from backend.services.workflow_registry import INGESTION_LOCK_CATEGORY, get_workflow_spec


INGESTION_CONFLICT_MESSAGE = "该群组已有采集或同步任务正在运行"
TASK_CREATED_MESSAGE = "任务已创建，正在后台执行"


class TaskLaunchConflict(Exception):
    def __init__(self, existing: Dict[str, Any]):
        super().__init__(INGESTION_CONFLICT_MESSAGE)
        self.existing = existing


def ingestion_conflict_detail(existing: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "message": INGESTION_CONFLICT_MESSAGE,
        "task_id": existing.get("task_id"),
        "type": existing.get("type"),
        "status": existing.get("status"),
    }


def task_created_response(task_id: str, message: str = TASK_CREATED_MESSAGE) -> Dict[str, str]:
    return {"task_id": task_id, "message": message}


def group_task_metadata(group_id: Any, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"group_id": str(group_id)}
    if extra:
        metadata.update(extra)
    return metadata


def _require_workflow(task_type: str):
    spec = get_workflow_spec(task_type)
    if not spec:
        raise ValueError(f"未注册的任务类型: {task_type}")
    return spec


def _require_ingestion_workflow(task_type: str) -> None:
    spec = _require_workflow(task_type)
    if spec.lock_category != INGESTION_LOCK_CATEGORY:
        raise ValueError(f"任务类型不是采集/同步工作流: {task_type}")


def create_ingestion_task_or_raise(task_type: str, description: str, group_id: str) -> str:
    _require_ingestion_workflow(task_type)
    task_id, existing = create_ingestion_task(task_type, description, group_id)
    if existing:
        raise TaskLaunchConflict(existing)
    return task_id


def launch_ingestion_task(
    task_type: str,
    description: str,
    task_func: Callable[..., Any],
    group_id: str,
    *task_args: Any,
    message: str = TASK_CREATED_MESSAGE,
    prepend_group_id_to_args: bool = True,
    on_created: Optional[Callable[[str], None]] = None,
) -> Dict[str, str]:
    task_id = create_ingestion_task_or_raise(task_type, description, group_id)
    if on_created:
        on_created(task_id)
    runtime_args = (group_id, *task_args) if prepend_group_id_to_args else task_args
    enqueue_runtime_task(task_func, task_id, *runtime_args)
    return task_created_response(task_id, message)


def _create_runtime_task(task_type: str, description: str, metadata: Optional[Dict[str, Any]]) -> str:
    if metadata:
        return create_task(task_type, description, metadata=metadata)
    return create_task(task_type, description)


def launch_task(
    task_type: str,
    description: str,
    task_func: Callable[..., Any],
    *task_args: Any,
    metadata: Optional[Dict[str, Any]] = None,
    group_id: Optional[Any] = None,
    message: str = TASK_CREATED_MESSAGE,
    on_created: Optional[Callable[[str], None]] = None,
) -> Dict[str, str]:
    _require_workflow(task_type)
    task_metadata = group_task_metadata(group_id, metadata) if group_id is not None else metadata
    task_id = _create_runtime_task(task_type, description, task_metadata)
    if on_created:
        on_created(task_id)
    enqueue_runtime_task(task_func, task_id, *task_args)
    return task_created_response(task_id, message)
