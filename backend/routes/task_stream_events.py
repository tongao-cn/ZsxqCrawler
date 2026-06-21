from __future__ import annotations

import json
from typing import Any

from fastapi.encoders import jsonable_encoder


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
