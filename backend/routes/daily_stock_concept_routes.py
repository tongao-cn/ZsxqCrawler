from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.daily_stock_concept_service import (
    extract_daily_stock_concepts,
    get_daily_stock_concepts,
)
from backend.services.task_runtime import (
    add_task_log,
    build_task_log_callback,
    create_task,
    enqueue_runtime_task,
    run_workflow,
)


router = APIRouter(prefix="/api/analysis/daily-stock-concepts", tags=["daily-stock-concepts"])
TASK_CREATED_MESSAGE = "任务已创建，正在后台执行"


class DailyStockConceptRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="报告日期，格式 YYYY-MM-DD；默认今天（东八区）")
    commentsPerTopic: int = Field(default=0, ge=0, le=50, description="每个话题最多纳入的评论数")


def _build_stock_concept_log_callback(task_id: str) -> Callable[[str], None]:
    return build_task_log_callback(
        task_id,
        lambda current_task_id, message: add_task_log(current_task_id, message),
    )


def _stock_concept_task_metadata(group_id: str, report_date: Optional[str]) -> dict[str, Optional[str]]:
    return {"group_id": group_id, "report_date": report_date}


def _create_daily_stock_concept_task_response(
    group_id: str,
    request: DailyStockConceptRequest,
) -> dict[str, str]:
    task_id = create_task(
        "daily_stock_concepts",
        f"提取每日股票概念 (群组: {group_id})",
        _stock_concept_task_metadata(group_id, request.date),
    )
    enqueue_runtime_task(run_daily_stock_concept_task, task_id, group_id, request)
    return {"task_id": task_id, "message": TASK_CREATED_MESSAGE}


def _extract_daily_stock_concepts_for_task(task_id: str, group_id: str, request: DailyStockConceptRequest) -> dict:
    return extract_daily_stock_concepts(
        group_id,
        request.date,
        comments_per_topic=request.commentsPerTopic,
        log_callback=_build_stock_concept_log_callback(task_id),
    )


def run_daily_stock_concept_task(task_id: str, group_id: str, request: DailyStockConceptRequest) -> None:
    def work() -> dict:
        return _extract_daily_stock_concepts_for_task(task_id, group_id, request)

    run_workflow(
        task_id,
        running_message="开始提取每日股票概念...",
        completed_message="每日股票概念提取完成",
        failure_label="每日股票概念提取",
        work=work,
    )


@router.post("/{group_id}")
async def create_daily_stock_concepts(
    group_id: str,
    request: DailyStockConceptRequest,
    background_tasks: BackgroundTasks,
):
    try:
        return _create_daily_stock_concept_task_response(group_id, request)
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
