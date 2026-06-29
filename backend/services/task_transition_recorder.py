from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Protocol


class TaskTransitionStore(Protocol):
    def update_task(
        self,
        task_id: str,
        status: str,
        message: str,
        result: Any = None,
        updated_at: Any = None,
    ) -> Any:
        ...

    def release_task_lock(self, task_id: str, reason: str, released_at: Any = None) -> None:
        ...


TaskLogWriter = Callable[[str, str], None]
TerminalStatusChecker = Callable[[str], bool]


def record_task_transition(
    store: TaskTransitionStore,
    task_id: str,
    status: str,
    message: str,
    result: Any,
    updated_at: datetime,
    *,
    add_task_log: TaskLogWriter,
    is_terminal_status: TerminalStatusChecker,
) -> None:
    store.update_task(task_id, status, message, result=result, updated_at=updated_at)
    add_task_log(task_id, f"状态更新: {message}")

    release_task_lock_on_terminal_status(
        store,
        task_id,
        status,
        updated_at,
        add_task_log=add_task_log,
        is_terminal_status=is_terminal_status,
    )


def release_task_lock_on_terminal_status(
    store: TaskTransitionStore,
    task_id: str,
    status: str,
    released_at: datetime,
    *,
    add_task_log: TaskLogWriter,
    is_terminal_status: TerminalStatusChecker,
) -> None:
    if not is_terminal_status(status):
        return

    try:
        store.release_task_lock(task_id, status, released_at=released_at)
    except Exception as exc:
        add_task_log(task_id, f"⚠️ 释放任务锁失败: {exc}")
