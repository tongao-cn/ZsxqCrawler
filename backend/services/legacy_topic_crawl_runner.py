"""Legacy topic crawl runner for non-time-range crawl workflows."""

from __future__ import annotations

from typing import Any, Callable, NamedTuple, Optional


INIT_STOPPED_MESSAGE = "🛑 任务在初始化过程中被停止"
CRAWLER_STARTUP_LOGS = ("📡 连接到知识星球API...", "🔍 检查数据库状态...")

LEGACY_CRAWL_HISTORICAL = "historical"
LEGACY_CRAWL_ALL = "all"
LEGACY_CRAWL_INCREMENTAL = "incremental"
LEGACY_CRAWL_LATEST = "latest"

TaskUpdater = Callable[[str, str, str], None]
TaskLogWriter = Callable[[str, str], None]
TaskStopChecker = Callable[[str], bool]
TaskCompletionWriter = Callable[[str, str, dict[str, Any]], None]
TaskFailureWriter = Callable[..., None]
LegacyCrawlerFactory = Callable[[str, str, Any], Any]


class LegacyTopicCrawlRuntime(NamedTuple):
    update_task: TaskUpdater
    add_task_log: TaskLogWriter
    task_stopped: TaskStopChecker
    complete_task: TaskCompletionWriter
    fail_task: TaskFailureWriter
    crawler_factory: LegacyCrawlerFactory


class LegacyTopicCrawlTarget(NamedTuple):
    task_id: str
    group_id: str
    mode: str
    crawl_settings: Any = None
    pages: Optional[int] = None
    per_page: Optional[int] = None


def log_legacy_crawler_startup(task_id: str, add_task_log: TaskLogWriter) -> None:
    for message in CRAWLER_STARTUP_LOGS:
        add_task_log(task_id, message)


def log_legacy_init_stopped(task_id: str, add_task_log: TaskLogWriter) -> None:
    add_task_log(task_id, INIT_STOPPED_MESSAGE)


def mark_legacy_expired_task(
    task_id: str,
    result: dict[str, Any],
    fail_task: TaskFailureWriter,
    default_message: str = "成员体验已到期",
) -> None:
    message = result.get("message", default_message)
    fail_task(
        task_id,
        "会员已过期",
        {"expired": True, "code": result.get("code"), "message": result.get("message")},
        log_message=f"❌ 会员已过期: {message}",
    )


def legacy_task_stopped_with_log(
    task_id: str,
    task_stopped: TaskStopChecker,
    add_task_log: TaskLogWriter,
) -> bool:
    if not task_stopped(task_id):
        return False
    add_task_log(task_id, "🛑 任务已停止")
    return True


def _running_message(target: LegacyTopicCrawlTarget) -> str:
    if target.mode == LEGACY_CRAWL_HISTORICAL:
        return f"开始爬取历史数据 {target.pages} 页..."
    if target.mode == LEGACY_CRAWL_ALL:
        return "开始全量爬取..."
    if target.mode == LEGACY_CRAWL_INCREMENTAL:
        return "开始增量爬取..."
    return "开始获取最新记录..."


def _opening_logs(target: LegacyTopicCrawlTarget) -> tuple[str, ...]:
    if target.mode == LEGACY_CRAWL_HISTORICAL:
        return (f"🚀 开始获取历史数据，{target.pages} 页，每页 {target.per_page} 条",)
    if target.mode == LEGACY_CRAWL_ALL:
        return (
            "🚀 开始全量爬取...",
            "⚠️ 警告：此模式将持续爬取直到没有数据，可能需要很长时间",
        )
    return ()


def _failure_message_prefix(mode: str) -> str:
    if mode == LEGACY_CRAWL_ALL:
        return "全量爬取失败"
    if mode == LEGACY_CRAWL_INCREMENTAL:
        return "增量爬取失败"
    if mode == LEGACY_CRAWL_LATEST:
        return "获取最新记录失败"
    return "爬取失败"


def _failure_log_prefix(mode: str) -> str:
    if mode == LEGACY_CRAWL_ALL:
        return "❌ 全量爬取失败"
    if mode == LEGACY_CRAWL_INCREMENTAL:
        return "❌ 增量爬取失败"
    if mode == LEGACY_CRAWL_LATEST:
        return "❌ 获取最新记录失败"
    return "❌ 获取失败"


