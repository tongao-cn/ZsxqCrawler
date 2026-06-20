"""Database loader for stock question topic payloads."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.services.stock_topic_analysis_payloads import build_question_topic_payload
from backend.services.stock_topic_analysis_store import load_question_topic_rows


def build_question_topic_payload_from_rows(
    search_result: Dict[str, Any],
    rows: List[Any],
    *,
    max_analysis_topics: int,
    max_topic_text_chars: int,
) -> List[Dict[str, Any]]:
    topic_ids = [str(topic.get("topic_id") or "") for topic in search_result.get("topics", [])[:max_analysis_topics]]
    if not topic_ids:
        return []

    allowed_topic_ids = set(topic_ids)
    rows_by_topic_id: Dict[str, Any] = {}
    for row in rows:
        topic_id = str(row["topic_id"])
        if topic_id in allowed_topic_ids and topic_id not in rows_by_topic_id:
            rows_by_topic_id[topic_id] = row

    ordered_rows = [rows_by_topic_id[topic_id] for topic_id in topic_ids if topic_id in rows_by_topic_id]
    return build_question_topic_payload(
        ordered_rows,
        keywords=list(search_result.get("keywords") or []),
        max_topic_text_chars=max_topic_text_chars,
    )


def load_question_topic_payload(
    search_result: Dict[str, Any],
    *,
    max_analysis_topics: int,
    max_topic_text_chars: int,
) -> List[Dict[str, Any]]:
    topic_ids = [str(topic.get("topic_id") or "") for topic in search_result.get("topics", [])[:max_analysis_topics]]
    if not topic_ids:
        return []

    rows = load_question_topic_rows(search_result["group_id"], topic_ids)

    return build_question_topic_payload_from_rows(
        search_result,
        rows,
        max_analysis_topics=max_analysis_topics,
        max_topic_text_chars=max_topic_text_chars,
    )
