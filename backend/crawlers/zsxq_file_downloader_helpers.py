"""Small helper functions for ZSXQ file downloader."""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional, Tuple


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
