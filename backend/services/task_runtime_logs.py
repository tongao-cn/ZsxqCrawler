from __future__ import annotations

import queue
from typing import Dict, List


def has_task_logs(task_logs: Dict[str, List[str]], task_id: str) -> bool:
    return task_id in task_logs


def task_logs_copy(task_logs: Dict[str, List[str]], task_id: str) -> List[str]:
    return list(task_logs.get(task_id, []))


def append_task_log(task_logs: Dict[str, List[str]], task_id: str, formatted_log: str) -> None:
    if task_id not in task_logs:
        task_logs[task_id] = []
    task_logs[task_id].append(formatted_log)


def add_task_log_subscriber(
    sse_connections: Dict[str, List[queue.Queue[str]]],
    task_id: str,
    subscriber: queue.Queue[str],
) -> None:
    sse_connections.setdefault(task_id, []).append(subscriber)


def remove_task_log_subscriber(
    sse_connections: Dict[str, List[queue.Queue[str]]],
    task_id: str,
    subscriber: queue.Queue[str],
) -> None:
    subscribers = sse_connections.get(task_id)
    if not subscribers:
        return
    try:
        subscribers.remove(subscriber)
    except ValueError:
        return
    if not subscribers:
        sse_connections.pop(task_id, None)


def task_log_subscribers_snapshot(
    sse_connections: Dict[str, List[queue.Queue[str]]],
    task_id: str,
) -> List[queue.Queue[str]]:
    return list(sse_connections.get(task_id, []))
