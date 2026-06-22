from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def clean_postgres_text(value: Any) -> str:
    return str(value or "").replace("\x00", "")


def normalize_group_id(group_id: Optional[str]) -> str:
    return clean_postgres_text(group_id).strip()


def build_topic_stock_extraction_rows(
    extractions: Sequence[Dict[str, Any]],
    group_id: Optional[str],
    now: datetime,
) -> List[Tuple[str, str, str, str, str, str, str, str, str, float, str, str, datetime]]:
    normalized_group_id = normalize_group_id(group_id)
    rows: List[Tuple[str, str, str, str, str, str, str, str, str, float, str, str, datetime]] = []
    for item in extractions:
        stock_name = clean_postgres_text(item.get("stock_name")).strip()
        topic_id = clean_postgres_text(item.get("topic_id")).strip()
        topic_date = clean_postgres_text(item.get("topic_date") or item.get("day")).strip()
        if not stock_name or not topic_id or not topic_date:
            continue
        rows.append(
            (
                clean_postgres_text(item.get("group_id") or normalized_group_id),
                topic_id,
                topic_date,
                stock_name,
                clean_postgres_text(item.get("stock_code")),
                clean_postgres_text(item.get("market")),
                clean_postgres_text(json.dumps(list(item.get("concepts") or []), ensure_ascii=False)),
                clean_postgres_text(item.get("excerpt")),
                clean_postgres_text(item.get("reason")),
                float(item.get("confidence") or 0),
                clean_postgres_text(item.get("model")),
                clean_postgres_text(item.get("prompt_version")),
                now,
            )
        )
    return rows


def parse_state_key(key: str) -> Optional[Tuple[str, str, str]]:
    parts = str(key or "").split(":")
    if len(parts) < 3:
        return None
    source = clean_postgres_text(parts[0]).strip()
    topic_id = clean_postgres_text(parts[1]).strip()
    day = clean_postgres_text(parts[-1]).strip()
    if not source or not topic_id or len(day) != 10:
        return None
    return source, topic_id, day


def build_processed_state_rows(
    processed_keys: Iterable[str],
    group_id: Optional[str],
    now: datetime,
) -> List[Tuple[str, str, str, str, datetime]]:
    normalized_group_id = normalize_group_id(group_id)
    rows: List[Tuple[str, str, str, str, datetime]] = []
    for key in sorted(set(processed_keys or [])):
        parsed = parse_state_key(key)
        if parsed is None:
            continue
        source, topic_id, day = parsed
        rows.append((normalized_group_id, source, topic_id, day, now))
    return rows
