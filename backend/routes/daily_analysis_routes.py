from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.schemas.crawl import CrawlSettingsRequest
from backend.services.daily_analysis_workflow import (
    create_daily_topic_analysis_task,
    create_daily_topic_crawl_and_analysis_task,
)
from backend.services.daily_topic_analysis_service import get_daily_report
from backend.services.task_launch import TASK_CREATED_MESSAGE as _TASK_CREATED_MESSAGE
from backend.routes.task_http_errors import task_launch_route_error


router = APIRouter(prefix="/api/analysis/daily", tags=["daily-analysis"])
TASK_CREATED_MESSAGE = _TASK_CREATED_MESSAGE


class DailyAnalysisRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）")
    commentsPerTopic: int = Field(default=0, ge=0, le=50, description="每个话题最多纳入的评论数")


class DailyRunTodayRequest(DailyAnalysisRequest):
    crawlLatestFirst: bool = Field(default=True, description="分析前先抓取最新话题")
    crawlSettings: Optional[CrawlSettingsRequest] = Field(default=None, description="抓取最新话题的间隔设置")


def _create_daily_report_task_response(
    group_id: str,
    request: DailyAnalysisRequest,
) -> dict[str, str]:
    return create_daily_topic_analysis_task(
        group_id,
        date=request.date,
        comments_per_topic=request.commentsPerTopic,
    )


def _create_daily_today_task_response(
    group_id: str,
    request: DailyRunTodayRequest,
) -> dict[str, str]:
    return create_daily_topic_crawl_and_analysis_task(
        group_id,
        date=request.date,
        comments_per_topic=request.commentsPerTopic,
        crawl_latest_first=request.crawlLatestFirst,
        crawl_settings=request.crawlSettings,
    )


def _daily_analysis_route_error(message: str, error: Exception) -> HTTPException:
    return task_launch_route_error(message, error)


def _daily_report_or_404(group_id: str, date: Optional[str]) -> dict:
    report = get_daily_report(group_id, date)
    if not report:
        raise HTTPException(status_code=404, detail="日报不存在，请先生成")
    return report

@router.post("/{group_id}")
async def create_daily_report(group_id: str, request: DailyAnalysisRequest):
    try:
        return _create_daily_report_task_response(group_id, request)
    except Exception as e:
        raise _daily_analysis_route_error("创建每日分析任务失败", e)


@router.post("/run-today/{group_id}")
async def run_today_report(group_id: str, request: DailyRunTodayRequest):
    try:
        return _create_daily_today_task_response(group_id, request)
    except Exception as e:
        raise _daily_analysis_route_error("创建每日抓取分析任务失败", e)


@router.get("/{group_id}")
async def read_daily_report(
    group_id: str,
    date: Optional[str] = Query(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）"),
):
    try:
        return _daily_report_or_404(group_id, date)
    except HTTPException:
        raise
    except Exception as e:
        raise _daily_analysis_route_error("获取每日报告失败", e)
