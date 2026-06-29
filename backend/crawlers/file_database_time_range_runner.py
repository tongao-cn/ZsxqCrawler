"""Database time-range reader for ZSXQ file metadata."""

from __future__ import annotations

from typing import Any, Dict, Protocol

from backend.crawlers.file_database_queries import (
    database_time_range_query,
    database_time_range_result,
    download_query_group_id,
)
from backend.crawlers.zsxq_file_downloader_targets import DatabaseTimeRangeTarget


class DatabaseTimeRangeRuntime(Protocol):
    group_id: str
    file_db: Any


def get_database_time_range(
    runtime: DatabaseTimeRangeRuntime,
    target: DatabaseTimeRangeTarget,
) -> Dict[str, Any]:
    stats = runtime.file_db.get_database_stats()
    total_files = stats.get("files", 0)

    if total_files == 0:
        return database_time_range_result(total_files, None)

    query, params = database_time_range_query(download_query_group_id(runtime.group_id))
    runtime.file_db.cursor.execute(query, params)

    result = runtime.file_db.cursor.fetchone()

    return database_time_range_result(total_files, result)
