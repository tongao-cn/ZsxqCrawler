"""Mutable stats helpers for topic pagination crawls."""

from __future__ import annotations

from typing import Any, Dict


def empty_topic_pagination_stats() -> Dict[str, int]:
    return {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0}


def add_topic_pagination_counts(
    stats: Dict[str, int],
    *,
    new_topics: int = 0,
    updated_topics: int = 0,
    errors: int = 0,
    pages: int = 0,
) -> None:
    stats["new_topics"] += new_topics
    stats["updated_topics"] += updated_topics
    stats["errors"] += errors
    stats["pages"] += pages


def add_topic_pagination_page_stats(stats: Dict[str, int], page_stats: Dict[str, Any]) -> None:
    add_topic_pagination_counts(
        stats,
        new_topics=page_stats["new_topics"],
        updated_topics=page_stats["updated_topics"],
        errors=page_stats["errors"],
        pages=1,
    )
