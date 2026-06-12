from __future__ import annotations

import os
from datetime import time, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from backend.core.account_context import get_cookie_for_group
from backend.crawlers.official_topic_client import (
    OfficialTopicClient,
    normalize_official_topic,
    official_payload_topics,
)
from backend.crawlers.topic_crawler import ZSXQTopicCrawler
from backend.schemas.crawl import CrawlTimeRangeRequest
from backend.services.task_runtime import (
    add_task_log,
    is_task_stopped,
    register_task_crawler,
    unregister_task_crawler,
    update_task,
)
from backend.storage.zsxq_database import ZSXQDatabase


INIT_STOPPED_MESSAGE = "🛑 任务在初始化过程中被停止"

CRAWLER_STARTUP_LOGS = ("📡 连接到知识星球API...", "🔍 检查数据库状态...")
# official means the MCP HTTP flow; "cli" is accepted only as an old spelling
# and does not shell out to zsxq-cli.
OFFICIAL_TOPIC_SOURCE_ALIASES = {"official", "cli", "mcp"}
# legacy means the cookie-based ZSXQTopicCrawler fallback.
LEGACY_TOPIC_SOURCE_ALIASES = {"legacy", "crawler", "cookie"}
OFFICIAL_CRAWL_COMPLETION_MESSAGES = {
    "latest": "官方最新采集完成",
    "incremental": "官方增量采集完成",
    "all": "官方全量采集完成",
}

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

