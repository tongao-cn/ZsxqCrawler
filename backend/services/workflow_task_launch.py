from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from backend.core.ai_provider_config import has_openai_api_key
from backend.schemas.crawl import CrawlHistoricalRequest, CrawlSettingsRequest, CrawlTimeRangeRequest
from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_CONCURRENCY as A_SHARE_DEFAULT_CONCURRENCY,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT as A_SHARE_DEFAULT_REASONING_EFFORT,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
    normalize_group_id,
    run_analysis,
)
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
    launch_ingestion_task,
    launch_task,
)
from backend.services.task_runtime import (
    add_task_log,
    build_task_log_callback,
    get_task_state,
    is_task_stopped,
    run_workflow,
    update_task,
)
from backend.services.tdx_a_share_export_service import export_a_share_rankings_to_tdx


A_SHARE_MISSING_API_KEY_MESSAGE = "未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key"
COLUMNS_FETCH_CREATED_MESSAGE = "专栏采集任务已启动"
COLUMNS_FETCH_RUNNING_MESSAGE = "正在采集专栏内容..."


def _launch_crawl_task(
    task_type: str,
    description: str,
    task_func: Any,
    group_id: str,
    *task_args: Any,
) -> dict[str, str]:
    return launch_ingestion_task(
        task_type,
        description,
        task_func,
        group_id,
        *task_args,
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
    response = launch_ingestion_task(
        "columns_fetch",
        f"采集专栏内容 (群组: {group_id})",
        run_columns_fetch_task,
        group_id,
        request,
        message=COLUMNS_FETCH_CREATED_MESSAGE,
        on_created=lambda task_id: update_task(task_id, "running", COLUMNS_FETCH_RUNNING_MESSAGE),
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
    return launch_task(
        "daily_topic_analysis",
        f"生成每日话题 AI 报告 (群组: {group_id})",
        run_daily_topic_analysis_task,
        group_id,
        request,
        metadata=_daily_task_metadata(group_id, request.date),
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
    return launch_task(
        "daily_topic_crawl_and_analysis",
        f"每日抓取与 AI 分析 (群组: {group_id})",
        run_daily_topic_crawl_and_analysis_task,
        group_id,
        request,
        metadata=_daily_task_metadata(group_id, request.date),
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
    return launch_task(
        "daily_stock_concepts",
        f"提取每日股票概念 (群组: {group_id})",
        run_daily_stock_concept_task,
        group_id,
        request,
        metadata=_daily_task_metadata(group_id, request.date),
    )


@dataclass(frozen=True)
class AShareAnalysisTaskRequest:
    group_id: Optional[str | int] = None
    days: int = 21
    concurrency: int = A_SHARE_DEFAULT_CONCURRENCY
    model: str = A_SHARE_DEFAULT_MODEL
    api_base: str = A_SHARE_DEFAULT_API_BASE
    wire_api: str = A_SHARE_DEFAULT_WIRE_API
    reasoning_effort: str = A_SHARE_DEFAULT_REASONING_EFFORT
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    reset_start_date: Optional[str] = None
    reset_end_date: Optional[str] = None

    def __post_init__(self) -> None:
        if self.days < 1 or self.days > 365:
            raise ValueError("days must be between 1 and 365")
        if self.concurrency < 1 or self.concurrency > 128:
            raise ValueError("concurrency must be between 1 and 128")


def _normalize_group_scope(group_id: Optional[str | int]) -> tuple[Optional[str], str]:
    normalized_group_id = normalize_group_id(group_id)
    scope_text = f"群组 {normalized_group_id}" if normalized_group_id else "全局聚合"
    return normalized_group_id, scope_text


def _normalized_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD 格式") from exc


def _run_range_text(request: AShareAnalysisTaskRequest) -> str:
    if request.start_date or request.end_date:
        if not request.start_date or not request.end_date:
            raise ValueError("start_date 和 end_date 需要同时提供")
        start_day = _normalized_date(request.start_date, "start_date")
        end_day = _normalized_date(request.end_date, "end_date")
        if start_day > end_day:
            raise ValueError("start_date 不能晚于 end_date")
        return f"{start_day} ~ {end_day}"
    return f"最近 {request.days} 天"


def _a_share_task_metadata(normalized_group_id: Optional[str]) -> dict[str, Optional[str]]:
    return {"group_id": normalized_group_id}


def _a_share_analysis_task_context(
    request: AShareAnalysisTaskRequest,
) -> tuple[Optional[str], str, str]:
    normalized_group_id, scope_text = _normalize_group_scope(request.group_id)
    return normalized_group_id, scope_text, _run_range_text(request)


def _a_share_api_key_available_or_fail_task(task_id: str) -> bool:
    if has_openai_api_key():
        return True

    update_task(task_id, "failed", A_SHARE_MISSING_API_KEY_MESSAGE)
    add_task_log(task_id, f"❌ {A_SHARE_MISSING_API_KEY_MESSAGE}")
    return False


def _a_share_task_ready_to_start(task_id: str) -> bool:
    if not _a_share_api_key_available_or_fail_task(task_id):
        return False
    return not is_task_stopped(task_id)


def _start_a_share_analysis_task(
    task_id: str,
    normalized_group_id: Optional[str],
    scope_text: str,
    run_range_text: str,
    request: AShareAnalysisTaskRequest,
) -> str:
    description = f"开始A股公司分析（{scope_text}），扫描{run_range_text}数据"
    update_task(task_id, "running", description)
    add_task_log(task_id, f"🚀 {description}")
    add_task_log(
        task_id,
        f"⚙️ 参数: group_id={normalized_group_id or 'GLOBAL'}, concurrency={request.concurrency}, "
        f"model={request.model}, api_base={request.api_base}, wire_api={request.wire_api}, "
        f"reasoning_effort={request.reasoning_effort}",
    )

    if request.reset_start_date or request.reset_end_date:
        add_task_log(
            task_id,
            f"🧹 删除并重跑区间: {request.reset_start_date or '-'} ~ {request.reset_end_date or '-'}",
        )

    return description


def _run_a_share_analysis_for_task(
    task_id: str,
    normalized_group_id: Optional[str],
    request: AShareAnalysisTaskRequest,
) -> dict:
    return run_analysis(
        days=request.days,
        group_id=normalized_group_id,
        model=request.model,
        api_base=request.api_base,
        wire_api=request.wire_api,
        reasoning_effort=request.reasoning_effort,
        concurrency=request.concurrency,
        start_date=request.start_date,
        end_date=request.end_date,
        reset_start_date=request.reset_start_date,
        reset_end_date=request.reset_end_date,
        log_callback=_task_log_callback(task_id),
    )


def _fail_a_share_analysis_task(task_id: str, error: Exception) -> None:
    try:
        message = f"A股公司分析失败: {str(error)}"
        add_task_log(task_id, f"❌ {message}")
        update_task(task_id, "failed", message)
    except Exception:
        pass


def _complete_a_share_analysis_task(task_id: str, result: dict) -> None:
    update_task(task_id, "completed", "A股公司分析完成", result)
    add_task_log(task_id, "✅ A股公司分析完成")


def run_a_share_analysis_task(task_id: str, request: AShareAnalysisTaskRequest) -> None:
    try:
        if not _a_share_task_ready_to_start(task_id):
            return

        normalized_group_id, scope_text, run_range_text = _a_share_analysis_task_context(request)
        _start_a_share_analysis_task(task_id, normalized_group_id, scope_text, run_range_text, request)

        result = _run_a_share_analysis_for_task(task_id, normalized_group_id, request)

        _complete_a_share_analysis_task(task_id, result)
    except Exception as exc:
        _fail_a_share_analysis_task(task_id, exc)


def create_a_share_analysis_task(
    *,
    group_id: Optional[str | int] = None,
    days: int = 21,
    concurrency: int = A_SHARE_DEFAULT_CONCURRENCY,
    model: str = A_SHARE_DEFAULT_MODEL,
    api_base: str = A_SHARE_DEFAULT_API_BASE,
    wire_api: str = A_SHARE_DEFAULT_WIRE_API,
    reasoning_effort: str = A_SHARE_DEFAULT_REASONING_EFFORT,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    reset_start_date: Optional[str] = None,
    reset_end_date: Optional[str] = None,
) -> dict[str, str]:
    if not has_openai_api_key():
        raise RuntimeError(A_SHARE_MISSING_API_KEY_MESSAGE)

    request = AShareAnalysisTaskRequest(
        group_id=group_id,
        days=days,
        concurrency=concurrency,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        start_date=start_date,
        end_date=end_date,
        reset_start_date=reset_start_date,
        reset_end_date=reset_end_date,
    )
    normalized_group_id, scope_text, run_range_text = _a_share_analysis_task_context(request)
    return launch_task(
        "a_share_analysis",
        f"A股公司分析（{scope_text}，{run_range_text}）",
        run_a_share_analysis_task,
        request,
        metadata=_a_share_task_metadata(normalized_group_id),
    )


async def export_a_share_analysis_to_tdx(
    *,
    group_id: Optional[str | int] = None,
    group_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    result = await asyncio.to_thread(
        export_a_share_rankings_to_tdx,
        start_date,
        end_date,
        group_id=normalize_group_id(group_id),
        group_name=group_name,
    )
    return {"success": True, **result}
