"""Topic end-time cursor helpers for paginated ZSXQ topic crawls."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional


LogCallback = Callable[[str], None]


def format_offset_zsxq_end_time(value: str, delta: Any) -> str:
    dt = datetime.fromisoformat(value.replace("+0800", "+08:00"))
    dt = dt - delta
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"


def offset_zsxq_end_time(value: str, offset_ms: int) -> str:
    return format_offset_zsxq_end_time(value, timedelta(milliseconds=offset_ms))


def offset_zsxq_end_time_by_hours(value: str, hours: int) -> str:
    return format_offset_zsxq_end_time(value, timedelta(hours=hours))


def next_topic_end_time(
    topics: List[Dict[str, Any]],
    timestamp_offset_ms: int,
    log: LogCallback,
) -> Optional[str]:
    if not topics:
        return None

    original_time = topics[-1].get("create_time")
    if not original_time:
        log("   ⚠️ 最后一条话题缺少 create_time，停止继续翻页")
        return None

    try:
        return offset_zsxq_end_time(original_time, timestamp_offset_ms)
    except Exception as e:
        log(f"   ⚠️ 时间戳调整失败: {e}")
        return original_time
