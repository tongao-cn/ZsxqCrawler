from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from backend.routes.crawl_routes import CrawlSettingsRequest, run_crawl_latest_task
from backend.services.daily_topic_analysis_service import analyze_daily_topics, get_daily_report
from backend.services.task_runtime import (
    add_task_log,
    create_task,
    current_tasks,
    is_task_stopped,
    update_task,
)


router = APIRouter(prefix="/api/analysis/daily", tags=["daily-analysis"])


class DailyAnalysisRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）")
    commentsPerTopic: int = Field(default=8, ge=0, le=50, description="每个话题最多纳入的评论数")


class DailyRunTodayRequest(DailyAnalysisRequest):
    crawlLatestFirst: bool = Field(default=True, description="分析前先抓取最新话题")
    crawlSettings: Optional[CrawlSettingsRequest] = Field(default=None, description="抓取最新话题的间隔设置")


def run_daily_analysis_task(
    task_id: str,
    group_id: str,
    request: DailyAnalysisRequest,
):
    try:
        if is_task_stopped(task_id):
            return

        update_task(task_id, "running", "开始生成每日话题 AI 报告...")

        def log_callback(message: str):
            add_task_log(task_id, message)

        result = analyze_daily_topics(
            group_id,
            request.date,
            comments_per_topic=request.commentsPerTopic,
            log_callback=log_callback,
        )

        if is_task_stopped(task_id):
            return

        update_task(task_id, "completed", "每日话题 AI 报告生成完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 每日话题 AI 报告生成失败: {str(e)}")
            update_task(task_id, "failed", f"每日话题 AI 报告生成失败: {str(e)}")


def run_daily_today_task(
    task_id: str,
    group_id: str,
    request: DailyRunTodayRequest,
):
    try:
        update_task(task_id, "running", "开始每日抓取与 AI 分析...")

        if request.crawlLatestFirst:
            add_task_log(task_id, "🔄 先抓取最新话题...")
            run_crawl_latest_task(task_id, group_id, request.crawlSettings)
            if is_task_stopped(task_id):
                return
            task = current_tasks.get(task_id, {})
            if task.get("status") == "failed":
                return
            update_task(task_id, "running", "最新话题抓取完成，开始 AI 分析...")

        def log_callback(message: str):
            add_task_log(task_id, message)

        result = analyze_daily_topics(
            group_id,
            request.date,
            comments_per_topic=request.commentsPerTopic,
            log_callback=log_callback,
        )

        if is_task_stopped(task_id):
            return

        update_task(task_id, "completed", "每日抓取与 AI 分析完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 每日抓取与 AI 分析失败: {str(e)}")
            update_task(task_id, "failed", f"每日抓取与 AI 分析失败: {str(e)}")


@router.post("/{group_id}")
async def create_daily_report(group_id: str, request: DailyAnalysisRequest, background_tasks: BackgroundTasks):
    try:
        task_id = create_task(
            "daily_topic_analysis",
            f"生成每日话题 AI 报告 (群组: {group_id})",
            {"group_id": group_id, "report_date": request.date},
        )
        background_tasks.add_task(run_daily_analysis_task, task_id, group_id, request)
        return {"task_id": task_id, "message": "任务已创建，正在后台执行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建每日分析任务失败: {str(e)}")


@router.post("/run-today/{group_id}")
async def run_today_report(group_id: str, request: DailyRunTodayRequest, background_tasks: BackgroundTasks):
    try:
        task_id = create_task(
            "daily_topic_crawl_and_analysis",
            f"每日抓取与 AI 分析 (群组: {group_id})",
            {"group_id": group_id, "report_date": request.date},
        )
        background_tasks.add_task(run_daily_today_task, task_id, group_id, request)
        return {"task_id": task_id, "message": "任务已创建，正在后台执行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建每日抓取分析任务失败: {str(e)}")


@router.get("/{group_id}")
async def read_daily_report(
    group_id: str,
    date: Optional[str] = Query(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）"),
):
    try:
        report = get_daily_report(group_id, date)
        if not report:
            raise HTTPException(status_code=404, detail="日报不存在，请先生成")
        return report
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取每日报告失败: {str(e)}")
