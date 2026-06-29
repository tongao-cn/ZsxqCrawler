from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.core.local_group_runtime import get_cached_local_group_ids
from backend.services.a_share_analysis_dates import normalize_date_range
from backend.services.a_share_analysis_local_store import (
    DEFAULT_OUTPUT_PATH,
    DEFAULT_STATE_PATH,
    normalize_group_id,
    resolve_analysis_paths,
)


LogCallback = Optional[Callable[[str], None]]
TopicReaderLastDays = Callable[[str, int, LogCallback], List[Dict[str, Any]]]
TopicReaderDateRange = Callable[[str, str, str, LogCallback], List[Dict[str, Any]]]


@dataclass(frozen=True)
class AShareAnalysisRunPlan:
    days: int
    concurrency: int
    normalized_group_id: Optional[str]
    output_path: str
    state_path: str
    run_date_range: Optional[Tuple[str, str]]


def build_analysis_run_plan(
    *,
    days: int,
    concurrency: int,
    output_path: str = DEFAULT_OUTPUT_PATH,
    state_path: str = DEFAULT_STATE_PATH,
    group_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> AShareAnalysisRunPlan:
    normalized_group_id = normalize_group_id(group_id)
    resolved_output_path, resolved_state_path = resolve_analysis_paths(output_path, state_path, normalized_group_id)
    return AShareAnalysisRunPlan(
        days=max(1, int(days)),
        concurrency=max(1, int(concurrency)),
        normalized_group_id=normalized_group_id,
        output_path=resolved_output_path,
        state_path=resolved_state_path,
        run_date_range=normalize_run_date_range(start_date, end_date),
    )


def normalize_run_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
) -> Optional[Tuple[str, str]]:
    if not start_date and not end_date:
        return None
    if not start_date or not end_date:
        raise ValueError("start_date 和 end_date 需要同时提供")
    return normalize_date_range(
        start_date,
        end_date,
        "start_date",
        "end_date",
        "start_date 不能晚于 end_date",
    )


def discover_analysis_groups(
    normalized_group_id: Optional[str],
    *,
    load_local_group_ids: Callable[..., set] = get_cached_local_group_ids,
) -> List[str]:
    if normalized_group_id:
        return [normalized_group_id]
    return [str(group_id) for group_id in sorted(load_local_group_ids(force_refresh=True))]


def load_analysis_run_items(
    groups: Sequence[str],
    *,
    days: int,
    run_date_range: Optional[Tuple[str, str]],
    read_topics_last_days: TopicReaderLastDays,
    read_topics_in_date_range: TopicReaderDateRange,
    log_callback: LogCallback = None,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for group_id in groups:
        if run_date_range:
            items.extend(read_topics_in_date_range(group_id, run_date_range[0], run_date_range[1], log_callback))
        else:
            items.extend(read_topics_last_days(group_id, days, log_callback))
    return items
