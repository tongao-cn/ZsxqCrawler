"""Extract search keywords from stock-related natural-language questions."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from backend.core.ai_provider_config import (
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.services.ai_runtime_request import (
    AIRuntimeStructuredObjectParseError,
    call_structured_ai_object,
)
from backend.services.stock_topic_analysis_ai_prompts import build_question_keyword_messages
from backend.services.stock_topic_analysis_helpers import _normalize_text, _ordered_unique


MAX_QUESTION_KEYWORDS = 8

QUESTION_KEYWORD_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["keywords"],
    "additionalProperties": False,
}


def normalize_question_keywords(values: Any, *, limit: int = MAX_QUESTION_KEYWORDS) -> List[str]:
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, Iterable):
        raw_values = list(values)
    else:
        raw_values = []
    return _ordered_unique(
        (_normalize_text(value) for value in raw_values),
        limit=max(1, min(limit, MAX_QUESTION_KEYWORDS)),
    )


def extract_question_keywords(question: str) -> Tuple[List[str], str]:
    messages = build_question_keyword_messages(question)
    try:
        result = call_structured_ai_object(
            messages,
            schema_name="stock_question_keyword_extraction",
            schema=QUESTION_KEYWORD_EXTRACTION_SCHEMA,
            label="AI 问题关键词抽取结果",
            get_ai_config=get_openai_compatible_config,
            wire_api="responses",
            reasoning_effort=get_summary_reasoning_effort(),
        )
    except AIRuntimeStructuredObjectParseError as exc:
        raise ValueError("AI 问题关键词抽取结果不是合法 JSON") from exc
    keywords = normalize_question_keywords(result.payload.get("keywords") or result.payload.get("keyword") or [])
    if not keywords:
        raise ValueError("AI 未能从问题中提取检索关键词")
    return keywords, result.model
