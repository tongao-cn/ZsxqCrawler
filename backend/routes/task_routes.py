from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services.task_observation_stream import (
    TaskObservationStreamDeps,
    drain_task_logs as _drain_task_logs,
    stream_task_observation_events,
    streaming_response_headers,
    wait_for_task_log as _wait_for_task_log,
)
from backend.services.task_runtime import (
    cleanup_tasks as cleanup_task_history,
    get_task_logs_state,
    get_task_state,
    is_terminal_task_status,
    list_tasks,
    subscribe_task_logs,
    unsubscribe_task_logs,
    stop_task,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCleanupRequest(BaseModel):
    keep_latest: int = Field(default=100, description="保留最近多少条终态任务")


def _task_observation_stream_deps() -> TaskObservationStreamDeps:
    return TaskObservationStreamDeps(
        subscribe_task_logs=subscribe_task_logs,
        unsubscribe_task_logs=unsubscribe_task_logs,
        get_task_logs_state=get_task_logs_state,
        get_task_state=get_task_state,
        is_terminal_task_status=is_terminal_task_status,
    )


@router.get("")
async def get_tasks(
    limit: Optional[int] = Query(default=None, ge=1, le=1000),
    group_id: Optional[str] = Query(default=None),
    task_type: Optional[str] = Query(default=None, alias="type"),
):
    """获取所有任务状态"""
    normalized_group_id = str(group_id).strip() if group_id else ""
    if normalized_group_id:
        return list_tasks(limit=limit, group_id=normalized_group_id, task_type=task_type)
    return list_tasks(limit=limit, task_type=task_type)


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
    return StreamingResponse(
        stream_task_observation_events(task_id, _task_observation_stream_deps()),
        media_type="text/event-stream",
        headers=streaming_response_headers(),
    )
