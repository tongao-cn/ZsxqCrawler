"""Payload builders for stock topic analysis AI inputs."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Sequence

from backend.services.daily_topic_analysis_topics import clip_text as _clip


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_company_name(value: Any) -> str:
    return (
        _normalize_text(value)
        .replace(" ", "")
        .replace("股份有限公司", "")
        .replace("有限责任公司", "")
        .replace("有限公司", "")
        .replace("集团", "")
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


def require_topic_excerpt(value: Any, *, topic_id: Any, stock_name: Any) -> str:
    excerpt = _normalize_text(value)
    if not excerpt:
        raise RuntimeError(f"topic {topic_id} 缺少 {_normalize_company_name(stock_name)} 的 excerpt，请先运行推荐池话题抽取")
    return excerpt


def build_analysis_topic_payload(search_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for topic in search_result.get("topics", []):
        topic_id = str(topic.get("topic_id") or "")
        excerpt = require_topic_excerpt(
            topic.get("excerpt"),
            topic_id=topic_id,
            stock_name=search_result.get("stock_name"),
        )
        payload.append(
            {
                "topic_id": topic_id,
                "title": topic.get("title") or "",
                "create_time": topic.get("create_time") or "",
                "metrics": {
                    "likes_count": int(topic.get("likes_count") or 0),
                    "comments_count": int(topic.get("comments_count") or 0),
                    "reading_count": int(topic.get("reading_count") or 0),
                },
                "concepts": list(topic.get("concepts") or []),
                "excerpt": excerpt,
            }
        )
    return payload


def build_question_topic_payload(
    rows: Sequence[Any],
    *,
    keywords: Sequence[str],
    max_topic_text_chars: int,
) -> List[Dict[str, Any]]:
    return [
        {
            "topic_id": str(row["topic_id"]),
            "title": row["title"] or "",
            "create_time": row["create_time"] or "",
            "metrics": {
                "likes_count": int(row["likes_count"] or 0),
                "comments_count": int(row["comments_count"] or 0),
                "reading_count": int(row["reading_count"] or 0),
            },
            "matched_keywords": [
                keyword
                for keyword in keywords
                if keyword.lower() in _topic_content(row).lower()
            ],
            "content": _clip(_topic_content(row), max_topic_text_chars),
        }
        for row in rows
    ]


def build_stock_analysis_prompt(
    search_result: Dict[str, Any],
    topics: List[Dict[str, Any]],
    *,
    existing_summary: str = "",
    max_analysis_prompt_chars: int,
) -> str:
    payload = {
        "group_id": search_result["group_id"],
        "analysis_date": date.today().isoformat(),
        "stock_name": search_result["stock_name"],
        "stock_code": search_result.get("stock_code") or "",
        "market": search_result.get("market") or "",
        "recommendation_count": search_result.get("recommendation_count") or 0,
        "concepts": search_result.get("concepts") or [],
        "existing_summary_markdown": existing_summary,
        "new_topic_count": len(topics),
        "new_topics": topics,
    }
    return _clip(json.dumps(payload, ensure_ascii=False, indent=2), max_analysis_prompt_chars)


def build_question_analysis_prompt(
    search_result: Dict[str, Any],
    topics: List[Dict[str, Any]],
    *,
    max_analysis_prompt_chars: int,
) -> str:
    payload = {
        "group_id": search_result["group_id"],
        "question": search_result["question"],
        "keywords": search_result.get("keywords") or [],
        "topic_count": len(topics),
        "topics": topics,
    }
    return _clip(json.dumps(payload, ensure_ascii=False, indent=2), max_analysis_prompt_chars)
