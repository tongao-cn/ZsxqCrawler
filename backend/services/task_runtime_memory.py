from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


def build_pending_task_state(
    task_id: str,
    task_type: str,
    description: str,
    now: datetime,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    task = {
        "task_id": task_id,
        "type": task_type,
        "status": "pending",
        "message": description,
        "result": None,
        "created_at": now,
        "updated_at": now,
    }
    if metadata:
        task.update(metadata)
    return task


def memory_task_state(current_tasks: Dict[str, Dict[str, Any]], task_id: str) -> Optional[Dict[str, Any]]:
    return current_tasks.get(task_id)


def set_memory_task(current_tasks: Dict[str, Dict[str, Any]], task_id: str, task: Dict[str, Any]) -> None:
    current_tasks[task_id] = task


def set_pending_memory_task(
    current_tasks: Dict[str, Dict[str, Any]],
    task_id: str,
    task_type: str,
    description: str,
    now: datetime,
    metadata: Optional[Dict[str, Any]] = None,
    task: Optional[Dict[str, Any]] = None,
) -> None:
    set_memory_task(
        current_tasks,
        task_id,
        task or build_pending_task_state(
            task_id,
            task_type,
            description,
            now,
            metadata,
        ),
    )


def memory_tasks_snapshot(current_tasks: Dict[str, Dict[str, Any]]) -> List[tuple[str, Dict[str, Any]]]:
    return list(current_tasks.items())


def has_memory_task(current_tasks: Dict[str, Dict[str, Any]], task_id: str) -> bool:
    return task_id in current_tasks


def update_memory_task(
    current_tasks: Dict[str, Dict[str, Any]],
    task_id: str,
    status: str,
    message: str,
    result: Optional[Dict[str, Any]],
    updated_at: datetime,
) -> None:
    if task_id in current_tasks:
        current_tasks[task_id].update(
            {
                "status": status,
                "message": message,
                "result": result,
                "updated_at": updated_at,
            }
        )


def should_apply_task_update(
    existing_task: Optional[Dict[str, Any]],
    has_memory_task: bool,
    status: str,
) -> bool:
    if not has_memory_task and existing_task is None:
        return False
    if existing_task and existing_task.get("status") == "cancelled" and status != "cancelled":
        return False
    return True
