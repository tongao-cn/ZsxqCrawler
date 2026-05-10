from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.stock_topic_analysis_service import (
    analyze_stock_topics,
    get_latest_stock_topic_analysis,
    search_stock_topics,
)
from backend.services.task_runtime import add_task_log, create_task, enqueue_runtime_task, is_task_stopped, update_task


router = APIRouter(prefix="/api/analysis/stock-topics", tags=["stock-topic-analysis"])
TASK_CREATED_MESSAGE = "任务已创建，正在后台执行"


class StockTopicAnalysisRequest(BaseModel):
    stockName: str = Field(..., min_length=1, description="股票名称")


def _build_stock_topic_log_callback(task_id: str) -> Callable[[str], None]:
    def log_callback(message: str) -> None:
        add_task_log(task_id, message)

    return log_callback


def _fail_stock_topic_task_unless_stopped(task_id: str, error: Exception) -> None:
    if is_task_stopped(task_id):
        return
    message = f"个股话题分析失败: {str(error)}"
    add_task_log(task_id, f"❌ {message}")
    update_task(task_id, "failed", message)


def run_stock_topic_analysis_task(task_id: str, group_id: str, request: StockTopicAnalysisRequest) -> None:
    try:
        if is_task_stopped(task_id):
            return

        log_callback = _build_stock_topic_log_callback(task_id)
        update_task(task_id, "running", "开始个股话题分析...")
        log_callback(f"🔎 股票名称: {request.stockName}")
        result = analyze_stock_topics(group_id, request.stockName, log_callback=log_callback)

        if is_task_stopped(task_id):
            return

        update_task(task_id, "completed", "个股话题分析完成", result)
    except Exception as exc:
        _fail_stock_topic_task_unless_stopped(task_id, exc)


@router.get("/{group_id}")
async def read_stock_topic_matches(
    group_id: str,
    stock_name: str = Query(..., min_length=1, description="股票名称"),
):
    try:
        return search_stock_topics(group_id, stock_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"搜索股票相关话题失败: {str(exc)}")


@router.post("/{group_id}/analyze")
async def create_stock_topic_analysis(
    group_id: str,
    request: StockTopicAnalysisRequest,
):
    try:
        if not request.stockName.strip():
            raise ValueError("stock_name 不能为空")
        task_id = create_task(
            "stock_topic_analysis",
            f"个股话题分析 (群组: {group_id}, 股票: {request.stockName})",
            {"group_id": str(group_id), "stock_name": request.stockName},
        )
        enqueue_runtime_task(run_stock_topic_analysis_task, task_id, group_id, request)
        return {"task_id": task_id, "message": TASK_CREATED_MESSAGE}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建个股话题分析任务失败: {str(exc)}")


@router.get("/{group_id}/latest")
async def read_latest_stock_topic_analysis(
    group_id: str,
    stock_name: str = Query(..., min_length=1, description="股票名称"),
):
    try:
        result = get_latest_stock_topic_analysis(group_id, stock_name)
        if not result:
            raise HTTPException(status_code=404, detail="个股话题分析结果不存在，请先分析")
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取个股话题分析结果失败: {str(exc)}")
