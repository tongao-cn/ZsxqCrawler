"""Task workflow interface for stock topic analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from backend.services.stock_topic_analysis_helpers import parse_stock_names
from backend.services.stock_topic_analysis_service import (
    answer_stock_question,
    analyze_stock_topics,
    analyze_stock_topics_batch,
)
from backend.services.task_launch import (
    TASK_CREATED_MESSAGE as TASK_CREATED_MESSAGE,
    TaskLaunchRecipe,
    launch_task_recipe,
)
from backend.services.task_runtime import add_task_log, build_task_log_callback, run_workflow


@dataclass(frozen=True)
class StockQuestionTaskRequest:
    question: str


@dataclass(frozen=True)
class StockTopicAnalysisTaskRequest:
    stock_name: str


@dataclass(frozen=True)
class StockTopicAnalysisBatchTaskRequest:
    stock_names: list[str]


def _build_stock_topic_log_callback(task_id: str) -> Callable[[str], None]:
    return build_task_log_callback(
        task_id,
        lambda current_task_id, message: add_task_log(current_task_id, message),
    )


def _create_stock_task_response(
    task_type: str,
    description: str,
    metadata: dict[str, Any],
    task_func,
    group_id: str,
    request,
) -> dict[str, str]:
    return launch_task_recipe(
        TaskLaunchRecipe(
            task_type=task_type,
            description=description,
            task_func=task_func,
            args=(group_id, request),
            metadata=metadata,
        )
    )


def _stock_topic_batch_completed_message(result: dict[str, Any]) -> str:
    summary = result.get("summary") or {}
    return (
        f"批量个股话题分析完成：成功 {summary.get('success', 0)}，"
        f"失败 {summary.get('failed', 0)}，无话题 {summary.get('no_topics', 0)}"
    )


def _stock_topic_batch_running_message(stock_count: int) -> str:
    return f"开始批量个股话题分析，共 {stock_count} 只股票..."


def run_stock_question_task(task_id: str, group_id: str, request: StockQuestionTaskRequest) -> None:
    def work() -> dict[str, Any]:
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


def run_stock_topic_analysis_task(task_id: str, group_id: str, request: StockTopicAnalysisTaskRequest) -> None:
    def work() -> dict[str, Any]:
        log_callback = _build_stock_topic_log_callback(task_id)
        log_callback(f"🔎 股票名称: {request.stock_name}")
        return analyze_stock_topics(group_id, request.stock_name, log_callback=log_callback)

    run_workflow(
        task_id,
        running_message="开始个股话题分析...",
        completed_message="个股话题分析完成",
        failure_label="个股话题分析",
        work=work,
    )


def run_stock_topic_analysis_batch_task(
    task_id: str,
    group_id: str,
    request: StockTopicAnalysisBatchTaskRequest,
) -> None:
    workflow_state: dict[str, Any] = {}

    def running_message() -> str:
        log_callback = _build_stock_topic_log_callback(task_id)
        stock_names = parse_stock_names(request.stock_names)
        workflow_state["log_callback"] = log_callback
        workflow_state["stock_names"] = stock_names
        return _stock_topic_batch_running_message(len(stock_names))

    def work() -> dict[str, Any]:
        return analyze_stock_topics_batch(
            group_id,
            workflow_state["stock_names"],
            log_callback=workflow_state["log_callback"],
        )

    run_workflow(
        task_id,
        running_message=running_message,
        completed_message=_stock_topic_batch_completed_message,
        failure_label="个股话题分析",
        work=work,
    )


def create_stock_question_task(group_id: str, question: str) -> dict[str, str]:
    if not question.strip():
        raise ValueError("question 不能为空")
    request = StockQuestionTaskRequest(question=question)
    return _create_stock_task_response(
        "stock_question_analysis",
        f"A股问答 (群组: {group_id})",
        {"group_id": str(group_id), "question": question},
        run_stock_question_task,
        group_id,
        request,
    )


def create_stock_topic_task(group_id: str, stock_name: str) -> dict[str, str]:
    if not stock_name.strip():
        raise ValueError("stock_name 不能为空")
    request = StockTopicAnalysisTaskRequest(stock_name=stock_name)
    return _create_stock_task_response(
        "stock_topic_analysis",
        f"个股话题分析 (群组: {group_id}, 股票: {stock_name})",
        {"group_id": str(group_id), "stock_name": stock_name},
        run_stock_topic_analysis_task,
        group_id,
        request,
    )


def create_stock_topic_batch_task(group_id: str, stock_names: Any) -> dict[str, str]:
    normalized_stock_names = parse_stock_names(stock_names)
    if not normalized_stock_names:
        raise ValueError("stock_names 不能为空")
    request = StockTopicAnalysisBatchTaskRequest(stock_names=normalized_stock_names)
    return _create_stock_task_response(
        "stock_topic_analysis_batch",
        f"批量个股话题分析 (群组: {group_id}, 股票数: {len(normalized_stock_names)})",
        {"group_id": str(group_id), "stock_names": normalized_stock_names},
        run_stock_topic_analysis_batch_task,
        group_id,
        request,
    )
