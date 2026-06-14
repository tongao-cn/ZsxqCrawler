from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.routes.ingestion_helpers import enqueue_ingestion_task
from backend.schemas.crawl import CrawlHistoricalRequest, CrawlSettingsRequest, CrawlTimeRangeRequest
from backend.services.crawl_service import (
    run_crawl_all_task,
    run_crawl_historical_task,
    run_crawl_incremental_task,
    run_crawl_latest_task,
    run_crawl_time_range_task,
)

router = APIRouter(prefix="/api/crawl", tags=["crawl"])


def _create_crawl_task_response(
    background_tasks: BackgroundTasks,
    task_type: str,
    description: str,
    task_func: Callable[..., Any],
    group_id: str,
    *task_args: Any,
) -> dict[str, str]:
    return enqueue_ingestion_task(
        background_tasks,
        task_type,
        description,
        task_func,
        group_id,
        *task_args,
    )


def _create_historical_crawl_task_response(
    background_tasks: BackgroundTasks,
    group_id: str,
    request: CrawlHistoricalRequest,
) -> dict[str, str]:
    return _create_crawl_task_response(
        background_tasks,
        "crawl_historical",
        f"爬取历史数据 {request.pages} 页 (群组: {group_id})",
        run_crawl_historical_task,
        group_id,
        request.pages,
        request.per_page,
        request,
    )


def _create_all_crawl_task_response(
    background_tasks: BackgroundTasks,
    group_id: str,
    request: CrawlSettingsRequest,
) -> dict[str, str]:
    return _create_crawl_task_response(
        background_tasks,
        "crawl_all",
        f"全量爬取所有历史数据 (群组: {group_id})",
        run_crawl_all_task,
        group_id,
        request,
    )


def _create_incremental_crawl_task_response(
    background_tasks: BackgroundTasks,
    group_id: str,
    request: CrawlHistoricalRequest,
) -> dict[str, str]:
    return _create_crawl_task_response(
        background_tasks,
        "crawl_incremental",
        f"增量爬取历史数据 {request.pages} 页 (群组: {group_id})",
        run_crawl_incremental_task,
        group_id,
        request.pages,
        request.per_page,
        request,
    )


def _create_latest_crawl_task_response(
    background_tasks: BackgroundTasks,
    group_id: str,
    request: CrawlSettingsRequest,
) -> dict[str, str]:
    return _create_crawl_task_response(
        background_tasks,
        "crawl_latest_until_complete",
        f"获取最新记录 (群组: {group_id})",
        run_crawl_latest_task,
        group_id,
        request,
    )


def _create_time_range_crawl_task_response(
    background_tasks: BackgroundTasks,
    group_id: str,
    request: CrawlTimeRangeRequest,
) -> dict[str, str]:
    return _create_crawl_task_response(
        background_tasks,
        "crawl_time_range",
        f"按时间区间爬取 (群组: {group_id})",
        run_crawl_time_range_task,
        group_id,
        request,
    )


@router.post("/historical/{group_id}")
async def crawl_historical(group_id: str, request: CrawlHistoricalRequest, background_tasks: BackgroundTasks):
    """爬取历史数据"""
    try:
        return _create_historical_crawl_task_response(background_tasks, group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建爬取任务失败: {str(e)}")


@router.post("/all/{group_id}")
async def crawl_all(group_id: str, request: CrawlSettingsRequest, background_tasks: BackgroundTasks):
    """全量爬取所有历史数据"""
    try:
        return _create_all_crawl_task_response(background_tasks, group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建全量爬取任务失败: {str(e)}")


@router.post("/incremental/{group_id}")
async def crawl_incremental(group_id: str, request: CrawlHistoricalRequest, background_tasks: BackgroundTasks):
    """增量爬取历史数据"""
    try:
        return _create_incremental_crawl_task_response(background_tasks, group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建增量爬取任务失败: {str(e)}")


@router.post("/latest-until-complete/{group_id}")
async def crawl_latest_until_complete(group_id: str, request: CrawlSettingsRequest, background_tasks: BackgroundTasks):
    """获取最新记录：智能增量更新"""
    try:
        return _create_latest_crawl_task_response(background_tasks, group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建获取最新记录任务失败: {str(e)}")


@router.post("/range/{group_id}")
async def crawl_by_time_range(group_id: str, request: CrawlTimeRangeRequest, background_tasks: BackgroundTasks):
    """按时间区间爬取话题（支持最近N天或自定义开始/结束时间）"""
    try:
        return _create_time_range_crawl_task_response(background_tasks, group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建时间区间爬取任务失败: {str(e)}")
