"""Official topic crawl runners for page and time-range workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, NamedTuple, Optional

from backend.crawlers.official_topic_client import OfficialTopicClient
from backend.services.crawl_time_range import filter_official_topics_by_time_range, format_zsxq_time
from backend.services.official_topic_page_fetcher import fetch_unique_official_topic_page
from backend.services.official_topic_page_importer import (
    import_official_page_topics,
    official_topics_to_import_for_mode,
)
from backend.services.official_topic_page_state import (
    add_official_page_stats,
    empty_official_crawl_stats,
    official_crawl_completion_message,
    official_next_cursor_or_log_end,
    official_pages_remaining,
    official_per_page_limit,
    official_reached_before_start,
)
from backend.storage.zsxq_database import ZSXQDatabase


TaskLogWriter = Callable[[str, str], None]
TaskStopChecker = Callable[[str], bool]
TaskCompletionWriter = Callable[[str, str, dict[str, Any]], None]
OfficialTopicClientFactory = Callable[[str], OfficialTopicClient]
OfficialDatabaseFactory = Callable[[str], ZSXQDatabase]


class OfficialTopicCrawlRuntime(NamedTuple):
    add_task_log: TaskLogWriter
    task_stopped: TaskStopChecker
    complete_task: TaskCompletionWriter
    client_factory: OfficialTopicClientFactory
    database_factory: OfficialDatabaseFactory


class OfficialCrawlTimeRangeTarget(NamedTuple):
    task_id: str
    group_id: str
    request: Any
    start_dt: datetime
    end_dt: datetime


class OfficialCrawlPagesTarget(NamedTuple):
    task_id: str
    group_id: str
    pages: Optional[int]
    per_page: int
    mode: str
    start_cursor: Optional[str] = None


def _task_stopped_with_log(runtime: OfficialTopicCrawlRuntime, task_id: str) -> bool:
    if not runtime.task_stopped(task_id):
        return False
    runtime.add_task_log(task_id, "🛑 任务已停止")
    return True


def run_official_crawl_time_range(
    runtime: OfficialTopicCrawlRuntime,
    target: OfficialCrawlTimeRangeTarget,
) -> None:
    runtime.add_task_log(target.task_id, "🔁 使用官方话题采集流程（MCP HTTP）")
    client = runtime.client_factory(target.task_id)
    db = runtime.database_factory(target.group_id)
    per_page = official_per_page_limit(target.request.perPage)
    if target.request.perPage and target.request.perPage > 30:
        runtime.add_task_log(target.task_id, "ℹ️ 官方接口单页上限按 30 处理")

    cursor = format_zsxq_time(target.end_dt)
    seen_topic_ids: set[int] = set()
    total_stats = empty_official_crawl_stats()

    while True:
        if _task_stopped_with_log(runtime, target.task_id):
            break

        page = fetch_unique_official_topic_page(
            target.task_id,
            client,
            target.group_id,
            per_page,
            cursor,
            seen_topic_ids,
            total_stats,
            runtime.add_task_log,
        )
        if page is None:
            break

        filtered, oldest_dt = filter_official_topics_by_time_range(
            page.unique_topics,
            target.start_dt,
            target.end_dt,
        )

        runtime.add_task_log(
            target.task_id,
            f"📄 官方本页获取 {len(page.topics)} 个话题，区间内 {len(filtered)} 个",
        )

        import_official_page_topics(
            total_stats,
            db,
            client,
            target.group_id,
            filtered,
            target.task_id,
            runtime.add_task_log,
            add_official_page_stats,
        )

        next_cursor = official_next_cursor_or_log_end(
            target.task_id,
            page.payload,
            cursor,
            runtime.add_task_log,
        )
        if not next_cursor:
            break
        cursor = next_cursor

        if official_reached_before_start(oldest_dt, target.start_dt):
            runtime.add_task_log(target.task_id, "✅ 已到达起始时间之前，任务结束")
            break

    runtime.complete_task(target.task_id, "官方时间区间采集完成", total_stats)


def run_official_crawl_pages(
    runtime: OfficialTopicCrawlRuntime,
    target: OfficialCrawlPagesTarget,
) -> None:
    client = runtime.client_factory(target.task_id)
    db = runtime.database_factory(target.group_id)
    per_page = official_per_page_limit(target.per_page)
    cursor = target.start_cursor
    total_stats = empty_official_crawl_stats()
    seen_topic_ids: set[int] = set()

    while official_pages_remaining(target.pages, total_stats):
        if _task_stopped_with_log(runtime, target.task_id):
            break

        page = fetch_unique_official_topic_page(
            target.task_id,
            client,
            target.group_id,
            per_page,
            cursor,
            seen_topic_ids,
            total_stats,
            runtime.add_task_log,
        )
        if page is None:
            break

        import_plan = official_topics_to_import_for_mode(
            db,
            target.group_id,
            target.mode,
            page.unique_topics,
            target.task_id,
            runtime.add_task_log,
        )
        if import_plan.should_stop:
            break

        import_official_page_topics(
            total_stats,
            db,
            client,
            target.group_id,
            import_plan.topics_to_import,
            target.task_id,
            runtime.add_task_log,
            add_official_page_stats,
        )

        next_cursor = official_next_cursor_or_log_end(
            target.task_id,
            page.payload,
            cursor,
            runtime.add_task_log,
        )
        if not next_cursor:
            break
        cursor = next_cursor

    runtime.complete_task(target.task_id, official_crawl_completion_message(target.mode), total_stats)
