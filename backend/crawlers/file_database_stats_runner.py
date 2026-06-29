"""Database statistics display runner for ZSXQ files."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from backend.core.console_output import safe_console_print as print
from backend.crawlers.file_database_queries import (
    database_stats_api_response_query,
    database_stats_time_range_query,
    database_stats_total_size_query,
    download_query_group_id,
)
from backend.crawlers.zsxq_file_downloader_helpers import (
    database_stats_table_emoji,
)
from backend.crawlers.zsxq_file_downloader_targets import (
    DatabaseStatsTimeRange,
    DatabaseStatsTotalSize,
    ShowDatabaseStatsEntryTarget,
    ShowDatabaseStatsTarget,
)
from backend.storage.postgres_core_schema import CORE_SCHEMA


class DatabaseStatsRuntime(Protocol):
    group_id: str
    file_db: Any


def database_stats_total_size_row(result: Any) -> Optional[DatabaseStatsTotalSize]:
    if not result:
        return None
    return DatabaseStatsTotalSize(result[0])


def database_stats_total_size(result: Any) -> Any:
    total_size = database_stats_total_size_row(result)
    if not total_size:
        return 0
    return total_size.total_size or 0


def database_stats_time_range_row(result: Any) -> Optional[DatabaseStatsTimeRange]:
    if not result or result[2] <= 0:
        return None

    min_time, max_time, time_count = result
    return DatabaseStatsTimeRange(min_time, max_time, time_count)


def database_stats_time_range(result: Any) -> Optional[DatabaseStatsTimeRange]:
    return database_stats_time_range_row(result)


def print_database_core_stats(stats: Dict[str, Any]) -> None:
    total_files = stats.get("files", 0)
    total_topics = stats.get("topics", 0)
    total_users = stats.get("users", 0)
    total_groups = stats.get("groups", 0)

    print("📈 核心数据:")
    print(f"   📄 文件数量: {total_files:,}")
    print(f"   💬 话题数量: {total_topics:,}")
    print(f"   👥 用户数量: {total_users:,}")
    print(f"   🏠 群组数量: {total_groups:,}")


def fetch_database_total_size(runtime: DatabaseStatsRuntime) -> Any:
    query, params = database_stats_total_size_query(download_query_group_id(runtime.group_id))
    runtime.file_db.cursor.execute(query, params)
    result = runtime.file_db.cursor.fetchone()
    return database_stats_total_size(result)


def fetch_database_time_range(runtime: DatabaseStatsRuntime) -> Optional[DatabaseStatsTimeRange]:
    query, params = database_stats_time_range_query(download_query_group_id(runtime.group_id))
    runtime.file_db.cursor.execute(query, params)
    time_result = runtime.file_db.cursor.fetchone()
    return database_stats_time_range(time_result)


def fetch_database_api_response_stats(runtime: DatabaseStatsRuntime) -> Any:
    runtime.file_db.cursor.execute(database_stats_api_response_query())
    return runtime.file_db.cursor.fetchall()


def print_database_total_size(runtime: DatabaseStatsRuntime) -> None:
    total_size = fetch_database_total_size(runtime)

    if total_size > 0:
        print(f"💾 总文件大小: {total_size/1024/1024:.2f} MB")


def print_database_table_stats(stats: Dict[str, Any]) -> None:
    print("\n📋 详细表统计:")
    for table_name, count in stats.items():
        if count > 0:
            emoji = database_stats_table_emoji(table_name)
            print(f"   {emoji} {table_name}: {count:,}")


def print_database_time_range(runtime: DatabaseStatsRuntime) -> None:
    time_range = fetch_database_time_range(runtime)
    if time_range:
        print("\n⏰ 文件时间范围:")
        print(f"   最早文件: {time_range.min_time}")
        print(f"   最新文件: {time_range.max_time}")
        print(f"   有时间信息的文件: {time_range.time_count:,}")


def print_database_api_response_stats(runtime: DatabaseStatsRuntime) -> None:
    api_stats = fetch_database_api_response_stats(runtime)

    if api_stats:
        print("\n📡 API响应统计:")
        for succeeded, count in api_stats:
            status = "成功" if succeeded else "失败"
            emoji = "✅" if succeeded else "❌"
            print(f"   {emoji} {status}: {count:,}")


def show_database_stats_entry(
    runtime: DatabaseStatsRuntime,
    target: ShowDatabaseStatsEntryTarget,
) -> None:
    print("\n📊 完整数据库统计信息:")
    print("=" * 60)
    print(f"📁 PostgreSQL schema: {CORE_SCHEMA}")

    stats = runtime.file_db.get_database_stats()

    show_database_stats_target(runtime, ShowDatabaseStatsTarget(stats))

    print("=" * 60)


def show_database_stats_target(
    runtime: DatabaseStatsRuntime,
    target: ShowDatabaseStatsTarget,
) -> None:
    print_database_core_stats(target.stats)
    print_database_total_size(runtime)
    print_database_table_stats(target.stats)
    print_database_time_range(runtime)
    print_database_api_response_stats(runtime)
