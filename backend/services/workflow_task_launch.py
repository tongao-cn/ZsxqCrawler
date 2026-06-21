from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.services.a_share_analysis_workflow import (
    A_SHARE_MISSING_API_KEY_MESSAGE as A_SHARE_MISSING_API_KEY_MESSAGE,
    AShareAnalysisTaskRequest as AShareAnalysisTaskRequest,
    create_a_share_analysis_task as create_a_share_analysis_task,
    export_a_share_analysis_to_tdx as export_a_share_analysis_to_tdx,
    run_a_share_analysis_task as run_a_share_analysis_task,
)
from backend.schemas.crawl import CrawlHistoricalRequest, CrawlSettingsRequest, CrawlTimeRangeRequest
from backend.services.columns_fetch_task_service import run_columns_fetch_task
from backend.services.crawl_service import (
    run_crawl_all_task,
    run_crawl_historical_task,
    run_crawl_incremental_task,
    run_crawl_latest_task,
    run_crawl_time_range_task,
)
from backend.services.daily_stock_concept_service import extract_daily_stock_concepts
from backend.services.daily_topic_analysis_service import analyze_daily_topics
from backend.services.task_launch import (
    TaskLaunchConflict,
    TaskLaunchRecipe,
    launch_task_recipe,
)
from backend.services.task_runtime import (
    add_task_log,
    build_task_log_callback,
    get_task_state,
    is_task_stopped,
    run_workflow,
    update_task,
)


COLUMNS_FETCH_CREATED_MESSAGE = "专栏采集任务已启动"
COLUMNS_FETCH_RUNNING_MESSAGE = "正在采集专栏内容..."


def _launch_crawl_task(
    task_type: str,
    description: str,
    task_func: Any,
    group_id: str,
    *task_args: Any,
) -> dict[str, str]:
    return launch_task_recipe(
        TaskLaunchRecipe.ingestion(
            task_type,
            description,
            task_func,
            group_id,
            *task_args,
        )
    )


def create_historical_crawl_task(group_id: str, request: CrawlHistoricalRequest) -> dict[str, str]:
    return _launch_crawl_task(
        "crawl_historical",
        f"爬取历史数据 {request.pages} 页 (群组: {group_id})",
        run_crawl_historical_task,
        group_id,
        request.pages,
        request.per_page,
        request,
    )


def create_all_crawl_task(group_id: str, request: CrawlSettingsRequest) -> dict[str, str]:
    return _launch_crawl_task(
        "crawl_all",
        f"全量爬取所有历史数据 (群组: {group_id})",
        run_crawl_all_task,
        group_id,
        request,
    )


def create_incremental_crawl_task(group_id: str, request: CrawlHistoricalRequest) -> dict[str, str]:
    return _launch_crawl_task(
        "crawl_incremental",
        f"增量爬取历史数据 {request.pages} 页 (群组: {group_id})",
        run_crawl_incremental_task,
        group_id,
        request.pages,
        request.per_page,
        request,
    )


def launch_latest_crawl_task(group_id: str, request: CrawlSettingsRequest) -> dict[str, str]:
    return _launch_crawl_task(
        "crawl_latest_until_complete",
        f"获取最新记录 (群组: {group_id})",
        run_crawl_latest_task,
        group_id,
        request,
    )


def create_time_range_crawl_task(group_id: str, request: CrawlTimeRangeRequest) -> dict[str, str]:
    return _launch_crawl_task(
        "crawl_time_range",
        f"按时间区间爬取 (群组: {group_id})",
        run_crawl_time_range_task,
        group_id,
        request,
    )


def launch_or_reuse_latest_crawl_task(group_id: str, request: CrawlSettingsRequest) -> tuple[dict[str, str], str]:
    try:
        return launch_latest_crawl_task(group_id, request), "created"
    except TaskLaunchConflict as exc:
        task_id = str(exc.existing.get("task_id") or "")
        if not task_id:
            raise
        return {"task_id": task_id, "message": str(exc)}, "existing"


def create_columns_fetch_task(group_id: str, request: Any) -> dict[str, Any]:
    response = launch_task_recipe(
        TaskLaunchRecipe.ingestion(
            "columns_fetch",
            f"采集专栏内容 (群组: {group_id})",
            run_columns_fetch_task,
            group_id,
            request,
            message=COLUMNS_FETCH_CREATED_MESSAGE,
            on_created=lambda task_id: update_task(task_id, "running", COLUMNS_FETCH_RUNNING_MESSAGE),
        )
    )
    return {"success": True, **response}


def _validate_comments_per_topic(value: int) -> int:
    normalized = int(value)
    if normalized < 0 or normalized > 50:
        raise ValueError("comments_per_topic must be between 0 and 50")
    return normalized


@dataclass(frozen=True)
class DailyTopicAnalysisTaskRequest:
    date: Optional[str] = None
    comments_per_topic: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "comments_per_topic", _validate_comments_per_topic(self.comments_per_topic))


@dataclass(frozen=True)
class DailyTopicCrawlAndAnalysisTaskRequest(DailyTopicAnalysisTaskRequest):
    crawl_latest_first: bool = True
    crawl_settings: Optional[CrawlSettingsRequest] = None


@dataclass(frozen=True)
class DailyStockConceptTaskRequest:
    date: Optional[str] = None
    comments_per_topic: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "comments_per_topic", _validate_comments_per_topic(self.comments_per_topic))


