from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException

from backend.routes.task_http_errors import internal_route_error
from backend.services.topic_local_service import (
    clear_topic_database_response as _clear_topic_database_response,
    delete_group_topics_response as _delete_group_topics_response,
    delete_single_topic_response as _delete_single_topic_response,
    get_group_tags_response as _get_group_tags_response,
    get_group_topics_response as _get_group_topics_response,
    get_topic_detail_response as _get_topic_detail_response,
    get_topics_by_tag_response as _get_topics_by_tag_response,
    get_topics_response as _get_topics_response,
)
from backend.services.topic_workflow_service import (
    TopicWorkflowError,
    fetch_more_comments as fetch_more_comments_workflow,
    fetch_single_topic as fetch_single_topic_workflow,
    refresh_topic_stats as refresh_topic_stats_workflow,
)

router = APIRouter(prefix="/api", tags=["topics"])


def _log_topic_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _topic_route_error(message: str, error: Exception) -> HTTPException:
    return internal_route_error(message, error)


async def _run_topic_workflow(workflow: Callable[..., dict], *args: Any) -> dict:
    try:
        return await asyncio.to_thread(workflow, *args)
    except TopicWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def _topics_page(page: int, per_page: int, search: Optional[str]) -> dict:
    return await asyncio.to_thread(_get_topics_response, page, per_page, search)


async def _group_topics_page(group_id: int, page: int, per_page: int, search: Optional[str]) -> dict:
    return await asyncio.to_thread(_get_group_topics_response, group_id, page, per_page, search)


async def _topic_detail(topic_id: int, group_id: str) -> dict:
    return await _run_topic_workflow(_get_topic_detail_response, topic_id, group_id)


async def _cleared_topic_database(group_id: str) -> dict:
    return await asyncio.to_thread(_clear_topic_database_response, group_id)


async def _refreshed_topic(topic_id: int, group_id: str) -> dict:
    return await _run_topic_workflow(refresh_topic_stats_workflow, topic_id, group_id)


async def _more_comments(topic_id: int, group_id: str) -> dict:
    return await _run_topic_workflow(fetch_more_comments_workflow, topic_id, group_id)


async def _deleted_single_topic(topic_id: int, group_id: int) -> dict:
    return await asyncio.to_thread(_delete_single_topic_response, topic_id, group_id)


async def _fetched_single_topic(group_id: str, topic_id: int, fetch_comments: bool) -> dict:
    return await _run_topic_workflow(fetch_single_topic_workflow, group_id, topic_id, fetch_comments)


async def _group_tags(group_id: str) -> dict:
    return await asyncio.to_thread(_get_group_tags_response, group_id)


async def _tagged_topics(group_id: int, tag_id: int, page: int, per_page: int) -> dict:
    return await _run_topic_workflow(_get_topics_by_tag_response, group_id, tag_id, page, per_page)


async def _deleted_group_topics(group_id: int) -> dict:
    return await asyncio.to_thread(_delete_group_topics_response, group_id)


@router.get("/topics")
async def get_topics(page: int = 1, per_page: int = 20, search: Optional[str] = None):
    """获取话题列表"""
    try:
        return await _topics_page(page, per_page, search)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取话题列表失败", e)


@router.get("/groups/{group_id}/topics")
async def get_group_topics(group_id: int, page: int = 1, per_page: int = 20, search: Optional[str] = None):
    """获取指定群组的话题列表"""
    try:
        return await _group_topics_page(group_id, page, per_page, search)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取群组话题失败", e)


@router.post("/topics/clear/{group_id}")
async def clear_topic_database(group_id: str):
    """删除指定群组的 PostgreSQL 话题数据"""
    try:
        return await _cleared_topic_database(group_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_topic_event("ERROR", f"删除话题数据库失败: {str(e)}")
        raise _topic_route_error("删除话题数据库失败", e)


@router.get("/topics/{topic_id}/{group_id}")
async def get_topic_detail(topic_id: int, group_id: str):
    """获取话题详情（仅从本地数据库读取，不主动爬取）"""
    try:
        return await _topic_detail(topic_id, group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取话题详情失败", e)


@router.post("/topics/{topic_id}/{group_id}/refresh")
async def refresh_topic(topic_id: int, group_id: str):
    """实时更新单个话题信息"""
    try:
        return await _refreshed_topic(topic_id, group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("更新话题失败", e)


@router.post("/topics/{topic_id}/{group_id}/fetch-comments")
async def fetch_more_comments(topic_id: int, group_id: str):
    """手动获取话题的更多评论（在已存在本地话题记录的前提下）"""
    try:
        return await _more_comments(topic_id, group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取更多评论失败", e)


@router.delete("/topics/{topic_id}/{group_id}")
async def delete_single_topic(topic_id: int, group_id: int):
    """删除单个话题及其所有关联数据"""
    try:
        return await _deleted_single_topic(topic_id, group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("删除话题失败", e)


@router.post("/topics/fetch-single/{group_id}/{topic_id}")
async def fetch_single_topic(group_id: str, topic_id: int, fetch_comments: bool = True):
    """爬取并导入单个话题（用于特殊话题测试），可选拉取完整评论"""
    try:
        return await _fetched_single_topic(group_id, topic_id, fetch_comments)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("单个话题采集失败", e)


@router.get("/groups/{group_id}/tags")
async def get_group_tags(group_id: str):
    """获取指定群组的所有标签"""
    try:
        return await _group_tags(group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取标签列表失败", e)


@router.get("/groups/{group_id}/tags/{tag_id}/topics")
async def get_topics_by_tag(group_id: int, tag_id: int, page: int = 1, per_page: int = 20):
    """根据标签获取指定群组的话题列表"""
    try:
        return await _tagged_topics(group_id, tag_id, page, per_page)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("根据标签获取话题失败", e)


@router.delete("/groups/{group_id}/topics")
async def delete_group_topics(group_id: int):
    """删除指定群组的所有话题数据"""
    try:
        return await _deleted_group_topics(group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("删除话题数据失败", e)
