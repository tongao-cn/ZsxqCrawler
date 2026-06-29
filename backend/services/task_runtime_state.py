from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.services.task_runtime_logs import (
    add_task_log_subscriber,
    append_task_log,
    has_task_logs,
    remove_task_log_subscriber,
    task_log_subscribers_snapshot,
    task_logs_copy,
)
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
        sse_connections: Dict[str, List[queue.Queue[str]]],
        runtime_task_threads: Dict[str, threading.Thread],
        runtime_task_heartbeats: Dict[str, threading.Event],
    ) -> None:
        self._current_tasks = current_tasks
        self._task_logs = task_logs
        self._task_stop_flags = task_stop_flags
        self._sse_connections = sse_connections
        self._runtime_task_threads = runtime_task_threads
        self._runtime_task_heartbeats = runtime_task_heartbeats

    def initialize_task(self, task_id: str) -> None:
        self._task_logs[task_id] = []
        self.set_task_stop_flag(task_id, False)

    def forget_task(self, task_id: str) -> None:
        self._current_tasks.pop(task_id, None)
        self._task_logs.pop(task_id, None)
        self._task_stop_flags.pop(task_id, None)
        self._sse_connections.pop(task_id, None)

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

    def add_log_subscriber(self, task_id: str, subscriber: queue.Queue[str]) -> None:
        add_task_log_subscriber(self._sse_connections, task_id, subscriber)

    def remove_log_subscriber(self, task_id: str, subscriber: queue.Queue[str]) -> None:
        remove_task_log_subscriber(self._sse_connections, task_id, subscriber)

    def log_subscribers_snapshot(self, task_id: str) -> List[queue.Queue[str]]:
        return task_log_subscribers_snapshot(self._sse_connections, task_id)

    def clear_log_subscribers(self) -> None:
        self._sse_connections.clear()

    def register_task_lock_heartbeat(self, task_id: str, stop_event: threading.Event) -> None:
        self._runtime_task_heartbeats[task_id] = stop_event

    def pop_task_lock_heartbeat(self, task_id: str) -> Optional[threading.Event]:
        return self._runtime_task_heartbeats.pop(task_id, None)

    def task_lock_heartbeat_ids(self) -> List[str]:
        return list(self._runtime_task_heartbeats)

    def register_runtime_task_thread(self, task_id: str, thread: threading.Thread) -> None:
        self._runtime_task_threads[task_id] = thread

    def forget_runtime_task_thread(self, task_id: str) -> None:
        self._runtime_task_threads.pop(task_id, None)

    def clear_runtime_task_threads(self) -> None:
        self._runtime_task_threads.clear()

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


@dataclass(frozen=True)
class TaskRuntimeStateBundle:
    current_tasks: Dict[str, Dict[str, Any]]
    task_logs: Dict[str, List[str]]
    task_stop_flags: Dict[str, bool]
    sse_connections: Dict[str, List[queue.Queue[str]]]
    runtime_task_threads: Dict[str, threading.Thread]
    runtime_task_heartbeats: Dict[str, threading.Event]
    state: TaskRuntimeState


def create_task_runtime_state_bundle() -> TaskRuntimeStateBundle:
    current_tasks: Dict[str, Dict[str, Any]] = {}
    task_logs: Dict[str, List[str]] = {}
    task_stop_flags: Dict[str, bool] = {}
    sse_connections: Dict[str, List[queue.Queue[str]]] = {}
    runtime_task_threads: Dict[str, threading.Thread] = {}
    runtime_task_heartbeats: Dict[str, threading.Event] = {}
    state = TaskRuntimeState(
        current_tasks,
        task_logs,
        task_stop_flags,
        sse_connections,
        runtime_task_threads,
        runtime_task_heartbeats,
    )
    return TaskRuntimeStateBundle(
        current_tasks=current_tasks,
        task_logs=task_logs,
        task_stop_flags=task_stop_flags,
        sse_connections=sse_connections,
        runtime_task_threads=runtime_task_threads,
        runtime_task_heartbeats=runtime_task_heartbeats,
        state=state,
    )