def _daily_task_metadata(group_id: str, report_date: Optional[str]) -> dict[str, Any]:
    return {"group_id": group_id, "report_date": report_date}


def _launch_daily_task(
    *,
    task_type: str,
    description: str,
    task_func: Any,
    group_id: str,
    request: Any,
) -> dict[str, str]:
    return launch_task_recipe(
        TaskLaunchRecipe(
            task_type=task_type,
            description=description,
            task_func=task_func,
            args=(group_id, request),
            metadata=_daily_task_metadata(group_id, request.date),
        )
    )


def _task_log_callback(task_id: str):
    return build_task_log_callback(
        task_id,
        lambda current_task_id, message: add_task_log(current_task_id, message),
    )


def run_daily_topic_analysis_task(
    task_id: str,
    group_id: str,
    request: DailyTopicAnalysisTaskRequest,
) -> None:
    def work() -> dict:
        return analyze_daily_topics(
            group_id,
            request.date,
            comments_per_topic=request.comments_per_topic,
            log_callback=_task_log_callback(task_id),
        )

    run_workflow(
        task_id,
        running_message="开始生成每日话题 AI 报告...",
        completed_message="每日话题 AI 报告生成完成",
        failure_label="每日话题 AI 报告生成",
        work=work,
    )


def create_daily_topic_analysis_task(
    group_id: str,
    *,
    date: Optional[str] = None,
    comments_per_topic: int = 0,
) -> dict[str, str]:
    request = DailyTopicAnalysisTaskRequest(date=date, comments_per_topic=comments_per_topic)
    return _launch_daily_task(
        task_type="daily_topic_analysis",
        description=f"生成每日话题 AI 报告 (群组: {group_id})",
        task_func=run_daily_topic_analysis_task,
        group_id=group_id,
        request=request,
    )


def _daily_task_stopped_or_failed(task_id: str) -> bool:
    if is_task_stopped(task_id):
        return True
    task = get_task_state(task_id) or {}
    return task.get("status") == "failed"


def _fail_daily_task_unless_stopped(task_id: str, label: str, error: Exception) -> None:
    if is_task_stopped(task_id):
        return
    message = f"{label}失败: {str(error)}"
    add_task_log(task_id, f"❌ {message}")
    update_task(task_id, "failed", message)


def _run_daily_crawl_first_step(
    task_id: str,
    group_id: str,
    request: DailyTopicCrawlAndAnalysisTaskRequest,
) -> bool:
    if not request.crawl_latest_first:
        return True

    add_task_log(task_id, "🔄 先抓取最新话题...")
    run_crawl_latest_task(task_id, group_id, request.crawl_settings)
    if _daily_task_stopped_or_failed(task_id):
        return False
    update_task(task_id, "running", "最新话题抓取完成，开始 AI 分析...")
    return True


def _complete_daily_crawl_and_analysis_unless_stopped(task_id: str, result: dict) -> None:
    if is_task_stopped(task_id):
        return
    update_task(task_id, "completed", "每日抓取与 AI 分析完成", result)


def run_daily_topic_crawl_and_analysis_task(
    task_id: str,
    group_id: str,
    request: DailyTopicCrawlAndAnalysisTaskRequest,
) -> None:
    try:
        update_task(task_id, "running", "开始每日抓取与 AI 分析...")

        if not _run_daily_crawl_first_step(task_id, group_id, request):
            return

        result = analyze_daily_topics(
            group_id,
            request.date,
            comments_per_topic=request.comments_per_topic,
            log_callback=_task_log_callback(task_id),
        )

        _complete_daily_crawl_and_analysis_unless_stopped(task_id, result)
    except Exception as exc:
        _fail_daily_task_unless_stopped(task_id, "每日抓取与 AI 分析", exc)


def create_daily_topic_crawl_and_analysis_task(
    group_id: str,
    *,
    date: Optional[str] = None,
    comments_per_topic: int = 0,
    crawl_latest_first: bool = True,
    crawl_settings: Optional[CrawlSettingsRequest] = None,
) -> dict[str, str]:
    request = DailyTopicCrawlAndAnalysisTaskRequest(
        date=date,
        comments_per_topic=comments_per_topic,
        crawl_latest_first=crawl_latest_first,
        crawl_settings=crawl_settings,
    )
    return _launch_daily_task(
        task_type="daily_topic_crawl_and_analysis",
        description=f"每日抓取与 AI 分析 (群组: {group_id})",
        task_func=run_daily_topic_crawl_and_analysis_task,
        group_id=group_id,
        request=request,
    )


def run_daily_stock_concept_task(
    task_id: str,
    group_id: str,
    request: DailyStockConceptTaskRequest,
) -> None:
    def work() -> dict:
        return extract_daily_stock_concepts(
            group_id,
            request.date,
            comments_per_topic=request.comments_per_topic,
            log_callback=_task_log_callback(task_id),
        )

    run_workflow(
        task_id,
        running_message="开始提取每日股票概念...",
        completed_message="每日股票概念提取完成",
        failure_label="每日股票概念提取",
        work=work,
    )


def create_daily_stock_concept_task(
    group_id: str,
    *,
    date: Optional[str] = None,
    comments_per_topic: int = 0,
) -> dict[str, str]:
    request = DailyStockConceptTaskRequest(date=date, comments_per_topic=comments_per_topic)
    return _launch_daily_task(
        task_type="daily_stock_concepts",
        description=f"提取每日股票概念 (群组: {group_id})",
        task_func=run_daily_stock_concept_task,
        group_id=group_id,
        request=request,
    )
