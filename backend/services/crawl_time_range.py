"""Pure time-range helpers for topic crawl workflows."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

from backend.schemas.crawl import CrawlTimeRangeRequest


def is_date_only(value: Optional[str]) -> bool:
    text = (value or "").strip()
    return len(text) == 10 and text[4] == "-" and text[7] == "-"


def parse_user_time(value: Optional[str], date_end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    try:
        if is_date_only(text):
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


def resolve_time_range(request: CrawlTimeRangeRequest, now_bj: datetime) -> tuple[datetime, datetime]:
    start_dt = parse_user_time(request.startTime)
    end_dt = parse_user_time(request.endTime, date_end=True) if request.endTime else None

    if request.lastDays and request.lastDays > 0:
        if end_dt is None:
            end_dt = now_bj
        start_dt = end_dt - timedelta(days=request.lastDays)

    if end_dt is None:
        end_dt = now_bj
    if start_dt is None:
        start_dt = end_dt - timedelta(days=30)

    if start_dt > end_dt:
        if is_date_only(request.startTime) and is_date_only(request.endTime):
            start_dt = parse_user_time(request.endTime)
            end_dt = parse_user_time(request.startTime, date_end=True)
        else:
            start_dt, end_dt = end_dt, start_dt

    return start_dt, end_dt


def format_zsxq_time(dt: datetime) -> str:
    return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"


def topic_time(topic: dict[str, Any]) -> Optional[datetime]:
    ts = topic.get("create_time")
    if not ts:
        return None
    try:
        ts_fixed = ts.replace("+0800", "+08:00") if ts.endswith("+0800") else ts
        return datetime.fromisoformat(ts_fixed)
    except Exception:
        return None


def filter_official_topics_by_time_range(
    topics: list[dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[list[dict[str, Any]], Optional[datetime]]:
    filtered: list[dict[str, Any]] = []
    oldest_dt = None
    for topic in topics:
        dt = topic_time(topic)
        if dt:
            oldest_dt = dt
            if start_dt <= dt <= end_dt:
                filtered.append(topic)
    return filtered, oldest_dt


def filter_legacy_topics_by_time_range(
    topics: list[dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[list[dict[str, Any]], Optional[datetime]]:
    filtered: list[dict[str, Any]] = []
    last_time_dt_in_page = None
    for topic in topics:
        dt = topic_time(topic)
        if dt:
            last_time_dt_in_page = dt
            if start_dt <= dt <= end_dt:
                filtered.append(topic)
    return filtered, last_time_dt_in_page


def legacy_next_end_time(topics: list[dict[str, Any]], timestamp_offset_ms: int) -> Optional[str]:
    oldest_in_page = topics[-1].get("create_time")
    try:
        dt_oldest = datetime.fromisoformat(oldest_in_page.replace("+0800", "+08:00"))
        dt_oldest = dt_oldest - timedelta(milliseconds=timestamp_offset_ms)
        return dt_oldest.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"
    except Exception:
        return oldest_in_page


def legacy_time_range_initial_cursors(start_dt: datetime, end_dt: datetime) -> tuple[str, str]:
    return format_zsxq_time(start_dt), format_zsxq_time(end_dt)
