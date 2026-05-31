from __future__ import annotations

import asyncio
import json
import random
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import requests

from backend.core.account_context import build_stealth_headers, get_cookie_for_group
from backend.core.db_path_manager import get_db_path_manager
from backend.core.image_cache_manager import get_image_cache_manager
from backend.core.logger_config import log_error, log_exception, log_info, log_warning
from backend.services.columns_column_service import (
    process_column as _service_process_column,
    process_column_topic as _service_process_column_topic,
)
from backend.services.columns_fetch_summary import (
    ColumnFetchStats,
    build_columns_fetch_result,
    build_columns_progress_message,
    combined_column_stats,
    resolve_columns_fetch_config,
)
from backend.services.columns_file_download_service import download_column_file as _service_download_column_file
from backend.services.columns_media_cache_service import (
    cache_topic_images as _service_cache_topic_images,
    cache_video_cover as _service_cache_video_cover,
)
from backend.services.columns_remote_service import (
    fetch_column_topics as _service_fetch_column_topics,
    fetch_columns_catalog as _service_fetch_columns_catalog,
    fetch_topic_detail as _service_fetch_topic_detail,
)
from backend.services.columns_resource_service import (
    collect_topic_files as _service_collect_topic_files,
    download_topic_files as _service_download_topic_files,
    download_topic_video as _service_download_topic_video,
    get_topic_video as _service_get_topic_video,
    process_topic_resources as _service_process_topic_resources,
)
from backend.services.columns_topic_persistence_service import (
    extract_topic_data as _service_extract_topic_data,
    prepare_column_topic as _service_prepare_column_topic,
    save_topic_detail as _service_save_topic_detail,
)
from backend.services.columns_video_download_service import download_column_video as _service_download_column_video
from backend.services.task_runtime import add_task_log, is_task_stopped, update_task
from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase


def get_columns_db(group_id: str) -> ZSXQColumnsDatabase:
    return ZSXQColumnsDatabase(group_id)


@contextmanager
def columns_db(group_id: str) -> Iterator[ZSXQColumnsDatabase]:
    db = get_columns_db(group_id)
    try:
        yield db
    finally:
        db.close()


def get_group_columns_response(group_id: str) -> Dict[str, Any]:
    with columns_db(group_id) as db:
        columns = db.get_columns(int(group_id))
        stats = db.get_stats(int(group_id))
    return {
        "columns": columns,
        "stats": stats,
    }


def get_column_topics_response(group_id: str, column_id: int) -> Dict[str, Any]:
    with columns_db(group_id) as db:
        topics = db.get_column_topics(column_id, group_id)
        column = db.get_column(column_id, group_id)
    return {
        "column": column,
        "topics": topics,
    }


def get_column_topic_detail_response(group_id: str, topic_id: int) -> Optional[Dict[str, Any]]:
    with columns_db(group_id) as db:
        detail = db.get_topic_detail(topic_id, group_id)

    if not detail:
        return None

    if detail.get("raw_json"):
        try:
            raw_data = json.loads(detail["raw_json"])
            topic_type = raw_data.get("type", "")

            if topic_type == "q&a":
                question = raw_data.get("question", {})
                answer = raw_data.get("answer", {})

                detail["question"] = {
                    "text": question.get("text", ""),
                    "owner": question.get("owner"),
                    "images": question.get("images", []),
                }
                detail["answer"] = {
                    "text": answer.get("text", ""),
                    "owner": answer.get("owner"),
                    "images": answer.get("images", []),
                }
                if not detail.get("full_text") and answer.get("text"):
                    detail["full_text"] = answer.get("text", "")
            elif topic_type == "talk":
                talk = raw_data.get("talk", {})
                if not detail.get("full_text") and talk.get("text"):
                    detail["full_text"] = talk.get("text", "")
        except (json.JSONDecodeError, TypeError):
            pass

    return detail


def get_columns_stats_response(group_id: str) -> Dict[str, Any]:
    with columns_db(group_id) as db:
        return db.get_stats(int(group_id))


def delete_all_columns_response(group_id: str) -> Dict[str, Any]:
    with columns_db(group_id) as db:
        stats = db.clear_all_data(int(group_id))
    return {
        "success": True,
        "message": "已清空专栏数据",
        "deleted": stats,
    }


