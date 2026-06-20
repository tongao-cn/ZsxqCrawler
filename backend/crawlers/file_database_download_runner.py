"""Database-backed file download runner for ZSXQ file downloads."""

from __future__ import annotations

from typing import Any, Dict, NamedTuple, Optional, Protocol

from backend.crawlers.zsxq_file_downloader_helpers import (
    database_download_completion_messages,
    database_download_effective_last_days,
    database_download_filter_messages,
    database_download_file_info,
    database_download_query_plan,
    database_download_start_messages,
    database_download_time_range_message,
    download_query_group_id,
    download_result_stats,
)


class DatabaseDownloadRuntime(Protocol):
    group_id: Any
    file_db: Any

    def log(self, message: str) -> None:
        ...

    def check_stop(self) -> bool:
        ...

    def download_file(self, file_info: Dict[str, Any]) -> Any:
        ...

    def check_long_delay(self) -> Any:
        ...

    def download_delay(self) -> Any:
        ...


class DatabaseDownloadRow(NamedTuple):
    file_id: Any
    file_name: Any
    file_size: Any
    download_count: Any
    create_time: Any


class DatabaseDownloadRowsTarget(NamedTuple):
    files_to_download: list[DatabaseDownloadRow]


class DatabaseDownloadAfterInitialStopTarget(NamedTuple):
    query_plan: Dict[str, Any]
    sort_by: str


class DatabaseDownloadTarget(NamedTuple):
    max_files: Optional[int]
    status_filter: str
    sort_by: str
    start_date: Optional[str]
    end_date: Optional[str]
    last_days: Optional[int]
    kwargs: Dict[str, Any]


def database_download_row(row: Any) -> DatabaseDownloadRow:
    return DatabaseDownloadRow(*row)


def record_database_download_result(result: Any, stats: Dict[str, int]) -> str:
    if result == "skipped":
        stats["skipped"] += 1
        return "skipped"
    if result:
        stats["downloaded"] += 1
        return "downloaded"
    stats["failed"] += 1
    return "failed"


def fetch_database_download_rows(
    runtime: DatabaseDownloadRuntime,
    query_plan: Dict[str, Any],
) -> list[DatabaseDownloadRow]:
    runtime.file_db.cursor.execute(query_plan["query"], query_plan["params"])
    return [database_download_row(row) for row in runtime.file_db.cursor.fetchall()]


def apply_database_download_result(
    runtime: DatabaseDownloadRuntime,
    result: Any,
    position: int,
    total_files: int,
    stats: Dict[str, int],
) -> None:
    result_status = record_database_download_result(result, stats)
    if result_status == "skipped":
        runtime.log("   ⚠️ 文件已跳过")
    elif result_status == "downloaded":
        runtime.check_long_delay()
        if position < total_files:
            runtime.download_delay()
    else:
        runtime.log("   ❌ 下载失败")


def download_database_file_row(
    runtime: DatabaseDownloadRuntime,
    file_row: DatabaseDownloadRow,
    position: int,
    total_files: int,
    stats: Dict[str, int],
) -> None:
    runtime.log(f"【{position}/{total_files}】{file_row.file_name}")
    runtime.log(
        f"   📊 文件ID: {file_row.file_id}, 大小: {file_row.file_size/1024:.1f}KB, "
        f"下载次数: {file_row.download_count}"
    )

    file_info = database_download_file_info(
        file_row.file_id,
        file_row.file_name,
        file_row.file_size,
        file_row.download_count,
    )

    result = runtime.download_file(file_info)
    apply_database_download_result(runtime, result, position, total_files, stats)


def download_database_file_rows(
    runtime: DatabaseDownloadRuntime,
    files_to_download: list[DatabaseDownloadRow],
    stats: Dict[str, int],
) -> None:
    total_files = len(files_to_download)
    for position, file_row in enumerate(files_to_download, 1):
        if runtime.check_stop():
            runtime.log("🛑 下载任务被停止")
            break

        try:
            download_database_file_row(runtime, file_row, position, total_files, stats)
        except KeyboardInterrupt:
            runtime.log("⏹️ 用户中断下载")
            break
        except Exception as e:
            runtime.log(f"   ❌ 处理文件异常: {e}")
            stats["failed"] += 1
            continue


