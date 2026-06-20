from __future__ import annotations

from typing import Any, Dict, Iterable, List

from backend.storage.db_compat import connect


def _query_group_id(group_id: str) -> Any:
    normalized = str(group_id or "").strip()
    return int(normalized) if normalized.isdigit() else normalized


def source_topic_rows_query(group_id: str) -> tuple[str, tuple[Any, ...]]:
    return (
        "SELECT t.topic_id, t.title, t.create_time FROM topics t WHERE t.group_id = ?",
        (_query_group_id(group_id),),
    )


def source_talk_rows_query(topic_ids: Iterable[Any]) -> tuple[str, tuple[Any, ...]]:
    ids = tuple(topic_ids)
    placeholders = ", ".join("?" for _ in ids)
    return (
        f"SELECT topic_id, text FROM talks WHERE topic_id IN ({placeholders})",
        ids,
    )


def source_topics_summary_query(group_id: str) -> tuple[str, tuple[Any, ...]]:
    return (
        "SELECT COUNT(*), MIN(create_time), MAX(create_time) FROM topics WHERE group_id = ?",
        (_query_group_id(group_id),),
    )


def load_source_topic_rows(group_id: str) -> List[Any]:
    conn = connect()
    try:
        cur = conn.cursor()
        sql, params = source_topic_rows_query(group_id)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def load_source_talk_texts(topic_ids: Iterable[Any]) -> Dict[Any, str]:
    ids = tuple(topic_ids)
    if not ids:
        return {}

    conn = connect()
    try:
        cur = conn.cursor()
        sql, params = source_talk_rows_query(ids)
        cur.execute(sql, params)
        return {topic_id: text or "" for topic_id, text in cur.fetchall()}
    finally:
        conn.close()


def load_source_topics_summary(group_id: str) -> Dict[str, Any]:
    conn = connect()
    try:
        cur = conn.cursor()
        sql, params = source_topics_summary_query(group_id)
        cur.execute(sql, params)
        row = cur.fetchone()
    finally:
        conn.close()

    topics_count, oldest_topic_time, latest_topic_time = row or (0, None, None)
    return {
        "topics_db_exists": True,
        "topics_count": int(topics_count or 0),
        "oldest_topic_time": oldest_topic_time,
        "latest_topic_time": latest_topic_time,
    }
