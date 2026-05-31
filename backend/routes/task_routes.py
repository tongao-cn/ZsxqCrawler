from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services.task_runtime import (
    cleanup_tasks as cleanup_task_history,
    get_task_logs_state,
    get_task_state,
    list_tasks,
    sse_connections,
    stop_task,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCleanupRequest(BaseModel):
    keep_latest: int = Field(default=100, description="保留最近多少条终态任务")


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _task_status_payload(task: dict) -> dict:
    return {"type": "status", "status": task["status"], "message": task["message"]}


def _streaming_response_headers() -> dict:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
    }


@router.get("")
async def get_tasks(
    limit: Optional[int] = Query(default=None, ge=1, le=1000),
    group_id: Optional[str] = Query(default=None),
    task_type: Optional[str] = Query(default=None, alias="type"),
):
    """获取所有任务状态"""
    tasks = list_tasks()
    if group_id:
        normalized_group_id = str(group_id).strip()
        tasks = [task for task in tasks if str(task.get("group_id") or "").strip() == normalized_group_id]
    if task_type:
        tasks = [task for task in tasks if task.get("type") == task_type]
    return tasks[:limit] if limit else tasks


@router.post("/cleanup")
async def cleanup_tasks(request: TaskCleanupRequest):
    """清理较旧的已结束任务和日志，不影响运行中任务。"""
    return cleanup_task_history(keep_latest=request.keep_latest)


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取特定任务状态"""
    task = get_task_state(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return task


@router.post("/{task_id}/stop")
async def stop_task_api(task_id: str):
    """停止任务"""
    if stop_task(task_id):
        return {"message": "任务停止请求已发送", "task_id": task_id}
    raise HTTPException(status_code=404, detail="任务不存在或无法停止")


@router.get("/{task_id}/logs")
async def get_task_logs(task_id: str):
    """获取任务日志"""
    logs = get_task_logs_state(task_id)
    if logs is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "task_id": task_id,
        "logs": logs,
    }


@router.get("/{task_id}/stream")
async def stream_task_logs(task_id: str):
    """SSE流式传输任务日志"""
    async def event_stream():
        # 初始化连接
        if task_id not in sse_connections:
            sse_connections[task_id] = []

        # 发送历史日志
        logs = get_task_logs_state(task_id) or []
        for log in logs:
            yield _sse_event({"type": "log", "message": log})

        # 发送任务状态
        task = get_task_state(task_id)
        if task:
            yield _sse_event(_task_status_payload(task))

        # 记录当前日志数量，用于检测新日志
        last_log_count = len(logs)

        # 保持连接活跃
        try:
            while True:
                # 检查是否有新日志
                logs = get_task_logs_state(task_id) or []
                current_log_count = len(logs)
                if current_log_count > last_log_count:
                    # 发送新日志
                    new_logs = logs[last_log_count:]
                    for log in new_logs:
                        yield _sse_event({"type": "log", "message": log})
                    last_log_count = current_log_count

                # 检查任务状态变化
                task = get_task_state(task_id)
                if task:
                    yield _sse_event(_task_status_payload(task))

                    if task["status"] in ["completed", "failed", "cancelled"]:
                        break
                else:
                    yield _sse_event({"type": "status", "status": "cancelled", "message": "任务记录已被清理"})
                    break

                # 发送心跳
                yield _sse_event({"type": "heartbeat"})
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            # 客户端断开连接
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_streaming_response_headers(),
    )
