"""Database loader for stock question topic payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from backend.services.daily_topic_analysis_topics import clip_text as _clip
from backend.services.stock_topic_analysis_helpers import _normalize_text
from backend.services.stock_topic_analysis_payloads import build_question_topic_payload
from backend.services.stock_topic_analysis_store import load_question_topic_rows


@dataclass(frozen=True)
class QuestionTopicMaterial:
    search_result: Dict[str, Any]
    analysis_topics: List[Dict[str, Any]]


def build_stock_question_search_result(
    *,
    group_id: str,
    question: str,
    keywords: List[str],
    keyword_model: str,
    rows: List[Any],
) -> Dict[str, Any]:
    topics_by_id: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        topic_id = str(row["topic_id"])
        content = _topic_content(row)
        matched_keywords = [keyword for keyword in keywords if keyword.lower() in content.lower()]
        topics_by_id[topic_id] = {
            "topic_id": topic_id,
            "title": row["title"] or "",
            "create_time": row["create_time"] or "",
            "likes_count": int(row["likes_count"] or 0),
            "comments_count": int(row["comments_count"] or 0),
            "reading_count": int(row["reading_count"] or 0),
            "content_preview": _clip(content, 300),
            "matched_keywords": matched_keywords,
        }

    topics = sorted(topics_by_id.values(), key=lambda item: str(item["create_time"] or ""), reverse=True)
    return {
        "group_id": group_id,
        "question": question,
        "keywords": keywords,
        "keyword_model": keyword_model,
        "topics": topics,
        "topic_count": len(topics),
    }


def build_question_topic_material(
    *,
    group_id: str,
    question: str,
    keywords: List[str],
    keyword_model: str,
    rows: List[Any],
    max_analysis_topics: int,
    max_topic_text_chars: int,
) -> QuestionTopicMaterial:
    search_result = build_stock_question_search_result(
        group_id=group_id,
        question=question,
        keywords=keywords,
        keyword_model=keyword_model,
        rows=rows,
    )
    return QuestionTopicMaterial(
        search_result=search_result,
        analysis_topics=build_question_topic_payload_from_rows(
            search_result,
            rows,
            max_analysis_topics=max_analysis_topics,
            max_topic_text_chars=max_topic_text_chars,
        ),
    )


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


def _topic_content(row: Any) -> str:
    return "\n".join(
        part
        for part in (
            _normalize_text(row["title"]),
            _normalize_text(row["talk_text"]),
            _normalize_text(row["question_text"]),
            _normalize_text(row["answer_text"]),
        )
        if part
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
