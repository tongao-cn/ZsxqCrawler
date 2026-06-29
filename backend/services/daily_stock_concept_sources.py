"""Source resolution for daily stock concept extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.core.ai_provider_config import (
    get_extraction_reasoning_effort,
    get_openai_compatible_config,
)
from backend.services.ai_runtime_request import call_structured_ai_object
from backend.services.daily_stock_concept_payload import (
    aggregate_topic_stock_extractions,
    parse_stock_concept_payload,
)
from backend.services.topic_stock_evidence_store import load_topic_stock_extractions


LogCallback = Optional[Callable[[str], None]]

STOCK_CONCEPT_PROMPT_VERSION = "daily-stock-concepts-v1"
STOCK_CONCEPT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "stock_name": {"type": "string"},
                    "stock_code": {"type": "string"},
                    "market": {"type": "string"},
                    "concepts": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "topic_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "stock_name",
                    "stock_code",
                    "market",
                    "concepts",
                    "reason",
                    "topic_ids",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["stocks"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class DailyStockConceptResolution:
    stocks: List[Dict[str, Any]]
    model: str
    source: str


def _log(log_callback: LogCallback, message: str) -> None:
    if log_callback:
        log_callback(message)


def generate_stock_concepts_with_ai(prompt_payload: str, report_date: str) -> Tuple[List[Dict[str, Any]], str]:
    messages = [
        {
            "role": "system",
            "content": (
                "你是A股股票和投资概念提取助手。"
                "只基于用户提供的知识星球话题数据提取，不要编造未出现的信息。"
                "如果无法判断为A股上市公司，就不要输出。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请从 {report_date} 的话题数据中提取明确提到的A股股票及对应概念。\n"
                "要求：\n"
                "1. 只输出明确提到或可从上下文明确映射到A股上市公司的股票。\n"
                "2. 概念必须来自上下文，例如固态电池、机器人、算力、低空经济等。\n"
                "3. topic_ids 使用输入中的 topic_id，方便回溯。\n"
                "4. 不确定时降低 confidence；不要猜股票代码。\n"
                "5. 输出必须符合 JSON schema。\n\n"
                f"话题数据：\n{prompt_payload}"
            ),
        },
    ]

    result = call_structured_ai_object(
        messages=messages,
        get_ai_config=get_openai_compatible_config,
        schema_name="daily_stock_concepts",
        schema=STOCK_CONCEPT_SCHEMA,
        label="AI 股票概念抽取结果",
        reasoning_effort=get_extraction_reasoning_effort(),
    )

    stocks = parse_stock_concept_payload(result.payload)
    return stocks, result.model


def resolve_daily_stock_concepts(
    *,
    group_id: str,
    report_date: str,
    prompt_payload: str,
    log_callback: LogCallback = None,
) -> DailyStockConceptResolution:
    try:
        topic_extractions = load_topic_stock_extractions(
            group_id=group_id,
            start_date=report_date,
            end_date=report_date,
        )
    except Exception as exc:
        topic_extractions = []
        _log(log_callback, f"⚠️ 读取话题级A股明细失败，将回退按天 AI 提取: {exc}")

    if topic_extractions:
        _log(log_callback, f"🧩 使用话题级A股抽取明细聚合股票概念: {len(topic_extractions)} 条")
        model_values = [str(item.get("model") or "") for item in topic_extractions if item.get("model")]
        return DailyStockConceptResolution(
            stocks=aggregate_topic_stock_extractions(topic_extractions),
            model=model_values[0] if model_values else "",
            source="topic_stock_extractions",
        )

    _log(log_callback, "🤖 未找到话题级明细，回退为按天 AI 提取股票概念...")
    stocks, model = generate_stock_concepts_with_ai(prompt_payload, report_date)
    return DailyStockConceptResolution(
        stocks=stocks,
        model=model,
        source="ai_fallback",
    )
