"""Shared topic material readers for group-level analysis workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from backend.services.daily_topic_analysis_prompts import build_prompt_payload, build_prompt_payload_unclipped
from backend.services.daily_topic_analysis_store import connect_topics_db
from backend.services.daily_topic_analysis_topics import fetch_topics_for_date


BJ_TZ = timezone(timedelta(hours=8))
DEFAULT_COMMENTS_PER_TOPIC = 8
MAX_TOPIC_CHARS = 5000
MAX_PROMPT_CHARS = 60000
MAX_IMAGES_PER_TOPIC = 2


@dataclass(frozen=True)
class DailyTopicMaterialSnapshot:
    group_id: str
    report_date: date
    topics: List[Dict[str, Any]]
    max_prompt_chars: int = MAX_PROMPT_CHARS

    @property
    def report_date_text(self) -> str:
        return self.report_date.isoformat()

    @property
    def topic_count(self) -> int:
        return len(self.topics)

    @property
    def prompt_payload(self) -> str:
        return build_daily_topic_material_payload(
            self.group_id,
            self.report_date_text,
            self.topics,
            max_prompt_chars=self.max_prompt_chars,
        )

    @property
    def prompt_payload_unclipped(self) -> str:
        return build_daily_topic_material_payload_unclipped(
            self.group_id,
            self.report_date_text,
            self.topics,
        )


def parse_topic_material_date(value: Optional[Union[str, date]]) -> date:
    if not value:
        return datetime.now(BJ_TZ).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
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


def build_daily_topic_material_payload_unclipped(
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
) -> str:
    return build_prompt_payload_unclipped(group_id, report_date, topics)


def load_daily_topic_material(
    group_id: str,
    report_date: Optional[Union[str, date]] = None,
    *,
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC,
    max_topic_chars: int = MAX_TOPIC_CHARS,
    max_images_per_topic: int = MAX_IMAGES_PER_TOPIC,
    max_prompt_chars: int = MAX_PROMPT_CHARS,
) -> DailyTopicMaterialSnapshot:
    parsed_date = parse_topic_material_date(report_date)
    conn = connect_topic_material_db(group_id)
    try:
        topics = fetch_daily_topic_material(
            conn,
            group_id=group_id,
            report_date=parsed_date,
            comments_per_topic=comments_per_topic,
            max_topic_chars=max_topic_chars,
            max_images_per_topic=max_images_per_topic,
        )
    finally:
        conn.close()

    return DailyTopicMaterialSnapshot(
        group_id=group_id,
        report_date=parsed_date,
        topics=topics,
        max_prompt_chars=max_prompt_chars,
    )
