from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from backend.services.a_share_analysis_source_store import load_source_talk_texts, load_source_topic_rows


LogCallback = Optional[Callable[[str], None]]


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    formats = (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo:
                return dt.astimezone().replace(tzinfo=None)
            return dt.replace(tzinfo=None)
        except Exception:
            continue
    try:
        if value.endswith("+0800"):
            base = value[:-5]
            return datetime.strptime(base, "%Y-%m-%dT%H:%M:%S.%f")
    except Exception:
        pass
    return None


def normalize_day(dt: datetime) -> str:
    if dt.tzinfo:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d")


def read_topics_in_time_range(
    group_id: str,
    start: datetime,
    end: datetime,
    range_label: str,
    *,
    debug_logger: Callable[[str], None],
    emit_log: Callable[[str, LogCallback], None],
    log_callback: LogCallback = None,
    topic_rows_loader: Optional[Callable[[str], List[Any]]] = None,
    talk_texts_loader: Optional[Callable[[List[Any]], Dict[Any, str]]] = None,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    normalized_group_id = str(group_id or "").strip()
    topic_rows_loader = topic_rows_loader or load_source_topic_rows
    talk_texts_loader = talk_texts_loader or load_source_talk_texts

    rows = topic_rows_loader(normalized_group_id)
    debug_logger(f"loaded topics rows: {len(rows)} from zsxq_core for group {normalized_group_id}")

    filtered_rows = []
    for topic_id, title, create_time in rows:
        dt = parse_time(create_time)
        if not dt or dt < start or dt > end:
            continue
        filtered_rows.append((topic_id, title, create_time, dt))

    topic_ids = [topic_id for topic_id, _, _, _ in filtered_rows]
    try:
        talk_texts = talk_texts_loader(topic_ids) if topic_ids else {}
    except Exception:
        talk_texts = {}
    debug_logger(f"loaded talks texts: {len(talk_texts)} for group {normalized_group_id}")

    for topic_id, title, create_time, dt in filtered_rows:
        text = talk_texts.get(topic_id) or (title or "")
        if not text:
            continue
        items.append(
            {
                "topic_id": topic_id,
                "title": title or "",
                "text": text,
                "create_time": create_time,
                "day": normalize_day(dt),
                "source": "topics",
                "group_id": normalized_group_id,
            }
        )

    emit_log(
        f"filtered topics items: {len(items)} for {range_label} in group {normalized_group_id}",
        log_callback,
    )
    return items
