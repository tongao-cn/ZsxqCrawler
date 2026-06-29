"""Small helper functions for ZSXQ file downloader."""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, NamedTuple, Optional, Tuple

from backend.crawlers.file_api_retry_policy import (
    API_FAILURE_NON_RETRY,
    API_FAILURE_PERMISSION_DENIED_1030,
    API_FAILURE_RETRY,
    API_FAILURE_RETRY_EXHAUSTED,
    HTTP_FAILURE_NON_RETRY,
    HTTP_FAILURE_RETRY,
    HTTP_FAILURE_RETRY_EXHAUSTED,
    RETRYABLE_API_ERROR_CODES,
    RETRYABLE_HTTP_STATUS_CODES,
    api_failure_detail,
    api_retry_user_agent_message,
    api_retry_wait_message,
    classify_api_failure,
    classify_http_failure,
    download_url_api_failure_plan,
    download_url_from_response_data,
    download_url_success_plan,
    file_list_api_failure_plan,
    has_retry_attempt_remaining,
    http_failure_plan,
    is_retryable_api_error,
    is_retryable_http_status,
    json_decode_failure_plan,
    request_exception_plan,
    retry_exhausted_message,
    should_log_full_response,
    should_retry_api_error,
    should_retry_http_status,
)
from backend.crawlers.file_list_page import (
    FileListPage,
    file_list_page,
    file_list_request_params,
    file_list_response_page,
)
from backend.crawlers.file_request_fingerprint import (
    STEALTH_ACCEPT_LANGUAGES,
    STEALTH_OPTIONAL_HEADERS,
    STEALTH_PLATFORMS,
    STEALTH_USER_AGENTS,
    risk_event_header_profile_label,
    risk_event_header_user_agent,
    risk_event_row,
    risk_event_user_agent_label,
    sec_ch_ua_for_user_agent,
    stealth_accept_languages,
    stealth_base_headers,
    stealth_optional_headers,
    stealth_platforms,
    stealth_request_id_header_value,
    stealth_timestamp_header_value,
    stealth_user_agents,
)
from backend.crawlers.file_time_window import (
    filter_files_newer_than,
    is_datetime_bound as _is_datetime_bound,
    normalize_date_range,
    page_crosses_stop_before,
    parse_create_time,
    summarize_page_time_range,
    time_collection_mode,
    time_dedupe_page_messages,
    time_dedupe_page_plan,
)
from backend.services.file_local_paths import (
    download_target_path as _download_target_path,
    safe_download_filename as _safe_download_filename,
)


IMPORT_STAT_KEYS = (
    "files",
    "topics",
    "users",
    "groups",
    "images",
    "comments",
    "likes",
    "columns",
    "solutions",
)

DOWNLOAD_PROGRESS_INTERVAL_BYTES = 10 * 1024 * 1024
DATABASE_STATS_TABLE_EMOJI = {
    "files": "📄",
    "groups": "🏠",
    "users": "👥",
    "topics": "💬",
    "talks": "💭",
    "images": "🖼️",
    "topic_files": "📎",
    "latest_likes": "👍",
    "comments": "💬",
    "like_emojis": "😊",
    "user_liked_emojis": "❤️",
    "columns": "📚",
    "topic_columns": "🔗",
    "solutions": "💡",
    "solution_files": "📋",
    "file_topic_relations": "🔗",
    "api_responses": "📡",
}


class DatabaseTimeRangeRow(NamedTuple):
    oldest_time: Any
    newest_time: Any
    time_based_count: Any


def clean_cookie_result(cookie: Any) -> tuple[Any, Optional[Exception]]:
    try:
        if isinstance(cookie, bytes):
            cookie = cookie.decode('utf-8')

        cookie = cookie.strip()

        if '\n' in cookie:
            cookie = cookie.split('\n')[0]

        cookie = cookie.rstrip('\\')

        if cookie.startswith("b'") and cookie.endswith("'"):
            cookie = cookie[2:-1]
        elif cookie.startswith('b"') and cookie.endswith('"'):
            cookie = cookie[2:-1]
        elif cookie.startswith("'") and cookie.endswith("'"):
            cookie = cookie[1:-1]
        elif cookie.startswith('"') and cookie.endswith('"'):
            cookie = cookie[1:-1]

        cookie = cookie.replace('\\n', '')
        cookie = cookie.replace('\\"', '"')
        cookie = cookie.replace("\\'", "'")

        cookie = '; '.join(part.strip() for part in cookie.split(';'))

        return cookie, None
    except Exception as exc:
        return cookie, exc


