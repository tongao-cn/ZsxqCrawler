"""Small helper functions for ZSXQ file downloader."""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, Optional, Tuple

from backend.core.log_redaction import redact_response_text


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

RETRYABLE_API_ERROR_CODES = {"1059", "500", "502", "503", "504"}
RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
API_FAILURE_RETRY = "retry"
API_FAILURE_NON_RETRY = "non_retry"
API_FAILURE_RETRY_EXHAUSTED = "retry_exhausted"
API_FAILURE_PERMISSION_DENIED_1030 = "permission_denied_1030"
HTTP_FAILURE_RETRY = "retry"
HTTP_FAILURE_NON_RETRY = "non_retry"
HTTP_FAILURE_RETRY_EXHAUSTED = "retry_exhausted"
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


def risk_event_user_agent_label(user_agent: str) -> str:
    text = str(user_agent or "")
    browser = "Other"
    if "Edg/" in text:
        browser = "Edge"
    elif "Chrome/" in text or "Chromium/" in text:
        browser = "Chrome"
    elif "Firefox/" in text:
        browser = "Firefox"
    elif "Safari/" in text:
        browser = "Safari"

    platform = "Other"
    if "Windows" in text:
        platform = "Windows"
    elif "Macintosh" in text or "Mac OS X" in text:
        platform = "Mac"
    elif "Linux" in text or "X11" in text:
        platform = "Linux"
    elif "Android" in text:
        platform = "Android"
    elif "iPhone" in text or "iPad" in text:
        platform = "iOS"

    return f"{browser} {platform}"


def risk_event_header_profile_label(headers: Dict[str, str]) -> str:
    normalized = {str(key).lower(): value for key, value in (headers or {}).items()}
    labels = []
    if "referer" in normalized:
        labels.append("referer")
    if "origin" in normalized:
        labels.append("origin")
    if any(key.startswith("sec-fetch-") for key in normalized):
        labels.append("sec-fetch")
    if any(key.startswith("sec-ch-") for key in normalized):
        labels.append("sec-ch")
    if "x-timestamp" in normalized:
        labels.append("x-timestamp")
    if "x-request-id" in normalized:
        labels.append("x-request-id")
    return "+".join(labels) or "minimal"


def is_retryable_api_error(error_code: Any) -> bool:
    return str(error_code) in RETRYABLE_API_ERROR_CODES


def is_retryable_http_status(status_code: int) -> bool:
    return int(status_code) in RETRYABLE_HTTP_STATUS_CODES


def has_retry_attempt_remaining(attempt: int, max_retries: int) -> bool:
    return int(attempt) < int(max_retries) - 1


def should_retry_api_error(error_code: Any, attempt: int, max_retries: int) -> bool:
    return is_retryable_api_error(error_code) and has_retry_attempt_remaining(attempt, max_retries)


def should_retry_http_status(status_code: int, attempt: int, max_retries: int) -> bool:
    return is_retryable_http_status(status_code) and has_retry_attempt_remaining(attempt, max_retries)


def should_log_full_response(attempt: int, max_retries: int, succeeded: Any) -> bool:
    return int(attempt) == 0 or int(attempt) == int(max_retries) - 1 or bool(succeeded)


def file_list_request_params(count: int, sort: str, index: Optional[str]) -> Dict[str, str]:
    params = {
        "count": str(count),
        "sort": sort,
    }
    if index:
        params["index"] = index
    return params


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


def file_list_response_page(data: Dict[str, Any]) -> Tuple[Any, Any]:
    resp_data = data.get("resp_data", {})
    return resp_data.get("files", []), resp_data.get("index")


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


def api_failure_detail(data: Dict[str, Any]) -> tuple[Any, Any]:
    return data.get("message", data.get("error", "未知错误")), data.get("code", "N/A")


def classify_api_failure(error_code: Any, attempt: int, max_retries: int) -> str:
    if str(error_code) == "1030":
        return API_FAILURE_PERMISSION_DENIED_1030
    if not is_retryable_api_error(error_code):
        return API_FAILURE_NON_RETRY
    if has_retry_attempt_remaining(attempt, max_retries):
        return API_FAILURE_RETRY
    return API_FAILURE_RETRY_EXHAUSTED


