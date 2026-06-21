from __future__ import annotations

import asyncio
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_CONCURRENCY as A_SHARE_DEFAULT_CONCURRENCY,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT as A_SHARE_DEFAULT_REASONING_EFFORT,
    DEFAULT_RANKING_WINDOWS as A_SHARE_DEFAULT_RANKING_WINDOWS,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
    build_chart_payload,
    normalize_group_id,
    reset_analysis_range,
)
from backend.services.a_share_analysis_status_service import get_a_share_analysis_status_payload
from backend.services.a_share_analysis_workflow import (
    A_SHARE_MISSING_API_KEY_MESSAGE,
    create_a_share_analysis_task,
    export_a_share_analysis_to_tdx as run_a_share_tdx_export,
)
from backend.services.task_launch import TASK_CREATED_MESSAGE as _TASK_CREATED_MESSAGE

router = APIRouter(prefix="/api/analytics/a-share", tags=["a-share"])
TASK_CREATED_MESSAGE = _TASK_CREATED_MESSAGE


def _a_share_route_error(message: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


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


def _bounded_chart_top_n(top_n: int) -> int:
    return max(1, min(top_n, 100))


def _success_payload(result: dict) -> dict:
    return {"success": True, **result}


def _create_a_share_analysis_task_response(request: AShareAnalysisRunRequest) -> dict[str, str]:
    return create_a_share_analysis_task(
        group_id=request.group_id,
        days=request.days,
        concurrency=request.concurrency,
        model=request.model,
        api_base=request.api_base,
        wire_api=request.wire_api,
        reasoning_effort=request.reasoning_effort,
        start_date=request.start_date,
        end_date=request.end_date,
        reset_start_date=request.reset_start_date,
        reset_end_date=request.reset_end_date,
    )


async def _a_share_chart_payload(
    normalized_group_id: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    top_n: int,
) -> dict:
    return await asyncio.to_thread(
        build_chart_payload,
        start_date=start_date,
        end_date=end_date,
        top_n=_bounded_chart_top_n(top_n),
        ranking_windows=A_SHARE_DEFAULT_RANKING_WINDOWS,
        group_id=normalized_group_id,
    )


async def _reset_a_share_analysis_range(request: AShareAnalysisResetRangeRequest) -> dict:
    return await asyncio.to_thread(
        reset_analysis_range,
        request.start_date,
        request.end_date,
        group_id=normalize_group_id(request.group_id),
    )


async def _export_a_share_analysis_to_tdx(request: AShareAnalysisExportTdxRequest) -> dict:
    return await run_a_share_tdx_export(
        group_id=normalize_group_id(request.group_id),
        group_name=request.group_name,
        start_date=request.start_date,
        end_date=request.end_date,
    )


@router.get("/status")
async def get_a_share_analysis_status(group_id: Optional[str] = None):
    """获取A股分析状态和文件摘要"""
    try:
        return await get_a_share_analysis_status_payload(group_id)
    except Exception as e:
        raise _a_share_route_error("获取A股分析状态失败", e)


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
        return await _a_share_chart_payload(normalized_group_id, start_date, end_date, top_n)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _a_share_route_error("获取A股分析图表失败", e)


@router.post("/run")
async def start_a_share_analysis(request: AShareAnalysisRunRequest):
    """启动A股公司提及分析后台任务"""
    try:
        return _create_a_share_analysis_task_response(request)
    except RuntimeError as e:
        if str(e) == A_SHARE_MISSING_API_KEY_MESSAGE:
            raise HTTPException(status_code=400, detail=str(e))
        raise _a_share_route_error("创建A股分析任务失败", e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _a_share_route_error("创建A股分析任务失败", e)


@router.post("/reset-range")
async def reset_a_share_analysis_date_range(request: AShareAnalysisResetRangeRequest):
    """删除A股分析结果中的指定日期区间"""
    try:
        result = await _reset_a_share_analysis_range(request)
        return _success_payload(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _a_share_route_error("删除A股分析日期区间失败", e)


@router.post("/export-tdx")
async def export_a_share_analysis_to_tdx(request: AShareAnalysisExportTdxRequest):
    """把当前A股推荐池覆盖导入到通达信现有板块"""
    try:
        return await _export_a_share_analysis_to_tdx(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"获取股票主数据失败: {str(e)}")
    except Exception as e:
        raise _a_share_route_error("导入通达信失败", e)