def file_list_start_messages(
    count: int,
    sort: str,
    index: Optional[str],
    url: str,
) -> tuple[str, ...]:
    messages = [
        "🌐 获取文件列表",
        f"   📊 参数: count={count}, sort={sort}",
    ]
    if index:
        messages.append(f"   📑 索引: {index}")
    messages.append(f"   🌐 请求URL: {url}")
    return tuple(messages)


def file_list_item_display_lines(position: int, file_info: Dict[str, Any]) -> tuple[str, ...]:
    file_data = file_info.get("file", {})
    topic_data = file_info.get("topic", {})

    file_name = file_data.get("name", "Unknown")
    file_size = file_data.get("size", 0)
    download_count = file_data.get("download_count", 0)
    create_time = file_data.get("create_time", "Unknown")
    topic_title = (
        topic_data.get("talk", {}).get("text", "")[:50]
        if topic_data.get("talk")
        else ""
    )

    lines = [
        f"{position:2d}. 📄 {file_name}",
        f"    📊 大小: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)",
        f"    📈 下载: {download_count} 次",
        f"    ⏰ 时间: {create_time}",
    ]
    if topic_title:
        lines.append(f"    💬 话题: {topic_title}...")
    lines.append("")
    return tuple(lines)


def file_list_next_index_message(next_index: Any) -> str:
    if next_index:
        return f"📑 下一页索引: {next_index}"
    return "📭 没有更多文件"


def file_collection_stats() -> Dict[str, int]:
    return {"total_files": 0, "new_files": 0, "skipped_files": 0}


def add_file_collection_page_stats(
    stats: Dict[str, int],
    file_count: int,
    page_stats: Dict[str, int],
) -> None:
    stats["new_files"] += page_stats.get("files", 0)
    stats["total_files"] += file_count


def file_collection_log_insert_query(start_time: str) -> tuple[str, tuple[str]]:
    return "INSERT INTO collection_log (start_time) VALUES (?) RETURNING id", (start_time,)


