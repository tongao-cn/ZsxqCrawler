from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence, Tuple


def validate_day(day: Optional[str], field_name: str = "date") -> Optional[str]:
    if day is None or str(day).strip() == "":
        return None
    try:
        return datetime.strptime(str(day).strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD 格式") from exc


def normalize_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    start_field_name: str = "start_date",
    end_field_name: str = "end_date",
    reverse_error: str = "start_date 不能晚于 end_date",
) -> Tuple[str, str]:
    start_day = validate_day(start_date, start_field_name) or ""
    end_day = validate_day(end_date, end_field_name) or ""
    if start_day > end_day:
        raise ValueError(reverse_error)
    return start_day, end_day


def get_last_days_range(days: int) -> Tuple[datetime, datetime]:
    now = datetime.now()
    return now - timedelta(days=days), now


def get_date_range_bounds(start_date: str, end_date: str) -> Tuple[datetime, datetime]:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    return start, end


def get_required_days_for_start_date(start_date: str) -> int:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    delta = datetime.now().date() - start_dt.date()
    return max(1, delta.days + 2)


def select_available_date_range(
    available_dates: Sequence[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[str, str, list[str]]:
    selected_start = validate_day(start_date, "start_date") or available_dates[0]
    selected_end = validate_day(end_date, "end_date") or available_dates[-1]
    if selected_start > selected_end:
        selected_start, selected_end = selected_end, selected_start
    range_dates = [day for day in available_dates if selected_start <= day <= selected_end]
    return selected_start, selected_end, range_dates
