"""Shared lifecycle primitives for file workflow tasks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from backend.services.task_runtime import add_task_log, is_task_stopped


IsStopped = Callable[[str], bool]
AddTaskLog = Callable[[str, str], None]


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
