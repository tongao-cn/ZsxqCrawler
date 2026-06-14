from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.core.logger_config import log_exception
from backend.routes.ingestion_helpers import create_ingestion_task_or_raise
from backend.services.columns_comment_service import fetch_column_topic_full_comments
from backend.services.columns_fetch_task_service import (
    delete_all_columns_response,
    get_column_topic_detail_response,
    get_column_topics_response,
    get_columns_stats_response,
    get_group_columns_response,
    run_columns_fetch_task,
)
from backend.services.columns_summary_service import get_columns_summary
from backend.services.task_runtime import enqueue_runtime_task, update_task

router = APIRouter(prefix="/api", tags=["columns"])
_fetch_columns_task = run_columns_fetch_task


class ColumnsSettingsRequest(BaseModel):
    """专栏采集设置请求"""
    crawlIntervalMin: Optional[float] = Field(default=2.0, ge=1.0, le=60.0, description="采集间隔最小值(秒)")
    crawlIntervalMax: Optional[float] = Field(default=5.0, ge=1.0, le=60.0, description="采集间隔最大值(秒)")
    longSleepIntervalMin: Optional[float] = Field(default=30.0, ge=10.0, le=600.0, description="长休眠间隔最小值(秒)")
    longSleepIntervalMax: Optional[float] = Field(default=60.0, ge=10.0, le=600.0, description="长休眠间隔最大值(秒)")
    itemsPerBatch: Optional[int] = Field(default=10, ge=3, le=50, description="每批次处理数量")
    downloadFiles: Optional[bool] = Field(default=True, description="是否下载文件")
    downloadVideos: Optional[bool] = Field(default=True, description="是否下载视频(需要ffmpeg)")
    cacheImages: Optional[bool] = Field(default=True, description="是否缓存图片")
    incrementalMode: Optional[bool] = Field(default=False, description="增量模式：跳过已存在的文章详情")


def _create_columns_fetch_task_response(
    group_id: str,
    request: ColumnsSettingsRequest,
) -> Dict[str, Any]:
    task_id = create_ingestion_task_or_raise(
        "columns_fetch",
        f"采集专栏内容 (群组: {group_id})",
        group_id,
    )
    update_task(task_id, "running", "正在采集专栏内容...")
    enqueue_runtime_task(_fetch_columns_task, task_id, group_id, request)
    return {
        "success": True,
        "task_id": task_id,
        "message": "专栏采集任务已启动",
    }


@router.get("/groups/{group_id}/columns/summary")
async def get_group_columns_summary(group_id: str):
    """获取群组专栏摘要信息，检查是否存在专栏内容"""
    return get_columns_summary(group_id)


@router.get("/groups/{group_id}/columns")
async def get_group_columns(group_id: str):
    """获取群组的专栏目录列表（从本地数据库）"""
    try:
        return await asyncio.to_thread(get_group_columns_response, group_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取专栏目录失败: {str(exc)}") from exc


@router.get("/groups/{group_id}/columns/{column_id}/topics")
async def get_column_topics(group_id: str, column_id: int):
    """获取专栏下的文章列表（从本地数据库）"""
    try:
        return await asyncio.to_thread(get_column_topics_response, group_id, column_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取专栏文章列表失败: {str(exc)}") from exc


async def _column_topic_detail_or_404(group_id: str, topic_id: int) -> Dict[str, Any]:
    detail = await asyncio.to_thread(get_column_topic_detail_response, group_id, topic_id)
    if not detail:
        raise HTTPException(status_code=404, detail="文章详情不存在")
    return detail


@router.get("/groups/{group_id}/columns/topics/{topic_id}")
async def get_column_topic_detail(group_id: str, topic_id: int):
    """获取专栏文章详情（从本地数据库）"""
    try:
        return await _column_topic_detail_or_404(group_id, topic_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取文章详情失败: {str(exc)}") from exc


@router.post("/groups/{group_id}/columns/fetch")
async def fetch_group_columns(group_id: str, request: ColumnsSettingsRequest, background_tasks: BackgroundTasks):
    """采集群组的所有专栏内容（后台任务）"""
    try:
        return _create_columns_fetch_task_response(group_id, request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"启动专栏采集失败: {str(exc)}") from exc


@router.get("/groups/{group_id}/columns/stats")
async def get_columns_stats(group_id: str):
    """获取专栏统计信息"""
    try:
        return await asyncio.to_thread(get_columns_stats_response, group_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取专栏统计失败: {str(exc)}") from exc


@router.delete("/groups/{group_id}/columns/all")
async def delete_all_columns(group_id: str):
    """删除群组的所有专栏数据"""
    try:
        return await asyncio.to_thread(delete_all_columns_response, group_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除专栏数据失败: {str(exc)}") from exc


@router.get("/groups/{group_id}/columns/topics/{topic_id}/comments")
async def get_column_topic_full_comments(group_id: str, topic_id: int):
    """获取专栏文章的完整评论列表（从API实时获取并持久化到数据库）"""
    try:
        return await asyncio.to_thread(fetch_column_topic_full_comments, group_id, topic_id)
    except HTTPException:
        raise
    except Exception as exc:
        log_exception(f"获取专栏完整评论失败: topic_id={topic_id}")
        raise HTTPException(status_code=500, detail=f"获取完整评论失败: {str(exc)}") from exc
