from __future__ import annotations

import asyncio
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
    DEFAULT_RETENTION_DAYS as A_SHARE_DEFAULT_RETENTION_DAYS,
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
    create_task,
    get_latest_task_by_type,
    is_task_stopped,
    update_task,
)

router = APIRouter(prefix="/api/analytics/a-share", tags=["a-share"])


class AShareAnalysisRunRequest(BaseModel):
    group_id: Optional[str | int] = Field(default=None, description="指定群组ID；为空时使用全局聚合")
    days: int = Field(default=21, ge=1, le=365, description="分析最近多少天的话题")
    retention_days: int = Field(
        default=A_SHARE_DEFAULT_RETENTION_DAYS,
        ge=1,
        le=3650,
        description="保留最近多少天的分析数据",
    )
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
    reset_start_date: Optional[str] = Field(default=None, description="删除并重跑的开始日期 YYYY-MM-DD")
    reset_end_date: Optional[str] = Field(default=None, description="删除并重跑的结束日期 YYYY-MM-DD")


class AShareAnalysisResetRangeRequest(BaseModel):
    group_id: Optional[str | int] = Field(default=None, description="指定群组ID；为空时删除全局聚合结果")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")


class AShareAnalysisExportTdxRequest(BaseModel):
    group_id: Optional[str | int] = Field(default=None, description="指定群组ID；为空时导出全局聚合结果")
    start_date: Optional[str] = Field(default=None, description="图表筛选开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="图表筛选结束日期 YYYY-MM-DD")


def _normalize_group_scope(group_id: Optional[str | int]) -> tuple[Optional[str], str]:
    normalized_group_id = normalize_group_id(group_id)
    scope_text = f"群组 {normalized_group_id}" if normalized_group_id else "全局聚合"
    return normalized_group_id, scope_text


def _analysis_defaults_payload() -> dict:
    return {
        "days": 21,
        "retention_days": A_SHARE_DEFAULT_RETENTION_DAYS,
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


def run_a_share_analysis_task(task_id: str, request: AShareAnalysisRunRequest):
    """后台执行A股公司提及分析任务"""
    try:
        if not has_openai_api_key():
            message = "未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key"
            update_task(task_id, "failed", message)
            add_task_log(task_id, f"❌ {message}")
            return

        if is_task_stopped(task_id):
            return

        normalized_group_id, scope_text = _normalize_group_scope(request.group_id)
        description = f"开始A股公司分析（{scope_text}），扫描最近 {request.days} 天数据"
        update_task(task_id, "running", description)
        add_task_log(task_id, f"🚀 {description}")
        add_task_log(
            task_id,
            f"⚙️ 参数: group_id={normalized_group_id or 'GLOBAL'}, retention_days={request.retention_days}, concurrency={request.concurrency}, "
            f"model={request.model}, api_base={request.api_base}, wire_api={request.wire_api}, "
            f"reasoning_effort={request.reasoning_effort}",
        )

        if request.reset_start_date or request.reset_end_date:
            add_task_log(
                task_id,
                f"🧹 删除并重跑区间: {request.reset_start_date or '-'} ~ {request.reset_end_date or '-'}",
            )

        def log_callback(message: str):
            add_task_log(task_id, message)

        result = run_analysis(
            days=request.days,
            group_id=normalized_group_id,
            model=request.model,
            api_base=request.api_base,
            wire_api=request.wire_api,
            reasoning_effort=request.reasoning_effort,
            concurrency=request.concurrency,
            retention_days=request.retention_days,
            reset_start_date=request.reset_start_date,
            reset_end_date=request.reset_end_date,
            log_callback=log_callback,
        )

        update_task(task_id, "completed", "A股公司分析完成", result)
        add_task_log(task_id, "✅ A股公司分析完成")
    except Exception as e:
        try:
            add_task_log(task_id, f"❌ A股公司分析失败: {str(e)}")
            update_task(task_id, "failed", f"A股公司分析失败: {str(e)}")
        except Exception:
            pass


@router.get("/status")
async def get_a_share_analysis_status(group_id: Optional[str] = None):
    """获取A股分析状态和文件摘要"""
    try:
        normalized_group_id = normalize_group_id(group_id)
        summary = await asyncio.to_thread(get_analysis_summary, group_id=normalized_group_id)
        latest_task = get_latest_task_by_type(
            "a_share_analysis",
            group_id=normalized_group_id,
        )
        running_task = get_latest_task_by_type(
            "a_share_analysis",
            status="running",
            group_id=normalized_group_id,
        )
        if normalized_group_id:
            storage = {
                "enabled": False,
                "mode": "file_per_group",
                "label": f"群组 {normalized_group_id} 本地分析文件",
                "daily_rows": summary.get("rows_count") or 0,
                "processed_rows": summary.get("processed_items") or 0,
            }
        else:
            try:
                storage = await asyncio.to_thread(get_storage_health)
            except Exception as storage_error:
                storage = {
                    "enabled": False,
                    "mode": "file_only",
                    "label": f"本地文件镜像（PostgreSQL 不可用: {storage_error}）",
                }

        try:
            latest_tdx_export = await asyncio.to_thread(get_latest_tdx_export, normalized_group_id)
        except Exception:
            latest_tdx_export = None

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
                detail="未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key",
            )

        normalized_group_id, scope_text = _normalize_group_scope(request.group_id)
        task_id = create_task(
            "a_share_analysis",
            f"A股公司分析（{scope_text}，最近 {request.days} 天）",
            metadata={"group_id": normalized_group_id},
        )
        background_tasks.add_task(run_a_share_analysis_task, task_id, request)
        return {"task_id": task_id, "message": "任务已创建，正在后台执行"}
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
