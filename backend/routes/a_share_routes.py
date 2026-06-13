from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.services.a_share_analysis_db_storage import get_storage_health
from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_CONCURRENCY as A_SHARE_DEFAULT_CONCURRENCY,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT as A_SHARE_DEFAULT_REASONING_EFFORT,
    DEFAULT_RANKING_WINDOWS as A_SHARE_DEFAULT_RANKING_WINDOWS,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
    build_chart_payload,
    get_analysis_summary,
    normalize_group_id,
    reset_analysis_range,
    run_analysis,
)
from backend.core.ai_provider_config import has_openai_api_key
from backend.services.tdx_a_share_export_service import export_a_share_rankings_to_tdx, get_latest_tdx_export
from backend.services.task_runtime import (
    add_task_log,
    build_task_log_callback,
    create_task,
    enqueue_runtime_task,
    get_latest_task_by_type,
    is_task_stopped,
    update_task,
)

router = APIRouter(prefix="/api/analytics/a-share", tags=["a-share"])
TASK_CREATED_MESSAGE = "任务已创建，正在后台执行"
A_SHARE_MISSING_API_KEY_MESSAGE = "未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key"


class AShareAnalysisRunRequest(BaseModel):
    group_id: Optional[str | int] = Field(default=None, description="指定群组ID；为空时使用全局聚合")
    days: int = Field(default=21, ge=1, le=365, description="分析最近多少天的话题")
    concurrency: int = Field(
        default=A_SHARE_DEFAULT_CONCURRENCY,
        ge=1,
        le=128,
        description="并发调用模型的线程数",
    )
    model: str = Field(default=A_SHARE_DEFAULT_MODEL, description="OpenAI兼容模型名称")
    api_base: str = Field(default=A_SHARE_DEFAULT_API_BASE, description="OpenAI兼容API地址")
    wire_api: str = Field(default=A_SHARE_DEFAULT_WIRE_API, description="OpenAI接口类型：responses 或 chat_completions")
    reasoning_effort: str = Field(default=A_SHARE_DEFAULT_REASONING_EFFORT, description="Responses API 的 reasoning effort")
    start_date: Optional[str] = Field(default=None, description="本次运行的开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="本次运行的结束日期 YYYY-MM-DD")
    reset_start_date: Optional[str] = Field(default=None, description="删除并重跑的开始日期 YYYY-MM-DD")
    reset_end_date: Optional[str] = Field(default=None, description="删除并重跑的结束日期 YYYY-MM-DD")


class AShareAnalysisResetRangeRequest(BaseModel):
    group_id: Optional[str | int] = Field(default=None, description="指定群组ID；为空时删除全局聚合结果")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")


class AShareAnalysisExportTdxRequest(BaseModel):
    group_id: Optional[str | int] = Field(default=None, description="指定群组ID；为空时导出全局聚合结果")
    group_name: Optional[str] = Field(default=None, description="当前群组名称；导出群组板块时用于生成通达信板块前缀")
    start_date: Optional[str] = Field(default=None, description="图表筛选开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="图表筛选结束日期 YYYY-MM-DD")


def _normalize_group_scope(group_id: Optional[str | int]) -> tuple[Optional[str], str]:
    normalized_group_id = normalize_group_id(group_id)
    scope_text = f"群组 {normalized_group_id}" if normalized_group_id else "全局聚合"
    return normalized_group_id, scope_text


def _analysis_defaults_payload() -> dict:
    return {
        "days": 21,
        "concurrency": A_SHARE_DEFAULT_CONCURRENCY,
        "model": A_SHARE_DEFAULT_MODEL,
        "api_base": A_SHARE_DEFAULT_API_BASE,
        "wire_api": A_SHARE_DEFAULT_WIRE_API,
        "reasoning_effort": A_SHARE_DEFAULT_REASONING_EFFORT,
        "ranking_windows": list(A_SHARE_DEFAULT_RANKING_WINDOWS),
    }


def _bounded_chart_top_n(top_n: int) -> int:
    return max(1, min(top_n, 100))


def _success_payload(result: dict) -> dict:
    return {"success": True, **result}


def _run_range_text(request: AShareAnalysisRunRequest) -> str:
    if request.start_date or request.end_date:
        if not request.start_date or not request.end_date:
            raise ValueError("start_date 和 end_date 需要同时提供")
        try:
            start_day = datetime.strptime(request.start_date.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
            end_day = datetime.strptime(request.end_date.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("start_date 和 end_date 必须是 YYYY-MM-DD 格式") from exc
        if start_day > end_day:
            raise ValueError("start_date 不能晚于 end_date")
        return f"{start_day} ~ {end_day}"
    return f"最近 {request.days} 天"


def _a_share_task_metadata(normalized_group_id: Optional[str]) -> dict[str, Optional[str]]:
    return {"group_id": normalized_group_id}


def _create_a_share_analysis_task_response(
    request: AShareAnalysisRunRequest,
    normalized_group_id: Optional[str],
    scope_text: str,
    run_range_text: str,
) -> dict[str, str]:
    task_id = create_task(
        "a_share_analysis",
        f"A股公司分析（{scope_text}，{run_range_text}）",
        metadata=_a_share_task_metadata(normalized_group_id),
    )
    enqueue_runtime_task(run_a_share_analysis_task, task_id, request)
    return {"task_id": task_id, "message": TASK_CREATED_MESSAGE}


def _start_a_share_analysis_task(
    task_id: str,
    normalized_group_id: Optional[str],
    scope_text: str,
    run_range_text: str,
    request: AShareAnalysisRunRequest,
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
    request: AShareAnalysisRunRequest,
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
        log_callback=build_task_log_callback(
            task_id,
            lambda current_task_id, message: add_task_log(current_task_id, message),
        ),
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


def _a_share_file_fallback_storage_status(summary: dict, storage_error: Exception) -> dict:
    return {
        "enabled": False,
        "mode": "file_fallback",
        "label": f"本地文件降级（PostgreSQL 不可用: {storage_error}）",
        "daily_rows": summary.get("rows_count") or 0,
        "processed_rows": summary.get("processed_items") or 0,
    }


async def _a_share_storage_status(summary: dict, normalized_group_id: Optional[str]) -> dict:
    try:
        return await asyncio.to_thread(get_storage_health, group_id=normalized_group_id)
    except Exception as storage_error:
        return _a_share_file_fallback_storage_status(summary, storage_error)


async def _latest_a_share_tdx_export(normalized_group_id: Optional[str]) -> Optional[dict]:
    try:
        return await asyncio.to_thread(get_latest_tdx_export, normalized_group_id)
    except Exception:
        return None


def _a_share_status_tasks(normalized_group_id: Optional[str]) -> tuple[Optional[dict], Optional[dict]]:
    latest_task = get_latest_task_by_type(
        "a_share_analysis",
        group_id=normalized_group_id,
    )
    running_task = get_latest_task_by_type(
        "a_share_analysis",
        status="running",
        group_id=normalized_group_id,
    )
    return latest_task, running_task


def _a_share_status_payload(
    normalized_group_id: Optional[str],
    summary: dict,
    latest_task: Optional[dict],
    running_task: Optional[dict],
    storage: dict,
    latest_tdx_export: Optional[dict],
) -> dict:
    return {
        "summary": summary,
        "group_id": normalized_group_id,
        "defaults": _analysis_defaults_payload(),
        "api_key_configured": has_openai_api_key(),
        "latest_task": latest_task,
        "running_task": running_task,
        "storage": storage,
        "latest_tdx_export": latest_tdx_export,
    }


def run_a_share_analysis_task(task_id: str, request: AShareAnalysisRunRequest):
    """后台执行A股公司提及分析任务"""
    try:
        if not _a_share_task_ready_to_start(task_id):
            return

        normalized_group_id, scope_text = _normalize_group_scope(request.group_id)
        run_range_text = _run_range_text(request)
        _start_a_share_analysis_task(task_id, normalized_group_id, scope_text, run_range_text, request)

        result = _run_a_share_analysis_for_task(task_id, normalized_group_id, request)

        _complete_a_share_analysis_task(task_id, result)
    except Exception as e:
        _fail_a_share_analysis_task(task_id, e)


@router.get("/status")
async def get_a_share_analysis_status(group_id: Optional[str] = None):
    """获取A股分析状态和文件摘要"""
    try:
        normalized_group_id = normalize_group_id(group_id)
        summary = await asyncio.to_thread(get_analysis_summary, group_id=normalized_group_id)
        latest_task, running_task = _a_share_status_tasks(normalized_group_id)
        storage = await _a_share_storage_status(summary, normalized_group_id)

        latest_tdx_export = await _latest_a_share_tdx_export(normalized_group_id)

        return _a_share_status_payload(
            normalized_group_id,
            summary,
            latest_task,
            running_task,
            storage,
            latest_tdx_export,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取A股分析状态失败: {str(e)}")


@router.get("/chart")
async def get_a_share_analysis_chart(
    group_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    top_n: int = 20,
):
    """获取A股分析图表和榜单数据"""
    try:
        normalized_group_id = normalize_group_id(group_id)
        payload = await asyncio.to_thread(
            build_chart_payload,
            start_date=start_date,
            end_date=end_date,
            top_n=_bounded_chart_top_n(top_n),
            ranking_windows=A_SHARE_DEFAULT_RANKING_WINDOWS,
            group_id=normalized_group_id,
        )
        return payload
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取A股分析图表失败: {str(e)}")


@router.post("/run")
async def start_a_share_analysis(request: AShareAnalysisRunRequest, background_tasks: BackgroundTasks):
    """启动A股公司提及分析后台任务"""
    try:
        if not has_openai_api_key():
            raise HTTPException(
                status_code=400,
                detail=A_SHARE_MISSING_API_KEY_MESSAGE,
            )

        normalized_group_id, scope_text = _normalize_group_scope(request.group_id)
        run_range_text = _run_range_text(request)
        return _create_a_share_analysis_task_response(request, normalized_group_id, scope_text, run_range_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建A股分析任务失败: {str(e)}")


@router.post("/reset-range")
async def reset_a_share_analysis_date_range(request: AShareAnalysisResetRangeRequest):
    """删除A股分析结果中的指定日期区间"""
    try:
        result = await asyncio.to_thread(
            reset_analysis_range,
            request.start_date,
            request.end_date,
            group_id=normalize_group_id(request.group_id),
        )
        return _success_payload(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除A股分析日期区间失败: {str(e)}")


@router.post("/export-tdx")
async def export_a_share_analysis_to_tdx(request: AShareAnalysisExportTdxRequest):
    """把当前A股推荐池覆盖导入到通达信现有板块"""
    try:
        result = await asyncio.to_thread(
            export_a_share_rankings_to_tdx,
            request.start_date,
            request.end_date,
            group_id=normalize_group_id(request.group_id),
            group_name=request.group_name,
        )
        return _success_payload(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"获取股票主数据失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入通达信失败: {str(e)}")
