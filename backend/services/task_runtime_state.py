from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.services.task_runtime_logs import append_task_log, has_task_logs, task_logs_copy
from backend.services.task_runtime_memory import (
    has_memory_task,
    memory_task_state,
    memory_tasks_snapshot,
    set_pending_memory_task,
    update_memory_task,
)


class TaskRuntimeState:
    def __init__(
        self,
        current_tasks: Dict[str, Dict[str, Any]],
        task_logs: Dict[str, List[str]],
        task_stop_flags: Dict[str, bool],
    ) -> None:
        self._current_tasks = current_tasks
        self._task_logs = task_logs
        self._task_stop_flags = task_stop_flags

    def initialize_task(self, task_id: str) -> None:
        self._task_logs[task_id] = []
        self.set_task_stop_flag(task_id, False)

    def forget_task(self, task_id: str) -> None:
        self._current_tasks.pop(task_id, None)
        self._task_logs.pop(task_id, None)
        self._task_stop_flags.pop(task_id, None)

    def memory_task_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        return memory_task_state(self._current_tasks, task_id)

    def set_pending_memory_task(
        self,
        task_id: str,
        task_type: str,
        description: str,
        now: datetime,
        metadata: Optional[Dict[str, Any]] = None,
        task: Optional[Dict[str, Any]] = None,
    ) -> None:
        set_pending_memory_task(
            self._current_tasks,
            task_id,
            task_type,
            description,
            now,
            metadata,
            task,
        )

    def memory_tasks_snapshot(self) -> List[tuple[str, Dict[str, Any]]]:
        return memory_tasks_snapshot(self._current_tasks)

    def has_task_logs(self, task_id: str) -> bool:
        return has_task_logs(self._task_logs, task_id)

    def task_logs_copy(self, task_id: str) -> List[str]:
        return task_logs_copy(self._task_logs, task_id)

    def append_task_log(self, task_id: str, formatted_log: str) -> None:
        append_task_log(self._task_logs, task_id, formatted_log)

    def has_memory_task(self, task_id: str) -> bool:
        return has_memory_task(self._current_tasks, task_id)

    def update_memory_task(
        self,
        task_id: str,
        status: str,
        message: str,
        result: Optional[Dict[str, Any]],
        updated_at: datetime,
    ) -> None:
        update_memory_task(self._current_tasks, task_id, status, message, result, updated_at)

    def set_task_stop_flag(self, task_id: str, stopped: bool) -> None:
        self._task_stop_flags[task_id] = stopped

    def task_stop_flag(self, task_id: str) -> bool:
        return self._task_stop_flags.get(task_id, False)