def _normalize_topic_source(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip().lower()
    if not text:
        return None
    if text in OFFICIAL_TOPIC_SOURCE_ALIASES:
        return "official"
    if text in LEGACY_TOPIC_SOURCE_ALIASES:
        return "legacy"
    return None

def _resolve_topic_source(request: Any) -> str:
    return (
        _normalize_topic_source(getattr(request, "topicSource", None))
        or _normalize_topic_source(os.getenv("ZSXQ_TOPIC_SOURCE"))
        or "official"
    )

def _uses_official_topic_source(request: Any) -> bool:
    return _resolve_topic_source(request) == "official"

def _mark_expired_task(task_id: str, result: dict[str, Any], default_message: str = "成员体验已到期") -> None:
    message = result.get("message", default_message)
    add_task_log(task_id, f"❌ 会员已过期: {message}")
    update_task(task_id, "failed", "会员已过期", {"expired": True, "code": result.get("code"), "message": result.get("message")})

def _is_date_only(value: Optional[str]) -> bool:
    text = (value or "").strip()
    return len(text) == 10 and text[4] == "-" and text[7] == "-"

def _parse_user_time(value: Optional[str], date_end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    try:
        if _is_date_only(text):
            dt = datetime.combine(datetime.strptime(text, "%Y-%m-%d").date(), time.max if date_end else time.min)
            return dt.replace(tzinfo=timezone(timedelta(hours=8)))
        if "T" in text and len(text) == 16:
            text = text + ":00"
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        if len(text) >= 24 and (text[-5] in ["+", "-"]) and text[-3] != ":":
            text = text[:-2] + ":" + text[-2:]
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return dt
    except Exception:
        return None

def _resolve_time_range(request: CrawlTimeRangeRequest, now_bj: datetime) -> tuple[datetime, datetime]:
    start_dt = _parse_user_time(request.startTime)
    end_dt = _parse_user_time(request.endTime, date_end=True) if request.endTime else None

    if request.lastDays and request.lastDays > 0:
        if end_dt is None:
            end_dt = now_bj
        start_dt = end_dt - timedelta(days=request.lastDays)

    if end_dt is None:
        end_dt = now_bj
    if start_dt is None:
        start_dt = end_dt - timedelta(days=30)

    if start_dt > end_dt:
        if _is_date_only(request.startTime) and _is_date_only(request.endTime):
            start_dt = _parse_user_time(request.endTime)
            end_dt = _parse_user_time(request.startTime, date_end=True)
        else:
            start_dt, end_dt = end_dt, start_dt

    return start_dt, end_dt

def _format_zsxq_time(dt: datetime) -> str:
    return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"

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

def _topic_time(topic: dict[str, Any]) -> Optional[datetime]:
    ts = topic.get("create_time")
    if not ts:
        return None
    try:
        ts_fixed = ts.replace("+0800", "+08:00") if ts.endswith("+0800") else ts
        return datetime.fromisoformat(ts_fixed)
    except Exception:
        return None

def _filter_official_topics_by_time_range(
    topics: list[dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[list[dict[str, Any]], Optional[datetime]]:
    filtered: list[dict[str, Any]] = []
    oldest_dt = None
    for topic in topics:
        dt = _topic_time(topic)
        if dt:
            oldest_dt = dt
            if start_dt <= dt <= end_dt:
                filtered.append(topic)
    return filtered, oldest_dt

def _filter_legacy_topics_by_time_range(
    topics: list[dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[list[dict[str, Any]], Optional[datetime]]:
    filtered: list[dict[str, Any]] = []
    last_time_dt_in_page = None
    for topic in topics:
        dt = _topic_time(topic)
        if dt:
            last_time_dt_in_page = dt
            if start_dt <= dt <= end_dt:
                filtered.append(topic)
    return filtered, last_time_dt_in_page

def _legacy_next_end_time(topics: list[dict[str, Any]], timestamp_offset_ms: int) -> Optional[str]:
    oldest_in_page = topics[-1].get("create_time")
    try:
        dt_oldest = datetime.fromisoformat(oldest_in_page.replace("+0800", "+08:00"))
        dt_oldest = dt_oldest - timedelta(milliseconds=timestamp_offset_ms)
        return dt_oldest.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"
    except Exception:
        return oldest_in_page

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
) -> int:
    retry += 1
    total_stats["errors"] += 1
    add_task_log(task_id, f"❌ 页面获取失败 (重试{retry}/{max_retries_per_page})")
    return retry

def _mark_legacy_time_range_expired(task_id: str, data: dict[str, Any]) -> None:
    add_task_log(task_id, f"❌ 会员已过期: {data.get('message')}")
    update_task(task_id, "failed", "会员已过期", data)

def _legacy_time_range_page_empty(task_id: str, topics: list[dict[str, Any]]) -> bool:
    if topics:
        return False
    add_task_log(task_id, "📭 无更多数据，任务结束")
    return True

def _legacy_time_range_task_stopped(task_id: str) -> bool:
    if not is_task_stopped(task_id):
        return False
    add_task_log(task_id, "🛑 任务已停止")
    return True

def _legacy_time_range_page_failed(task_id: str, page_processed: bool) -> bool:
    if page_processed:
        return False
    add_task_log(task_id, "🚫 当前页面达到最大重试次数，终止任务")
    return True

def _legacy_time_range_reached_before_start(
    last_time_dt_in_page: Optional[datetime],
    start_dt: datetime,
) -> bool:
    return last_time_dt_in_page is not None and last_time_dt_in_page < start_dt

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
) -> None:
    add_task_log(task_id, f"📄 本页获取 {len(topics)} 个话题，区间内 {len(filtered)} 个")

def _empty_legacy_time_range_stats() -> dict[str, int]:
    return {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0}

def _query_group_id(group_id: str) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value

def _official_import_topic(db: ZSXQDatabase, group_id: str, topic_data: dict[str, Any]) -> str:
    topic_id = topic_data.get("topic_id")
    exists = _official_topic_exists(db, group_id, topic_id)
    if not db.import_topic_data(topic_data):
        return "error"
    return "updated" if exists else "new"

def _official_topic_exists(db: ZSXQDatabase, group_id: str, topic_id: Any) -> bool:
    db.cursor.execute(
        "SELECT topic_id FROM topics WHERE topic_id = ? AND group_id = ?",
        (topic_id, _query_group_id(group_id)),
    )
    return db.cursor.fetchone() is not None

def _official_topic_id(topic: dict[str, Any]) -> int:
    return int(topic.get("topic_id") or 0)

def _official_topic_comments_count(topic: dict[str, Any]) -> int:
    return int((topic.get("counts") or {}).get("comments") or 0)

def _add_official_import_result(stats: dict[str, int], imported: str) -> None:
    if imported == "new":
        stats["new_topics"] += 1
    elif imported == "updated":
        stats["updated_topics"] += 1
    else:
        stats["errors"] += 1

def _new_official_topics(db: ZSXQDatabase, group_id: str, topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        topic
        for topic in topics
        if not _official_topic_exists(db, group_id, _official_topic_id(topic))
    ]

def _fetch_official_comments(
    client: OfficialTopicClient,
    topic_id: int,
    comments_count: int,
    task_id: str,
) -> list[dict[str, Any]]:
    if comments_count <= 0:
        return []
    try:
        comments = client.get_topic_comments(topic_id)
        add_task_log(task_id, f"📝 话题 {topic_id} 官方评论拉取 {len(comments)}/{comments_count} 条")
        return comments
    except Exception as exc:
        add_task_log(task_id, f"⚠️ 话题 {topic_id} 官方评论拉取失败: {exc}")
        return []

def _official_import_topics(
    db: ZSXQDatabase,
    client: OfficialTopicClient,
    group_id: str,
    topics: list[dict[str, Any]],
    task_id: str,
) -> dict[str, int]:
    stats = {"new_topics": 0, "updated_topics": 0, "errors": 0}
    for topic in topics:
        topic_id = _official_topic_id(topic)
        comments_count = _official_topic_comments_count(topic)
        comments = _fetch_official_comments(client, topic_id, comments_count, task_id)
        normalized = normalize_official_topic(topic, group_id, comments=comments if comments_count else None)
        imported = _official_import_topic(db, group_id, normalized)
        _add_official_import_result(stats, imported)
    db.conn.commit()
    return stats

def _empty_official_crawl_stats() -> dict[str, Any]:
    return {
        "new_topics": 0,
        "updated_topics": 0,
        "errors": 0,
        "pages": 0,
        "duplicates": 0,
        "source": "official",
    }

def _add_official_page_stats(total_stats: dict[str, Any], page_stats: dict[str, int]) -> None:
    total_stats["new_topics"] += page_stats["new_topics"]
    total_stats["updated_topics"] += page_stats["updated_topics"]
    total_stats["errors"] += page_stats["errors"]
    total_stats["pages"] += 1

def _dedupe_official_page_topics(
    topics: list[dict[str, Any]],
    seen_topic_ids: set[int],
    total_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    unique_topics = []
    for topic in topics:
        topic_id = _official_topic_id(topic)
        if topic_id in seen_topic_ids:
            total_stats["duplicates"] += 1
            continue
        seen_topic_ids.add(topic_id)
        unique_topics.append(topic)
    return unique_topics

def _official_page_cursor(payload: dict[str, Any], current_cursor: Optional[str]) -> Optional[str]:
    next_cursor = payload.get("next_end_time")
    if not next_cursor or next_cursor == current_cursor:
        return None
    return next_cursor

def _official_next_page_cursor(payload: dict[str, Any], current_cursor: Optional[str]) -> Optional[str]:
    if not payload.get("has_more"):
        return None
    return _official_page_cursor(payload, current_cursor)

def _official_pages_remaining(pages: Optional[int], total_stats: dict[str, Any]) -> bool:
    return pages is None or total_stats["pages"] < pages

def _official_reached_before_start(oldest_dt: Optional[datetime], start_dt: datetime) -> bool:
    return bool(oldest_dt and oldest_dt < start_dt)

def _official_per_page_limit(per_page: Optional[int]) -> int:
    return min(per_page or 20, 30)

def _official_crawl_completion_message(mode: str) -> str:
    return OFFICIAL_CRAWL_COMPLETION_MESSAGES.get(mode, "官方采集完成")

def _official_cursor_before_timestamp(oldest_timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(oldest_timestamp.replace("+0800", "+08:00"))
        return _format_zsxq_time(dt - timedelta(milliseconds=1))
    except Exception:
        return oldest_timestamp

def _official_start_cursor_from_oldest(db: ZSXQDatabase, task_id: str, allow_empty: bool) -> Optional[str]:
    timestamp_info = db.get_timestamp_range_info()
    if not timestamp_info["has_data"]:
        if allow_empty:
            add_task_log(task_id, "📊 数据库为空，将从最新数据开始")
            return None
        add_task_log(task_id, "❌ 数据库中没有话题数据，请先采集最新或全量")
        return ""

    oldest_timestamp = timestamp_info["oldest_timestamp"]
    add_task_log(task_id, f"📊 当前最老时间戳: {oldest_timestamp}")
    return _official_cursor_before_timestamp(oldest_timestamp)

def _run_official_incremental_pages_from_oldest(
    task_id: str,
    group_id: str,
    pages: int,
    per_page: int,
    empty_failure_message: str,
) -> None:
    db = ZSXQDatabase(group_id)
    start_cursor = _official_start_cursor_from_oldest(db, task_id, allow_empty=False)
    if start_cursor == "":
        update_task(task_id, "failed", empty_failure_message)
        return
    _run_official_crawl_pages_task(task_id, group_id, pages, per_page, "incremental", start_cursor=start_cursor)

def _run_official_all_pages_from_oldest(task_id: str, group_id: str) -> None:
    db = ZSXQDatabase(group_id)
    start_cursor = _official_start_cursor_from_oldest(db, task_id, allow_empty=True)
    _run_official_crawl_pages_task(task_id, group_id, None, 20, "all", start_cursor=start_cursor)

def _run_official_crawl_time_range_task(
    task_id: str,
    group_id: str,
    request: Any,
    start_dt: datetime,
    end_dt: datetime,
) -> None:
    add_task_log(task_id, "🔁 使用官方话题采集流程（MCP HTTP）")
    client = OfficialTopicClient(log_callback=lambda message: add_task_log(task_id, message))
    db = ZSXQDatabase(group_id)
    per_page = _official_per_page_limit(request.perPage)
    if request.perPage and request.perPage > 30:
        add_task_log(task_id, "ℹ️ 官方接口单页上限按 30 处理")

    cursor = _format_zsxq_time(end_dt)
    seen_topic_ids: set[int] = set()
    total_stats = _empty_official_crawl_stats()

    while True:
        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务已停止")
            break

        payload = client.get_group_topics(group_id, limit=per_page, scope="all", end_time=cursor)
        topics = official_payload_topics(payload)
        if not topics:
            add_task_log(task_id, "📭 无更多数据，任务结束")
            break

        unique_topics = _dedupe_official_page_topics(topics, seen_topic_ids, total_stats)
        filtered, oldest_dt = _filter_official_topics_by_time_range(unique_topics, start_dt, end_dt)

        add_task_log(task_id, f"📄 官方本页获取 {len(topics)} 个话题，区间内 {len(filtered)} 个")

        page_stats = _official_import_topics(db, client, group_id, filtered, task_id)
        _add_official_page_stats(total_stats, page_stats)

        next_cursor = _official_next_page_cursor(payload, cursor)
        if not next_cursor:
            add_task_log(task_id, "✅ 官方分页已无更多数据")
            break
        cursor = next_cursor

        if _official_reached_before_start(oldest_dt, start_dt):
            add_task_log(task_id, "✅ 已到达起始时间之前，任务结束")
            break

    update_task(task_id, "completed", "官方时间区间采集完成", total_stats)

def _run_official_crawl_pages_task(
    task_id: str,
    group_id: str,
    pages: Optional[int],
    per_page: int,
    mode: str,
    start_cursor: Optional[str] = None,
) -> None:
    client = OfficialTopicClient(log_callback=lambda message: add_task_log(task_id, message))
    db = ZSXQDatabase(group_id)
    per_page = _official_per_page_limit(per_page)
    cursor = start_cursor
    total_stats = _empty_official_crawl_stats()
    seen_topic_ids: set[int] = set()

    while _official_pages_remaining(pages, total_stats):
        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务已停止")
            break

        payload = client.get_group_topics(group_id, limit=per_page, scope="all", end_time=cursor)
        topics = official_payload_topics(payload)
        if not topics:
            add_task_log(task_id, "📭 无更多数据，任务结束")
            break

        unique_topics = _dedupe_official_page_topics(topics, seen_topic_ids, total_stats)

        topics_to_import = unique_topics
        if mode == "latest":
            new_topics = _new_official_topics(db, group_id, unique_topics)
            add_task_log(task_id, f"📊 官方页面分析: {len(unique_topics)} 个话题，{len(new_topics)} 个新话题")
            if not new_topics:
                add_task_log(task_id, "✅ 本页话题均已存在，最新采集完成")
                break
            topics_to_import = new_topics
        else:
            add_task_log(task_id, f"📄 官方本页获取 {len(unique_topics)} 个话题")

        page_stats = _official_import_topics(db, client, group_id, topics_to_import, task_id)
        _add_official_page_stats(total_stats, page_stats)

        next_cursor = _official_next_page_cursor(payload, cursor)
        if not next_cursor:
            add_task_log(task_id, "✅ 官方分页已无更多数据")
            break
        cursor = next_cursor

    update_task(task_id, "completed", _official_crawl_completion_message(mode), total_stats)

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
        update_task(task_id, "completed", "历史数据爬取完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 获取失败: {str(e)}")
            update_task(task_id, "failed", f"爬取失败: {str(e)}")
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
        update_task(task_id, "completed", "全量爬取完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 全量爬取失败: {str(e)}")
            update_task(task_id, "failed", f"全量爬取失败: {str(e)}")
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

        add_task_log(task_id, f"✅ 增量爬取完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        update_task(task_id, "completed", "增量爬取完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 增量爬取失败: {str(e)}")
            update_task(task_id, "failed", f"增量爬取失败: {str(e)}")
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
        update_task(task_id, "completed", "获取最新记录完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 获取最新记录失败: {str(e)}")
            update_task(task_id, "failed", f"获取最新记录失败: {str(e)}")
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

        per_page = request.perPage or 20
        total_stats = _empty_legacy_time_range_stats()
        begin_time_param = _format_zsxq_time(start_dt)
        end_time_param = _format_zsxq_time(end_dt)
        max_retries_per_page = 10

        while True:
            if _legacy_time_range_task_stopped(task_id):
                break

            retry = 0
            page_processed = False
            reached_end = False
            last_time_dt_in_page = None

            while retry < max_retries_per_page:
                if is_task_stopped(task_id):
                    break

                data = _fetch_legacy_time_range_page(
                    crawler,
                    per_page,
                    begin_time_param,
                    end_time_param,
                )

                if data and isinstance(data, dict) and data.get("expired"):
                    _mark_legacy_time_range_expired(task_id, data)
                    return

                if not data:
                    retry = _record_legacy_time_range_fetch_failure(
                        task_id,
                        total_stats,
                        retry,
                        max_retries_per_page,
                    )
                    continue

                topics = _legacy_time_range_topics(data)
                if _legacy_time_range_page_empty(task_id, topics):
                    page_processed = True
                    reached_end = True
                    break

                filtered, last_time_dt_in_page = _filter_legacy_topics_by_time_range(topics, start_dt, end_dt)

                _log_legacy_time_range_page_summary(task_id, topics, filtered)

                _store_legacy_time_range_page(crawler, total_stats, filtered)
                page_processed = True

                end_time_param = _legacy_next_end_time(topics, crawler.timestamp_offset_ms)

                if _legacy_time_range_reached_before_start(last_time_dt_in_page, start_dt):
                    add_task_log(task_id, "✅ 已到达起始时间之前，任务结束")
                    break

                crawler.check_page_long_delay()
                break

            if _legacy_time_range_page_failed(task_id, page_processed):
                break

            if reached_end or _legacy_time_range_reached_before_start(last_time_dt_in_page, start_dt):
                break

        update_task(task_id, "completed", "时间区间爬取完成", total_stats)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 时间区间爬取失败: {str(e)}")
            update_task(task_id, "failed", f"时间区间爬取失败: {str(e)}")
    finally:
        unregister_task_crawler(task_id)
