from __future__ import annotations

import asyncio
import json
import queue
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Optional

from fastapi.encoders import jsonable_encoder


TaskLogSubscription = queue.Queue[str]


@dataclass(frozen=True)
class TaskObservationStreamDeps:
    subscribe_task_logs: Callable[[str], TaskLogSubscription]
    unsubscribe_task_logs: Callable[[str, TaskLogSubscription], None]
    get_task_logs_state: Callable[[str], Optional[list[str]]]
    get_task_state: Callable[[str], Optional[dict[str, Any]]]
    is_terminal_task_status: Callable[[str], bool]
    log_wait_timeout_seconds: float = 0.5


def wait_for_task_log(subscription: TaskLogSubscription, timeout: float = 0.5) -> Optional[str]:
    try:
        return subscription.get(timeout=timeout)
    except queue.Empty:
        return None


def drain_task_logs(subscription: TaskLogSubscription) -> list[str]:
    logs: list[str] = []
    while True:
        try:
            logs.append(subscription.get_nowait())
        except queue.Empty:
            return logs


async def stream_task_observation_events(
    task_id: str,
    deps: TaskObservationStreamDeps,
) -> AsyncIterator[str]:
    subscription = deps.subscribe_task_logs(task_id)

    try:
        logs = deps.get_task_logs_state(task_id) or []
        for log in logs:
            yield task_log_event(log)

        task = deps.get_task_state(task_id)
        if task:
            yield task_status_event(task)

        while True:
            log = await asyncio.to_thread(wait_for_task_log, subscription, deps.log_wait_timeout_seconds)
            if log is not None:
                yield task_log_event(log)
            for queued_log in drain_task_logs(subscription):
                yield task_log_event(queued_log)

            task = deps.get_task_state(task_id)
            if task:
                yield task_status_event(task)
                if deps.is_terminal_task_status(task["status"]):
                    break
            else:
                yield task_removed_event()
                break

            yield task_heartbeat_event()
    except asyncio.CancelledError:
        pass
    finally:
        deps.unsubscribe_task_logs(task_id, subscription)


def task_log_event(message: str) -> str:
    return _sse_event({"type": "log", "message": message})


def task_status_event(task: dict[str, Any]) -> str:
    return _sse_event({"type": "status", "status": task["status"], "message": task["message"], "task": task})


def task_removed_event() -> str:
    return _sse_event({"type": "status", "status": "cancelled", "message": "任务记录已被清理"})


def task_heartbeat_event() -> str:
    return _sse_event({"type": "heartbeat"})


def streaming_response_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
    }


def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(jsonable_encoder(payload))}\n\n"
