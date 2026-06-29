"""AI adapter for stock topic analysis workflows."""

from __future__ import annotations

from typing import Tuple

from backend.core.ai_provider_config import (
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.services.ai_runtime_request import call_runtime_ai_text
from backend.services.stock_topic_analysis_ai_prompts import (
    build_question_analysis_messages,
    build_stock_analysis_messages,
)


def call_stock_analysis_ai(prompt_payload: str, *, incremental: bool = False) -> Tuple[str, str]:
    messages = build_stock_analysis_messages(prompt_payload)
    result = call_runtime_ai_text(
        messages,
        get_ai_config=get_openai_compatible_config,
        wire_api="responses",
        reasoning_effort=get_summary_reasoning_effort(),
    )

    return (
        result.text.strip(),
        result.model,
    )


def call_question_analysis_ai(question: str, prompt_payload: str) -> Tuple[str, str]:
    messages = build_question_analysis_messages(question, prompt_payload)
    result = call_runtime_ai_text(
        messages,
        get_ai_config=get_openai_compatible_config,
        wire_api="responses",
        reasoning_effort=get_summary_reasoning_effort(),
    )

    return (
        result.text.strip(),
        result.model,
    )


__all__ = [
    "call_question_analysis_ai",
    "call_stock_analysis_ai",
]
