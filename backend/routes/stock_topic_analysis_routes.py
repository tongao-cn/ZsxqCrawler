from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.stock_external_summary_service import get_external_stock_summaries
from backend.services.stock_topic_analysis_service import (
    answer_stock_question,
    analyze_stock_topics,
    analyze_stock_topics_batch,
    extract_stock_names_from_image,
    get_latest_stock_topic_analysis,
    get_latest_stock_topic_analyses,
    parse_stock_names,
    search_stock_question_topics,
    search_stock_topics,
)
from backend.services.task_runtime import (
    add_task_log,
    create_task,
    enqueue_runtime_task,
    is_task_stopped,
    run_workflow,
    update_task,
)


router = APIRouter(prefix="/api/analysis/stock-topics", tags=["stock-topic-analysis"])
TASK_CREATED_MESSAGE = "任务已创建，正在后台执行"


class StockTopicAnalysisRequest(BaseModel):
    stockName: str = Field(..., min_length=1, description="股票名称")


class StockTopicAnalysisBatchRequest(BaseModel):
    stockNames: list[str] = Field(..., min_length=1, description="股票名称列表")


class ExternalStockSummaryRequest(BaseModel):
    stockNames: list[str] = Field(..., min_length=1, description="股票名称列表")
    date: str | None = Field(default=None, description="每日概念日期，格式 YYYY-MM-DD；不传则取最新可用记录")


class StockTopicImageExtractRequest(BaseModel):
    imageDataUrl: str = Field(..., min_length=1, description="图片 data URL")


class StockQuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, description="A股问题")


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


def _create_stock_task_response(
    task_type: str,
    description: str,
    metadata: dict,
    task_func,
    group_id: str,
    request,
) -> dict[str, str]:
    task_id = create_task(task_type, description, metadata)
    enqueue_runtime_task(task_func, task_id, group_id, request)
    return {"task_id": task_id, "message": TASK_CREATED_MESSAGE}


def _stock_topic_batch_completed_message(result: dict) -> str:
    summary = result.get("summary") or {}
    return (
        f"批量个股话题分析完成：成功 {summary.get('success', 0)}，"
        f"失败 {summary.get('failed', 0)}，无话题 {summary.get('no_topics', 0)}"
    )


def _stock_topic_batch_running_message(stock_count: int) -> str:
    return f"开始批量个股话题分析，共 {stock_count} 只股票..."


def run_stock_topic_analysis_task(task_id: str, group_id: str, request: StockTopicAnalysisRequest) -> None:
    def work() -> dict:
        log_callback = _build_stock_topic_log_callback(task_id)
        log_callback(f"🔎 股票名称: {request.stockName}")
        return analyze_stock_topics(group_id, request.stockName, log_callback=log_callback)

    run_workflow(
        task_id,
        running_message="开始个股话题分析...",
        completed_message="个股话题分析完成",
        failure_label="个股话题分析",
        work=work,
    )


def run_stock_question_task(task_id: str, group_id: str, request: StockQuestionRequest) -> None:
    def work() -> dict:
        log_callback = _build_stock_topic_log_callback(task_id)
        log_callback(f"❓ 问题: {request.question}")
        return answer_stock_question(group_id, request.question, log_callback=log_callback)

    run_workflow(
        task_id,
        running_message="开始A股问答分析...",
        completed_message="A股问答分析完成",
        failure_label="A股问答",
        work=work,
    )


def run_stock_topic_analysis_batch_task(task_id: str, group_id: str, request: StockTopicAnalysisBatchRequest) -> None:
    try:
        if is_task_stopped(task_id):
            return

        log_callback = _build_stock_topic_log_callback(task_id)
        stock_names = parse_stock_names(request.stockNames)
        update_task(task_id, "running", _stock_topic_batch_running_message(len(stock_names)))
        result = analyze_stock_topics_batch(group_id, stock_names, log_callback=log_callback)

        if is_task_stopped(task_id):
            return

        update_task(
            task_id,
            "completed",
            _stock_topic_batch_completed_message(result),
            result,
        )
    except Exception as exc:
        _fail_stock_topic_task_unless_stopped(task_id, exc)


@router.get("/{group_id}/questions")
async def read_stock_question_matches(
    group_id: str,
    question: str = Query(..., min_length=1, description="A股问题"),
):
    try:
        return search_stock_question_topics(group_id, question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"搜索A股问答相关话题失败: {str(exc)}")


@router.post("/{group_id}/questions/analyze")
async def create_stock_question_analysis(
    group_id: str,
    request: StockQuestionRequest,
):
    try:
        if not request.question.strip():
            raise ValueError("question 不能为空")
        return _create_stock_task_response(
            "stock_question_analysis",
            f"A股问答 (群组: {group_id})",
            {"group_id": str(group_id), "question": request.question},
            run_stock_question_task,
            group_id,
            request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建A股问答任务失败: {str(exc)}")


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


@router.post("/extract-stocks-from-image")
async def extract_stock_topics_from_image(request: StockTopicImageExtractRequest):
    try:
        return extract_stock_names_from_image(request.imageDataUrl)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"从图片提取股票失败: {str(exc)}")


@router.post("/{group_id}/analyze")
async def create_stock_topic_analysis(
    group_id: str,
    request: StockTopicAnalysisRequest,
):
    try:
        if not request.stockName.strip():
            raise ValueError("stock_name 不能为空")
        return _create_stock_task_response(
            "stock_topic_analysis",
            f"个股话题分析 (群组: {group_id}, 股票: {request.stockName})",
            {"group_id": str(group_id), "stock_name": request.stockName},
            run_stock_topic_analysis_task,
            group_id,
            request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建个股话题分析任务失败: {str(exc)}")


@router.post("/{group_id}/analyze-batch")
async def create_stock_topic_analysis_batch(
    group_id: str,
    request: StockTopicAnalysisBatchRequest,
):
    try:
        stock_names = parse_stock_names(request.stockNames)
        if not stock_names:
            raise ValueError("stock_names 不能为空")
        normalized_request = StockTopicAnalysisBatchRequest(stockNames=stock_names)
        return _create_stock_task_response(
            "stock_topic_analysis_batch",
            f"批量个股话题分析 (群组: {group_id}, 股票数: {len(stock_names)})",
            {"group_id": str(group_id), "stock_names": stock_names},
            run_stock_topic_analysis_batch_task,
            group_id,
            normalized_request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建批量个股话题分析任务失败: {str(exc)}")


@router.post("/{group_id}/external-summary")
async def read_external_stock_summaries(
    group_id: str,
    request: ExternalStockSummaryRequest,
):
    try:
        return get_external_stock_summaries(group_id, request.stockNames, report_date=request.date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取外部股票汇总失败: {str(exc)}")


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


@router.get("/{group_id}/latest-batch")
async def read_latest_stock_topic_analyses(
    group_id: str,
    stock_names: str = Query(..., min_length=1, description="股票名称，支持逗号、顿号、空格或换行分隔"),
):
    try:
        return get_latest_stock_topic_analyses(group_id, stock_names)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取批量个股话题分析结果失败: {str(exc)}")
