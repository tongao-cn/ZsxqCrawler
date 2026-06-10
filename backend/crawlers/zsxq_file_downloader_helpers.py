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


def content_disposition_filename(content_disposition: str) -> Optional[str]:
    if "filename=" not in content_disposition:
        return None
    filename_match = re.search(r"filename[*]?=([^;]+)", content_disposition)
    if not filename_match:
        return None
    real_filename = filename_match.group(1).strip('"\'')
    return real_filename or None


def empty_import_stats() -> Dict[str, int]:
    return {key: 0 for key in IMPORT_STAT_KEYS}


def add_import_stats(total_stats: Dict[str, int], page_stats: Dict[str, Any]) -> None:
    for key in IMPORT_STAT_KEYS:
        total_stats[key] = int(total_stats.get(key, 0) or 0) + int(page_stats.get(key, 0) or 0)