def file_collection_log_update_query(
    end_time: str,
    stats: Dict[str, int],
    log_id: Any,
) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            UPDATE collection_log SET
                end_time = ?, total_files = ?, new_files = ?, status = 'completed'
            WHERE id = ?
        ''',
        (end_time, stats["total_files"], stats["new_files"], log_id),
    )


def file_collection_next_page_plan(next_index: Any) -> Dict[str, Any]:
    if next_index:
        return {
            "has_next": True,
            "next_index": next_index,
            "delay_min": 2,
            "delay_max": 5,
        }
    return {
        "has_next": False,
        "next_index": None,
        "delay_min": None,
        "delay_max": None,
    }


def file_collection_start_message() -> str:
    return "\n📊 开始收集文件列表到数据库..."


def file_collection_page_message(page_count: int) -> str:
    return f"\n📄 收集第{page_count}页文件列表..."


def file_collection_fetch_failed_messages(page_count: int) -> tuple[str, str]:
    return (
        f"❌ 第{page_count}页获取失败，收集过程中断",
        f"💾 已成功收集前{page_count-1}页的数据",
    )


def file_collection_empty_page_message() -> str:
    return "📭 没有更多文件"


def file_collection_page_files_message(file_count: int) -> str:
    return f"   📋 当前页面: {file_count} 个文件"


def file_collection_page_import_messages(page_stats: Dict[str, int]) -> tuple[str, str]:
    return (
        f"      ✅ 新增文件: {page_stats.get('files', 0)}",
        (
            f"      📊 其他数据: 话题+{page_stats.get('topics', 0)}, "
            f"用户+{page_stats.get('users', 0)}"
        ),
    )


def file_collection_storage_failed_message(page_count: int, exc: Exception) -> str:
    return f"   ❌ 第{page_count}页存储失败: {exc}"


def file_collection_page_stored_message(page_count: int) -> str:
    return f"   ✅ 第{page_count}页存储完成"


def file_collection_interrupted_message() -> str:
    return "\n⏹️ 用户中断收集"


def file_collection_exception_message(exc: Exception) -> str:
    return f"\n❌ 收集过程异常: {exc}"


def file_collection_completion_messages(stats: Dict[str, int], page_count: int) -> tuple[str, ...]:
    return (
        "\n🎉 文件列表收集完成:",
        f"   📊 处理文件数: {stats['total_files']}",
        f"   ✅ 新增文件: {stats['new_files']}",
        f"   ⚠️ 跳过重复: {stats.get('skipped_files', 0)}",
        f"   📄 收集页数: {page_count}",
    )


def database_download_query_plan(
    query_group_id: Any,
    max_files: Optional[int] = None,
    status_filter: Optional[str] = "pending",
    sort_by: str = "download_count",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    last_days: Optional[int] = None,
    legacy_order_by: Any = None,
) -> Dict[str, Any]:
    normalized_start, normalized_end, _ = normalize_date_range(
        start_date=start_date,
        end_date=end_date,
        last_days=last_days,
    )

    legacy_order = str(legacy_order_by or "").strip().lower()
    if legacy_order.startswith("create_time"):
        sort_by = "create_time"
    elif legacy_order.startswith("download_count"):
        sort_by = "download_count"

    conditions = ["group_id = ?"]
    params: list[Any] = [query_group_id]
    if status_filter:
        conditions.append("download_status = ?")
        params.append(status_filter)
    if normalized_start:
        conditions.append(
            "create_time >= ?" if _is_datetime_bound(normalized_start) else "substr(create_time, 1, 10) >= ?"
        )
        params.append(normalized_start)
    if normalized_end:
        conditions.append(
            "create_time <= ?" if _is_datetime_bound(normalized_end) else "substr(create_time, 1, 10) <= ?"
        )
        params.append(normalized_end)

    where_clause = f"WHERE {' AND '.join(conditions)}"
    order_clause = (
        "ORDER BY create_time DESC, download_count DESC"
        if sort_by == "create_time"
        else "ORDER BY download_count DESC, size ASC"
    )
    limit_clause = "LIMIT ?" if max_files else ""
    if max_files:
        params.append(max_files)

    query = f'''
            SELECT file_id, name, size, download_count, create_time
            FROM files
            {where_clause}
            {order_clause}
            {limit_clause}
        '''
    return {
        "query": query,
        "params": tuple(params),
        "sort_by": sort_by,
        "normalized_start": normalized_start,
        "normalized_end": normalized_end,
    }


def database_download_effective_last_days(
    last_days: Optional[int],
    legacy_recent_days: Any,
) -> Any:
    if last_days is None and legacy_recent_days is not None:
        return legacy_recent_days
    return last_days


def database_download_filter_messages(
    normalized_start: Optional[str],
    normalized_end: Optional[str],
    last_days: Optional[int],
    sort_by: str,
) -> tuple[str, ...]:
    messages = []
    if normalized_start or normalized_end:
        messages.append(f"   📅 下载区间: {normalized_start or '-'} ~ {normalized_end or '-'}")
    elif last_days:
        messages.append(f"   📅 时间筛选: 最近{last_days}天")
    messages.append(f"   📌 下载排序: {'按时间倒序' if sort_by == 'create_time' else '按热度倒序'}")
    return tuple(messages)


def database_download_start_messages(max_files: Optional[int], status_filter: str) -> tuple[str, ...]:
    messages = ["📥 开始从完整数据库下载文件..."]
    if max_files:
        messages.append(f"   🎯 下载限制: {max_files}个文件")
    messages.append(f"   🔍 状态筛选: {status_filter}")
    return tuple(messages)


def database_download_time_range_message(files_to_download: list[Any], sort_by: str) -> Optional[str]:
    if sort_by == "create_time" and files_to_download:
        newest = files_to_download[0][4]
        oldest = files_to_download[-1][4]
        return f"   🗓️ 本次待下载文件时间范围: {newest} ~ {oldest}"
    return None


def date_range_collection_start_messages(
    normalized_start: Optional[str],
    normalized_end: Optional[str],
) -> tuple[str, ...]:
    messages = ["📅 启动按时间范围收集文件列表..."]
    if normalized_start or normalized_end:
        messages.append(f"   范围: {normalized_start or '-'} ~ {normalized_end or '-'}")
    return tuple(messages)


def incremental_start_index(oldest_time: Any) -> str:
    if "+" in oldest_time:
        dt = datetime.datetime.fromisoformat(oldest_time.replace("+0800", "+08:00"))
        timestamp_ms = int(dt.timestamp() * 1000)
    else:
        timestamp_ms = int(oldest_time)
    return str(timestamp_ms)


def incremental_collection_start_message() -> str:
    return "🔄 开始增量文件收集..."


def incremental_collection_empty_database_message() -> str:
    return "📊 数据库为空，将进行全量收集"


def incremental_collection_status_messages(time_info: Dict[str, Any]) -> tuple[str, ...]:
    return (
        "📊 数据库现状:",
        f"   现有文件数: {time_info['total_files']}",
        f"   最老时间: {time_info['oldest_time']}",
        f"   最新时间: {time_info['newest_time']}",
    )


def incremental_collection_missing_time_message() -> str:
    return "⚠️ 数据库中没有有效的时间信息，进行全量收集"


def incremental_collection_target_message() -> str:
    return "🎯 将从最老时间戳开始收集更早的文件..."


def incremental_collection_start_index_message(start_index: Any) -> str:
    return f"🚀 增量收集起始时间戳: {start_index}"


def incremental_collection_timestamp_failure_messages(exc: Exception) -> tuple[str, str]:
    return (f"⚠️ 时间戳处理失败: {exc}", "🔄 改为全量收集")


def database_time_range_query(query_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT MIN(create_time) as oldest_time,
                   MAX(create_time) as newest_time,
                   COUNT(*) as total_count
            FROM files
            WHERE group_id = ?
              AND create_time IS NOT NULL AND create_time != ''
        ''',
        (query_group_id,),
    )


