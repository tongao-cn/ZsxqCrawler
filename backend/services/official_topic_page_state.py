"""Official topic page state helpers for crawl workflows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, NamedTuple, Optional

from backend.services.official_topic_page_importer import official_topic_id


TaskLogWriter = Callable[[str, str], None]
ZsxqTimeFormatter = Callable[[datetime], str]

OFFICIAL_CRAWL_COMPLETION_MESSAGES = {
    "latest": "官方最新采集完成",
    "incremental": "官方增量采集完成",
    "all": "官方全量采集完成",
}


class OfficialStartCursorResult(NamedTuple):
    cursor: Optional[str]
    is_empty_failure: bool


def empty_official_crawl_stats() -> dict[str, Any]:
    return {
        "new_topics": 0,
        "updated_topics": 0,
        "errors": 0,
        "pages": 0,
        "duplicates": 0,
        "source": "official",
    }


def add_official_page_stats(
    total_stats: dict[str, Any],
    page_stats: dict[str, int],
) -> None:
    total_stats["new_topics"] += page_stats["new_topics"]
    total_stats["updated_topics"] += page_stats["updated_topics"]
    total_stats["errors"] += page_stats["errors"]
    total_stats["pages"] += 1


def dedupe_official_page_topics(
    topics: list[dict[str, Any]],
    seen_topic_ids: set[int],
    total_stats: dict[str, Any],
    *,
    topic_id: Callable[[dict[str, Any]], int] = official_topic_id,
) -> list[dict[str, Any]]:
    unique_topics = []
    for topic in topics:
        current_topic_id = topic_id(topic)
        if current_topic_id in seen_topic_ids:
            total_stats["duplicates"] += 1
            continue
        seen_topic_ids.add(current_topic_id)
        unique_topics.append(topic)
    return unique_topics


def official_topic_page_empty(
    task_id: str,
    topics: list[dict[str, Any]],
    add_task_log: TaskLogWriter,
) -> bool:
    if topics:
        return False
    add_task_log(task_id, "📭 无更多数据，任务结束")
    return True


def official_page_cursor(
    payload: dict[str, Any],
    current_cursor: Optional[str],
) -> Optional[str]:
    next_cursor = payload.get("next_end_time")
    if not next_cursor or next_cursor == current_cursor:
        return None
    return next_cursor


def official_next_page_cursor(
    payload: dict[str, Any],
    current_cursor: Optional[str],
) -> Optional[str]:
    if not payload.get("has_more"):
        return None
    return official_page_cursor(payload, current_cursor)


def official_next_cursor_or_log_end(
    task_id: str,
    payload: dict[str, Any],
    current_cursor: Optional[str],
    add_task_log: TaskLogWriter,
) -> Optional[str]:
    next_cursor = official_next_page_cursor(payload, current_cursor)
    if next_cursor:
        return next_cursor
    add_task_log(task_id, "✅ 官方分页已无更多数据")
    return None


def official_pages_remaining(pages: Optional[int], total_stats: dict[str, Any]) -> bool:
    return pages is None or total_stats["pages"] < pages


def official_reached_before_start(
    oldest_dt: Optional[datetime],
    start_dt: datetime,
) -> bool:
    return bool(oldest_dt and oldest_dt < start_dt)


def official_per_page_limit(per_page: Optional[int]) -> int:
    return min(per_page or 20, 30)


def official_crawl_completion_message(mode: str) -> str:
    return OFFICIAL_CRAWL_COMPLETION_MESSAGES.get(mode, "官方采集完成")


def official_cursor_before_timestamp(
    oldest_timestamp: str,
    format_zsxq_time: ZsxqTimeFormatter,
) -> str:
    try:
        dt = datetime.fromisoformat(oldest_timestamp.replace("+0800", "+08:00"))
        return format_zsxq_time(dt - timedelta(milliseconds=1))
    except Exception:
        return oldest_timestamp


def official_start_cursor_from_oldest(
    timestamp_info: dict[str, Any],
    task_id: str,
    allow_empty: bool,
    add_task_log: TaskLogWriter,
    *,
    cursor_before_timestamp: Callable[[str], str],
) -> OfficialStartCursorResult:
    if not timestamp_info["has_data"]:
        if allow_empty:
            add_task_log(task_id, "📊 数据库为空，将从最新数据开始")
            return OfficialStartCursorResult(None, False)
        add_task_log(task_id, "❌ 数据库中没有话题数据，请先采集最新或全量")
        return OfficialStartCursorResult(None, True)

    oldest_timestamp = timestamp_info["oldest_timestamp"]
    add_task_log(task_id, f"📊 当前最老时间戳: {oldest_timestamp}")
    return OfficialStartCursorResult(cursor_before_timestamp(oldest_timestamp), False)
