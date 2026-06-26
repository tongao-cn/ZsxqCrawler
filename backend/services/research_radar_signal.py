from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List


CATALYST_TERMS = (
    "涨价/供需",
    "国产替代/自主可控",
    "出海/出口",
    "订单/扩产",
    "政策",
    "业绩",
    "并购",
    "供需紧张",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = _text(item)
        if text and text not in result:
            result.append(text)
    return result


def _topic_key(value: Any) -> str:
    return _text(value)


def _topic_text(topic: Dict[str, Any]) -> str:
    parts = [
        _text(topic.get("title")),
        _text(topic.get("talk_text")),
        _text(topic.get("question_text")),
        _text(topic.get("answer_text")),
    ]
    for comment in topic.get("comments") or []:
        if isinstance(comment, dict):
            parts.append(_text(comment.get("text")))
    return "\n".join(part for part in parts if part)


def _clip(value: str, limit: int = 260) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _row_concepts(row: Dict[str, Any]) -> List[str]:
    return _text_list(row.get("concepts"))


def _row_catalysts(row: Dict[str, Any]) -> List[str]:
    concepts = _row_concepts(row)
    reason = _text(row.get("reason"))
    catalysts = [concept for concept in concepts if concept in CATALYST_TERMS]
    for term in CATALYST_TERMS:
        if term not in catalysts and term.replace("/", "") in reason.replace("/", ""):
            catalysts.append(term)
    return catalysts


def _canonical_catalysts(catalysts: List[str]) -> List[str]:
    return [term for term in CATALYST_TERMS if term in catalysts]


def _row_directions(row: Dict[str, Any]) -> List[str]:
    return [concept for concept in _row_concepts(row) if concept not in CATALYST_TERMS]


def _stock_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": _text(row.get("stock_name")),
        "code": _text(row.get("stock_code")),
        "market": _text(row.get("market")),
        "confidence": float(row.get("confidence") or 0),
    }


def _baseline_directions(rows: Iterable[Dict[str, Any]]) -> set[str]:
    directions: set[str] = set()
    for row in rows:
        directions.update(_row_directions(row))
    return directions


def _evidence_for_topic(topic: Dict[str, Any], row: Dict[str, Any], direction: str) -> Dict[str, Any]:
    topic_id = _topic_key(topic.get("topic_id") or row.get("topic_id"))
    return {
        "source_type": "topic",
        "source_id": topic_id,
        "topic_id": topic_id,
        "source_time": _text(topic.get("create_time")),
        "excerpt": _clip(_topic_text(topic) or _text(row.get("excerpt")) or _text(row.get("reason"))),
        "matched_entities": {
            "direction": direction,
            "concepts": _row_concepts(row),
            "stock_name": _text(row.get("stock_name")),
        },
        "support_reason": _text(row.get("reason")) or f"话题提到{direction}相关股票。",
        "navigation": {"type": "topic", "topic_id": topic_id},
    }


def _confidence(topic_count: int, stock_count: int, catalyst_count: int, is_new: bool, row_confidence: float) -> float:
    score = 0.12 + min(topic_count, 4) * 0.07 + min(stock_count, 4) * 0.05 + min(catalyst_count, 3) * 0.04
    if is_new:
        score += 0.03
    score += min(max(row_confidence, 0), 1) * 0.5
    return round(min(score, 0.99), 3)


def _tier(confidence: float, evidence_count: int, stock_count: int) -> str:
    if confidence >= 0.75 and (evidence_count >= 2 or stock_count >= 2):
        return "strong"
    if confidence >= 0.58 and evidence_count >= 1:
        return "medium"
    return "weak"


def build_research_radar_candidates(
    *,
    topics: List[Dict[str, Any]],
    current_stock_rows: List[Dict[str, Any]],
    baseline_stock_rows: List[Dict[str, Any]],
    max_candidates: int = 8,
) -> List[Dict[str, Any]]:
    if not current_stock_rows:
        return []

    topics_by_id = {_topic_key(topic.get("topic_id")): topic for topic in topics}
    baseline = _baseline_directions(baseline_stock_rows)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in current_stock_rows:
        for direction in _row_directions(row):
            grouped[direction].append(row)

    candidates: List[Dict[str, Any]] = []
    for direction, rows in grouped.items():
        topic_ids = sorted({_topic_key(row.get("topic_id")) for row in rows if _topic_key(row.get("topic_id"))})
        stocks_by_name: Dict[str, Dict[str, Any]] = {}
        catalysts: List[str] = []
        evidence: List[Dict[str, Any]] = []
        max_row_confidence = 0.0
        for row in rows:
            stock = _stock_payload(row)
            if stock["name"] and stock["name"] not in stocks_by_name:
                stocks_by_name[stock["name"]] = stock
            for catalyst in _row_catalysts(row):
                if catalyst not in catalysts:
                    catalysts.append(catalyst)
            max_row_confidence = max(max_row_confidence, float(row.get("confidence") or 0))
            topic_id = _topic_key(row.get("topic_id"))
            topic = topics_by_id.get(topic_id)
            if topic and topic_id not in {item["topic_id"] for item in evidence}:
                evidence.append(_evidence_for_topic(topic, row, direction))

        if not evidence:
            continue

        catalysts = _canonical_catalysts(catalysts)
        confidence = _confidence(
            len(topic_ids),
            len(stocks_by_name),
            len(catalysts),
            direction not in baseline,
            max_row_confidence,
        )
        candidates.append(
            {
                "candidate_id": f"direction:{direction}",
                "direction": direction,
                "title": f"{direction}研究信号升温",
                "summary": f"{direction}在当前窗口出现研究信号，关联{len(stocks_by_name)}只股票和{len(evidence)}条证据。",
                "tier": _tier(confidence, len(evidence), len(stocks_by_name)),
                "confidence": confidence,
                "concepts": [direction],
                "stocks": list(stocks_by_name.values()),
                "catalysts": catalysts,
                "risks": [],
                "evidence": evidence,
                "evidence_count": len(evidence),
            }
        )

    tier_order = {"strong": 0, "medium": 1, "weak": 2}
    return sorted(
        candidates,
        key=lambda item: (tier_order.get(str(item["tier"]), 9), -float(item["confidence"]), str(item["direction"])),
    )[:max_candidates]