def _database_time_range_row(result: Any) -> DatabaseTimeRangeRow:
    if not result:
        return DatabaseTimeRangeRow(None, None, 0)
    return DatabaseTimeRangeRow(result[0], result[1], result[2])


def database_time_range_result(total_files: Any, result: Any) -> Dict[str, Any]:
    if total_files == 0:
        return {"has_data": False, "total_files": 0}
    time_range = _database_time_range_row(result)
    return {
        "has_data": True,
        "total_files": total_files,
        "oldest_time": time_range.oldest_time,
        "newest_time": time_range.newest_time,
        "time_based_count": time_range.time_based_count,
    }


def latest_file_create_time_query(query_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
                SELECT MAX(create_time) FROM files
                WHERE group_id = ?
                  AND create_time IS NOT NULL AND create_time != ''
            ''',
        (query_group_id,),
    )


def time_collection_start_messages(
    sort: str,
    start_time: Optional[str],
    stop_before_time: Optional[datetime.datetime],
) -> tuple[str, ...]:
    messages = [
        "📊 开始按时间顺序收集文件列表到完整数据库...",
        f"   📅 排序方式: {sort}",
    ]
    if start_time:
        messages.append(f"   ⏰ 起始时间: {start_time}")
    if stop_before_time:
        messages.append(f"   🎯 收集边界: 覆盖到 {stop_before_time.strftime('%Y-%m-%d')} 即停止")
    return tuple(messages)


def time_collection_database_status_message(initial_files: Any) -> str:
    return f"   📊 数据库初始状态: {initial_files} 个文件"


def time_collection_latest_file_time_message(db_latest_time: Any) -> str:
    return f"   📅 数据库最新文件时间: {db_latest_time}"


def time_collection_page_message(page_count: int) -> str:
    return f"📄 收集第{page_count}页文件列表..."


def time_collection_fetch_failed_messages(page_count: int) -> tuple[str, str]:
    return (
        f"❌ 第{page_count}页获取失败，收集过程中断",
        f"💾 已成功收集前{page_count-1}页的数据",
    )


def time_collection_empty_page_message() -> str:
    return "📭 没有更多文件"


def time_collection_page_files_message(file_count: int) -> str:
    return f"   📋 当前页面: {file_count} 个文件"


def time_collection_page_time_range_message(
    page_oldest: Optional[str],
    page_newest: Optional[str],
) -> Optional[str]:
    if page_oldest and page_newest:
        return f"   🗓️ 当前页文件时间范围: {page_newest} ~ {page_oldest}"
    return None


def time_collection_storage_failed_message(page_count: int, exc: Exception) -> str:
    return f"   ❌ 第{page_count}页存储失败: {exc}"


def time_collection_initial_stop_message() -> str:
    return "🛑 任务被停止"


def time_collection_loop_stop_message() -> str:
    return "🛑 文件收集任务被停止"


def time_collection_stop_before_boundary_message(
    oldest_page_time: datetime.datetime,
    stop_before_time: datetime.datetime,
) -> str:
    return (
        f"🛑 当前页最老文件时间 {oldest_page_time.strftime('%Y-%m-%d %H:%M:%S')} "
        f"早于目标起始时间 {stop_before_time.strftime('%Y-%m-%d')}，停止继续收集更早文件"
    )


def time_collection_interrupted_message() -> str:
    return "⏹️ 用户中断收集"


def time_collection_exception_message(exc: Exception) -> str:
    return f"❌ 收集过程异常: {exc}"


def time_collection_next_page_plan(next_index: Any) -> Dict[str, Any]:
    if next_index:
        return {
            "has_next": True,
            "next_index": next_index,
            "message": f"   ⏭️ 下一页时间戳: {next_index}",
        }
    return {
        "has_next": False,
        "next_index": None,
        "message": "📭 已到达最后一页",
    }


def time_collection_page_import_messages(
    page_count: int,
    page_stats: Dict[str, Any],
    should_stop_after_insert: bool,
) -> tuple[str, ...]:
    messages = [
        f"   ✅ 第{page_count}页存储完成: 文件+{page_stats.get('files', 0)}, 话题+{page_stats.get('topics', 0)}",
    ]
    if should_stop_after_insert:
        messages.append("   ✅ 已插入本页新数据，后续页面均为旧数据，停止收集")
        messages.append("   💡 提示: 如需强制重新收集，请传入 force_refresh=True 参数")
    return tuple(messages)


def time_collection_final_summary(
    final_stats: Dict[str, int],
    initial_files: int,
    total_imported_stats: Dict[str, int],
    page_count: int,
) -> Dict[str, Any]:
    final_files = final_stats.get("files", 0)
    new_files = final_files - initial_files
    return {
        "final_files": final_files,
        "new_files": new_files,
        "imported_items": tuple((key, value) for key, value in total_imported_stats.items() if value > 0),
        "database_items": tuple((table, count) for table, count in final_stats.items() if count > 0),
        "result": {
            "total_files": final_files,
            "new_files": new_files,
            "pages": page_count,
            **total_imported_stats,
        },
    }


def time_collection_summary_messages(summary: Dict[str, Any], page_count: int) -> tuple[str, ...]:
    messages = [
        "🎉 完整文件列表收集完成:",
        f"   📊 处理页数: {page_count}",
        f"   📁 新增文件: {summary['new_files']} (总计: {summary['final_files']})",
        "   📋 累计导入统计:",
    ]
    messages.extend(f"      {key}: +{value}" for key, value in summary["imported_items"])
    messages.append("   📚 当前数据库状态:")
    messages.extend(f"      {table}: {count}" for table, count in summary["database_items"])
    return tuple(messages)


def safe_download_filename(file_name: Any, file_id: Any) -> str:
    return _safe_download_filename(file_name, file_id)


def download_target_path(download_dir: str, file_name: Any, file_id: Any) -> tuple[str, str]:
    return _download_target_path(download_dir, file_name, file_id)


def download_file_data(file_info: Dict[str, Any]) -> Dict[str, Any]:
    file_data = file_info.get("file", {}) or {}
    return {
        "file_id": file_data.get("id") or file_data.get("file_id"),
        "file_name": file_data.get("name", "Unknown"),
        "file_size": file_data.get("size", 0),
        "download_count": file_data.get("download_count", 0),
    }


def download_result_stats(total_files: int = 0) -> Dict[str, int]:
    return {
        "total_files": int(total_files),
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
    }


def _download_completion_messages(title: str, stats: Dict[str, int]) -> tuple[str, ...]:
    return (
        title,
        f"   📊 总文件数: {stats['total_files']}",
        f"   ✅ 下载成功: {stats['downloaded']}",
        f"   ⚠️ 跳过: {stats['skipped']}",
        f"   ❌ 失败: {stats['failed']}",
    )


def batch_download_start_messages(max_files: Optional[int]) -> tuple[str, ...]:
    if max_files is None:
        return ("📥 开始无限下载文件 (直到没有更多文件)",)
    return (f"📥 开始批量下载文件 (最多{max_files}个)",)


def batch_download_item_message(item_number: int, max_files: Optional[int], file_name: Any) -> str:
    if max_files is None:
        return f"【第{item_number}个文件】{file_name}"
    return f"【{item_number}/{max_files}】{file_name}"


def batch_download_skipped_message() -> str:
    return "   ⚠️ 文件已跳过，继续下一个"


def batch_download_fetch_failed_message() -> str:
    return "❌ 获取文件列表失败"


def batch_download_empty_page_message() -> str:
    return "📭 没有更多文件"


def batch_download_page_files_message(file_count: int) -> str:
    return f"📋 当前批次: {file_count} 个文件"


def batch_download_initial_stop_message() -> str:
    return "🛑 任务被停止"


def batch_download_loop_stop_message() -> str:
    return "🛑 批量下载任务被停止"


def batch_download_file_stop_message() -> str:
    return "🛑 文件下载过程中被停止"


def batch_download_next_page_plan(
    next_index: Any,
    downloaded_in_batch: int,
    max_files: Optional[int],
) -> Dict[str, Any]:
    should_continue = max_files is None or downloaded_in_batch < max_files
    if next_index and should_continue:
        return {
            "should_continue": True,
            "next_index": next_index,
            "message": f"📄 准备获取下一页: {next_index}",
            "delay": 2,
        }
    return {
        "should_continue": False,
        "next_index": None,
        "message": None,
        "delay": None,
    }


def batch_download_completion_messages(stats: Dict[str, int]) -> tuple[str, ...]:
    return _download_completion_messages("🎉 批量下载完成:", stats)


def database_download_completion_messages(stats: Dict[str, int]) -> tuple[str, ...]:
    return _download_completion_messages("🎉 数据库下载完成:", stats)


def database_download_file_info(
    file_id: Any,
    file_name: Any,
    file_size: Any,
    download_count: Any,
) -> Dict[str, Dict[str, Any]]:
    return {
        "file": {
            "id": file_id,
            "name": file_name,
            "size": file_size,
            "download_count": download_count,
        }
    }


def database_stats_table_emoji(table_name: str) -> str:
    return DATABASE_STATS_TABLE_EMOJI.get(table_name, "📊")


def database_stats_total_size_query(query_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return "SELECT SUM(size) FROM files WHERE group_id = ? AND size IS NOT NULL", (query_group_id,)


def database_stats_time_range_query(query_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT MIN(create_time), MAX(create_time), COUNT(*)
            FROM files
            WHERE group_id = ? AND create_time IS NOT NULL
        ''',
        (query_group_id,),
    )


