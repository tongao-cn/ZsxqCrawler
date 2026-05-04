from __future__ import annotations

import asyncio
import json
import sys

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _main_module():
    return sys.modules.get("main") or sys.modules.get("__main__")


def _get_main_attr(name: str):
    module = _main_module()
    if module is None or not hasattr(module, name):
        raise RuntimeError(f"主模块未初始化，无法访问 {name}")
    return getattr(module, name)


@router.get("")
async def get_tasks():
    """获取所有任务状态"""
    current_tasks = _get_main_attr("current_tasks")
    return list(current_tasks.values())


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取特定任务状态"""
    current_tasks = _get_main_attr("current_tasks")
    if task_id not in current_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    return current_tasks[task_id]


@router.post("/{task_id}/stop")
async def stop_task_api(task_id: str):
    """停止任务"""
    stop_task = _get_main_attr("stop_task")
    if stop_task(task_id):
        return {"message": "任务停止请求已发送", "task_id": task_id}
    raise HTTPException(status_code=404, detail="任务不存在或无法停止")


@router.get("/{task_id}/logs")
async def get_task_logs(task_id: str):
    """获取任务日志"""
    task_logs = _get_main_attr("task_logs")
    if task_id not in task_logs:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "task_id": task_id,
        "logs": task_logs[task_id],
    }


@router.get("/{task_id}/stream")
async def stream_task_logs(task_id: str):
    """SSE流式传输任务日志"""
    task_logs = _get_main_attr("task_logs")
    current_tasks = _get_main_attr("current_tasks")
    sse_connections = _get_main_attr("sse_connections")

    async def event_stream():
        # 初始化连接
        if task_id not in sse_connections:
            sse_connections[task_id] = []

        # 发送历史日志
        if task_id in task_logs:
            for log in task_logs[task_id]:
                yield f"data: {json.dumps({'type': 'log', 'message': log})}\n\n"

        # 发送任务状态
        if task_id in current_tasks:
            task = current_tasks[task_id]
            yield f"data: {json.dumps({'type': 'status', 'status': task['status'], 'message': task['message']})}\n\n"

        # 记录当前日志数量，用于检测新日志
        last_log_count = len(task_logs.get(task_id, []))

        # 保持连接活跃
        try:
            while True:
                # 检查是否有新日志
                current_log_count = len(task_logs.get(task_id, []))
                if current_log_count > last_log_count:
                    # 发送新日志
                    new_logs = task_logs[task_id][last_log_count:]
                    for log in new_logs:
                        yield f"data: {json.dumps({'type': 'log', 'message': log})}\n\n"
                    last_log_count = current_log_count

                # 检查任务状态变化
                if task_id in current_tasks:
                    task = current_tasks[task_id]
                    yield f"data: {json.dumps({'type': 'status', 'status': task['status'], 'message': task['message']})}\n\n"

                    if task["status"] in ["completed", "failed", "cancelled"]:
                        break

                # 发送心跳
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            # 客户端断开连接
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )
