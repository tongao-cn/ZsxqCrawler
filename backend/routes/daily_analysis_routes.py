from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from backend.schemas.crawl import CrawlSettingsRequest
from backend.services.crawl_service import run_crawl_latest_task
from backend.services.daily_topic_analysis_service import analyze_daily_topics, get_daily_report
from backend.services.task_launch import TASK_CREATED_MESSAGE as _TASK_CREATED_MESSAGE, launch_task
from backend.services.task_runtime import (
    add_task_log,
    build_task_log_callback,
    current_tasks,
    is_task_stopped,
    run_workflow,
    update_task,
)


router = APIRouter(prefix="/api/analysis/daily", tags=["daily-analysis"])
TASK_CREATED_MESSAGE = _TASK_CREATED_MESSAGE


class DailyAnalysisRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）")
    commentsPerTopic: int = Field(default=0, ge=0, le=50, description="每个话题最多纳入的评论数")


class DailyRunTodayRequest(DailyAnalysisRequest):
    crawlLatestFirst: bool = Field(default=True, description="分析前先抓取最新话题")
    crawlSettings: Optional[CrawlSettingsRequest] = Field(default=None, description="抓取最新话题的间隔设置")


def _build_daily_log_callback(task_id: str) -> Callable[[str], None]:
    return build_task_log_callback(
        task_id,
        lambda current_task_id, message: add_task_log(current_task_id, message),
    )


def _daily_task_stopped_or_failed(task_id: str) -> bool:
    if is_task_stopped(task_id):
        return True
    task = current_tasks.get(task_id, {})
    return task.get("status") == "failed"


def _fail_daily_task_unless_stopped(task_id: str, label: str, error: Exception) -> None:
    if is_task_stopped(task_id):
        return
    message = f"{label}失败: {str(error)}"
    add_task_log(task_id, f"❌ {message}")
    update_task(task_id, "failed", message)


def _daily_task_metadata(group_id: str, report_date: Optional[str]) -> dict[str, Any]:
    return {"group_id": group_id, "report_date": report_date}


def _create_daily_task_response(
    background_tasks: BackgroundTasks,
    task_type: str,
    description: str,
    metadata: dict[str, Any],
    task_func: Callable[..., Any],
    *task_args: Any,
) -> dict[str, str]:
    return launch_task(task_type, description, task_func, *task_args, metadata=metadata)


def _create_daily_report_task_response(
    group_id: str,
    request: DailyAnalysisRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    return _create_daily_task_response(
        background_tasks,
        "daily_topic_analysis",
        f"生成每日话题 AI 报告 (群组: {group_id})",
        _daily_task_metadata(group_id, request.date),
        run_daily_analysis_task,
        group_id,
        request,
    )


def _create_daily_today_task_response(
    group_id: str,
    request: DailyRunTodayRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    return _create_daily_task_response(
        background_tasks,
        "daily_topic_crawl_and_analysis",
        f"每日抓取与 AI 分析 (群组: {group_id})",
        _daily_task_metadata(group_id, request.date),
        run_daily_today_task,
        group_id,
        request,
    )


def _daily_analysis_route_error(message: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


def _analyze_daily_topics_for_task(task_id: str, group_id: str, request: DailyAnalysisRequest) -> dict:
    return analyze_daily_topics(
        group_id,
        request.date,
        comments_per_topic=request.commentsPerTopic,
        log_callback=_build_daily_log_callback(task_id),
    )


def _run_daily_today_crawl_first_step(task_id: str, group_id: str, request: DailyRunTodayRequest) -> bool:
    if not request.crawlLatestFirst:
        return True

    add_task_log(task_id, "🔄 先抓取最新话题...")
    run_crawl_latest_task(task_id, group_id, request.crawlSettings)
    if _daily_task_stopped_or_failed(task_id):
        return False
    update_task(task_id, "running", "最新话题抓取完成，开始 AI 分析...")
    return True


def _complete_daily_today_task_unless_stopped(task_id: str, result: dict) -> None:
    if is_task_stopped(task_id):
        return
    update_task(task_id, "completed", "每日抓取与 AI 分析完成", result)


def _daily_report_or_404(group_id: str, date: Optional[str]) -> dict:
    report = get_daily_report(group_id, date)
    if not report:
        raise HTTPException(status_code=404, detail="日报不存在，请先生成")
    return report


def run_daily_analysis_task(
    task_id: str,
    group_id: str,
    request: DailyAnalysisRequest,
):
    def work() -> dict:
        return _analyze_daily_topics_for_task(task_id, group_id, request)

    run_workflow(
        task_id,
        running_message="开始生成每日话题 AI 报告...",
        completed_message="每日话题 AI 报告生成完成",
        failure_label="每日话题 AI 报告生成",
        work=work,
    )


def run_daily_today_task(
    task_id: str,
    group_id: str,
    request: DailyRunTodayRequest,
):
    try:
        update_task(task_id, "running", "开始每日抓取与 AI 分析...")

        if not _run_daily_today_crawl_first_step(task_id, group_id, request):
            return

        result = _analyze_daily_topics_for_task(task_id, group_id, request)

        _complete_daily_today_task_unless_stopped(task_id, result)
    except Exception as e:
        _fail_daily_task_unless_stopped(task_id, "每日抓取与 AI 分析", e)


@router.post("/{group_id}")
async def create_daily_report(group_id: str, request: DailyAnalysisRequest, background_tasks: BackgroundTasks):
    try:
        return _create_daily_report_task_response(group_id, request, background_tasks)
    except Exception as e:
        raise _daily_analysis_route_error("创建每日分析任务失败", e)


@router.post("/run-today/{group_id}")
async def run_today_report(group_id: str, request: DailyRunTodayRequest, background_tasks: BackgroundTasks):
    try:
        return _create_daily_today_task_response(group_id, request, background_tasks)
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
