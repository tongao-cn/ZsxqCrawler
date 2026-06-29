from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Callable
from typing import Any, Optional


HeartbeatTaskLock = Callable[[str, int], None]
RegisterHeartbeat = Callable[[str, threading.Event], None]
PopHeartbeat = Callable[[str], Optional[threading.Event]]
RegisterThread = Callable[[str, threading.Thread], None]
ForgetThread = Callable[[str], None]


def start_task_lock_heartbeat(
    task_id: str,
    *,
    task: Optional[dict[str, Any]],
    ingestion_lock_key: str,
    heartbeat_seconds: int,
    lease_minutes: int,
    register_heartbeat: RegisterHeartbeat,
    heartbeat_task_lock: HeartbeatTaskLock,
    event_factory: Callable[[], threading.Event] = threading.Event,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
) -> Optional[threading.Event]:
    if not task or task.get("ingestion_lock_key") != ingestion_lock_key:
        return None

    stop_event = event_factory()
    register_heartbeat(task_id, stop_event)

    def heartbeat() -> None:
        while not stop_event.wait(heartbeat_seconds):
            try:
                heartbeat_task_lock(task_id, lease_minutes)
            except Exception:
                pass

    thread = thread_factory(
        target=heartbeat,
        name=f"zsxq-lock-heartbeat-{task_id}",
        daemon=True,
    )
    thread.start()
    return stop_event


def stop_task_lock_heartbeat(task_id: str, *, pop_heartbeat: PopHeartbeat) -> None:
    stop_event = pop_heartbeat(task_id)
    if stop_event:
        stop_event.set()


def run_runtime_task(
    task_func: Callable[..., Any],
    task_id: str,
    task_args: tuple[Any, ...],
    *,
    start_heartbeat: Callable[[str], None],
    stop_heartbeat: Callable[[str], None],
    forget_thread: ForgetThread,
) -> None:
    try:
        start_heartbeat(task_id)
        result = task_func(task_id, *task_args)
        if inspect.isawaitable(result):
            asyncio.run(result)
    finally:
        stop_heartbeat(task_id)
        forget_thread(task_id)


def enqueue_runtime_task(
    task_func: Callable[..., Any],
    task_id: str,
    task_args: tuple[Any, ...],
    *,
    run_task: Callable[[Callable[..., Any], str, tuple[Any, ...]], None],
    register_thread: RegisterThread,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
) -> threading.Thread:
    thread = thread_factory(
        target=run_task,
        args=(task_func, task_id, task_args),
        name=f"zsxq-task-{task_id}",
        daemon=True,
    )
    register_thread(task_id, thread)
    thread.start()
    return thread
