"""A-share research dataset aggregation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


DEFAULT_RESEARCH_DATASET_FIELDS = [
    "group_id",
    "signal_date",
    "stock_name",
    "stock_code",
    "market",
    "mention_count",
    "topic_count",
    "topic_ids",
    "concepts",
    "avg_confidence",
    "max_confidence",
    "likes_count",
    "comments_count",
    "reading_count",
    "topic_titles",
    "reasons",
]


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_group_id(group_id: Any) -> str:
    return _normalize_text(group_id)


def company_key(value: Any) -> str:
    return (
        _normalize_text(value)
        .replace(" ", "")
        .replace("*", "")
        .replace("股份有限公司", "")
        .replace("有限责任公司", "")
        .replace("有限公司", "")
        .replace("集团", "")
    )


def _parse_day(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD 格式") from exc


def validate_date_range(start_date: Optional[str], end_date: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    start_day = _parse_day(start_date, "start_date")
    end_day = _parse_day(end_date, "end_date")
    if start_day and end_day and start_day > end_day:
        raise ValueError("start_date 不能晚于 end_date")
    return start_day, end_day


def parse_json_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        try:
            raw_items = json.loads(value)
        except Exception:
            return []
    if not isinstance(raw_items, list):
        return []
    return [_normalize_text(item) for item in raw_items if _normalize_text(item)]


def ordered_unique(values: Iterable[Any], *, limit: int = 200) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = _normalize_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
        if len(result) >= limit:
            break
    return result


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def mention_key(signal_date: Any, company: Any) -> Tuple[str, str]:
    return (_normalize_text(signal_date), company_key(company))


def build_research_dataset(
    topic_rows: Iterable[Mapping[str, Any]],
    mention_counts: Mapping[Tuple[str, str], int] | None = None,
) -> List[Dict[str, Any]]:
    mentions = mention_counts or {}
    grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    seen_topics: Dict[Tuple[str, str, str], set[str]] = {}
    confidence_values: Dict[Tuple[str, str, str], List[float]] = {}

    for raw in topic_rows:
        group_id = normalize_group_id(raw.get("group_id"))
        signal_date = _normalize_text(raw.get("signal_date") or raw.get("topic_date"))
        stock_name = _normalize_text(raw.get("stock_name"))
        if not group_id or not signal_date or not stock_name:
            continue

        key = (group_id, signal_date, stock_name)
        item = grouped.setdefault(
            key,
            {
                "group_id": group_id,
                "signal_date": signal_date,
                "stock_name": stock_name,
                "stock_code": "",
                "market": "",
                "mention_count": int(mentions.get(mention_key(signal_date, stock_name), 0)),
                "topic_count": 0,
                "topic_ids": [],
                "concepts": [],
                "avg_confidence": 0.0,
                "max_confidence": 0.0,
                "likes_count": 0,
                "comments_count": 0,
                "reading_count": 0,
                "topic_titles": [],
                "reasons": [],
            },
        )
        if not item["stock_code"]:
            item["stock_code"] = _normalize_text(raw.get("stock_code"))
        if not item["market"]:
            item["market"] = _normalize_text(raw.get("market")).upper()

        topic_id = _normalize_text(raw.get("topic_id"))
        topic_seen = seen_topics.setdefault(key, set())
        if topic_id and topic_id not in topic_seen:
            topic_seen.add(topic_id)
            item["topic_count"] += 1
            item["topic_ids"] = ordered_unique([*item["topic_ids"], topic_id])
            item["likes_count"] += safe_int(raw.get("likes_count"))
            item["comments_count"] += safe_int(raw.get("comments_count"))
            item["reading_count"] += safe_int(raw.get("reading_count"))

        item["concepts"] = ordered_unique([*item["concepts"], *parse_json_list(raw.get("concepts"))])
        item["topic_titles"] = ordered_unique([*item["topic_titles"], raw.get("title")], limit=50)
        item["reasons"] = ordered_unique([*item["reasons"], raw.get("reason")], limit=50)

        confidence = safe_float(raw.get("confidence"))
        confidence_values.setdefault(key, []).append(confidence)
        item["max_confidence"] = max(float(item["max_confidence"]), confidence)

    for key, values in confidence_values.items():
        grouped[key]["avg_confidence"] = round(sum(values) / len(values), 4) if values else 0.0
        grouped[key]["max_confidence"] = round(float(grouped[key]["max_confidence"]), 4)

    return sorted(grouped.values(), key=lambda item: (item["signal_date"], item["stock_name"]))