def log_columns_fetch_config(task_id: str, group_id: str, config: Dict[str, Any]) -> None:
    add_task_log(task_id, f"📚 开始采集群组 {group_id} 的专栏内容")
    add_task_log(task_id, "=" * 50)
    add_task_log(task_id, "⚙️ 采集配置:")
    add_task_log(task_id, f"   ⏱️ 请求间隔: {config['crawl_interval_min']}~{config['crawl_interval_max']} 秒")
    add_task_log(task_id, f"   😴 长休眠间隔: {config['long_sleep_min']}~{config['long_sleep_max']} 秒")
    add_task_log(task_id, f"   📦 批次大小: {config['items_per_batch']} 个请求")
    add_task_log(task_id, f"   📥 下载文件: {'是' if config['download_files'] else '否'}")
    add_task_log(task_id, f"   🎬 下载视频: {'是' if config['download_videos'] else '否'}")
    add_task_log(task_id, f"   🖼️ 缓存图片: {'是' if config['cache_images'] else '否'}")
    add_task_log(task_id, f"   🔄 增量模式: {'是（跳过已存在）' if config['incremental_mode'] else '否（全量采集）'}")
    add_task_log(task_id, "=" * 50)


def complete_empty_columns_task(task_id: str) -> None:
    add_task_log(task_id, "ℹ️ 该群组没有专栏内容")
    update_task(task_id, "completed", "该群组没有专栏内容")


