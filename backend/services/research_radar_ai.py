from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from backend.core.ai_provider_config import get_openai_compatible_config, get_summary_reasoning_effort
from backend.services.ai_runtime_request import call_structured_ai_object


RESEARCH_RADAR_AI_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "logic_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "candidate_id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["candidate_id", "title", "summary"],
            },
        }
    },
    "required": ["logic_items"],
}


def _text(value: Any, limit: int = 1000) -> str:
    text = str(value or "").strip()
    if limit >= 0 and len(text) > limit:
        return text[:limit].rstrip()
    return text


def _safe_stock_payload(stock: Any) -> Dict[str, Any]:
    if not isinstance(stock, dict):
        return {"name": _text(stock, 120)}
    return {
        "name": _text(stock.get("name"), 120),
        "code": _text(stock.get("code"), 60),
        "market": _text(stock.get("market"), 60),
    }


def _safe_evidence_payload(evidence: Any) -> Dict[str, Any]:
    if not isinstance(evidence, dict):
        return {"excerpt": _text(evidence)}
    return {
        "topic_id": _text(evidence.get("topic_id") or evidence.get("source_id"), 120),
        "source_time": _text(evidence.get("source_time"), 120),
        "excerpt": _text(evidence.get("excerpt")),
        "support_reason": _text(evidence.get("support_reason")),
    }


def _candidate_prompt_payload(candidates: List[Dict[str, Any]]) -> str:
    prompt_candidates: List[Dict[str, Any]] = []
    for candidate in candidates:
        prompt_candidates.append(
            {
                "candidate_id": _text(candidate.get("candidate_id"), 200),
                "direction": _text(candidate.get("direction"), 200),
                "title": _text(candidate.get("title"), 200),
                "summary": _text(candidate.get("summary")),
                "tier": _text(candidate.get("tier"), 60),
                "confidence": candidate.get("confidence"),
                "concepts": [_text(item, 120) for item in candidate.get("concepts") or []],
                "stocks": [_safe_stock_payload(item) for item in candidate.get("stocks") or []],
                "catalysts": [_text(item, 120) for item in candidate.get("catalysts") or []],
                "risks": [_text(item, 200) for item in candidate.get("risks") or []],
                "evidence_count": candidate.get("evidence_count"),
                "evidence": [_safe_evidence_payload(item) for item in candidate.get("evidence") or []],
            }
        )
    return json.dumps(prompt_candidates, ensure_ascii=False)


def apply_ai_logic_summaries(candidates: List[Dict[str, Any]], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = [dict(candidate) for candidate in candidates]
    by_id = {_text(candidate.get("candidate_id")): candidate for candidate in result}
    logic_items = payload.get("logic_items") if isinstance(payload, dict) else None
    if not isinstance(logic_items, list):
        return result

    for item in logic_items:
        if not isinstance(item, dict):
            continue
        candidate = by_id.get(_text(item.get("candidate_id")))
        if candidate is None:
            continue
        title = _text(item.get("title"), 200)
        summary = _text(item.get("summary"))
        if title:
            candidate["title"] = title
        if summary:
            candidate["summary"] = summary
    return result


def summarize_radar_candidates(
    candidates: List[Dict[str, Any]], *, report_date: str
) -> Tuple[List[Dict[str, Any]], str]:
    if not candidates:
        return [], ""

    messages = [
        {
            "role": "system",
            "content": (
                "你是中文 A 股研究雷达写作助手。只改写输入候选的 title 和 summary。"
                "不要新增候选、股票、概念、催化剂、风险或证据。"
                "必须解释证据支持的研究逻辑，不提供买卖建议。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"报告日期：{_text(report_date, 40)}\n"
                "请基于以下候选和证据，为每个 candidate_id 输出更清晰的研究逻辑标题和摘要：\n"
                f"{_candidate_prompt_payload(candidates)}"
            ),
        },
    ]
    result = call_structured_ai_object(
        messages,
        schema_name="research_radar_logic_summaries",
        schema=RESEARCH_RADAR_AI_SCHEMA,
        label="研究雷达 AI 摘要结果",
        get_ai_config=get_openai_compatible_config,
        reasoning_effort=get_summary_reasoning_effort(),
        timeout=180,
    )
    return apply_ai_logic_summaries(candidates, result.payload), result.model
