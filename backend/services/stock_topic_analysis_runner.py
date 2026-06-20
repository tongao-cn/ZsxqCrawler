"""Runner interface for stock topic analysis workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Protocol


LogCallback = Callable[[str], None] | None


@dataclass(frozen=True)
class AnalyzeStockTopicsRequest:
    group_id: str
    stock_name: str
    limit: int | None = None
    log_callback: LogCallback = None


@dataclass(frozen=True)
class AnalyzeStockTopicsBatchRequest:
    group_id: str
    stock_names: Any
    log_callback: LogCallback = None
    max_stocks: int | None = None


@dataclass(frozen=True)
class AnswerStockQuestionRequest:
    group_id: str
    question: str
    log_callback: LogCallback = None


class StockTopicAnalysisOperations(Protocol):
    def analyze_stock_topics(self, request: AnalyzeStockTopicsRequest) -> Dict[str, Any]:
        ...

    def analyze_stock_topics_batch(self, request: AnalyzeStockTopicsBatchRequest) -> Dict[str, Any]:
        ...

    def answer_stock_question(self, request: AnswerStockQuestionRequest) -> Dict[str, Any]:
        ...


def analyze_stock_topics(
    operations: StockTopicAnalysisOperations,
    request: AnalyzeStockTopicsRequest,
) -> Dict[str, Any]:
    return operations.analyze_stock_topics(request)


def analyze_stock_topics_batch(
    operations: StockTopicAnalysisOperations,
    request: AnalyzeStockTopicsBatchRequest,
) -> Dict[str, Any]:
    return operations.analyze_stock_topics_batch(request)


def answer_stock_question(
    operations: StockTopicAnalysisOperations,
    request: AnswerStockQuestionRequest,
) -> Dict[str, Any]:
    return operations.answer_stock_question(request)