def download_url_api_failure_plan(data: Dict[str, Any], attempt: int, max_retries: int) -> Dict[str, Any]:
    error_msg, error_code = api_failure_detail(data)
    failure_class = classify_api_failure(error_code, attempt, max_retries)
    messages = [f"   ❌ API返回失败: {error_msg} (代码: {error_code})"]
    last_error = None

    if failure_class == API_FAILURE_PERMISSION_DENIED_1030:
        last_error = {
            "code": error_code,
            "message": error_msg,
        }
        messages.append("   🚫 权限不足错误(1030)：此文件可能只能在手机端下载，已跳过当前文件")
    elif failure_class == API_FAILURE_RETRY:
        messages.append("   🔄 检测到可重试错误，准备重试...")
    elif failure_class == API_FAILURE_NON_RETRY:
        messages.append("   🚫 非可重试错误，停止重试")

    return {
        "error_msg": error_msg,
        "error_code": error_code,
        "failure_class": failure_class,
        "messages": tuple(messages),
        "last_download_url_error": last_error,
    }


def classify_http_failure(status_code: int, attempt: int, max_retries: int) -> str:
    if not is_retryable_http_status(status_code):
        return HTTP_FAILURE_NON_RETRY
    if has_retry_attempt_remaining(attempt, max_retries):
        return HTTP_FAILURE_RETRY
    return HTTP_FAILURE_RETRY_EXHAUSTED


def http_failure_plan(
    status_code: int,
    response_text: Any,
    attempt: int,
    max_retries: int,
) -> Dict[str, Any]:
    failure_class = classify_http_failure(status_code, attempt, max_retries)
    messages = [
        f"   ❌ HTTP错误: {status_code}",
        f"   📄 响应内容: {redact_response_text(response_text, limit=200)}",
    ]
    if failure_class == HTTP_FAILURE_RETRY:
        messages.append("   🔄 服务器错误，准备重试...")
    elif failure_class == HTTP_FAILURE_NON_RETRY:
        messages.append("   🚫 非可重试HTTP错误，停止重试")
    return {"failure_class": failure_class, "messages": tuple(messages)}


def request_exception_plan(exc: Exception, attempt: int, max_retries: int) -> Dict[str, Any]:
    should_retry = has_retry_attempt_remaining(attempt, max_retries)
    messages = [f"   ❌ 请求异常: {exc}"]
    if should_retry:
        messages.append("   🔄 请求异常，准备重试...")
    return {"should_retry": should_retry, "messages": tuple(messages)}


def retry_exhausted_message(max_retries: int) -> str:
    return f"   🚫 已重试{max_retries}次，全部失败"


def json_decode_failure_plan(exc: Exception, response_text: Any, attempt: int, max_retries: int) -> Dict[str, Any]:
    should_retry = has_retry_attempt_remaining(attempt, max_retries)
    messages = [
        f"   ❌ JSON解析失败: {exc}",
        f"   📄 原始响应: {redact_response_text(response_text, limit=500)}",
    ]
    if should_retry:
        messages.append("   🔄 JSON解析失败，准备重试...")
    return {"should_retry": should_retry, "messages": tuple(messages)}


def download_url_success_plan(attempt: int) -> tuple[str, str]:
    if attempt > 0:
        return f"   ✅ 重试成功！第{attempt}次重试获取到下载链接", "download_url_retry_response"
    return "   ✅ 获取下载链接成功", "download_url_response"


