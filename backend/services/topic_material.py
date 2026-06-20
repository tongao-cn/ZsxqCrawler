"""Shared topic material readers for group-level analysis workflows."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.services.daily_topic_analysis_prompts import build_prompt_payload
from backend.services.daily_topic_analysis_store import connect_topics_db
from backend.services.daily_topic_analysis_topics import fetch_topics_for_date


BJ_TZ = timezone(timedelta(hours=8))
DEFAULT_COMMENTS_PER_TOPIC = 8
MAX_TOPIC_CHARS = 5000
MAX_PROMPT_CHARS = 60000
MAX_IMAGES_PER_TOPIC = 2


def parse_topic_material_date(value: Optional[str]) -> date:
    if not value:
        return datetime.now(BJ_TZ).date()
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError("date 必须是 YYYY-MM-DD 格式") from exc


def connect_topic_material_db(group_id: str):
    return connect_topics_db(group_id)


def fetch_daily_topic_material(
    conn: Any,
    *,
    group_id: str,
    report_date: date,
    comments_per_topic: int,
    max_topic_chars: int = MAX_TOPIC_CHARS,
    max_images_per_topic: int = MAX_IMAGES_PER_TOPIC,
) -> List[Dict[str, Any]]:
    return fetch_topics_for_date(
        conn,
        group_id=group_id,
        report_date=report_date,
        comments_per_topic=comments_per_topic,
        max_topic_chars=max_topic_chars,
        max_images_per_topic=max_images_per_topic,
    )


def build_daily_topic_material_payload(
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    *,
    max_prompt_chars: int = MAX_PROMPT_CHARS,
) -> str:
    return build_prompt_payload(group_id, report_date, topics, max_prompt_chars=max_prompt_chars)
