from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from backend.core.account_context import get_cookie_for_group
from backend.crawlers.official_topic_client import (
    OfficialTopicClient,
    normalize_official_topic,
)
from backend.crawlers.topic_crawler import ZSXQTopicCrawler
from backend.services.crawl_time_range import (
    format_zsxq_time as _format_zsxq_time,
    is_date_only as _is_date_only,
    parse_user_time as _parse_user_time,
    resolve_time_range as _resolve_time_range,
    topic_time as _topic_time,
)
from backend.services.legacy_time_range_runner import (
    LegacyTimeRangeRunResult,
    run_legacy_time_range_pages,
)
from backend.services.official_topic_crawl_runner import (
    OfficialCrawlPagesTarget,
    OfficialCrawlTimeRangeTarget,
    OfficialTopicCrawlRuntime,
    run_official_crawl_pages,
    run_official_crawl_time_range,
)
from backend.services.crawl_topic_source import (
    LEGACY_TOPIC_SOURCE_ALIASES,
    OFFICIAL_TOPIC_SOURCE_ALIASES,
    normalize_topic_source as _normalize_topic_source,
    resolve_topic_source as _resolve_topic_source,
    uses_official_topic_source as _uses_official_topic_source,
)
from backend.services.official_topic_page_importer import (
    add_official_import_result,
    fetch_official_comments,
    import_official_page_topics,
    import_official_topic,
    import_official_topics,
    new_official_topics,
    official_topics_to_import_for_mode,
    official_topic_comments_count,
    official_topic_exists,
    official_topic_id,
)
from backend.services.official_topic_page_fetcher import (
    OfficialTopicPage,
    OfficialUniqueTopicPage,
    fetch_official_topic_page,
    fetch_unique_official_topic_page,
)
from backend.services.official_topic_page_state import (
    OfficialStartCursorResult,
    add_official_page_stats,
    dedupe_official_page_topics,
    empty_official_crawl_stats,
    official_crawl_completion_message,
    official_cursor_before_timestamp,
    official_page_cursor,
    official_next_cursor_or_log_end,
    official_next_page_cursor,
    official_pages_remaining,
    official_per_page_limit,
    official_reached_before_start,
    official_start_cursor_from_oldest,
    official_topic_page_empty,
)
from backend.services.task_runtime import (
    add_task_log,
    complete_task_unless_stopped,
    fail_task_with_message_unless_stopped,
    is_task_stopped,
    register_task_crawler,
    unregister_task_crawler,
    update_task,
)
from backend.storage.zsxq_database import ZSXQDatabase


INIT_STOPPED_MESSAGE = "🛑 任务在初始化过程中被停止"

CRAWLER_STARTUP_LOGS = ("📡 连接到知识星球API...", "🔍 检查数据库状态...")

def _should_stop_task(task_id: str) -> bool:
    return is_task_stopped(task_id)

def _build_task_callbacks(task_id: str) -> tuple[Callable[[str], None], Callable[[], bool]]:
    def log_callback(message: str) -> None:
        add_task_log(task_id, message)

    def stop_check() -> bool:
        return _should_stop_task(task_id)

    return log_callback, stop_check

def _log_crawler_startup(task_id: str) -> None:
    for message in CRAWLER_STARTUP_LOGS:
        add_task_log(task_id, message)

def _log_init_stopped(task_id: str) -> None:
    add_task_log(task_id, INIT_STOPPED_MESSAGE)

def _crawl_interval_kwargs(crawl_settings: Any) -> dict[str, Any]:
    return {
        "crawl_interval_min": crawl_settings.crawlIntervalMin,
        "crawl_interval_max": crawl_settings.crawlIntervalMax,
        "long_sleep_interval_min": crawl_settings.longSleepIntervalMin,
        "long_sleep_interval_max": crawl_settings.longSleepIntervalMax,
        "pages_per_batch": crawl_settings.pagesPerBatch,
    }

def _has_crawl_interval_overrides(crawl_settings: Any) -> bool:
    return any(_crawl_interval_kwargs(crawl_settings).values())

def _apply_crawl_settings(crawler: Any, crawl_settings: Any, require_overrides: bool = False) -> bool:
    if not crawl_settings:
        return False
    if require_overrides and not _has_crawl_interval_overrides(crawl_settings):
        return False

    crawler.set_custom_intervals(**_crawl_interval_kwargs(crawl_settings))
    return True

