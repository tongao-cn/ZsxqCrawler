from __future__ import annotations

import threading
from typing import Dict, List, Optional


def register_task_lock_heartbeat(
    runtime_task_heartbeats: Dict[str, threading.Event],
    task_id: str,
    stop_event: threading.Event,
) -> None:
    runtime_task_heartbeats[task_id] = stop_event


def pop_task_lock_heartbeat(
    runtime_task_heartbeats: Dict[str, threading.Event],
    task_id: str,
) -> Optional[threading.Event]:
    return runtime_task_heartbeats.pop(task_id, None)


def task_lock_heartbeat_ids(runtime_task_heartbeats: Dict[str, threading.Event]) -> List[str]:
    return list(runtime_task_heartbeats)


def register_runtime_task_thread(
    runtime_task_threads: Dict[str, threading.Thread],
    task_id: str,
    thread: threading.Thread,
) -> None:
    runtime_task_threads[task_id] = thread


def forget_runtime_task_thread(runtime_task_threads: Dict[str, threading.Thread], task_id: str) -> None:
    runtime_task_threads.pop(task_id, None)


def clear_runtime_task_threads(runtime_task_threads: Dict[str, threading.Thread]) -> None:
    runtime_task_threads.clear()
