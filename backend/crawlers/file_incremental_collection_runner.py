"""Incremental and date-range collection runner for ZSXQ files."""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional, Protocol

from backend.crawlers.file_time_collection_runner import should_stop_time_collection_initially
from backend.crawlers.zsxq_file_downloader_helpers import (
    date_range_collection_start_messages,
    incremental_collection_empty_database_message,
    incremental_collection_missing_time_message,
    incremental_collection_start_index_message,
    incremental_collection_start_message,
    incremental_collection_status_messages,
    incremental_collection_target_message,
    incremental_collection_timestamp_failure_messages,
    incremental_start_index,
    normalize_date_range,
)
from backend.crawlers.zsxq_file_downloader_targets import (
    DateRangeCollectionTarget,
    IncrementalCollectionTarget,
)


class IncrementalCollectionRuntime(Protocol):
    def log(self, message: str) -> None:
        ...

    def check_stop(self) -> bool:
        ...

    def get_database_time_range(self) -> Dict[str, Any]:
        ...

    def collect_files_by_time(
        self,
        sort: str = "by_create_time",
        start_time: Optional[str] = None,
        stop_before_time: Optional[datetime.datetime] = None,
        **kwargs: Any,
    ) -> Dict[str, int]:
        ...


def collect_incremental_from_oldest_time(
    runtime: IncrementalCollectionRuntime,
    oldest_time: Any,
) -> Dict[str, int]:
    runtime.log(incremental_collection_target_message())

    try:
        start_index = incremental_start_index(oldest_time)
        runtime.log(incremental_collection_start_index_message(start_index))

        return runtime.collect_files_by_time(start_time=start_index)

    except Exception as e:
        for message in incremental_collection_timestamp_failure_messages(e):
            runtime.log(message)
        return runtime.collect_files_by_time()


def collect_incremental_from_time_info(
    runtime: IncrementalCollectionRuntime,
    time_info: Dict[str, Any],
) -> Dict[str, int]:
    if not time_info["has_data"]:
        runtime.log(incremental_collection_empty_database_message())
        return runtime.collect_files_by_time()

    oldest_time = time_info["oldest_time"]
    # Preserve historical key validation before emitting status logs.
    _ = (time_info["newest_time"], time_info["total_files"])

    for message in incremental_collection_status_messages(time_info):
        runtime.log(message)

    if not oldest_time:
        runtime.log(incremental_collection_missing_time_message())
        return runtime.collect_files_by_time()

    return collect_incremental_from_oldest_time(runtime, oldest_time)


def collect_files_for_normalized_date_range(
    runtime: IncrementalCollectionRuntime,
    normalized_start: Optional[str],
    normalized_end: Optional[str],
    stop_before_dt: Optional[datetime.datetime],
) -> Dict[str, int]:
    for message in date_range_collection_start_messages(normalized_start, normalized_end):
        runtime.log(message)
    return runtime.collect_files_by_time(
        sort="by_create_time",
        start_time=None,
        stop_before_time=stop_before_dt,
    )


def collect_incremental_files(
    runtime: IncrementalCollectionRuntime,
    target: IncrementalCollectionTarget,
) -> Dict[str, int]:
    runtime.log(incremental_collection_start_message())

    if should_stop_time_collection_initially(runtime):
        return {"total_files": 0, "new_files": 0}

    time_info = runtime.get_database_time_range()

    return collect_incremental_from_time_info(runtime, time_info)


def collect_files_for_date_range(
    runtime: IncrementalCollectionRuntime,
    target: DateRangeCollectionTarget,
) -> Dict[str, int]:
    normalized_start, normalized_end, stop_before_dt = normalize_date_range(
        start_date=target.start_date,
        end_date=target.end_date,
        last_days=target.last_days,
    )
    return collect_files_for_normalized_date_range(
        runtime,
        normalized_start,
        normalized_end,
        stop_before_dt,
    )
