from __future__ import annotations

import asyncio
import json
import random
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.core.account_context import build_stealth_headers, get_cookie_for_group
from backend.core.db_path_manager import get_db_path_manager
from backend.core.image_cache_manager import get_image_cache_manager
from backend.core.logger_config import log_debug, log_error, log_exception, log_info, log_warning
from backend.services.columns_fetch_summary import (
    ColumnFetchStats,
    build_columns_fetch_result as _build_columns_fetch_result,
    build_columns_progress_message as _build_columns_progress_message,
    combined_column_stats as _combined_column_stats,
    resolve_columns_fetch_config as _resolve_columns_fetch_config,
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
    redact_response_for_log as _redact_response_for_log,
    retry_wait_seconds as _retry_wait_seconds,
)
from backend.services.columns_resource_service import (
    collect_topic_files as _service_collect_topic_files,
    download_topic_files as _service_download_topic_files,
    download_topic_video as _service_download_topic_video,
    get_topic_video as _service_get_topic_video,
    process_topic_resources as _service_process_topic_resources,
)
from backend.services.columns_summary_service import get_columns_summary
from backend.services.columns_topic_persistence_service import (
    extract_topic_data as _service_extract_topic_data,
    prepare_column_topic as _service_prepare_column_topic,
    save_topic_detail as _service_save_topic_detail,
)
from backend.services.columns_video_download_service import download_column_video as _service_download_column_video
from backend.routes.ingestion_helpers import create_ingestion_task_or_raise
from backend.services.task_runtime import add_task_log, enqueue_runtime_task, is_task_stopped, update_task
from backend.storage.accounts_sql_manager import get_accounts_sql_manager
from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

router = APIRouter(prefix="/api", tags=["columns"])


class ColumnsSettingsRequest(BaseModel):
    """专栏采集设置请求"""
    crawlIntervalMin: Optional[float] = Field(default=2.0, ge=1.0, le=60.0, description="采集间隔最小值(秒)")
    crawlIntervalMax: Optional[float] = Field(default=5.0, ge=1.0, le=60.0, description="采集间隔最大值(秒)")
    longSleepIntervalMin: Optional[float] = Field(default=30.0, ge=10.0, le=600.0, description="长休眠间隔最小值(秒)")
    longSleepIntervalMax: Optional[float] = Field(default=60.0, ge=10.0, le=600.0, description="长休眠间隔最大值(秒)")
    itemsPerBatch: Optional[int] = Field(default=10, ge=3, le=50, description="每批次处理数量")
    downloadFiles: Optional[bool] = Field(default=True, description="是否下载文件")
    downloadVideos: Optional[bool] = Field(default=True, description="是否下载视频(需要ffmpeg)")
    cacheImages: Optional[bool] = Field(default=True, description="是否缓存图片")
    incrementalMode: Optional[bool] = Field(default=False, description="增量模式：跳过已存在的文章详情")

def _log_columns_fetch_config(task_id: str, group_id: str, config: Dict[str, Any]) -> None:
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


def _create_columns_fetch_task_response(
    background_tasks: BackgroundTasks,
    group_id: str,
    request: ColumnsSettingsRequest,
) -> Dict[str, Any]:
    task_id = create_ingestion_task_or_raise(
        "columns_fetch",
        f"采集专栏内容 (群组: {group_id})",
        group_id,
    )
    update_task(task_id, "running", "正在采集专栏内容...")
    enqueue_runtime_task(_fetch_columns_task, task_id, group_id, request)
    return {
        "success": True,
        "task_id": task_id,
        "message": "专栏采集任务已启动",
    }


def _complete_empty_columns_task(task_id: str) -> None:
    add_task_log(task_id, "ℹ️ 该群组没有专栏内容")
    update_task(task_id, "completed", "该群组没有专栏内容")