def _mark_expired_task(task_id: str, result: dict[str, Any], default_message: str = "成员体验已到期") -> None:
    message = result.get("message", default_message)
    fail_task_with_message_unless_stopped(
        task_id,
        "会员已过期",
        {"expired": True, "code": result.get("code"), "message": result.get("message")},
        log_message=f"❌ 会员已过期: {message}",
    )

def _create_task_crawler(task_id: str, group_id: str, log_callback: Callable[[str], None], stop_check: Callable[[], bool]) -> ZSXQTopicCrawler:
    cookie = get_cookie_for_group(group_id)
    crawler = ZSXQTopicCrawler(cookie, group_id, log_callback)
    crawler.stop_check_func = stop_check
    register_task_crawler(task_id, crawler)
    return crawler

def _prepare_legacy_crawler(
    task_id: str,
    group_id: str,
    crawl_settings: Any,
    require_overrides: bool = False,
) -> ZSXQTopicCrawler:
    log_callback, stop_check = _build_task_callbacks(task_id)
    crawler = _create_task_crawler(task_id, group_id, log_callback, stop_check)
    _apply_crawl_settings(crawler, crawl_settings, require_overrides=require_overrides)
    return crawler

def _task_stopped_with_log(task_id: str) -> bool:
    if not is_task_stopped(task_id):
        return False
    add_task_log(task_id, "🛑 任务已停止")
    return True

def _run_legacy_time_range_pages(
    task_id: str,
    crawler: Any,
    request: Any,
    start_dt: datetime,
    end_dt: datetime,
) -> LegacyTimeRangeRunResult:
    return run_legacy_time_range_pages(
        task_id,
        crawler,
        request,
        start_dt,
        end_dt,
        add_task_log=add_task_log,
        task_stopped=is_task_stopped,
        fail_task_with_message_unless_stopped=fail_task_with_message_unless_stopped,
    )

def _official_import_topic(db: ZSXQDatabase, _group_id: str, topic_data: dict[str, Any]) -> str:
    return import_official_topic(db, _group_id, topic_data)

def _official_topic_exists(db: ZSXQDatabase, _group_id: str, topic_id: Any) -> bool:
    return official_topic_exists(db, _group_id, topic_id)

def _official_topic_id(topic: dict[str, Any]) -> int:
    return official_topic_id(topic)

def _official_topic_comments_count(topic: dict[str, Any]) -> int:
    return official_topic_comments_count(topic)

def _add_official_import_result(stats: dict[str, int], imported: str) -> None:
    add_official_import_result(stats, imported)

