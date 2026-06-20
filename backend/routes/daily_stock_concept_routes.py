from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.daily_stock_concept_service import get_daily_stock_concepts
from backend.services.task_launch import TASK_CREATED_MESSAGE as _TASK_CREATED_MESSAGE
from backend.services.workflow_task_launch import create_daily_stock_concept_task


router = APIRouter(prefix="/api/analysis/daily-stock-concepts", tags=["daily-stock-concepts"])
TASK_CREATED_MESSAGE = _TASK_CREATED_MESSAGE


class DailyStockConceptRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）")
    commentsPerTopic: int = Field(default=0, ge=0, le=50, description="每个话题最多纳入的评论数")


def _create_daily_stock_concept_task_response(
    group_id: str,
    request: DailyStockConceptRequest,
) -> dict[str, str]:
    return create_daily_stock_concept_task(
        group_id,
        date=request.date,
        comments_per_topic=request.commentsPerTopic,
    )


def _daily_stock_concept_route_error(message: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


def _daily_stock_concepts_or_404(group_id: str, date: Optional[str]) -> dict:
    result = get_daily_stock_concepts(group_id, date)
    if not result:
        raise HTTPException(status_code=404, detail="股票概念结果不存在，请先提取")
    return result


@router.post("/{group_id}")
async def create_daily_stock_concepts(
    group_id: str,
    request: DailyStockConceptRequest,
    background_tasks: BackgroundTasks,
):
    try:
        return _create_daily_stock_concept_task_response(group_id, request)
    except Exception as e:
        raise _daily_stock_concept_route_error("创建每日股票概念提取任务失败", e)


@router.get("/{group_id}")
async def read_daily_stock_concepts(
    group_id: str,
    date: Optional[str] = Query(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）"),
):
    try:
        return _daily_stock_concepts_or_404(group_id, date)
    except HTTPException:
        raise
    except Exception as e:
        raise _daily_stock_concept_route_error("获取每日股票概念失败", e)
