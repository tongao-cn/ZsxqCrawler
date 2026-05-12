"""Read-only A-share research dataset export helpers."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from backend.services.a_share_analysis_db_storage import (
    DAILY_MENTIONS_TABLE,
    TOPIC_STOCK_EXTRACTIONS_TABLE,
    get_connection,
)
from backend.storage.postgres_core_schema import CORE_SCHEMA, quote_identifier


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


def _core_table_ref(table_name: str) -> str:
    return f"{quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)}"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_group_id(group_id: Any) -> str:
    return _normalize_text(group_id)


def _company_key(value: Any) -> str:
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


def _parse_json_list(value: Any) -> List[str]:
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


def _ordered_unique(values: Iterable[Any], *, limit: int = 200) -> List[str]:
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


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _mention_key(signal_date: Any, company: Any) -> Tuple[str, str]:
    return (_normalize_text(signal_date), _company_key(company))


def _load_mention_counts(group_id: str, start_date: Optional[str], end_date: Optional[str]) -> Dict[Tuple[str, str], int]:
    conditions = ["group_id = %s"]
    params: List[Any] = [group_id]
    if start_date:
        conditions.append("mention_date >= %s::date")
        params.append(start_date)
    if end_date:
        conditions.append("mention_date <= %s::date")
        params.append(end_date)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT mention_date::text, company, SUM(mentions_count)
                FROM {_core_table_ref(DAILY_MENTIONS_TABLE)}
                WHERE {" AND ".join(conditions)}
                GROUP BY mention_date, company
                """,
                params,
            )
            return {
                _mention_key(day, company): _safe_int(count)
                for day, company, count in cur.fetchall()
            }


def _load_topic_signal_rows(group_id: str, start_date: Optional[str], end_date: Optional[str]) -> List[Dict[str, Any]]:
    conditions = ["e.group_id = %s"]
    params: List[Any] = [group_id]
    if start_date:
        conditions.append("e.topic_date >= %s::date")
        params.append(start_date)
    if end_date:
        conditions.append("e.topic_date <= %s::date")
        params.append(end_date)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    e.group_id,
                    e.topic_date::text AS signal_date,
                    e.topic_id,
                    e.stock_name,
                    e.stock_code,
                    e.market,
                    e.concepts_json,
                    e.reason,
                    e.confidence,
                    t.title,
                    t.create_time,
                    t.likes_count,
                    t.comments_count,
                    t.reading_count
                FROM {_core_table_ref(TOPIC_STOCK_EXTRACTIONS_TABLE)} e
                LEFT JOIN {_core_table_ref("topics")} t
                  ON t.group_id::text = e.group_id
                 AND t.topic_id::text = e.topic_id
                WHERE {" AND ".join(conditions)}
                ORDER BY e.topic_date ASC, e.stock_name ASC, e.topic_id ASC
                """,
                params,
            )
            return [
                {
                    "group_id": _normalize_text(row[0]),
                    "signal_date": _normalize_text(row[1]),
                    "topic_id": _normalize_text(row[2]),
                    "stock_name": _normalize_text(row[3]),
                    "stock_code": _normalize_text(row[4]),
                    "market": _normalize_text(row[5]).upper(),
                    "concepts": _parse_json_list(row[6]),
                    "reason": _normalize_text(row[7]),
                    "confidence": _safe_float(row[8]),
                    "title": _normalize_text(row[9]),
                    "create_time": _normalize_text(row[10]),
                    "likes_count": _safe_int(row[11]),
                    "comments_count": _safe_int(row[12]),
                    "reading_count": _safe_int(row[13]),
                }
                for row in cur.fetchall()
                if _normalize_text(row[1]) and _normalize_text(row[3])
            ]


def build_research_dataset(
    topic_rows: Iterable[Mapping[str, Any]],
    mention_counts: Mapping[Tuple[str, str], int] | None = None,
) -> List[Dict[str, Any]]:
    mentions = mention_counts or {}
    grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    seen_topics: Dict[Tuple[str, str, str], set[str]] = {}
    confidence_values: Dict[Tuple[str, str, str], List[float]] = {}

    for raw in topic_rows:
        group_id = _normalize_group_id(raw.get("group_id"))
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
                "mention_count": int(mentions.get(_mention_key(signal_date, stock_name), 0)),
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
            item["topic_ids"] = _ordered_unique([*item["topic_ids"], topic_id])
            item["likes_count"] += _safe_int(raw.get("likes_count"))
            item["comments_count"] += _safe_int(raw.get("comments_count"))
            item["reading_count"] += _safe_int(raw.get("reading_count"))

        item["concepts"] = _ordered_unique([*item["concepts"], *_parse_json_list(raw.get("concepts"))])
        item["topic_titles"] = _ordered_unique([*item["topic_titles"], raw.get("title")], limit=50)
        item["reasons"] = _ordered_unique([*item["reasons"], raw.get("reason")], limit=50)

        confidence = _safe_float(raw.get("confidence"))
        confidence_values.setdefault(key, []).append(confidence)
        item["max_confidence"] = max(float(item["max_confidence"]), confidence)

    for key, values in confidence_values.items():
        grouped[key]["avg_confidence"] = round(sum(values) / len(values), 4) if values else 0.0
        grouped[key]["max_confidence"] = round(float(grouped[key]["max_confidence"]), 4)

    return sorted(grouped.values(), key=lambda item: (item["signal_date"], item["stock_name"]))


def load_a_share_research_dataset(
    *,
    group_id: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    normalized_group_id = _normalize_group_id(group_id)
    if not normalized_group_id:
        raise ValueError("group_id 不能为空")

    start_day, end_day = validate_date_range(start_date, end_date)
    topic_rows = _load_topic_signal_rows(normalized_group_id, start_day, end_day)
    mention_counts = _load_mention_counts(normalized_group_id, start_day, end_day)
    return build_research_dataset(topic_rows, mention_counts)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    return value


def write_a_share_research_dataset_csv(
    rows: Iterable[Mapping[str, Any]],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DEFAULT_RESEARCH_DATASET_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in DEFAULT_RESEARCH_DATASET_FIELDS})
    return path


__all__ = [
    "DEFAULT_RESEARCH_DATASET_FIELDS",
    "build_research_dataset",
    "load_a_share_research_dataset",
    "validate_date_range",
    "write_a_share_research_dataset_csv",
]
