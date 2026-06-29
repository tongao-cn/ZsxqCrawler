"""Database query contracts for ZSXQ file metadata workflows."""

from __future__ import annotations

from typing import Any, Dict, NamedTuple, Optional

from backend.crawlers.file_time_window import (
    is_datetime_bound as _is_datetime_bound,
    normalize_date_range,
)


class DatabaseTimeRangeRow(NamedTuple):
    oldest_time: Any
    newest_time: Any
    time_based_count: Any


def download_query_group_id(group_id: Any) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def database_download_effective_last_days(
    last_days: Optional[int],
    legacy_recent_days: Any,
) -> Any:
    if last_days is None and legacy_recent_days is not None:
        return legacy_recent_days
    return last_days


def database_download_query_plan(
    query_group_id: Any,
    max_files: Optional[int] = None,
    status_filter: Optional[str] = "pending",
    sort_by: str = "download_count",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    last_days: Optional[int] = None,
    legacy_order_by: Any = None,
) -> Dict[str, Any]:
    normalized_start, normalized_end, _ = normalize_date_range(
        start_date=start_date,
        end_date=end_date,
        last_days=last_days,
    )

    legacy_order = str(legacy_order_by or "").strip().lower()
    if legacy_order.startswith("create_time"):
        sort_by = "create_time"
    elif legacy_order.startswith("download_count"):
        sort_by = "download_count"

    conditions = ["group_id = ?"]
    params: list[Any] = [query_group_id]
    if status_filter:
        conditions.append("download_status = ?")
        params.append(status_filter)
    if normalized_start:
        conditions.append(
            "create_time >= ?" if _is_datetime_bound(normalized_start) else "substr(create_time, 1, 10) >= ?"
        )
        params.append(normalized_start)
    if normalized_end:
        conditions.append(
            "create_time <= ?" if _is_datetime_bound(normalized_end) else "substr(create_time, 1, 10) <= ?"
        )
        params.append(normalized_end)

    where_clause = f"WHERE {' AND '.join(conditions)}"
    order_clause = (
        "ORDER BY create_time DESC, download_count DESC"
        if sort_by == "create_time"
        else "ORDER BY download_count DESC, size ASC"
    )
    limit_clause = "LIMIT ?" if max_files else ""
    if max_files:
        params.append(max_files)

    query = f'''
            SELECT file_id, name, size, download_count, create_time
            FROM files
            {where_clause}
            {order_clause}
            {limit_clause}
        '''
    return {
        "query": query,
        "params": tuple(params),
        "sort_by": sort_by,
        "normalized_start": normalized_start,
        "normalized_end": normalized_end,
    }


def database_time_range_query(query_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT MIN(create_time) as oldest_time,
                   MAX(create_time) as newest_time,
                   COUNT(*) as total_count
            FROM files
            WHERE group_id = ?
              AND create_time IS NOT NULL AND create_time != ''
        ''',
        (query_group_id,),
    )


def _database_time_range_row(result: Any) -> DatabaseTimeRangeRow:
    if not result:
        return DatabaseTimeRangeRow(None, None, 0)
    return DatabaseTimeRangeRow(result[0], result[1], result[2])


def database_time_range_result(total_files: Any, result: Any) -> Dict[str, Any]:
    if total_files == 0:
        return {"has_data": False, "total_files": 0}
    time_range = _database_time_range_row(result)
    return {
        "has_data": True,
        "total_files": total_files,
        "oldest_time": time_range.oldest_time,
        "newest_time": time_range.newest_time,
        "time_based_count": time_range.time_based_count,
    }


def latest_file_create_time_query(query_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
                SELECT MAX(create_time) FROM files
                WHERE group_id = ?
                  AND create_time IS NOT NULL AND create_time != ''
            ''',
        (query_group_id,),
    )


def database_stats_total_size_query(query_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return "SELECT SUM(size) FROM files WHERE group_id = ? AND size IS NOT NULL", (query_group_id,)


def database_stats_time_range_query(query_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT MIN(create_time), MAX(create_time), COUNT(*)
            FROM files
            WHERE group_id = ? AND create_time IS NOT NULL
        ''',
        (query_group_id,),
    )


def database_stats_api_response_query() -> str:
    return '''
            SELECT succeeded, COUNT(*)
            FROM api_responses
            GROUP BY succeeded
        '''


__all__ = [
    "DatabaseTimeRangeRow",
    "database_download_effective_last_days",
    "database_download_query_plan",
    "database_stats_api_response_query",
    "database_stats_time_range_query",
    "database_stats_total_size_query",
    "database_time_range_query",
    "database_time_range_result",
    "download_query_group_id",
    "latest_file_create_time_query",
]