def _new_official_topics(db: ZSXQDatabase, group_id: str, topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return new_official_topics(
        db,
        group_id,
        topics,
        topic_exists=_official_topic_exists,
        topic_id=_official_topic_id,
    )

def _fetch_official_comments(
    client: OfficialTopicClient,
    topic_id: int,
    comments_count: int,
    task_id: str,
) -> list[dict[str, Any]]:
    return fetch_official_comments(client, topic_id, comments_count, task_id, add_task_log)

def _official_import_topics(
    db: ZSXQDatabase,
    client: OfficialTopicClient,
    group_id: str,
    topics: list[dict[str, Any]],
    task_id: str,
) -> dict[str, int]:
    return import_official_topics(
        db,
        client,
        group_id,
        topics,
        task_id,
        add_task_log,
        topic_id=_official_topic_id,
        comments_count_for_topic=_official_topic_comments_count,
        fetch_comments=_fetch_official_comments,
        normalize_topic=normalize_official_topic,
        import_topic=_official_import_topic,
        add_import_result=_add_official_import_result,
    )

def _official_import_page_topics(
    total_stats: dict[str, Any],
    db: ZSXQDatabase,
    client: OfficialTopicClient,
    group_id: str,
    topics: list[dict[str, Any]],
    task_id: str,
) -> dict[str, int]:
    return import_official_page_topics(
        total_stats,
        db,
        client,
        group_id,
        topics,
        task_id,
        add_task_log,
        _add_official_page_stats,
        import_topics=_official_import_topics,
    )

def _official_topic_client(task_id: str) -> OfficialTopicClient:
    return OfficialTopicClient(log_callback=lambda message: add_task_log(task_id, message))

def _official_topic_crawl_runtime() -> OfficialTopicCrawlRuntime:
    return OfficialTopicCrawlRuntime(
        add_task_log,
        is_task_stopped,
        complete_task_unless_stopped,
        _official_topic_client,
        ZSXQDatabase,
    )

def _empty_official_crawl_stats() -> dict[str, Any]:
    return empty_official_crawl_stats()

def _add_official_page_stats(total_stats: dict[str, Any], page_stats: dict[str, int]) -> None:
    add_official_page_stats(total_stats, page_stats)

def _dedupe_official_page_topics(
    topics: list[dict[str, Any]],
    seen_topic_ids: set[int],
    total_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    return dedupe_official_page_topics(
        topics,
        seen_topic_ids,
        total_stats,
        topic_id=_official_topic_id,
    )

def _official_topics_to_import_for_mode(
    task_id: str,
    db: ZSXQDatabase,
    group_id: str,
    mode: str,
    unique_topics: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    plan = official_topics_to_import_for_mode(
        db,
        group_id,
        mode,
        unique_topics,
        task_id,
        add_task_log,
        find_new_topics=_new_official_topics,
    )
    return plan.topics_to_import, plan.should_stop

def _fetch_official_topic_page(
    client: OfficialTopicClient,
    group_id: str,
    per_page: int,
    cursor: Optional[str],
) -> OfficialTopicPage:
    return fetch_official_topic_page(client, group_id, per_page, cursor)

def _fetch_unique_official_topic_page(
    task_id: str,
    client: OfficialTopicClient,
    group_id: str,
    per_page: int,
    cursor: Optional[str],
    seen_topic_ids: set[int],
    total_stats: dict[str, Any],
) -> Optional[OfficialUniqueTopicPage]:
    return fetch_unique_official_topic_page(
        task_id,
        client,
        group_id,
        per_page,
        cursor,
        seen_topic_ids,
        total_stats,
        add_task_log,
        fetch_page=_fetch_official_topic_page,
    )

def _official_topic_page_empty(task_id: str, topics: list[dict[str, Any]]) -> bool:
    return official_topic_page_empty(task_id, topics, add_task_log)

def _official_page_cursor(payload: dict[str, Any], current_cursor: Optional[str]) -> Optional[str]:
    return official_page_cursor(payload, current_cursor)

def _official_next_page_cursor(payload: dict[str, Any], current_cursor: Optional[str]) -> Optional[str]:
    return official_next_page_cursor(payload, current_cursor)

def _official_next_cursor_or_log_end(
    task_id: str,
    payload: dict[str, Any],
    current_cursor: Optional[str],
) -> Optional[str]:
    return official_next_cursor_or_log_end(task_id, payload, current_cursor, add_task_log)

def _official_pages_remaining(pages: Optional[int], total_stats: dict[str, Any]) -> bool:
    return official_pages_remaining(pages, total_stats)

def _official_reached_before_start(oldest_dt: Optional[datetime], start_dt: datetime) -> bool:
    return official_reached_before_start(oldest_dt, start_dt)

def _official_per_page_limit(per_page: Optional[int]) -> int:
    return official_per_page_limit(per_page)

def _official_crawl_completion_message(mode: str) -> str:
    return official_crawl_completion_message(mode)

def _official_cursor_before_timestamp(oldest_timestamp: str) -> str:
    return official_cursor_before_timestamp(oldest_timestamp, _format_zsxq_time)

def _official_start_cursor_from_oldest(
    db: ZSXQDatabase,
    task_id: str,
    allow_empty: bool,
) -> OfficialStartCursorResult:
    return official_start_cursor_from_oldest(
        db.get_timestamp_range_info(),
        task_id,
        allow_empty,
        add_task_log,
        cursor_before_timestamp=_official_cursor_before_timestamp,
    )

def _official_start_cursor_for_group_oldest(
    group_id: str,
    task_id: str,
    allow_empty: bool,
) -> OfficialStartCursorResult:
    db = ZSXQDatabase(group_id)
    return _official_start_cursor_from_oldest(db, task_id, allow_empty=allow_empty)

def _run_official_incremental_pages_from_oldest(
    task_id: str,
    group_id: str,
    pages: int,
    per_page: int,
    empty_failure_message: str,
) -> None:
    start_cursor = _official_start_cursor_for_group_oldest(group_id, task_id, allow_empty=False)
    if start_cursor.is_empty_failure:
        fail_task_with_message_unless_stopped(task_id, empty_failure_message)
        return
    _run_official_crawl_pages_task(
        task_id,
        group_id,
        pages,
        per_page,
        "incremental",
        start_cursor=start_cursor.cursor,
    )

def _run_official_all_pages_from_oldest(task_id: str, group_id: str) -> None:
    start_cursor = _official_start_cursor_for_group_oldest(group_id, task_id, allow_empty=True)
    _run_official_crawl_pages_task(task_id, group_id, None, 20, "all", start_cursor=start_cursor.cursor)

def _run_official_crawl_time_range_task(
    task_id: str,
    group_id: str,
    request: Any,
    start_dt: datetime,
    end_dt: datetime,
) -> None:
    run_official_crawl_time_range(
        _official_topic_crawl_runtime(),
        OfficialCrawlTimeRangeTarget(task_id, group_id, request, start_dt, end_dt),
    )

def _run_official_crawl_pages_task(
    task_id: str,
    group_id: str,
    pages: Optional[int],
    per_page: int,
    mode: str,
    start_cursor: Optional[str] = None,
) -> None:
    run_official_crawl_pages(
        _official_topic_crawl_runtime(),
        OfficialCrawlPagesTarget(task_id, group_id, pages, per_page, mode, start_cursor),
    )

def run_crawl_historical_task(
    task_id: str,
    group_id: str,
    pages: int,
    per_page: int,
    crawl_settings: Any = None,
):
    """后台执行历史数据爬取任务"""
    try:

        if is_task_stopped(task_id):
            return

        update_task(task_id, "running", f"开始爬取历史数据 {pages} 页...")
        add_task_log(task_id, f"🚀 开始获取历史数据，{pages} 页，每页 {per_page} 条")

        if _uses_official_topic_source(crawl_settings):
            add_task_log(task_id, "🔁 使用官方历史增量采集流程（MCP HTTP）")
            _run_official_incremental_pages_from_oldest(
                task_id,
                group_id,
                pages,
                per_page,
                "官方历史增量采集失败: 数据库为空",
            )
            return

        if is_task_stopped(task_id):
            return

        crawler = _prepare_legacy_crawler(task_id, group_id, crawl_settings)

        if is_task_stopped(task_id):
            _log_init_stopped(task_id)
            return

        _log_crawler_startup(task_id)

        if is_task_stopped(task_id):
            return

        result = crawler.crawl_incremental(pages, per_page)

        if is_task_stopped(task_id):
            return

        if result and result.get("expired"):
            _mark_expired_task(task_id, result)
            return

        add_task_log(task_id, f"✅ 获取完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        complete_task_unless_stopped(task_id, "历史数据爬取完成", result)
    except Exception as e:
        fail_task_with_message_unless_stopped(
            task_id,
            f"爬取失败: {str(e)}",
            log_message=f"❌ 获取失败: {str(e)}",
        )
    finally:
        unregister_task_crawler(task_id)

def run_crawl_all_task(task_id: str, group_id: str, crawl_settings: Any = None):
    try:

        update_task(task_id, "running", "开始全量爬取...")
        add_task_log(task_id, "🚀 开始全量爬取...")
        add_task_log(task_id, "⚠️ 警告：此模式将持续爬取直到没有数据，可能需要很长时间")

        if _uses_official_topic_source(crawl_settings):
            add_task_log(task_id, "🔁 使用官方全量采集流程（MCP HTTP）")
            _run_official_all_pages_from_oldest(task_id, group_id)
            return

        crawler = _prepare_legacy_crawler(task_id, group_id, crawl_settings)

        if is_task_stopped(task_id):
            _log_init_stopped(task_id)
            return

        _log_crawler_startup(task_id)

        if is_task_stopped(task_id):
            return

        db_stats = crawler.db.get_database_stats()
        add_task_log(task_id, f"📊 当前数据库状态: 话题: {db_stats.get('topics', 0)}, 用户: {db_stats.get('users', 0)}")

        if is_task_stopped(task_id):
            return

        add_task_log(task_id, "🌊 开始无限历史爬取...")
        result = crawler.crawl_all_historical(per_page=20, auto_confirm=True)

        if is_task_stopped(task_id):
            return

        if result and result.get("expired"):
            _mark_expired_task(task_id, result)
            return

        add_task_log(task_id, "🎉 全量爬取完成！")
        add_task_log(task_id, f"📊 最终统计: 新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}, 总页数: {result.get('pages', 0)}")
        complete_task_unless_stopped(task_id, "全量爬取完成", result)
    except Exception as e:
        fail_task_with_message_unless_stopped(
            task_id,
            f"全量爬取失败: {str(e)}",
            log_message=f"❌ 全量爬取失败: {str(e)}",
        )
    finally:
        unregister_task_crawler(task_id)

def run_crawl_incremental_task(
    task_id: str,
    group_id: str,
    pages: int,
    per_page: int,
    crawl_settings: Any = None,
):
    try:

        update_task(task_id, "running", "开始增量爬取...")

        if _uses_official_topic_source(crawl_settings):
            add_task_log(task_id, "🔁 使用官方增量采集流程（MCP HTTP）")
            _run_official_incremental_pages_from_oldest(
                task_id,
                group_id,
                pages,
                per_page,
                "官方增量采集失败: 数据库为空",
            )
            return

        crawler = _prepare_legacy_crawler(task_id, group_id, crawl_settings)

        if is_task_stopped(task_id):
            _log_init_stopped(task_id)
            return

        _log_crawler_startup(task_id)

        result = crawler.crawl_incremental(pages, per_page)

        if is_task_stopped(task_id):
            return

        if result and result.get("expired"):
            _mark_expired_task(task_id, result)
            return

        add_task_log(task_id, f"✅ 增量爬取完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        complete_task_unless_stopped(task_id, "增量爬取完成", result)
    except Exception as e:
        fail_task_with_message_unless_stopped(
            task_id,
            f"增量爬取失败: {str(e)}",
            log_message=f"❌ 增量爬取失败: {str(e)}",
        )
    finally:
        unregister_task_crawler(task_id)

def run_crawl_latest_task(task_id: str, group_id: str, crawl_settings: Any = None):
    try:

        update_task(task_id, "running", "开始获取最新记录...")

        if _uses_official_topic_source(crawl_settings):
            add_task_log(task_id, "🔁 使用官方最新采集流程（MCP HTTP）")
            _run_official_crawl_pages_task(task_id, group_id, None, 20, "latest")
            return

        crawler = _prepare_legacy_crawler(task_id, group_id, crawl_settings)

        if is_task_stopped(task_id):
            _log_init_stopped(task_id)
            return

        _log_crawler_startup(task_id)

        result = crawler.crawl_latest_until_complete()

        if is_task_stopped(task_id):
            return

        if result and result.get("expired"):
            _mark_expired_task(task_id, result)
            return

        add_task_log(task_id, f"✅ 获取最新记录完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        complete_task_unless_stopped(task_id, "获取最新记录完成", result)
    except Exception as e:
        fail_task_with_message_unless_stopped(
            task_id,
            f"获取最新记录失败: {str(e)}",
            log_message=f"❌ 获取最新记录失败: {str(e)}",
        )
    finally:
        unregister_task_crawler(task_id)

def run_crawl_time_range_task(task_id: str, group_id: str, request: Any):
    """后台执行“按时间区间爬取”任务：仅导入位于区间 [startTime, endTime] 内的话题"""
    try:
        bj_tz = timezone(timedelta(hours=8))
        now_bj = datetime.now(bj_tz)
        start_dt, end_dt = _resolve_time_range(request, now_bj)

        update_task(task_id, "running", "开始按时间区间爬取...")
        add_task_log(task_id, f"🗓️ 时间范围: {start_dt.isoformat()} ~ {end_dt.isoformat()}")

        if _uses_official_topic_source(request):
            _run_official_crawl_time_range_task(task_id, group_id, request, start_dt, end_dt)
            return

        crawler = _prepare_legacy_crawler(task_id, group_id, request, require_overrides=True)

        legacy_result = _run_legacy_time_range_pages(task_id, crawler, request, start_dt, end_dt)
        if legacy_result.expired:
            return

        complete_task_unless_stopped(task_id, "时间区间爬取完成", legacy_result.stats)
    except Exception as e:
        fail_task_with_message_unless_stopped(
            task_id,
            f"时间区间爬取失败: {str(e)}",
            log_message=f"❌ 时间区间爬取失败: {str(e)}",
        )
    finally:
        unregister_task_crawler(task_id)
