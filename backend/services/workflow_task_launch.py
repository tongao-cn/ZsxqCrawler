from __future__ import annotations

from typing import Any

from backend.services.a_share_analysis_workflow import (
    A_SHARE_MISSING_API_KEY_MESSAGE as A_SHARE_MISSING_API_KEY_MESSAGE,
    AShareAnalysisTaskRequest as AShareAnalysisTaskRequest,
    create_a_share_analysis_task as create_a_share_analysis_task,
    export_a_share_analysis_to_tdx as export_a_share_analysis_to_tdx,
    run_a_share_analysis_task as run_a_share_analysis_task,
)
from backend.schemas.crawl import CrawlHistoricalRequest, CrawlSettingsRequest, CrawlTimeRangeRequest
from backend.services.daily_analysis_workflow import (
    DailyStockConceptTaskRequest as DailyStockConceptTaskRequest,
    DailyTopicAnalysisTaskRequest as DailyTopicAnalysisTaskRequest,
    DailyTopicCrawlAndAnalysisTaskRequest as DailyTopicCrawlAndAnalysisTaskRequest,
    create_daily_stock_concept_task as create_daily_stock_concept_task,
    create_daily_topic_analysis_task as create_daily_topic_analysis_task,
    create_daily_topic_crawl_and_analysis_task as create_daily_topic_crawl_and_analysis_task,
    run_daily_stock_concept_task as run_daily_stock_concept_task,
    run_daily_topic_analysis_task as run_daily_topic_analysis_task,
    run_daily_topic_crawl_and_analysis_task as run_daily_topic_crawl_and_analysis_task,
)
from backend.services.columns_fetch_task_service import run_columns_fetch_task
from backend.services.crawl_service import (
    run_crawl_all_task,
    run_crawl_historical_task,
    run_crawl_incremental_task,
    run_crawl_latest_task,
    run_crawl_time_range_task,
)
from backend.services.task_launch import (
    TaskLaunchConflict,
    TaskLaunchRecipe,
    launch_task_recipe,
)
from backend.services.task_runtime import update_task


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
