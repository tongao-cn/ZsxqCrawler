"""Extract A-share stock names from uploaded image data."""

from __future__ import annotations

from typing import Any, Dict

from backend.core.ai_provider_config import (
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.services.ai_runtime_request import (
    AIRuntimeStructuredObjectParseError,
    call_structured_ai_object,
)
from backend.services.stock_topic_analysis_ai_prompts import build_image_stock_extraction_input
from backend.services.stock_topic_analysis_helpers import parse_stock_names
from backend.services.stock_topic_image_input import parse_image_data_url


IMAGE_STOCK_NAME_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "stockNames": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["stockNames"],
    "additionalProperties": False,
}


def extract_stock_names_from_image(image_data_url: str) -> Dict[str, Any]:
    mime_type, normalized_data_url, image_bytes = parse_image_data_url(image_data_url)
    prompt = (
        "请从这张图片中提取出现的 A 股股票名称。"
        "只输出符合 schema 的 JSON，不要 Markdown，不要解释。"
        "如果识别到股票，JSON 结构为 {\"stockNames\": [\"股票名1\", \"股票名2\"]}。"
        "如果图片中没有明确股票名称，stockNames 返回空数组。"
        "要求：保留图片里的股票中文简称，去重，最多 50 个。"
    )

    try:
        result = call_structured_ai_object(
            build_image_stock_extraction_input(prompt, normalized_data_url),
            schema_name="stock_image_name_extraction",
            schema=IMAGE_STOCK_NAME_EXTRACTION_SCHEMA,
            label="AI 图片股票抽取结果",
            get_ai_config=get_openai_compatible_config,
            wire_api="responses",
            reasoning_effort=get_summary_reasoning_effort(),
        )
    except AIRuntimeStructuredObjectParseError as exc:
        raise ValueError("AI 图片股票抽取结果不是合法 JSON") from exc

    stock_names = parse_stock_names(result.payload.get("stockNames") or result.payload.get("stock_names") or [])
    if not stock_names:
        raise ValueError("图片里没有识别到明确股票名称")
    return {
        "stockNames": stock_names,
        "model": result.model,
        "mime_type": mime_type,
        "image_bytes": len(image_bytes),
    }
