"""Small helper functions for ZSXQ file downloader."""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, Optional, Tuple


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


def classify_api_failure(error_code: Any, attempt: int, max_retries: int) -> str:
    if str(error_code) == "1030":
        return API_FAILURE_PERMISSION_DENIED_1030
    if not is_retryable_api_error(error_code):
        return API_FAILURE_NON_RETRY
    if has_retry_attempt_remaining(attempt, max_retries):
        return API_FAILURE_RETRY
    return API_FAILURE_RETRY_EXHAUSTED


def classify_http_failure(status_code: int, attempt: int, max_retries: int) -> str:
    if not is_retryable_http_status(status_code):
        return HTTP_FAILURE_NON_RETRY
    if has_retry_attempt_remaining(attempt, max_retries):
        return HTTP_FAILURE_RETRY
    return HTTP_FAILURE_RETRY_EXHAUSTED


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