def _completion_message(mode: str) -> str:
    if mode == LEGACY_CRAWL_HISTORICAL:
        return "历史数据爬取完成"
    if mode == LEGACY_CRAWL_ALL:
        return "全量爬取完成"
    if mode == LEGACY_CRAWL_INCREMENTAL:
        return "增量爬取完成"
    return "获取最新记录完成"


def _log_completion(
    runtime: LegacyTopicCrawlRuntime,
    target: LegacyTopicCrawlTarget,
    result: dict[str, Any],
) -> None:
    if target.mode == LEGACY_CRAWL_ALL:
        runtime.add_task_log(target.task_id, "🎉 全量爬取完成！")
        runtime.add_task_log(
            target.task_id,
            (
                f"📊 最终统计: 新增话题: {result.get('new_topics', 0)}, "
                f"更新话题: {result.get('updated_topics', 0)}, 总页数: {result.get('pages', 0)}"
            ),
        )
        return

    if target.mode == LEGACY_CRAWL_LATEST:
        prefix = "✅ 获取最新记录完成！"
    elif target.mode == LEGACY_CRAWL_INCREMENTAL:
        prefix = "✅ 增量爬取完成！"
    else:
        prefix = "✅ 获取完成！"

    runtime.add_task_log(
        target.task_id,
        f"{prefix}新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}",
    )


def _run_crawler(crawler: Any, target: LegacyTopicCrawlTarget) -> dict[str, Any]:
    if target.mode == LEGACY_CRAWL_ALL:
        return crawler.crawl_all_historical(per_page=20, auto_confirm=True)
    if target.mode == LEGACY_CRAWL_LATEST:
        return crawler.crawl_latest_until_complete()
    return crawler.crawl_incremental(target.pages, target.per_page)


def _log_database_stats(
    runtime: LegacyTopicCrawlRuntime,
    target: LegacyTopicCrawlTarget,
    crawler: Any,
) -> None:
    db_stats = crawler.db.get_database_stats()
    runtime.add_task_log(
        target.task_id,
        f"📊 当前数据库状态: 话题: {db_stats.get('topics', 0)}, 用户: {db_stats.get('users', 0)}",
    )


def _should_skip_before_start(runtime: LegacyTopicCrawlRuntime, target: LegacyTopicCrawlTarget) -> bool:
    return target.mode == LEGACY_CRAWL_HISTORICAL and runtime.task_stopped(target.task_id)


def _should_stop_after_startup(runtime: LegacyTopicCrawlRuntime, target: LegacyTopicCrawlTarget) -> bool:
    return target.mode in {LEGACY_CRAWL_HISTORICAL, LEGACY_CRAWL_ALL} and runtime.task_stopped(target.task_id)


def run_legacy_topic_crawl(
    runtime: LegacyTopicCrawlRuntime,
    target: LegacyTopicCrawlTarget,
) -> None:
    try:
        if _should_skip_before_start(runtime, target):
            return

        runtime.update_task(target.task_id, "running", _running_message(target))
        for message in _opening_logs(target):
            runtime.add_task_log(target.task_id, message)

        crawler = runtime.crawler_factory(target.task_id, target.group_id, target.crawl_settings)

        if runtime.task_stopped(target.task_id):
            log_legacy_init_stopped(target.task_id, runtime.add_task_log)
            return

        log_legacy_crawler_startup(target.task_id, runtime.add_task_log)

        if _should_stop_after_startup(runtime, target):
            return

        if target.mode == LEGACY_CRAWL_ALL:
            _log_database_stats(runtime, target, crawler)
            if runtime.task_stopped(target.task_id):
                return
            runtime.add_task_log(target.task_id, "🌊 开始无限历史爬取...")

        result = _run_crawler(crawler, target)

        if runtime.task_stopped(target.task_id):
            return

        if result and result.get("expired"):
            mark_legacy_expired_task(target.task_id, result, runtime.fail_task)
            return

        _log_completion(runtime, target, result)
        runtime.complete_task(target.task_id, _completion_message(target.mode), result)
    except Exception as exc:
        runtime.fail_task(
            target.task_id,
            f"{_failure_message_prefix(target.mode)}: {str(exc)}",
            log_message=f"{_failure_log_prefix(target.mode)}: {str(exc)}",
        )
