from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.daily_stock_concept_service import (
    extract_daily_stock_concepts,
    get_daily_stock_concepts,
)
from backend.services.task_runtime import add_task_log, create_task, enqueue_runtime_task, is_task_stopped, update_task


router = APIRouter(prefix="/api/analysis/daily-stock-concepts", tags=["daily-stock-concepts"])
TASK_CREATED_MESSAGE = "任务已创建，正在后台执行"


class DailyStockConceptRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）")
    commentsPerTopic: int = Field(default=0, ge=0, le=50, description="每个话题最多纳入的评论数")


def _build_stock_concept_log_callback(task_id: str) -> Callable[[str], None]:
    def log_callback(message: str) -> None:
        add_task_log(task_id, message)

    return log_callback


def _fail_stock_concept_task_unless_stopped(task_id: str, error: Exception) -> None:
    if is_task_stopped(task_id):
        return
    message = f"每日股票概念提取失败: {str(error)}"
    add_task_log(task_id, f"❌ {message}")
    update_task(task_id, "failed", message)


def run_daily_stock_concept_task(task_id: str, group_id: str, request: DailyStockConceptRequest) -> None:
    try:
        if is_task_stopped(task_id):
            return

        update_task(task_id, "running", "开始提取每日股票概念...")
        result = extract_daily_stock_concepts(
            group_id,
            request.date,
            comments_per_topic=request.commentsPerTopic,
            log_callback=_build_stock_concept_log_callback(task_id),
        )

        if is_task_stopped(task_id):
            return

        update_task(task_id, "completed", "每日股票概念提取完成", result)
    except Exception as e:
        _fail_stock_concept_task_unless_stopped(task_id, e)


@router.post("/{group_id}")
async def create_daily_stock_concepts(
    group_id: str,
    request: DailyStockConceptRequest,
    background_tasks: BackgroundTasks,
):
    try:
        task_id = create_task(
            "daily_stock_concepts",
            f"提取每日股票概念 (群组: {group_id})",
            {"group_id": group_id, "report_date": request.date},
        )
        enqueue_runtime_task(run_daily_stock_concept_task, task_id, group_id, request)
        return {"task_id": task_id, "message": TASK_CREATED_MESSAGE}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建每日股票概念提取任务失败: {str(e)}")


@router.get("/{group_id}")
async def read_daily_stock_concepts(
    group_id: str,
    date: Optional[str] = Query(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）"),
):
    try:
        result = get_daily_stock_concepts(group_id, date)
        if not result:
            raise HTTPException(status_code=404, detail="股票概念结果不存在，请先提取")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取每日股票概念失败: {str(e)}")