def extract_topic_data(topic_detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _service_extract_topic_data(topic_detail)


def save_topic_detail(
    db: ZSXQColumnsDatabase,
    group_id: str,
    topic_detail: Dict[str, Any],
) -> bool:
    return _service_save_topic_detail(db=db, group_id=group_id, topic_detail=topic_detail)


def prepare_column_topic(
    task_id: str,
    db: ZSXQColumnsDatabase,
    column_id: int,
    group_id: str,
    topic: Dict[str, Any],
    topic_idx: int,
    total_topics: int,
    incremental_mode: bool,
) -> tuple[Optional[int], str, bool]:
    return _service_prepare_column_topic(
        add_task_log=add_task_log,
        column_id=column_id,
        db=db,
        group_id=group_id,
        incremental_mode=incremental_mode,
        task_id=task_id,
        topic=topic,
        topic_idx=topic_idx,
        total_topics=total_topics,
    )


async def process_topic_resources(
    task_id: str,
    group_id: str,
    topic_id: int,
    topic_detail: Dict[str, Any],
    db: ZSXQColumnsDatabase,
    headers: Dict[str, str],
    current_request_count: int,
    config: Dict[str, Any],
) -> ColumnFetchStats:
    return await _service_process_topic_resources(
        add_task_log=add_task_log,
        cache_topic_images=cache_topic_images,
        cache_video_cover=cache_video_cover,
        config=config,
        current_request_count=current_request_count,
        db=db,
        download_topic_files=download_topic_files,
        download_topic_video=download_topic_video,
        get_topic_video_fn=get_topic_video,
        group_id=group_id,
        headers=headers,
        task_id=task_id,
        topic_detail=topic_detail,
        topic_id=topic_id,
    )


async def process_column_topic(
    task_id: str,
    group_id: str,
    column_id: int,
    topic: Dict[str, Any],
    topic_idx: int,
    total_topics: int,
    db: ZSXQColumnsDatabase,
    headers: Dict[str, str],
    current_request_count: int,
    config: Dict[str, Any],
) -> ColumnFetchStats:
    return await _service_process_column_topic(
        column_id=column_id,
        config=config,
        current_request_count=current_request_count,
        db=db,
        fetch_topic_detail=fetch_topic_detail,
        group_id=group_id,
        headers=headers,
        prepare_column_topic=prepare_column_topic,
        process_topic_resources=process_topic_resources,
        save_topic_detail=save_topic_detail,
        task_id=task_id,
        topic=topic,
        topic_idx=topic_idx,
        total_topics=total_topics,
    )


async def process_column(
    task_id: str,
    group_id: str,
    column: Dict[str, Any],
    col_idx: int,
    total_columns: int,
    db: ZSXQColumnsDatabase,
    headers: Dict[str, str],
    current_request_count: int,
    config: Dict[str, Any],
    base_stats: ColumnFetchStats | None = None,
) -> ColumnFetchStats:
    return await _service_process_column(
        add_task_log=add_task_log,
        base_stats=base_stats,
        build_progress_message=build_columns_progress_message,
        column=column,
        col_idx=col_idx,
        combined_stats=combined_column_stats,
        config=config,
        current_request_count=current_request_count,
        db=db,
        fetch_column_topics=fetch_column_topics,
        group_id=group_id,
        headers=headers,
        is_task_stopped=is_task_stopped,
        process_column_topic=process_column_topic,
        random_uniform=random.uniform,
        sleep=asyncio.sleep,
        task_id=task_id,
        total_columns=total_columns,
        update_task=update_task,
    )


async def fetch_columns_catalog(task_id: str, group_id: str, headers: Dict[str, str]) -> tuple[List[Dict[str, Any]], int]:
    return await _service_fetch_columns_catalog(
        task_id,
        group_id,
        headers,
        request_get=requests.get,
        is_task_stopped=is_task_stopped,
        add_task_log=add_task_log,
        log_error=log_error,
        log_exception=log_exception,
        sleep=asyncio.sleep,
    )


def fetch_column_topics(
    task_id: str,
    column_id: int,
    topics_url: str,
    headers: Dict[str, str],
) -> tuple[Optional[List[Dict[str, Any]]], int]:
    return _service_fetch_column_topics(
        task_id,
        column_id,
        topics_url,
        headers,
        request_get=requests.get,
        add_task_log=add_task_log,
        log_error=log_error,
        log_exception=log_exception,
    )


async def fetch_topic_detail(
    task_id: str,
    topic_id: int,
    headers: Dict[str, str],
    current_request_count: int,
    items_per_batch: int,
    long_sleep_min: float,
    long_sleep_max: float,
    crawl_interval_min: float,
    crawl_interval_max: float,
) -> tuple[Optional[Dict[str, Any]], int]:
    return await _service_fetch_topic_detail(
        task_id,
        topic_id,
        headers,
        current_request_count,
        items_per_batch,
        long_sleep_min,
        long_sleep_max,
        crawl_interval_min,
        crawl_interval_max,
        request_get=requests.get,
        is_task_stopped=is_task_stopped,
        add_task_log=add_task_log,
        log_error=log_error,
        log_exception=log_exception,
        sleep=asyncio.sleep,
        random_uniform=random.uniform,
    )


def collect_topic_files(topic_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _service_collect_topic_files(topic_detail)


async def download_column_file(
    group_id: str,
    file_id: int,
    file_name: str,
    file_size: int,
    topic_id: int,
    db: ZSXQColumnsDatabase,
    headers: dict,
    task_id: str = None,
) -> str:
    group_dir = get_db_path_manager().get_group_dir(group_id)
    return await _service_download_column_file(
        add_task_log=add_task_log,
        db=db,
        file_id=file_id,
        file_name=file_name,
        file_size=file_size,
        group_dir=group_dir,
        headers=headers,
        log_error=log_error,
        log_exception=log_exception,
        log_warning=log_warning,
        request_get=requests.get,
        sleep=asyncio.sleep,
        task_id=task_id,
    )


async def download_topic_files(
    task_id: str,
    group_id: str,
    topic_id: int,
    topic_detail: Dict[str, Any],
    db: ZSXQColumnsDatabase,
    headers: Dict[str, str],
    current_request_count: int,
    items_per_batch: int,
    long_sleep_min: float,
    long_sleep_max: float,
    crawl_interval_min: float,
    crawl_interval_max: float,
) -> tuple[int, int, int]:
    return await _service_download_topic_files(
        add_task_log=add_task_log,
        crawl_interval_max=crawl_interval_max,
        crawl_interval_min=crawl_interval_min,
        current_request_count=current_request_count,
        db=db,
        download_column_file=download_column_file,
        group_id=group_id,
        headers=headers,
        is_task_stopped=is_task_stopped,
        items_per_batch=items_per_batch,
        log_exception=log_exception,
        long_sleep_max=long_sleep_max,
        long_sleep_min=long_sleep_min,
        random_uniform=random.uniform,
        sleep=asyncio.sleep,
        task_id=task_id,
        topic_detail=topic_detail,
        topic_id=topic_id,
    )


def cache_topic_images(task_id: str, group_id: str, topic_detail: Dict[str, Any], db: ZSXQColumnsDatabase) -> int:
    return _service_cache_topic_images(
        add_task_log=add_task_log,
        cache_manager_factory=get_image_cache_manager,
        db=db,
        group_id=group_id,
        is_task_stopped=is_task_stopped,
        log_exception=log_exception,
        task_id=task_id,
        topic_detail=topic_detail,
    )


def get_topic_video(topic_detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _service_get_topic_video(topic_detail)


def cache_video_cover(
    task_id: str,
    group_id: str,
    video_id: int,
    cover_url: Optional[str],
    db: ZSXQColumnsDatabase,
) -> bool:
    return _service_cache_video_cover(
        add_task_log=add_task_log,
        cache_manager_factory=get_image_cache_manager,
        cover_url=cover_url,
        db=db,
        group_id=group_id,
        log_exception=log_exception,
        log_warning=log_warning,
        task_id=task_id,
        video_id=video_id,
    )


async def download_column_video(
    group_id: str,
    video_id: int,
    video_size: int,
    video_duration: int,
    topic_id: int,
    db: ZSXQColumnsDatabase,
    headers: dict,
    task_id: str = None,
) -> str:
    group_dir = get_db_path_manager().get_group_dir(group_id)
    return await _service_download_column_video(
        add_task_log=add_task_log,
        db=db,
        group_dir=group_dir,
        headers=headers,
        log_error=log_error,
        log_exception=log_exception,
        log_info=log_info,
        request_get=requests.get,
        task_id=task_id,
        topic_id=topic_id,
        video_duration=video_duration,
        video_id=video_id,
        video_size=video_size,
    )


async def download_topic_video(
    task_id: str,
    group_id: str,
    topic_id: int,
    video: Dict[str, Any],
    db: ZSXQColumnsDatabase,
    headers: Dict[str, str],
    current_request_count: int,
    items_per_batch: int,
    long_sleep_min: float,
    long_sleep_max: float,
    crawl_interval_min: float,
    crawl_interval_max: float,
) -> tuple[int, int, int]:
    return await _service_download_topic_video(
        add_task_log=add_task_log,
        crawl_interval_max=crawl_interval_max,
        crawl_interval_min=crawl_interval_min,
        current_request_count=current_request_count,
        db=db,
        download_column_video=download_column_video,
        group_id=group_id,
        headers=headers,
        items_per_batch=items_per_batch,
        log_exception=log_exception,
        long_sleep_max=long_sleep_max,
        long_sleep_min=long_sleep_min,
        random_uniform=random.uniform,
        sleep=asyncio.sleep,
        task_id=task_id,
        topic_id=topic_id,
        video=video,
    )


async def run_columns_fetch_task(task_id: str, group_id: str, settings: Any) -> None:
    log_id = None
    db = None

    try:
        config = resolve_columns_fetch_config(settings)

        log_columns_fetch_config(task_id, group_id, config)

        cookie = get_cookie_for_group(group_id)
        if not cookie:
            raise RuntimeError("未找到可用Cookie，请先配置账号")

        headers = build_stealth_headers(cookie)
        db = get_columns_db(group_id)
        log_id = db.start_crawl_log(int(group_id), "full_fetch")

        stats = ColumnFetchStats()
        request_count = 0

        add_task_log(task_id, "📂 获取专栏目录列表...")
        columns, catalog_request_count = await fetch_columns_catalog(task_id, group_id, headers)
        request_count += catalog_request_count

        add_task_log(task_id, f"✅ 获取到 {len(columns)} 个专栏目录")

        if len(columns) == 0:
            complete_empty_columns_task(task_id)
            return

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

        if is_task_stopped(task_id):
            update_task(task_id, "stopped", "任务已被用户停止")
            return

        if log_id:
            db.update_crawl_log(
                log_id,
                columns_count=stats.columns_count,
                topics_count=stats.topics_count,
                details_count=stats.details_count,
                files_count=stats.files_count,
                status="completed",
            )

        result_msg, result_payload = build_columns_fetch_result(
            stats.columns_count,
            stats.topics_count,
            stats.details_count,
            stats.files_count,
            stats.images_count,
            stats.videos_count,
            stats.skipped_count,
            stats.files_skipped,
            stats.videos_skipped,
        )

        update_task(
            task_id,
            "completed",
            result_msg,
            result_payload,
        )
    except Exception as exc:
        try:
            if log_id and db:
                db.update_crawl_log(log_id, status="failed", error_message=str(exc))
        except Exception:
            pass

        try:
            update_task(task_id, "failed", f"专栏采集失败: {str(exc)}")
        except Exception:
            pass

        try:
            add_task_log(task_id, f"❌ 专栏采集失败: {str(exc)}")
        except Exception:
            pass
    finally:
        try:
            if db:
                db.close()
        except Exception:
            pass
