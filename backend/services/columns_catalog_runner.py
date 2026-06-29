from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List

from backend.services.columns_fetch_summary import ColumnFetchStats


ColumnProcessor = Callable[
    [
        str,
        str,
        Dict[str, Any],
        int,
        int,
        Any,
        Dict[str, str],
        int,
        Dict[str, Any],
        ColumnFetchStats,
    ],
    Awaitable[ColumnFetchStats],
]
TaskStoppedChecker = Callable[[str], bool]
TaskLogWriter = Callable[[str, str], None]


@dataclass(frozen=True)
class ColumnsCatalogRunResult:
    stats: ColumnFetchStats
    request_count: int


async def process_columns_catalog(
    *,
    task_id: str,
    group_id: str,
    columns: List[Dict[str, Any]],
    db: Any,
    headers: Dict[str, str],
    request_count: int,
    config: Dict[str, Any],
    stats: ColumnFetchStats,
    process_column: ColumnProcessor,
    is_task_stopped: TaskStoppedChecker,
    add_task_log: TaskLogWriter,
) -> ColumnsCatalogRunResult:
    for col_idx, column in enumerate(columns, 1):
        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务已被用户停止")
            break

        column_stats = await process_column(
            task_id,
            group_id,
            column,
            col_idx,
            len(columns),
            db,
            headers,
            request_count,
            config,
            stats,
        )
        stats.add(column_stats)
        request_count += column_stats.request_count

    return ColumnsCatalogRunResult(stats=stats, request_count=request_count)