def database_stats_api_response_query() -> str:
    return '''
            SELECT succeeded, COUNT(*)
            FROM api_responses
            GROUP BY succeeded
        '''


def download_settings_display_lines(
    download_interval_min: float,
    download_interval_max: float,
    long_delay_interval: int,
    long_delay_min: float,
    long_delay_max: float,
    download_dir: str,
) -> tuple[str, ...]:
    return (
        "\n🔧 当前下载设置:",
        f"   下载间隔: {download_interval_min}-{download_interval_max}秒 ({download_interval_min/60:.1f}-{download_interval_max/60:.1f}分钟)",
        f"   长休眠间隔: 每{long_delay_interval}个文件",
        f"   长休眠时间: {long_delay_min}-{long_delay_max}秒 ({long_delay_min/60:.1f}-{long_delay_max/60:.1f}分钟)",
        f"   下载目录: {download_dir}",
    )


def download_query_group_id(group_id: Any) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def existing_file_matches(file_path: str, expected_size: int) -> tuple[bool, bool, int]:
    if not os.path.exists(file_path):
        return False, False, 0
    existing_size = os.path.getsize(file_path)
    matches = existing_size == expected_size or (expected_size == 0 and existing_size > 0)
    return True, matches, existing_size


def remove_partial_download(temp_path: str) -> bool:
    if not os.path.exists(temp_path):
        return False
    os.remove(temp_path)
    return True


