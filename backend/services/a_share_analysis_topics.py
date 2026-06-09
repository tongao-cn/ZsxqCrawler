from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


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
    connect_func: Callable[[], Any],
    debug_logger: Callable[[str], None],
    emit_log: Callable[[str, LogCallback], None],
    log_callback: LogCallback = None,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    normalized_group_id = str(group_id or "").strip()
    query_group_id: Any = int(normalized_group_id) if normalized_group_id.isdigit() else normalized_group_id

    conn = connect_func()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT t.topic_id, t.title, t.create_time FROM topics t WHERE t.group_id = ?",
            (query_group_id,),
        )
        rows = cur.fetchall()
        debug_logger(f"loaded topics rows: {len(rows)} from zsxq_core for group {normalized_group_id}")

        filtered_rows = []
        for topic_id, title, create_time in rows:
            dt = parse_time(create_time)
            if not dt or dt < start or dt > end:
                continue
            filtered_rows.append((topic_id, title, create_time, dt))

        talk_texts: Dict[Any, str] = {}
        topic_ids = [topic_id for topic_id, _, _, _ in filtered_rows]
        if topic_ids:
            try:
                placeholders = ", ".join("?" for _ in topic_ids)
                cur.execute(
                    f"SELECT topic_id, text FROM talks WHERE topic_id IN ({placeholders})",
                    tuple(topic_ids),
                )
                for topic_id, text in cur.fetchall():
                    talk_texts[topic_id] = text or ""
            except Exception:
                pass
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
    finally:
        conn.close()

    emit_log(
        f"filtered topics items: {len(items)} for {range_label} in group {normalized_group_id}",
        log_callback,
    )
    return items
