from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.schemas.crawl import CrawlSettingsRequest
from backend.services.crawl_service import run_crawl_latest_task
from backend.services.daily_stock_concept_service import extract_daily_stock_concepts
from backend.services.daily_topic_analysis_service import analyze_daily_topics
from backend.services.task_launch import TaskLaunchRecipe, launch_task_recipe
from backend.services.task_runtime import (
    add_task_log,
    build_task_log_callback,
    get_task_state,
    is_task_stopped,
    run_workflow,
    skip_workflow_completion,
    update_task,
)


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
    return build_task_log_callback(task_id)


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


def run_daily_topic_crawl_and_analysis_task(
    task_id: str,
    group_id: str,
    request: DailyTopicCrawlAndAnalysisTaskRequest,
) -> None:
    def work() -> Any:
        if not _run_daily_crawl_first_step(task_id, group_id, request):
            return skip_workflow_completion()

        return analyze_daily_topics(
            group_id,
            request.date,
            comments_per_topic=request.comments_per_topic,
            log_callback=_task_log_callback(task_id),
        )

    run_workflow(
        task_id,
        running_message="开始每日抓取与 AI 分析...",
        completed_message="每日抓取与 AI 分析完成",
        failure_label="每日抓取与 AI 分析",
        work=work,
    )


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
