"""Read-only A-share research dataset export helpers."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from backend.services.a_share_analysis_db_storage import (
    DAILY_MENTIONS_TABLE,
    TOPIC_STOCK_EXTRACTIONS_TABLE,
    get_connection,
)
from backend.services.a_share_research_dataset import (
    DEFAULT_RESEARCH_DATASET_FIELDS,
    build_research_dataset,
    mention_key as _mention_key,
    normalize_group_id as _normalize_group_id,
    parse_json_list as _parse_json_list,
    safe_float as _safe_float,
    safe_int as _safe_int,
    validate_date_range,
)
from backend.storage.postgres_core_schema import CORE_SCHEMA, quote_identifier


def _core_table_ref(table_name: str) -> str:
    return f"{quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)}"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


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
