"""Time-window and dedupe policy for ZSXQ file collection."""

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
        stop_before_dt = (
            parse_create_time(start)
            if is_datetime_bound(start)
            else datetime.datetime.strptime(start, "%Y-%m-%d")
        )
    if start and end and start > end:
        start, end = end, start
    return start, end, stop_before_dt


def is_datetime_bound(value: Optional[str]) -> bool:
    return bool(value and len(value.strip()) > 10)


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


__all__ = [
    "filter_files_newer_than",
    "is_datetime_bound",
    "normalize_date_range",
    "page_crosses_stop_before",
    "parse_create_time",
    "summarize_page_time_range",
    "time_collection_mode",
    "time_dedupe_page_messages",
    "time_dedupe_page_plan",
]
