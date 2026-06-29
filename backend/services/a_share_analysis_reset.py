from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple

from backend.services.a_share_analysis_dates import get_required_days_for_start_date


@dataclass(frozen=True)
class AnalysisResetResult:
    daily: Dict[str, Dict[str, int]]
    processed_keys: Set[str]
    reset_summary: Dict[str, Any]
    days: int


def extract_day_from_state_key(key: str) -> Optional[str]:
    if not key:
        return None
    parts = key.split(":")
    if len(parts) < 3:
        return None
    day = parts[-1].strip()
    if len(day) != 10:
        return None
    return day


def remove_daily_range(
    daily: Dict[str, Dict[str, int]],
    start_date: str,
    end_date: str,
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int]]:
    kept: Dict[str, Dict[str, int]] = {}
    removed_days = 0
    removed_rows = 0
    removed_mentions = 0
    for day, company_counts in daily.items():
        if start_date <= day <= end_date:
            removed_days += 1
            removed_rows += len(company_counts)
            removed_mentions += sum(company_counts.values())
            continue
        kept[day] = company_counts
    return kept, {
        "removed_days": removed_days,
        "removed_rows": removed_rows,
        "removed_mentions": removed_mentions,
    }


def remove_state_range(processed_keys: Set[str], start_date: str, end_date: str) -> Tuple[Set[str], int]:
    kept = set()
    removed = 0
    for key in processed_keys:
        day = extract_day_from_state_key(key)
        if day and start_date <= day <= end_date:
            removed += 1
            continue
        kept.add(key)
    return kept, removed


def apply_analysis_reset_range(
    daily: Dict[str, Dict[str, int]],
    processed_keys: Set[str],
    start_day: str,
    end_day: str,
    days: int,
) -> AnalysisResetResult:
    daily, removed_daily = remove_daily_range(daily, start_day, end_day)
    processed_keys, removed_state_in_range = remove_state_range(processed_keys, start_day, end_day)
    required_days = get_required_days_for_start_date(start_day)
    return AnalysisResetResult(
        daily=daily,
        processed_keys=processed_keys,
        reset_summary={
            "start_date": start_day,
            "end_date": end_day,
            **removed_daily,
            "removed_state_keys": removed_state_in_range,
        },
        days=required_days if required_days > days else days,
    )
