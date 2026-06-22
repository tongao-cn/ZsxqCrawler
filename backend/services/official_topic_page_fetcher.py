"""Official topic page fetch helpers for crawl workflows."""

from __future__ import annotations

from typing import Any, Callable, NamedTuple, Optional

from backend.crawlers.official_topic_client import OfficialTopicClient, official_payload_topics
from backend.services.official_topic_page_state import (
    TaskLogWriter,
    dedupe_official_page_topics,
    official_topic_page_empty,
)


class OfficialTopicPage(NamedTuple):
    payload: dict[str, Any]
    topics: list[dict[str, Any]]


class OfficialUniqueTopicPage(NamedTuple):
    payload: dict[str, Any]
    topics: list[dict[str, Any]]
    unique_topics: list[dict[str, Any]]


def fetch_official_topic_page(
    client: OfficialTopicClient,
    group_id: str,
    per_page: int,
    cursor: Optional[str],
) -> OfficialTopicPage:
    payload = client.get_group_topics(
        group_id,
        limit=per_page,
        scope="all",
        end_time=cursor,
    )
    return OfficialTopicPage(payload=payload, topics=official_payload_topics(payload))


def fetch_unique_official_topic_page(
    task_id: str,
    client: OfficialTopicClient,
    group_id: str,
    per_page: int,
    cursor: Optional[str],
    seen_topic_ids: set[int],
    total_stats: dict[str, Any],
    add_task_log: TaskLogWriter,
    *,
    fetch_page: Callable[
        [OfficialTopicClient, str, int, Optional[str]],
        OfficialTopicPage,
    ] = fetch_official_topic_page,
) -> Optional[OfficialUniqueTopicPage]:
    page = fetch_page(client, group_id, per_page, cursor)
    if official_topic_page_empty(task_id, page.topics, add_task_log):
        return None
    unique_topics = dedupe_official_page_topics(page.topics, seen_topic_ids, total_stats)
    return OfficialUniqueTopicPage(
        payload=page.payload,
        topics=page.topics,
        unique_topics=unique_topics,
    )
