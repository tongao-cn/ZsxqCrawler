from __future__ import annotations

import asyncio
import random
from typing import Any, Awaitable, Callable, Dict, List

from backend.services.columns_fetch_summary import (
    ColumnFetchStats,
    build_columns_progress_message,
    combined_column_stats,
)


async def process_column_topic(
    *,
    config: Dict[str, Any],
    current_request_count: int,
    db: Any,
    fetch_topic_detail: Callable[..., Awaitable[tuple[Dict[str, Any] | None, int]]],
    group_id: str,
    headers: Dict[str, str],
    prepare_column_topic: Callable[..., tuple[int | None, str, bool]],
    process_topic_resources: Callable[..., Awaitable[ColumnFetchStats]],
    save_topic_detail: Callable[..., bool],
    task_id: str,
    topic: Dict[str, Any],
    topic_idx: int,
    total_topics: int,
    column_id: int,
) -> ColumnFetchStats:
    topic_id, _topic_title, topic_skipped = prepare_column_topic(
        task_id,
        db,
        column_id,
        group_id,
        topic,
        topic_idx,
        total_topics,
        config["incremental_mode"],
    )
    if topic_skipped:
        return ColumnFetchStats(topics_count=1, skipped_count=1)

    topic_detail, detail_request_count = await fetch_topic_detail(
        task_id,
        topic_id,
        headers,
        current_request_count,
        config["items_per_batch"],
        config["long_sleep_min"],
        config["long_sleep_max"],
        config["crawl_interval_min"],
        config["crawl_interval_max"],
    )

    if not topic_detail or not topic_detail.get("succeeded"):
        return ColumnFetchStats(topics_count=1, request_count=detail_request_count)

    if not save_topic_detail(db, group_id, topic_detail):
        return ColumnFetchStats(topics_count=1, request_count=detail_request_count)

    stats = ColumnFetchStats(topics_count=1, details_count=1, request_count=detail_request_count)
    stats.add(
        await process_topic_resources(
            task_id,
            group_id,
            topic_id,
            topic_detail,
            db,
            headers,
            current_request_count + detail_request_count,
            config,
        )
    )

    return stats


async def process_column(
    *,
    add_task_log: Callable[[str, str], None],
    base_stats: ColumnFetchStats | None = None,
    build_progress_message: Callable[[int, int, int, int], str] = build_columns_progress_message,
    column: Dict[str, Any],
    col_idx: int,
    combined_stats: Callable[[ColumnFetchStats, ColumnFetchStats], ColumnFetchStats] = combined_column_stats,
    config: Dict[str, Any],
    current_request_count: int,
    db: Any,
    fetch_column_topics: Callable[[str, int, str, Dict[str, str]], tuple[List[Dict[str, Any]] | None, int]],
    group_id: str,
    headers: Dict[str, str],
    is_task_stopped: Callable[[str], bool],
    process_column_topic: Callable[..., Awaitable[ColumnFetchStats]],
    random_uniform: Callable[[float, float], float] = random.uniform,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    task_id: str,
    total_columns: int,
    update_task: Callable[[str, str, str], None],
) -> ColumnFetchStats:
    request_count = current_request_count
    stats = ColumnFetchStats(columns_count=1)

    column_id = column.get("column_id")
    column_name = column.get("name", "未命名")
    column_topics_count = column.get("statistics", {}).get("topics_count", 0)
    db.insert_column(int(group_id), column)

    add_task_log(task_id, "")
    add_task_log(task_id, f"📁 [{col_idx}/{total_columns}] 专栏: {column_name}")
    add_task_log(task_id, f"   📊 预计文章数: {column_topics_count}")

    if request_count > 0 and request_count % config["items_per_batch"] == 0:
        sleep_time = random_uniform(config["long_sleep_min"], config["long_sleep_max"])
        add_task_log(task_id, f"   😴 已完成 {request_count} 次请求，休眠 {sleep_time:.1f} 秒...")
        await sleep(sleep_time)

    delay = random_uniform(config["crawl_interval_min"], config["crawl_interval_max"])
    add_task_log(task_id, f"   ⏳ 等待 {delay:.1f} 秒后获取文章列表...")
    await sleep(delay)

    topics_url = f"https://api.zsxq.com/v2/groups/{group_id}/columns/{column_id}/topics?count=100&sort=default&direction=desc"
    topics_list, topics_request_count = fetch_column_topics(task_id, column_id, topics_url, headers)
    request_count += topics_request_count
    stats.request_count += topics_request_count
    if topics_list is None:
        return stats

    for topic_idx, topic in enumerate(topics_list, 1):
        if is_task_stopped(task_id):
            break

        topic_stats = await process_column_topic(
            task_id,
            group_id,
            column_id,
            topic,
            topic_idx,
            len(topics_list),
            db,
            headers,
            request_count,
            config,
        )
        stats.add(topic_stats)
        request_count += topic_stats.request_count

        if topic_stats.details_count:
            progress_stats = combined_stats(base_stats or ColumnFetchStats(), stats)
            update_task(
                task_id,
                "running",
                build_progress_message(
                    progress_stats.details_count,
                    progress_stats.files_count,
                    progress_stats.videos_count,
                    progress_stats.images_count,
                ),
            )

    return stats
