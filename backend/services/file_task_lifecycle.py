"""Shared lifecycle primitives for file workflow tasks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, Optional

from backend.services.task_runtime import add_task_log, is_task_stopped, update_task


IsStopped = Callable[[str], bool]
AddTaskLog = Callable[[str, str], None]
UpdateTask = Callable[..., None]


def fail_file_task(
    task_id: str,
    log_message: str,
    task_message: str,
    result: Optional[Dict[str, Any]] = None,
    *,
    is_stopped: Optional[IsStopped] = None,
    add_log: Optional[AddTaskLog] = None,
    update: Optional[UpdateTask] = None,
) -> None:
    is_stopped = is_stopped or is_task_stopped
    add_log = add_log or add_task_log
    update = update or update_task
    try:
        if is_stopped(task_id):
            return
        add_log(task_id, f"❌ {log_message}")
        if result is None:
            update(task_id, "failed", task_message)
        else:
            update(task_id, "failed", task_message, result)
    except Exception:
        pass


def finish_file_task(
    task_id: str,
    status: str,
    task_message: str,
    result: Any = None,
    *,
    log_message: Optional[str] = None,
    skip_if_stopped: bool = False,
    is_stopped: Optional[IsStopped] = None,
    add_log: Optional[AddTaskLog] = None,
    update: Optional[UpdateTask] = None,
) -> bool:
    if skip_if_stopped:
        is_stopped = is_stopped or is_task_stopped
        if is_stopped(task_id):
            return False

    if log_message is not None:
        add_log = add_log or add_task_log
        add_log(task_id, log_message)

    update = update or update_task
    if result is None:
        update(task_id, status, task_message)
    else:
        update(task_id, status, task_message, result)
    return True


def file_task_stopped_after_init(
    task_id: str,
    *,
    is_stopped: Optional[IsStopped] = None,
    add_log: Optional[AddTaskLog] = None,
) -> bool:
    is_stopped = is_stopped or is_task_stopped
    add_log = add_log or add_task_log
    if is_stopped(task_id):
        add_log(task_id, "🛑 任务在初始化过程中被停止")
        return True
    return False