def parse_create_time(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value:
        return None
    text = str(value).strip()
    formats = (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(text, fmt)
            if dt.tzinfo:
                return dt.astimezone().replace(tzinfo=None)
            return dt
        except Exception:
            continue
    try:
        if text.endswith("+0800"):
            return datetime.datetime.strptime(text[:-5], "%Y-%m-%dT%H:%M:%S.%f")
    except Exception:
        pass
    return None


def normalize_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    last_days: Optional[int] = None,
) -> Tuple[Optional[str], Optional[str], Optional[datetime.datetime]]:
    if last_days:
        start_dt = datetime.datetime.now() - datetime.timedelta(days=max(1, int(last_days)))
        start = start_dt.strftime("%Y-%m-%d")
        end = datetime.datetime.now().strftime("%Y-%m-%d")
        return start, end, start_dt
    start = str(start_date or "").strip() or None
    end = str(end_date or "").strip() or None
    stop_before_dt = None
    if start:
        stop_before_dt = datetime.datetime.strptime(start, "%Y-%m-%d")
    if start and end and start > end:
        start, end = end, start
    return start, end, stop_before_dt


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
        conditions.append("substr(create_time, 1, 10) >= ?")
        params.append(normalized_start)
    if normalized_end:
        conditions.append("substr(create_time, 1, 10) <= ?")
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


def database_time_range_result(total_files: Any, result: Any) -> Dict[str, Any]:
    if total_files == 0:
        return {"has_data": False, "total_files": 0}
    return {
        "has_data": True,
        "total_files": total_files,
        "oldest_time": result[0] if result else None,
        "newest_time": result[1] if result else None,
        "time_based_count": result[2] if result else 0,
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


def time_collection_mode(
    sort: str,
    force_refresh: bool,
    stop_before_time: Optional[datetime.datetime],
) -> Dict[str, Any]:
    enable_time_dedupe = sort == "by_create_time" and not force_refresh and stop_before_time is None
    mode_message = None
    if force_refresh:
        mode_message = "   🔄 强制刷新模式: 将收集所有文件（包括已存在的）"
    elif enable_time_dedupe:
        mode_message = "   ✅ 智能去重模式: 遇到已存在的文件将停止收集"
    return {
        "force_refresh": force_refresh,
        "enable_time_dedupe": enable_time_dedupe,
        "mode_message": mode_message,
    }


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


def summarize_page_time_range(files: list[Dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
    timestamps: list[datetime.datetime] = []
    for item in files:
        file_data = item.get("file", {}) or {}
        file_dt = parse_create_time(file_data.get("create_time"))
        if file_dt:
            timestamps.append(file_dt)

    if not timestamps:
        return None, None

    oldest = min(timestamps).strftime("%Y-%m-%d %H:%M:%S")
    newest = max(timestamps).strftime("%Y-%m-%d %H:%M:%S")
    return oldest, newest


def filter_files_newer_than(files: list[Dict[str, Any]], latest_time: str) -> tuple[list[Dict[str, Any]], int]:
    newer_files = [
        file_info
        for file_info in files
        if (file_info.get("file", {}) or {}).get("create_time", "") > latest_time
    ]
    return newer_files, len(files) - len(newer_files)


def time_dedupe_page_plan(files: list[Dict[str, Any]], latest_time: str) -> Dict[str, Any]:
    newer_files, older_count = filter_files_newer_than(files, latest_time)
    newer_count = len(newer_files)
    return {
        "newer_files": newer_files,
        "newer_count": newer_count,
        "older_count": older_count,
        "should_stop_before_insert": newer_count == 0,
        "should_filter_before_insert": newer_count > 0 and older_count > 0,
        "should_stop_after_insert": newer_count > 0 and older_count > 0,
    }


def time_dedupe_page_messages(dedupe_plan: Dict[str, Any]) -> tuple[str, ...]:
    newer_count = dedupe_plan["newer_count"]
    older_count = dedupe_plan["older_count"]
    messages = [
        f"   📊 时间分析: 新于数据库{newer_count}个, 旧于或等于数据库{older_count}个",
    ]

    if dedupe_plan["should_stop_before_insert"]:
        messages.append("   ✅ 本页全部文件均已存在于数据库（时间不晚于数据库最新），停止收集")
        messages.append("   💡 提示: 如需强制重新收集，请传入 force_refresh=True 参数")

    if dedupe_plan["should_filter_before_insert"]:
        messages.append(f"   🔄 过滤掉{older_count}个旧数据，只插入{newer_count}个新数据")

    return tuple(messages)


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


def page_crosses_stop_before(
    files: list[Dict[str, Any]],
    stop_before_time: datetime.datetime,
) -> tuple[bool, Optional[datetime.datetime]]:
    page_times = []
    for item in files:
        file_data = item.get("file", {}) or {}
        file_dt = parse_create_time(file_data.get("create_time"))
        if file_dt:
            page_times.append(file_dt)
    if not page_times:
        return False, None
    oldest = min(page_times)
    return oldest < stop_before_time, oldest


def safe_download_filename(file_name: Any, file_id: Any) -> str:
    safe_filename = "".join(c for c in str(file_name or "") if c.isalnum() or c in "._-（）()[]{}")
    if not safe_filename:
        safe_filename = f"file_{file_id}"
    return safe_filename


def download_target_path(download_dir: str, file_name: Any, file_id: Any) -> tuple[str, str]:
    safe_filename = safe_download_filename(file_name, file_id)
    return safe_filename, os.path.join(download_dir, safe_filename)


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
