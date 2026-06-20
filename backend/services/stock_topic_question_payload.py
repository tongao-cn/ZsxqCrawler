"""Database loader for stock question topic payloads."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.services.stock_topic_analysis_payloads import build_question_topic_payload
from backend.storage.db_compat import connect


def load_question_topic_payload(
    search_result: Dict[str, Any],
    *,
    max_analysis_topics: int,
    max_topic_text_chars: int,
) -> List[Dict[str, Any]]:
    topic_ids = [str(topic.get("topic_id") or "") for topic in search_result.get("topics", [])[:max_analysis_topics]]
    if not topic_ids:
        return []

    conn = connect()
    try:
        placeholders = ",".join("?" for _ in topic_ids)
        rows = conn.execute(
            f"""
            SELECT
                t.topic_id,
                t.title,
                t.create_time,
                t.likes_count,
                t.comments_count,
                t.reading_count,
                tk.text AS talk_text,
                q.text AS question_text,
                a.text AS answer_text
            FROM topics t
            LEFT JOIN talks tk ON t.topic_id = tk.topic_id
            LEFT JOIN questions q ON t.topic_id = q.topic_id
            LEFT JOIN answers a ON t.topic_id = a.topic_id
            WHERE t.group_id::text = ?
              AND t.topic_id::text IN ({placeholders})
            ORDER BY t.create_time DESC
            """,
            [search_result["group_id"], *topic_ids],
        ).fetchall()
    finally:
        conn.close()

    return build_question_topic_payload(
        rows,
        keywords=list(search_result.get("keywords") or []),
        max_topic_text_chars=max_topic_text_chars,
    )
