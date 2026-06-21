from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

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


@dataclass(frozen=True)
class TaskLaunchRecipe:
    task_type: str
    description: str
    task_func: Callable[..., Any]
    args: Tuple[Any, ...] = ()
    group_id: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None
    message: str = TASK_CREATED_MESSAGE
    ingestion_group_id: Optional[str] = None
    prepend_group_id_to_args: bool = True
    on_created: Optional[Callable[[str], None]] = None

    @classmethod
    def ingestion(
        cls,
        task_type: str,
        description: str,
        task_func: Callable[..., Any],
        group_id: str,
        *args: Any,
        message: str = TASK_CREATED_MESSAGE,
        prepend_group_id_to_args: bool = True,
        on_created: Optional[Callable[[str], None]] = None,
    ) -> "TaskLaunchRecipe":
        return cls(
            task_type=task_type,
            description=description,
            task_func=task_func,
            args=args,
            ingestion_group_id=group_id,
            message=message,
            prepend_group_id_to_args=prepend_group_id_to_args,
            on_created=on_created,
        )


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


def _create_runtime_task(task_type: str, description: str, metadata: Optional[Dict[str, Any]]) -> str:
    if metadata:
        return create_task(task_type, description, metadata=metadata)
    return create_task(task_type, description)


def _launch_ingestion_recipe(recipe: TaskLaunchRecipe) -> Dict[str, str]:
    group_id = recipe.ingestion_group_id
    if group_id is None:
        raise ValueError("采集/同步任务缺少群组 ID")

    task_id = create_ingestion_task_or_raise(recipe.task_type, recipe.description, group_id)
    if recipe.on_created:
        recipe.on_created(task_id)
    runtime_args = (group_id, *recipe.args) if recipe.prepend_group_id_to_args else recipe.args
    enqueue_runtime_task(recipe.task_func, task_id, *runtime_args)
    return task_created_response(task_id, recipe.message)


def _launch_runtime_recipe(recipe: TaskLaunchRecipe) -> Dict[str, str]:
    _require_workflow(recipe.task_type)
    task_metadata = (
        group_task_metadata(recipe.group_id, recipe.metadata)
        if recipe.group_id is not None
        else recipe.metadata
    )
    task_id = _create_runtime_task(recipe.task_type, recipe.description, task_metadata)
    if recipe.on_created:
        recipe.on_created(task_id)
    enqueue_runtime_task(recipe.task_func, task_id, *recipe.args)
    return task_created_response(task_id, recipe.message)


def launch_task_recipe(recipe: TaskLaunchRecipe) -> Dict[str, str]:
    if recipe.ingestion_group_id is not None:
        return _launch_ingestion_recipe(recipe)
    return _launch_runtime_recipe(recipe)