def download_progress_message(downloaded_size: int, total_size: int) -> Optional[str]:
    if downloaded_size % DOWNLOAD_PROGRESS_INTERVAL_BYTES == 0 or downloaded_size == total_size:
        if total_size > 0:
            progress = (downloaded_size / total_size) * 100
            return f"   📊 进度: {progress:.1f}% ({downloaded_size:,}/{total_size:,} bytes)"

    if downloaded_size % DOWNLOAD_PROGRESS_INTERVAL_BYTES != 0 and downloaded_size != total_size:
        if total_size == 0:
            return f"   📊 已下载: {downloaded_size:,} bytes"

    return None


def download_url_failure_detail(error_detail: Optional[Dict[str, Any]]) -> tuple[str, str]:
    detail = error_detail or {
        "code": "download_url_unavailable",
        "message": "无法获取下载链接",
    }
    return (
        str(detail.get("code") or "download_url_unavailable"),
        str(detail.get("message") or "无法获取下载链接"),
    )


def download_retry_wait(attempt: int, download_retries: int) -> tuple[int, str]:
    retry_delay = 2 * attempt
    return (
        retry_delay,
        f"   🔄 文件下载重试 {attempt + 1}/{download_retries}，等待 {retry_delay} 秒...",
    )


def download_interval_plan(
    current_batch_count: int,
    files_per_batch: int,
    download_interval: float,
    long_sleep_interval: float,
) -> tuple[Optional[float], tuple[str, ...], bool]:
    if current_batch_count >= files_per_batch:
        return (
            long_sleep_interval,
            (
                f"⏰ 已下载 {current_batch_count} 个文件，开始长休眠 {long_sleep_interval} 秒...",
                "😴 长休眠结束，继续下载",
            ),
            True,
        )
    if download_interval > 0:
        return (
            download_interval,
            (f"⏱️ 下载间隔休眠 {download_interval} 秒...",),
            False,
        )
    return None, (), False


