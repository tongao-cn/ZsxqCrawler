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


class StockTopicAnalysisEngine:
    def __init__(self, operations: StockTopicAnalysisOperations):
        self._operations = operations

    def analyze_stock_topics(
        self,
        group_id: str,
        stock_name: str,
        *,
        limit: int | None = None,
        log_callback: LogCallback = None,
    ) -> Dict[str, Any]:
        return self._operations.analyze_stock_topics(
            AnalyzeStockTopicsRequest(
                group_id=group_id,
                stock_name=stock_name,
                limit=limit,
                log_callback=log_callback,
            )
        )

    def analyze_stock_topics_batch(
        self,
        group_id: str,
        stock_names: Any,
        *,
        log_callback: LogCallback = None,
        max_stocks: int | None = None,
    ) -> Dict[str, Any]:
        return self._operations.analyze_stock_topics_batch(
            AnalyzeStockTopicsBatchRequest(
                group_id=group_id,
                stock_names=stock_names,
                log_callback=log_callback,
                max_stocks=max_stocks,
            )
        )

    def answer_stock_question(
        self,
        group_id: str,
        question: str,
        *,
        log_callback: LogCallback = None,
    ) -> Dict[str, Any]:
        return self._operations.answer_stock_question(
            AnswerStockQuestionRequest(
                group_id=group_id,
                question=question,
                log_callback=log_callback,
            )
        )
