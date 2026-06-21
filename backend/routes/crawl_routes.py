from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.routes.task_http_errors import task_launch_route_error
from backend.schemas.crawl import CrawlHistoricalRequest, CrawlSettingsRequest, CrawlTimeRangeRequest
from backend.services.crawl_workflow import (
    create_all_crawl_task,
    create_historical_crawl_task,
    create_incremental_crawl_task,
    create_time_range_crawl_task,
    launch_latest_crawl_task,
)

router = APIRouter(prefix="/api/crawl", tags=["crawl"])


def _crawl_route_error(message: str, error: Exception) -> HTTPException:
    return task_launch_route_error(message, error)


@router.post("/historical/{group_id}")
async def crawl_historical(group_id: str, request: CrawlHistoricalRequest):
    """爬取历史数据"""
    try:
        return create_historical_crawl_task(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _crawl_route_error("创建爬取任务失败", e)


@router.post("/all/{group_id}")
async def crawl_all(group_id: str, request: CrawlSettingsRequest):
    """全量爬取所有历史数据"""
    try:
        return create_all_crawl_task(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _crawl_route_error("创建全量爬取任务失败", e)


@router.post("/incremental/{group_id}")
async def crawl_incremental(group_id: str, request: CrawlHistoricalRequest):
    """增量爬取历史数据"""
    try:
        return create_incremental_crawl_task(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _crawl_route_error("创建增量爬取任务失败", e)


@router.post("/latest-until-complete/{group_id}")
async def crawl_latest_until_complete(group_id: str, request: CrawlSettingsRequest):
    """获取最新记录：智能增量更新"""
    try:
        return launch_latest_crawl_task(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _crawl_route_error("创建获取最新记录任务失败", e)


@router.post("/range/{group_id}")
async def crawl_by_time_range(group_id: str, request: CrawlTimeRangeRequest):
    """按时间区间爬取话题（支持最近N天或自定义开始/结束时间）"""
    try:
        return create_time_range_crawl_task(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _crawl_route_error("创建时间区间爬取任务失败", e)