def should_stop_database_download_initially(runtime: DatabaseDownloadRuntime) -> bool:
    if runtime.check_stop():
        runtime.log("🛑 任务被停止")
        return True

    return False


def database_download_query_plan_with_effective_days(
    runtime: DatabaseDownloadRuntime,
    target: DatabaseDownloadTarget,
) -> tuple[Dict[str, Any], Any]:
    last_days = database_download_effective_last_days(target.last_days, target.kwargs.get("recent_days"))

    query_plan = database_download_query_plan(
        download_query_group_id(runtime.group_id),
        max_files=target.max_files,
        status_filter=target.status_filter,
        sort_by=target.sort_by,
        start_date=target.start_date,
        end_date=target.end_date,
        last_days=last_days,
        legacy_order_by=target.kwargs.get("order_by"),
    )
    return query_plan, last_days


def prepare_database_download_query_plan(
    runtime: DatabaseDownloadRuntime,
    target: DatabaseDownloadTarget,
) -> Dict[str, Any]:
    query_plan, last_days = database_download_query_plan_with_effective_days(runtime, target)
    normalized_start = query_plan["normalized_start"]
    normalized_end = query_plan["normalized_end"]
    sort_by = query_plan["sort_by"]

    for message in database_download_filter_messages(normalized_start, normalized_end, last_days, sort_by):
        runtime.log(message)

    return query_plan


def log_database_download_rows_summary(
    runtime: DatabaseDownloadRuntime,
    files_to_download: list[DatabaseDownloadRow],
    sort_by: str,
) -> None:
    if not files_to_download:
        runtime.log("📭 数据库中没有符合条件的文件可下载")
        return

    runtime.log(f"📋 找到 {len(files_to_download)} 个待下载文件")
    time_range_message = database_download_time_range_message(files_to_download, sort_by)
    if time_range_message:
        runtime.log(time_range_message)


def log_database_download_completion(runtime: DatabaseDownloadRuntime, stats: Dict[str, int]) -> None:
    for message in database_download_completion_messages(stats):
        runtime.log(message)


def log_database_download_start(
    runtime: DatabaseDownloadRuntime,
    max_files: Optional[int],
    status_filter: str,
) -> None:
    for message in database_download_start_messages(max_files, status_filter):
        runtime.log(message)


def run_database_download_rows(
    runtime: DatabaseDownloadRuntime,
    files_to_download: list[DatabaseDownloadRow],
) -> Dict[str, int]:
    return run_database_download_rows_target(
        runtime,
        DatabaseDownloadRowsTarget(files_to_download),
    )


def run_database_download_rows_target(
    runtime: DatabaseDownloadRuntime,
    target: DatabaseDownloadRowsTarget,
) -> Dict[str, int]:
    stats = download_result_stats(len(target.files_to_download))

    download_database_file_rows(runtime, target.files_to_download, stats)
    log_database_download_completion(runtime, stats)

    return stats


def run_database_download_after_initial_stop(
    runtime: DatabaseDownloadRuntime,
    query_plan: Dict[str, Any],
    sort_by: str,
) -> Dict[str, int]:
    return run_database_download_after_initial_stop_target(
        runtime,
        DatabaseDownloadAfterInitialStopTarget(query_plan, sort_by),
    )


def run_database_download_after_initial_stop_target(
    runtime: DatabaseDownloadRuntime,
    target: DatabaseDownloadAfterInitialStopTarget,
) -> Dict[str, int]:
    files_to_download = fetch_database_download_rows(runtime, target.query_plan)

    log_database_download_rows_summary(runtime, files_to_download, target.sort_by)
    if not files_to_download:
        return download_result_stats()

    return run_database_download_rows(runtime, files_to_download)


def run_database_file_download(
    runtime: DatabaseDownloadRuntime,
    target: DatabaseDownloadTarget,
) -> Dict[str, int]:
    log_database_download_start(runtime, target.max_files, target.status_filter)

    query_plan = prepare_database_download_query_plan(runtime, target)
    sort_by = query_plan["sort_by"]

    if should_stop_database_download_initially(runtime):
        return download_result_stats()

    return run_database_download_after_initial_stop(runtime, query_plan, sort_by)
