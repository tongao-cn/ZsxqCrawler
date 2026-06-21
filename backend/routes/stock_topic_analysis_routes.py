from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.routes.task_http_errors import route_error
from backend.services.stock_external_summary_service import get_external_stock_summaries
from backend.services.stock_topic_analysis_service import (
    extract_stock_names_from_image,
    get_latest_stock_topic_analysis,
    get_latest_stock_topic_analyses,
    search_stock_question_topics,
    search_stock_topics,
)
from backend.services.stock_topic_analysis_workflow import (
    create_stock_question_task,
    create_stock_topic_batch_task,
    create_stock_topic_task,
)


router = APIRouter(prefix="/api/analysis/stock-topics", tags=["stock-topic-analysis"])


def _stock_topic_route_error(message: str, error: Exception) -> HTTPException:
    return route_error(message, error)


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


def _latest_stock_topic_analysis_or_404(group_id: str, stock_name: str) -> dict:
    result = get_latest_stock_topic_analysis(group_id, stock_name)
    if not result:
        raise HTTPException(status_code=404, detail="个股话题分析结果不存在，请先分析")
    return result


def _external_stock_summaries(group_id: str, request: ExternalStockSummaryRequest) -> dict:
    return get_external_stock_summaries(group_id, request.stockNames, report_date=request.date)


def _latest_stock_topic_analyses(group_id: str, stock_names: str) -> dict:
    return get_latest_stock_topic_analyses(group_id, stock_names)


def _stock_question_matches(group_id: str, question: str) -> dict:
    return search_stock_question_topics(group_id, question)


def _stock_topic_matches(group_id: str, stock_name: str) -> dict:
    return search_stock_topics(group_id, stock_name)


def _stock_names_from_image(request: StockTopicImageExtractRequest) -> dict:
    return extract_stock_names_from_image(request.imageDataUrl)


def _create_stock_question_task_response(group_id: str, request: StockQuestionRequest) -> dict[str, str]:
    return create_stock_question_task(group_id, request.question)


def _create_stock_topic_task_response(group_id: str, request: StockTopicAnalysisRequest) -> dict[str, str]:
    return create_stock_topic_task(group_id, request.stockName)


def _create_stock_topic_batch_task_response(group_id: str, stock_names: list[str]) -> dict[str, str]:
    return create_stock_topic_batch_task(group_id, stock_names)


@router.get("/{group_id}/questions")
async def read_stock_question_matches(
    group_id: str,
    question: str = Query(..., min_length=1, description="A股问题"),
):
    try:
        return _stock_question_matches(group_id, question)
    except Exception as exc:
        raise _stock_topic_route_error("搜索A股问答相关话题失败", exc)


@router.post("/{group_id}/questions/analyze")
async def create_stock_question_analysis(
    group_id: str,
    request: StockQuestionRequest,
):
    try:
        if not request.question.strip():
            raise ValueError("question 不能为空")
        return _create_stock_question_task_response(group_id, request)
    except Exception as exc:
        raise _stock_topic_route_error("创建A股问答任务失败", exc)


@router.get("/{group_id}")
async def read_stock_topic_matches(
    group_id: str,
    stock_name: str = Query(..., min_length=1, description="股票名称"),
):
    try:
        return _stock_topic_matches(group_id, stock_name)
    except Exception as exc:
        raise _stock_topic_route_error("搜索股票相关话题失败", exc)


@router.post("/extract-stocks-from-image")
async def extract_stock_topics_from_image(request: StockTopicImageExtractRequest):
    try:
        return _stock_names_from_image(request)
    except Exception as exc:
        raise _stock_topic_route_error("从图片提取股票失败", exc)


@router.post("/{group_id}/analyze")
async def create_stock_topic_analysis(
    group_id: str,
    request: StockTopicAnalysisRequest,
):
    try:
        if not request.stockName.strip():
            raise ValueError("stock_name 不能为空")
        return _create_stock_topic_task_response(group_id, request)
    except Exception as exc:
        raise _stock_topic_route_error("创建个股话题分析任务失败", exc)


@router.post("/{group_id}/analyze-batch")
async def create_stock_topic_analysis_batch(
    group_id: str,
    request: StockTopicAnalysisBatchRequest,
):
    try:
        return _create_stock_topic_batch_task_response(group_id, request.stockNames)
    except Exception as exc:
        raise _stock_topic_route_error("创建批量个股话题分析任务失败", exc)


@router.post("/{group_id}/external-summary")
async def read_external_stock_summaries(
    group_id: str,
    request: ExternalStockSummaryRequest,
):
    try:
        return _external_stock_summaries(group_id, request)
    except Exception as exc:
        raise _stock_topic_route_error("获取外部股票汇总失败", exc)


@router.get("/{group_id}/latest")
async def read_latest_stock_topic_analysis(
    group_id: str,
    stock_name: str = Query(..., min_length=1, description="股票名称"),
):
    try:
        return _latest_stock_topic_analysis_or_404(group_id, stock_name)
    except Exception as exc:
        raise _stock_topic_route_error("获取个股话题分析结果失败", exc)


@router.get("/{group_id}/latest-batch")
async def read_latest_stock_topic_analyses(
    group_id: str,
    stock_names: str = Query(..., min_length=1, description="股票名称，支持逗号、顿号、空格或换行分隔"),
):
    try:
        return _latest_stock_topic_analyses(group_id, stock_names)
    except Exception as exc:
        raise _stock_topic_route_error("获取批量个股话题分析结果失败", exc)
