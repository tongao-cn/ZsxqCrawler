from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from backend.services.ai_workflow_preflight import (
    fail_task_if_openai_api_key_missing,
    require_openai_api_key,
)
from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_CONCURRENCY as A_SHARE_DEFAULT_CONCURRENCY,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT as A_SHARE_DEFAULT_REASONING_EFFORT,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
    normalize_group_id,
    run_analysis,
)
from backend.services.task_launch import TaskLaunchRecipe, launch_task_recipe
from backend.services.task_runtime import add_task_log, build_task_log_callback, is_task_stopped, update_task
from backend.services.tdx_a_share_export_service import export_a_share_rankings_to_tdx


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


def _task_log_callback(task_id: str):
    return build_task_log_callback(
        task_id,
        lambda current_task_id, message: add_task_log(current_task_id, message),
    )


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
    return not fail_task_if_openai_api_key_missing(
        task_id,
        update_task_state=update_task,
        add_task_log=add_task_log,
    )


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
    require_openai_api_key()

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
    return launch_task_recipe(
        TaskLaunchRecipe(
            task_type="a_share_analysis",
            description=f"A股公司分析（{scope_text}，{run_range_text}）",
            task_func=run_a_share_analysis_task,
            args=(request,),
            metadata=_a_share_task_metadata(normalized_group_id),
        )
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