def _extract_topic_data(topic_detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _service_extract_topic_data(topic_detail)


def _save_topic_detail(
    db: ZSXQColumnsDatabase,
    group_id: str,
    topic_detail: Dict[str, Any],
) -> bool:
    return _service_save_topic_detail(db=db, group_id=group_id, topic_detail=topic_detail)


def _prepare_column_topic(
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


async def _process_topic_resources(
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
        cache_topic_images=_cache_topic_images,
        cache_video_cover=_cache_video_cover,
        config=config,
        current_request_count=current_request_count,
        db=db,
        download_topic_files=_download_topic_files,
        download_topic_video=_download_topic_video,
        get_topic_video_fn=_get_topic_video,
        group_id=group_id,
        headers=headers,
        task_id=task_id,
        topic_detail=topic_detail,
        topic_id=topic_id,
    )


async def _process_column_topic(
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
    topic_id, _topic_title, topic_skipped = _prepare_column_topic(
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

    topic_detail, detail_request_count = await _fetch_topic_detail(
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

    if not _save_topic_detail(db, group_id, topic_detail):
        return ColumnFetchStats(topics_count=1, request_count=detail_request_count)

    stats = ColumnFetchStats(topics_count=1, details_count=1, request_count=detail_request_count)
    stats.add(await _process_topic_resources(
        task_id,
        group_id,
        topic_id,
        topic_detail,
        db,
        headers,
        current_request_count + detail_request_count,
        config,
    ))

    return stats


async def _process_column(
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
        sleep_time = random.uniform(config["long_sleep_min"], config["long_sleep_max"])
        add_task_log(task_id, f"   😴 已完成 {request_count} 次请求，休眠 {sleep_time:.1f} 秒...")
        await asyncio.sleep(sleep_time)

    delay = random.uniform(config["crawl_interval_min"], config["crawl_interval_max"])
    add_task_log(task_id, f"   ⏳ 等待 {delay:.1f} 秒后获取文章列表...")
    await asyncio.sleep(delay)

    topics_url = f"https://api.zsxq.com/v2/groups/{group_id}/columns/{column_id}/topics?count=100&sort=default&direction=desc"
    topics_list, topics_request_count = _fetch_column_topics(task_id, column_id, topics_url, headers)
    request_count += topics_request_count
    stats.request_count += topics_request_count
    if topics_list is None:
        return stats

    for topic_idx, topic in enumerate(topics_list, 1):
        if is_task_stopped(task_id):
            break

        topic_stats = await _process_column_topic(
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
            progress_stats = _combined_column_stats(base_stats or ColumnFetchStats(), stats)
            update_task(
                task_id,
                "running",
                _build_columns_progress_message(
                    progress_stats.details_count,
                    progress_stats.files_count,
                    progress_stats.videos_count,
                    progress_stats.images_count,
                ),
            )

    return stats


def get_columns_db(group_id: str) -> ZSXQColumnsDatabase:
    """获取指定群组的专栏数据库实例"""
    return ZSXQColumnsDatabase(group_id)


@contextmanager
def _columns_db(group_id: str) -> Iterator[ZSXQColumnsDatabase]:
    db = get_columns_db(group_id)
    try:
        yield db
    finally:
        db.close()


async def _fetch_columns_catalog(task_id: str, group_id: str, headers: Dict[str, str]) -> tuple[List[Dict[str, Any]], int]:
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


def _fetch_column_topics(
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


async def _fetch_topic_detail(
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


def _collect_topic_files(topic_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _service_collect_topic_files(topic_detail)


async def _download_column_file(group_id: str, file_id: int, file_name: str, file_size: int,
                                topic_id: int, db: ZSXQColumnsDatabase, headers: dict, task_id: str = None) -> str:
    """下载专栏文件"""
    path_manager = get_db_path_manager()
    group_dir = path_manager.get_group_dir(group_id)
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


async def _download_topic_files(
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
        download_column_file=_download_column_file,
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


def _cache_topic_images(task_id: str, group_id: str, topic_detail: Dict[str, Any], db: ZSXQColumnsDatabase) -> int:
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


def _get_topic_video(topic_detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _service_get_topic_video(topic_detail)


def _cache_video_cover(
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


async def _download_column_video(group_id: str, video_id: int, video_size: int, video_duration: int,
                                 topic_id: int, db: ZSXQColumnsDatabase, headers: dict, task_id: str = None) -> str:
    path_manager = get_db_path_manager()
    group_dir = path_manager.get_group_dir(group_id)
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


async def _download_topic_video(
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
        download_column_video=_download_column_video,
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


@router.get("/groups/{group_id}/columns/summary")
async def get_group_columns_summary(group_id: str):
    """获取群组专栏摘要信息，检查是否存在专栏内容"""
    return get_columns_summary(group_id)


@router.get("/groups/{group_id}/columns")
async def get_group_columns(group_id: str):
    """获取群组的专栏目录列表（从本地数据库）"""
    try:
        with _columns_db(group_id) as db:
            columns = db.get_columns(int(group_id))
            stats = db.get_stats(int(group_id))
        return {
            "columns": columns,
            "stats": stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取专栏目录失败: {str(e)}")


@router.get("/groups/{group_id}/columns/{column_id}/topics")
async def get_column_topics(group_id: str, column_id: int):
    """获取专栏下的文章列表（从本地数据库）"""
    try:
        with _columns_db(group_id) as db:
            topics = db.get_column_topics(column_id, group_id)
            column = db.get_column(column_id, group_id)
        return {
            "column": column,
            "topics": topics,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取专栏文章列表失败: {str(e)}")


@router.get("/groups/{group_id}/columns/topics/{topic_id}")
async def get_column_topic_detail(group_id: str, topic_id: int):
    """获取专栏文章详情（从本地数据库）"""
    try:
        with _columns_db(group_id) as db:
            detail = db.get_topic_detail(topic_id, group_id)

        if not detail:
            raise HTTPException(status_code=404, detail="文章详情不存在")

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文章详情失败: {str(e)}")


@router.post("/groups/{group_id}/columns/fetch")
async def fetch_group_columns(group_id: str, request: ColumnsSettingsRequest, background_tasks: BackgroundTasks):
    """采集群组的所有专栏内容（后台任务）"""
    try:
        return _create_columns_fetch_task_response(background_tasks, group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动专栏采集失败: {str(e)}")


async def _fetch_columns_task(task_id: str, group_id: str, settings: ColumnsSettingsRequest):
    """专栏采集后台任务"""
    log_id = None
    db = None

    try:
        config = _resolve_columns_fetch_config(settings)

        _log_columns_fetch_config(task_id, group_id, config)

        cookie = get_cookie_for_group(group_id)
        if not cookie:
            raise Exception("未找到可用Cookie，请先配置账号")

        headers = build_stealth_headers(cookie)
        db = get_columns_db(group_id)
        log_id = db.start_crawl_log(int(group_id), "full_fetch")

        stats = ColumnFetchStats()
        request_count = 0

        add_task_log(task_id, "📂 获取专栏目录列表...")
        columns, catalog_request_count = await _fetch_columns_catalog(task_id, group_id, headers)
        request_count += catalog_request_count

        add_task_log(task_id, f"✅ 获取到 {len(columns)} 个专栏目录")

        if len(columns) == 0:
            _complete_empty_columns_task(task_id)
            return

        for col_idx, column in enumerate(columns, 1):
            if is_task_stopped(task_id):
                add_task_log(task_id, "🛑 任务已被用户停止")
                break

            column_stats = await _process_column(
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

        result_msg, result_payload = _build_columns_fetch_result(
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
    except Exception as e:
        try:
            if log_id and db:
                db.update_crawl_log(log_id, status="failed", error_message=str(e))
        except Exception:
            pass

        try:
            update_task(task_id, "failed", f"专栏采集失败: {str(e)}")
        except Exception:
            pass

        try:
            add_task_log(task_id, f"❌ 专栏采集失败: {str(e)}")
        except Exception:
            pass
    finally:
        try:
            if db:
                db.close()
        except Exception:
            pass


@router.get("/groups/{group_id}/columns/stats")
async def get_columns_stats(group_id: str):
    """获取专栏统计信息"""
    try:
        with _columns_db(group_id) as db:
            stats = db.get_stats(int(group_id))
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取专栏统计失败: {str(e)}")


@router.delete("/groups/{group_id}/columns/all")
async def delete_all_columns(group_id: str):
    """删除群组的所有专栏数据"""
    try:
        with _columns_db(group_id) as db:
            stats = db.clear_all_data(int(group_id))
        return {
            "success": True,
            "message": "已清空专栏数据",
            "deleted": stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除专栏数据失败: {str(e)}")


@router.get("/groups/{group_id}/columns/topics/{topic_id}/comments")
async def get_column_topic_full_comments(group_id: str, topic_id: int):
    """获取专栏文章的完整评论列表（从API实时获取并持久化到数据库）"""
    try:
        manager = get_accounts_sql_manager()
        account = manager.get_account_for_group(group_id, mask_cookie=False)
        if not account or not account.get("cookie"):
            raise HTTPException(status_code=400, detail="No valid account found for this group")

        cookie = account["cookie"]
        headers = build_stealth_headers(cookie)

        comments_url = f"https://api.zsxq.com/v2/topics/{topic_id}/comments?sort=asc&count=30&with_sticky=true"
        log_info(f"Fetching comments from: {comments_url}")
        resp = requests.get(comments_url, headers=headers, timeout=30)

        if resp.status_code != 200:
            log_error(f"Failed to fetch comments: HTTP {resp.status_code}, response={_redact_response_for_log(resp.text)}")
            raise HTTPException(status_code=resp.status_code, detail=f"Failed to fetch comments: HTTP {resp.status_code}")

        data = resp.json()
        log_debug(f"Comments API response: succeeded={data.get('succeeded')}, resp_data keys={list(data.get('resp_data', {}).keys()) if data.get('resp_data') else 'None'}")

        if not data.get("succeeded"):
            resp_data = data.get("resp_data", {})
            error_msg = resp_data.get("message") or resp_data.get("error_msg") or data.get("error_msg") or data.get("message")
            error_code = resp_data.get("code") or resp_data.get("error_code") or data.get("code")
            log_error(f"Comments API failed: code={error_code}, message={error_msg}, full_response={json.dumps(data, ensure_ascii=False)[:500]}")
            raise HTTPException(status_code=400, detail=f"API error: {error_msg or 'Request failed'} (code: {error_code})")

        comments = data.get("resp_data", {}).get("comments", [])

        processed_comments = []
        for comment in comments:
            processed = {
                "comment_id": comment.get("comment_id"),
                "parent_comment_id": comment.get("parent_comment_id"),
                "text": comment.get("text", ""),
                "create_time": comment.get("create_time"),
                "likes_count": comment.get("likes_count", 0),
                "rewards_count": comment.get("rewards_count", 0),
                "replies_count": comment.get("replies_count", 0),
                "sticky": comment.get("sticky", False),
                "owner": comment.get("owner"),
                "repliee": comment.get("repliee"),
                "images": comment.get("images", []),
            }

            replied_comments = comment.get("replied_comments", [])
            if replied_comments:
                processed["replied_comments"] = [
                    {
                        "comment_id": rc.get("comment_id"),
                        "parent_comment_id": rc.get("parent_comment_id"),
                        "text": rc.get("text", ""),
                        "create_time": rc.get("create_time"),
                        "likes_count": rc.get("likes_count", 0),
                        "owner": rc.get("owner"),
                        "repliee": rc.get("repliee"),
                        "images": rc.get("images", []),
                    }
                    for rc in replied_comments
                ]

            processed_comments.append(processed)

        try:
            with _columns_db(group_id) as db:
                saved_count = db.import_comments(topic_id, processed_comments)
            log_info(f"Saved {saved_count} comments to database for topic {topic_id}")
        except Exception as e:
            log_error(f"Failed to save comments to database: {e}")

        total_count = sum(1 + len(c.get("replied_comments", [])) for c in processed_comments)

        return {
            "success": True,
            "comments": processed_comments,
            "total": total_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"获取专栏完整评论失败: topic_id={topic_id}")
        raise HTTPException(status_code=500, detail=f"获取完整评论失败: {str(e)}")