def download_size_mismatch_detail(expected_size: int, final_size: int) -> Optional[tuple[str, str]]:
    if expected_size <= 0 or final_size == expected_size:
        return None
    return (
        "size_mismatch",
        f"文件大小不匹配: 预期{expected_size:,}, 实际{final_size:,}",
    )


def download_http_failure_detail(status_code: int) -> tuple[str, str]:
    return "http_status", f"HTTP {status_code}"


def download_exception_detail(exc: Exception) -> tuple[str, str]:
    return "download_exception", str(exc)


def download_final_failure_detail(
    last_error_code: Optional[str],
    last_error: Optional[str],
) -> tuple[str, str]:
    return last_error_code or "download_failed", last_error or "文件下载失败"


def download_expected_size(file_size: int, total_size: int) -> int:
    return file_size if file_size > 0 else total_size


def download_total_size(response_headers: Dict[str, Any]) -> int:
    return int(response_headers.get("content-length", 0))


def partial_download_path(file_path: str) -> str:
    return f"{file_path}.part"


def content_disposition_filename(content_disposition: str) -> Optional[str]:
    if "filename=" not in content_disposition:
        return None
    filename_match = re.search(r"filename[*]?=([^;]+)", content_disposition)
    if not filename_match:
        return None
    real_filename = filename_match.group(1).strip('"\'')
    return real_filename or None


def response_filename_override(
    file_name: str,
    file_id: Any,
    download_dir: str,
    response_headers: Dict[str, Any],
) -> Optional[Tuple[str, str, str]]:
    if not file_name.startswith("file_") or "content-disposition" not in response_headers:
        return None

    real_filename = content_disposition_filename(response_headers["content-disposition"])
    if not real_filename:
        return None

    safe_filename = safe_download_filename(real_filename, file_id)
    file_path = os.path.join(download_dir, safe_filename)
    return real_filename, safe_filename, file_path


def empty_import_stats() -> Dict[str, int]:
    return {key: 0 for key in IMPORT_STAT_KEYS}


def add_import_stats(total_stats: Dict[str, int], page_stats: Dict[str, Any]) -> None:
    for key in IMPORT_STAT_KEYS:
        total_stats[key] = int(total_stats.get(key, 0) or 0) + int(page_stats.get(key, 0) or 0)
