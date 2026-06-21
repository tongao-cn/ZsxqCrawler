"""Result assembly for stock-scoped topic search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from backend.services.daily_topic_analysis_topics import clip_text as _clip
from backend.services.stock_topic_analysis_helpers import (
    _normalize_text,
    _ordered_unique,
    _parse_json_list,
    _safe_float,
)
from backend.services.stock_topic_analysis_payloads import require_topic_excerpt


@dataclass(frozen=True)
class StockTopicSearchResultDraft:
    group_id: str
    stock_name: str
    processed_topic_ids: List[Any]
    topics_by_id: Dict[str, Dict[str, Any]]
    stock_codes: List[str]
    markets: List[str]
    recommendation_names: List[str]
    had_rows: bool


def build_empty_stock_topic_search_result(
    group_id: str,
    stock_name: str,
    *,
    processed_topic_ids: Iterable[Any] = (),
) -> Dict[str, Any]:
    tracked_topic_ids = list(processed_topic_ids or [])
    return {
        "group_id": group_id,
        "stock_name": stock_name,
        "stock_code": "",
        "market": "",
        "topics": [],
        "concepts": [],
        "topic_count": 0,
        "recommendation_count": 0,
        "processed_topic_ids": tracked_topic_ids,
        "analyzed_topic_ids": tracked_topic_ids,
        "skipped_topic_ids": [],
    }


def draft_stock_topic_search_result(
    *,
    group_id: str,
    stock_name: str,
    rows: Sequence[Any],
    processed_topic_ids: Iterable[Any],
    alias_terms: Sequence[str],
) -> StockTopicSearchResultDraft:
    processed_topic_id_list = list(processed_topic_ids or [])
    processed_topic_id_set = set(processed_topic_id_list)
    row_list = list(rows or [])
    topics_by_id: Dict[str, Dict[str, Any]] = {}
    stock_names: List[str] = []
    stock_codes: List[str] = []
    markets: List[str] = []

    for row in row_list:
        topic_id = str(row["topic_id"])
        if topic_id in processed_topic_id_set:
            continue
        stored_excerpt = require_topic_excerpt(row["excerpt"], topic_id=topic_id, stock_name=stock_name)
        extracted_content = stored_excerpt
        mode = "stored_excerpt"
        matched_terms = _ordered_unique([_normalize_text(row["stock_name"]), *alias_terms], limit=10)
        topic = topics_by_id.setdefault(
            topic_id,
            {
                "topic_id": topic_id,
                "title": row["title"] or "",
                "create_time": row["create_time"] or "",
                "likes_count": int(row["likes_count"] or 0),
                "comments_count": int(row["comments_count"] or 0),
                "reading_count": int(row["reading_count"] or 0),
                "content_preview": _clip(extracted_content, 260),
                "concepts": [],
                "reasons": [],
                "excerpt": stored_excerpt,
                "confidence": 0.0,
                "recommendation_count": 0,
                "extract_mode": mode,
                "relevance_score": 0,
                "analysis_content": extracted_content,
            },
        )
        stock_names.append(row["stock_name"] or stock_name)
        stock_codes.append(row["stock_code"] or "")
        markets.append(row["market"] or "")
        topic["concepts"] = _ordered_unique([*topic["concepts"], *_parse_json_list(row["concepts_json"])], limit=12)
        topic["reasons"] = _ordered_unique([*topic["reasons"], row["reason"]], limit=6)
        topic["confidence"] = max(_safe_float(topic["confidence"]), _safe_float(row["confidence"]))
        topic["relevance_score"] = max(
            int(topic["relevance_score"]),
            _score_relevant_topic(extracted_content, mode, matched_terms, topic),
        )
        topic["extract_mode"] = mode if topic.get("extract_mode") != "full" else topic["extract_mode"]
        if len(extracted_content) > len(str(topic.get("analysis_content") or "")):
            topic["analysis_content"] = extracted_content

    return StockTopicSearchResultDraft(
        group_id=group_id,
        stock_name=stock_name,
        processed_topic_ids=processed_topic_id_list,
        topics_by_id=topics_by_id,
        stock_codes=stock_codes,
        markets=markets,
        recommendation_names=_ordered_unique([stock_name, *stock_names], limit=10),
        had_rows=bool(row_list),
    )


def build_stock_topic_search_result(
    draft: StockTopicSearchResultDraft,
    *,
    recommendation_count: int,
    recommendation_by_date: Dict[str, int],
    limit: int | None,
    max_tracked_topic_ids: int,
) -> Dict[str, Any]:
    topics: List[Dict[str, Any]] = []
    for topic in draft.topics_by_id.values():
        item = {**topic}
        topic_day = str(item["create_time"] or "")[:10]
        item["recommendation_count"] = recommendation_by_date.get(topic_day, 0)
        topics.append(item)

    topics = sorted(
        topics,
        key=lambda item: (
            int(item.get("relevance_score") or 0),
            str(item["create_time"] or ""),
        ),
        reverse=True,
    )
    if limit is not None:
        topics = topics[: max(1, int(limit))]
    concepts = _ordered_unique(
        concept
        for topic in topics
        for concept in topic.get("concepts", [])
    )
    stock_code_values = _ordered_unique(draft.stock_codes, limit=1)
    market_values = _ordered_unique(draft.markets, limit=1)
    tracked_topic_ids = _ordered_unique(draft.processed_topic_ids, limit=max_tracked_topic_ids)
    return {
        "group_id": draft.group_id,
        "stock_name": draft.stock_name,
        "stock_code": stock_code_values[0] if stock_code_values else "",
        "market": market_values[0] if market_values else "",
        "topics": topics,
        "concepts": concepts,
        "topic_count": len(topics),
        "recommendation_count": recommendation_count,
        "processed_topic_ids": tracked_topic_ids,
        "analyzed_topic_ids": tracked_topic_ids,
        "skipped_topic_ids": [],
    }


def _score_relevant_topic(extracted_content: str, mode: str, matched_terms: Iterable[str], topic_row: Dict[str, Any]) -> int:
    if not extracted_content:
        return 0
    score = 100 if mode in {"full", "title_full"} else 70
    score += min(len(_ordered_unique(matched_terms, limit=10)) * 5, 15)
    confidence = _safe_float(topic_row.get("confidence"))
    if confidence > 0:
        score += min(int(confidence * 10), 10)
    return score
