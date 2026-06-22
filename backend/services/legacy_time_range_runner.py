"""Legacy topic time-range runner for crawl workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, NamedTuple, Optional

from backend.services.crawl_time_range import (
    filter_legacy_topics_by_time_range,
    legacy_next_end_time,
    legacy_time_range_initial_cursors,
)


LEGACY_TIME_RANGE_DEFAULT_PER_PAGE = 20
LEGACY_TIME_RANGE_MAX_RETRIES_PER_PAGE = 10

TaskLogWriter = Callable[[str, str], None]
TaskStopChecker = Callable[[str], bool]
TaskFailureWriter = Callable[..., None]


class LegacyTimeRangeNonEmptyPageResult(NamedTuple):
    last_time_dt_in_page: Optional[datetime]
    end_time_param: Optional[str]
    reached_before_start: bool


class LegacyTimeRangePageResult(NamedTuple):
    page_processed: bool
    reached_end: bool
    last_time_dt_in_page: Optional[datetime]
    end_time_param: Optional[str]
    expired: bool


class LegacyTimeRangeRunResult(NamedTuple):
    stats: dict[str, int]
    expired: bool


def _store_legacy_time_range_page(
    crawler: Any,
    total_stats: dict[str, int],
    filtered: list[dict[str, Any]],
) -> None:
    if filtered:
        filtered_data = {"succeeded": True, "resp_data": {"topics": filtered}}
        page_stats = crawler.store_batch_data(filtered_data)
        total_stats["new_topics"] += page_stats.get("new_topics", 0)
        total_stats["updated_topics"] += page_stats.get("updated_topics", 0)
        total_stats["errors"] += page_stats.get("errors", 0)
    total_stats["pages"] += 1


def _record_legacy_time_range_fetch_failure(
    task_id: str,
    total_stats: dict[str, int],
    retry: int,
    max_retries_per_page: int,
    add_task_log: TaskLogWriter,
) -> int:
    retry += 1
    total_stats["errors"] += 1
    add_task_log(task_id, f"❌ 页面获取失败 (重试{retry}/{max_retries_per_page})")
    return retry


def _legacy_time_range_response_expired(
    task_id: str,
    data: Any,
    fail_task_with_message_unless_stopped: TaskFailureWriter,
) -> bool:
    if not data or not isinstance(data, dict) or not data.get("expired"):
        return False
    fail_task_with_message_unless_stopped(
        task_id,
        "会员已过期",
        data,
        log_message=f"❌ 会员已过期: {data.get('message')}",
    )
    return True


def _legacy_time_range_page_empty(
    task_id: str,
    topics: list[dict[str, Any]],
    add_task_log: TaskLogWriter,
) -> bool:
    if topics:
        return False
    add_task_log(task_id, "📭 无更多数据，任务结束")
    return True


def _task_stopped_with_log(
    task_id: str,
    task_stopped: TaskStopChecker,
    add_task_log: TaskLogWriter,
) -> bool:
    if not task_stopped(task_id):
        return False
    add_task_log(task_id, "🛑 任务已停止")
    return True


def _legacy_time_range_page_failed(
    task_id: str,
    page_processed: bool,
    add_task_log: TaskLogWriter,
) -> bool:
    if page_processed:
        return False
    add_task_log(task_id, "🚫 当前页面达到最大重试次数，终止任务")
    return True


def _legacy_time_range_reached_before_start(
    last_time_dt_in_page: Optional[datetime],
    start_dt: datetime,
) -> bool:
    return last_time_dt_in_page is not None and last_time_dt_in_page < start_dt


def _legacy_time_range_reached_before_start_with_log(
    task_id: str,
    last_time_dt_in_page: Optional[datetime],
    start_dt: datetime,
    add_task_log: TaskLogWriter,
) -> bool:
    if not _legacy_time_range_reached_before_start(last_time_dt_in_page, start_dt):
        return False
    add_task_log(task_id, "✅ 已到达起始时间之前，任务结束")
    return True


def _legacy_time_range_should_finish(
    reached_end: bool,
    last_time_dt_in_page: Optional[datetime],
    start_dt: datetime,
) -> bool:
    return reached_end or _legacy_time_range_reached_before_start(last_time_dt_in_page, start_dt)


def _fetch_legacy_time_range_page(
    crawler: Any,
    per_page: int,
    begin_time_param: str,
    end_time_param: Optional[str],
) -> Any:
    return crawler.fetch_topics_safe(
        scope="all",
        count=per_page,
        begin_time=begin_time_param,
        end_time=end_time_param,
        is_historical=True,
    )


def _legacy_time_range_topics(data: dict[str, Any]) -> list[dict[str, Any]]:
    return (data.get("resp_data", {}) or {}).get("topics", []) or []


def _log_legacy_time_range_page_summary(
    task_id: str,
    topics: list[dict[str, Any]],
    filtered: list[dict[str, Any]],
    add_task_log: TaskLogWriter,
) -> None:
    add_task_log(task_id, f"📄 本页获取 {len(topics)} 个话题，区间内 {len(filtered)} 个")


def _process_legacy_time_range_non_empty_page(
    task_id: str,
    crawler: Any,
    total_stats: dict[str, int],
    topics: list[dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
    add_task_log: TaskLogWriter,
) -> LegacyTimeRangeNonEmptyPageResult:
    filtered, last_time_dt_in_page = filter_legacy_topics_by_time_range(
        topics, start_dt, end_dt
    )
    _log_legacy_time_range_page_summary(task_id, topics, filtered, add_task_log)
    _store_legacy_time_range_page(crawler, total_stats, filtered)
    next_end_time_param = legacy_next_end_time(topics, crawler.timestamp_offset_ms)
    reached_before_start = _legacy_time_range_reached_before_start_with_log(
        task_id, last_time_dt_in_page, start_dt, add_task_log
    )
    if not reached_before_start:
        crawler.check_page_long_delay()
    return LegacyTimeRangeNonEmptyPageResult(
        last_time_dt_in_page=last_time_dt_in_page,
        end_time_param=next_end_time_param,
        reached_before_start=reached_before_start,
    )


def _process_legacy_time_range_page(
    task_id: str,
    crawler: Any,
    total_stats: dict[str, int],
    per_page: int,
    begin_time_param: str,
    end_time_param: Optional[str],
    start_dt: datetime,
    end_dt: datetime,
    max_retries_per_page: int,
    add_task_log: TaskLogWriter,
    task_stopped: TaskStopChecker,
    fail_task_with_message_unless_stopped: TaskFailureWriter,
) -> LegacyTimeRangePageResult:
    retry = 0
    page_processed = False
    reached_end = False
    last_time_dt_in_page = None
    next_end_time_param = end_time_param

    while retry < max_retries_per_page:
        if task_stopped(task_id):
            break

        data = _fetch_legacy_time_range_page(
            crawler,
            per_page,
            begin_time_param,
            next_end_time_param,
        )

        if _legacy_time_range_response_expired(
            task_id,
            data,
            fail_task_with_message_unless_stopped,
        ):
            return LegacyTimeRangePageResult(
                page_processed=False,
                reached_end=False,
                last_time_dt_in_page=None,
                end_time_param=next_end_time_param,
                expired=True,
            )

        if not data:
            retry = _record_legacy_time_range_fetch_failure(
                task_id,
                total_stats,
                retry,
                max_retries_per_page,
                add_task_log,
            )
            continue

        topics = _legacy_time_range_topics(data)
        if _legacy_time_range_page_empty(task_id, topics, add_task_log):
            page_processed = True
            reached_end = True
            break

        page_result = _process_legacy_time_range_non_empty_page(
            task_id,
            crawler,
            total_stats,
            topics,
            start_dt,
            end_dt,
            add_task_log,
        )
        page_processed = True
        last_time_dt_in_page = page_result.last_time_dt_in_page
        next_end_time_param = page_result.end_time_param

        if page_result.reached_before_start:
            break
        break

    return LegacyTimeRangePageResult(
        page_processed=page_processed,
        reached_end=reached_end,
        last_time_dt_in_page=last_time_dt_in_page,
        end_time_param=next_end_time_param,
        expired=False,
    )


def _empty_legacy_time_range_stats() -> dict[str, int]:
    return {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0}


def _legacy_time_range_per_page(request: Any) -> int:
    return request.perPage or LEGACY_TIME_RANGE_DEFAULT_PER_PAGE


def run_legacy_time_range_pages(
    task_id: str,
    crawler: Any,
    request: Any,
    start_dt: datetime,
    end_dt: datetime,
    *,
    add_task_log: TaskLogWriter,
    task_stopped: TaskStopChecker,
    fail_task_with_message_unless_stopped: TaskFailureWriter,
) -> LegacyTimeRangeRunResult:
    per_page = _legacy_time_range_per_page(request)
    total_stats = _empty_legacy_time_range_stats()
    begin_time_param, end_time_param = legacy_time_range_initial_cursors(start_dt, end_dt)
    max_retries_per_page = LEGACY_TIME_RANGE_MAX_RETRIES_PER_PAGE

    while True:
        if _task_stopped_with_log(task_id, task_stopped, add_task_log):
            break

        page_result = _process_legacy_time_range_page(
            task_id,
            crawler,
            total_stats,
            per_page,
            begin_time_param,
            end_time_param,
            start_dt,
            end_dt,
            max_retries_per_page,
            add_task_log,
            task_stopped,
            fail_task_with_message_unless_stopped,
        )
        if page_result.expired:
            return LegacyTimeRangeRunResult(stats=total_stats, expired=True)

        end_time_param = page_result.end_time_param

        if _legacy_time_range_page_failed(task_id, page_result.page_processed, add_task_log):
            break

        if _legacy_time_range_should_finish(
            page_result.reached_end, page_result.last_time_dt_in_page, start_dt
        ):
            break

    return LegacyTimeRangeRunResult(stats=total_stats, expired=False)
