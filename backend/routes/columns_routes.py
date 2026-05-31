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
from backend.core.log_redaction import redact_response_text
from backend.core.logger_config import log_debug, log_error, log_exception, log_info, log_warning
from backend.services.columns_fetch_summary import (
    ColumnFetchStats,
    build_columns_fetch_result as _build_columns_fetch_result,
    build_columns_progress_message as _build_columns_progress_message,
    combined_column_stats as _combined_column_stats,
    resolve_columns_fetch_config as _resolve_columns_fetch_config,
)
from backend.services.columns_summary_service import get_columns_summary
from backend.routes.ingestion_helpers import create_ingestion_task_or_raise
from backend.services.task_runtime import add_task_log, enqueue_runtime_task, is_task_stopped, update_task
from backend.storage.accounts_sql_manager import get_accounts_sql_manager
from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

router = APIRouter(prefix="/api", tags=["columns"])


def _redact_response_for_log(text: str | None, limit: int = 500) -> str:
    if not text:
        return "empty"
    return redact_response_text(text, limit=limit)


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
    resp_data = topic_detail.get("resp_data", {}) or {}
    topic_data = resp_data.get("topic", {}) or {}
    return topic_data or None


def _save_topic_detail(
    db: ZSXQColumnsDatabase,
    group_id: str,
    topic_detail: Dict[str, Any],
) -> bool:
    topic_data = _extract_topic_data(topic_detail)
    if not topic_data:
        return False

    db.insert_topic_detail(int(group_id), topic_data, json.dumps(topic_detail, ensure_ascii=False))
    return True


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
    topic_id = topic.get("topic_id")
    topic_title = topic.get("title", "无标题")[:30]
    db.insert_column_topic(column_id, int(group_id), topic)

    if incremental_mode and db.topic_detail_exists(topic_id):
        add_task_log(task_id, f"   📄 [{topic_idx}/{total_topics}] {topic_title}... ⏭️ 跳过（已存在）")
        return topic_id, topic_title, True

    add_task_log(task_id, f"   📄 [{topic_idx}/{total_topics}] {topic_title}...")
    return topic_id, topic_title, False


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
    stats = ColumnFetchStats()
    request_count = current_request_count

    if config["download_files"]:
        downloaded_files, skipped_files, file_request_count = await _download_topic_files(
            task_id,
            group_id,
            topic_id,
            topic_detail,
            db,
            headers,
            request_count,
            config["items_per_batch"],
            config["long_sleep_min"],
            config["long_sleep_max"],
            config["crawl_interval_min"],
            config["crawl_interval_max"],
        )
        stats.files_count += downloaded_files
        stats.files_skipped += skipped_files
        request_count += file_request_count
        stats.request_count += file_request_count

    if config["cache_images"]:
        stats.images_count += _cache_topic_images(task_id, group_id, topic_detail, db)

    video = _get_topic_video(topic_detail)
    if not video:
        return stats

    video_id = video.get("video_id")
    video_size = video.get("size", 0)
    video_duration = video.get("duration", 0)
    cover = video.get("cover", {})
    cover_url = cover.get("url")

    add_task_log(task_id, f"      🎬 发现视频: ID={video_id}, 大小={video_size/(1024*1024):.1f}MB, 时长={video_duration}秒")

    if config["cache_images"] and cover_url:
        _cache_video_cover(task_id, group_id, video_id, cover_url, db)

    if config["download_videos"]:
        downloaded_videos, skipped_videos, video_request_count = await _download_topic_video(
            task_id,
            group_id,
            topic_id,
            video,
            db,
            headers,
            request_count,
            config["items_per_batch"],
            config["long_sleep_min"],
            config["long_sleep_max"],
            config["crawl_interval_min"],
            config["crawl_interval_max"],
        )
        stats.videos_count += downloaded_videos
        stats.videos_skipped += skipped_videos
        stats.request_count += video_request_count
    else:
        add_task_log(task_id, f"      ⏭️ 跳过视频下载（已禁用）")

    return stats


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


def _retry_wait_seconds(retry: int) -> int:
    return 2 if retry < 3 else (5 if retry < 6 else 10)


async def _fetch_columns_catalog(task_id: str, group_id: str, headers: Dict[str, str]) -> tuple[List[Dict[str, Any]], int]:
    columns_url = f"https://api.zsxq.com/v2/groups/{group_id}/columns"
    max_retries = 10
    request_count = 0

    for retry in range(max_retries):
        if is_task_stopped(task_id):
            break

        try:
            resp = requests.get(columns_url, headers=headers, timeout=30)
            request_count += 1
        except Exception as req_err:
            log_exception(f"获取专栏目录请求异常: group_id={group_id}, url={columns_url}")
            if retry < max_retries - 1:
                wait_time = _retry_wait_seconds(retry)
                add_task_log(task_id, f"   ⚠️ 请求异常，等待{wait_time}秒后重试 ({retry+1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
            raise Exception(f"获取专栏目录请求异常: {req_err}")

        if resp.status_code != 200:
            log_error(f"获取专栏目录失败: group_id={group_id}, HTTP {resp.status_code}, response={_redact_response_for_log(resp.text)}")
            if retry < max_retries - 1:
                wait_time = _retry_wait_seconds(retry)
                add_task_log(task_id, f"   ⚠️ HTTP {resp.status_code}，等待{wait_time}秒后重试 ({retry+1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
            raise Exception(f"获取专栏目录失败: HTTP {resp.status_code}")

        try:
            data = resp.json()
        except Exception as json_err:
            log_exception(f"解析专栏目录JSON失败: group_id={group_id}, response={_redact_response_for_log(resp.text)}")
            raise Exception(f"解析专栏目录失败: {json_err}")

        if not data.get("succeeded"):
            error_code = data.get("code")
            error_msg = data.get("error_message", "未知错误")

            if "expired" in error_msg.lower() or data.get("resp_data", {}).get("expired"):
                raise Exception(f"会员已过期: {error_msg}")

            if error_code == 1059:
                if retry < max_retries - 1:
                    wait_time = _retry_wait_seconds(retry)
                    add_task_log(task_id, f"   ⚠️ 遇到反爬机制 (错误码1059)，等待{wait_time}秒后重试 ({retry+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                log_error(f"获取专栏目录重试{max_retries}次后仍失败: group_id={group_id}, code={error_code}")
                raise Exception(f"获取专栏目录失败，重试{max_retries}次后仍遇到反爬限制")

            log_error(f"获取专栏目录API失败: group_id={group_id}, code={error_code}, message={error_msg}, response={json.dumps(data, ensure_ascii=False)[:500]}")
            raise Exception(f"API返回失败: {error_msg} (code={error_code})")

        columns = data.get("resp_data", {}).get("columns", [])
        if retry > 0:
            add_task_log(task_id, f"   ✅ 重试成功 (第{retry+1}次尝试)")
        return columns, request_count

    raise Exception("获取专栏目录失败")


def _fetch_column_topics(
    task_id: str,
    column_id: int,
    topics_url: str,
    headers: Dict[str, str],
) -> tuple[Optional[List[Dict[str, Any]]], int]:
    request_count = 0

    try:
        topics_resp = requests.get(topics_url, headers=headers, timeout=30)
        request_count += 1
    except Exception as req_err:
        log_exception(f"获取专栏文章列表请求异常: column_id={column_id}, url={topics_url}")
        add_task_log(task_id, f"   ⚠️ 获取文章列表请求异常: {req_err}")
        return None, request_count

    if topics_resp.status_code != 200:
        log_error(f"获取专栏文章列表失败: column_id={column_id}, HTTP {topics_resp.status_code}, response={_redact_response_for_log(topics_resp.text)}")
        add_task_log(task_id, f"   ⚠️ 获取文章列表失败: HTTP {topics_resp.status_code}")
        return None, request_count

    try:
        topics_data = topics_resp.json()
    except Exception as json_err:
        log_exception(f"解析专栏文章列表JSON失败: column_id={column_id}, response={_redact_response_for_log(topics_resp.text)}")
        add_task_log(task_id, f"   ⚠️ 解析文章列表失败: {json_err}")
        return None, request_count

    if not topics_data.get("succeeded"):
        error_code = topics_data.get("code", "unknown")
        error_message = topics_data.get("error_message", "未知错误")
        log_error(f"获取专栏文章列表失败: column_id={column_id}, code={error_code}, message={error_message}")
        add_task_log(task_id, f"   ⚠️ 获取文章列表失败: {error_message} (code={error_code})")
        return None, request_count

    topics_list = topics_data.get("resp_data", {}).get("topics", [])
    add_task_log(task_id, f"   📝 获取到 {len(topics_list)} 篇文章")
    return topics_list, request_count


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
    max_retries = 10
    request_count = current_request_count
    requests_made = 0

    for _ in range(max_retries):
        if is_task_stopped(task_id):
            break

        if request_count > 0 and request_count % items_per_batch == 0:
            sleep_time = random.uniform(long_sleep_min, long_sleep_max)
            add_task_log(task_id, f"      😴 已完成 {request_count} 次请求，休眠 {sleep_time:.1f} 秒...")
            await asyncio.sleep(sleep_time)

        delay = random.uniform(crawl_interval_min, crawl_interval_max)
        await asyncio.sleep(delay)

        detail_url = f"https://api.zsxq.com/v2/topics/{topic_id}/info"
        try:
            detail_resp = requests.get(detail_url, headers=headers, timeout=30)
            request_count += 1
            requests_made += 1
        except Exception as req_err:
            log_exception(f"获取文章详情请求异常: topic_id={topic_id}, url={detail_url}")
            add_task_log(task_id, f"      ⚠️ 获取详情请求异常: {req_err}")
            continue

        if detail_resp.status_code != 200:
            log_error(f"获取文章详情失败: topic_id={topic_id}, HTTP {detail_resp.status_code}, response={_redact_response_for_log(detail_resp.text)}")
            add_task_log(task_id, f"      ⚠️ 获取详情失败: HTTP {detail_resp.status_code}")
            continue

        try:
            topic_detail = detail_resp.json()
        except Exception as json_err:
            log_exception(f"解析文章详情JSON失败: topic_id={topic_id}, response={_redact_response_for_log(detail_resp.text)}")
            add_task_log(task_id, f"      ⚠️ 解析详情失败: {json_err}")
            continue

        if topic_detail and topic_detail.get("succeeded"):
            return topic_detail, requests_made

        error_msg = (topic_detail or {}).get("error_message", "未知错误")
        log_error(f"获取文章详情API失败: topic_id={topic_id}, message={error_msg}")
        add_task_log(task_id, f"      ⚠️ 获取详情API失败: {error_msg}")

    return None, requests_made


def _collect_topic_files(topic_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    talk = topic_detail.get("talk", {}) or {}
    all_files = list(talk.get("files", []) or [])
    content_voice = topic_detail.get("content_voice")
    if content_voice:
        all_files.append(content_voice)
    return all_files


async def _download_column_file(group_id: str, file_id: int, file_name: str, file_size: int,
                                topic_id: int, db: ZSXQColumnsDatabase, headers: dict, task_id: str = None) -> str:
    """下载专栏文件"""
    import os

    path_manager = get_db_path_manager()
    group_dir = path_manager.get_group_dir(group_id)
    downloads_dir = os.path.join(group_dir, "column_downloads")
    local_path = os.path.join(downloads_dir, file_name)

    if os.path.exists(local_path):
        existing_size = os.path.getsize(local_path)
        if existing_size == file_size or (file_size == 0 and existing_size > 0):
            db.update_file_download_status(file_id, "completed", local_path)
            if task_id:
                add_task_log(task_id, f"         ⏭️ 文件已存在，跳过下载 ({existing_size/(1024*1024):.2f}MB)")
            return "skipped"

    download_url = f"https://api.zsxq.com/v2/files/{file_id}/download_url"
    max_retries = 10
    real_url = None

    for retry in range(max_retries):
        try:
            resp = requests.get(download_url, headers=headers, timeout=30)
        except Exception as req_err:
            if retry < max_retries - 1:
                wait_time = 2 if retry < 3 else (5 if retry < 6 else 10)
                await asyncio.sleep(wait_time)
                continue
            log_exception(f"获取下载链接请求异常: file_id={file_id}")
            raise Exception(f"获取下载链接请求异常: {req_err}")

        if resp.status_code != 200:
            if retry < max_retries - 1:
                wait_time = 2 if retry < 3 else (5 if retry < 6 else 10)
                await asyncio.sleep(wait_time)
                continue
            error_msg = f"获取下载链接失败: HTTP {resp.status_code}, URL={download_url}, Response={_redact_response_for_log(resp.text)}"
            log_error(error_msg)
            raise Exception(error_msg)

        data = resp.json()
        if not data.get("succeeded"):
            error_code = data.get("code")
            error_message = data.get("error_message", "未知错误")

            if error_code == 1059:
                if retry < max_retries - 1:
                    wait_time = 2 if retry < 3 else (5 if retry < 6 else 10)
                    await asyncio.sleep(wait_time)
                    continue
                log_error(f"获取下载链接重试{max_retries}次后仍失败: file_id={file_id}, code={error_code}")
                raise Exception(f"获取下载链接失败，重试{max_retries}次后仍遇到反爬限制")

            error_msg = f"获取下载链接失败: code={error_code}, message={error_message}, file_id={file_id}, file_name={file_name}"
            log_error(error_msg)
            raise Exception(f"获取下载链接失败: {error_message} (code={error_code})")

        real_url = data.get("resp_data", {}).get("download_url")
        break

    if not real_url:
        raise Exception("下载链接为空")

    os.makedirs(downloads_dir, exist_ok=True)

    download_retries = 3
    last_error = None

    for download_attempt in range(download_retries):
        try:
            file_resp = requests.get(real_url, headers=headers, stream=True, timeout=300)
            if file_resp.status_code == 200:
                with open(local_path, "wb") as f:
                    for chunk in file_resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                db.update_file_download_status(file_id, "completed", local_path)
                return "downloaded"

            last_error = f"HTTP {file_resp.status_code}"
            if download_attempt < download_retries - 1:
                log_warning(f"文件下载失败 (尝试 {download_attempt + 1}/{download_retries}): {last_error}, file_id={file_id}")
                await asyncio.sleep(2 * (download_attempt + 1))
                continue
        except requests.exceptions.SSLError as ssl_err:
            last_error = f"SSL错误: {ssl_err}"
            if download_attempt < download_retries - 1:
                log_warning(f"文件下载SSL错误 (尝试 {download_attempt + 1}/{download_retries}): file_id={file_id}, error={ssl_err}")
                await asyncio.sleep(3 * (download_attempt + 1))
                continue
        except requests.exceptions.RequestException as req_err:
            last_error = f"网络错误: {req_err}"
            if download_attempt < download_retries - 1:
                log_warning(f"文件下载网络错误 (尝试 {download_attempt + 1}/{download_retries}): file_id={file_id}, error={req_err}")
                await asyncio.sleep(2 * (download_attempt + 1))
                continue

    db.update_file_download_status(file_id, "failed")
    raise Exception(f"下载失败 (重试{download_retries}次): {last_error}")


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
    request_count = current_request_count
    downloaded_count = 0
    skipped_count = 0
    requests_made = 0

    for file_info in _collect_topic_files(topic_detail):
        if is_task_stopped(task_id):
            break

        file_id = file_info.get("file_id")
        file_name = file_info.get("name", "")
        file_size = file_info.get("size", 0)

        if not file_id:
            continue

        add_task_log(task_id, f"      📥 下载文件: {file_name[:40]}...")

        if request_count > 0 and request_count % items_per_batch == 0:
            sleep_time = random.uniform(long_sleep_min, long_sleep_max)
            add_task_log(task_id, f"      😴 已完成 {request_count} 次请求，休眠 {sleep_time:.1f} 秒...")
            await asyncio.sleep(sleep_time)

        delay = random.uniform(crawl_interval_min, crawl_interval_max)
        await asyncio.sleep(delay)

        try:
            result = await _download_column_file(
                group_id, file_id, file_name, file_size,
                topic_id, db, headers, task_id
            )
            if result == "downloaded":
                downloaded_count += 1
                request_count += 1
                requests_made += 1
                add_task_log(task_id, f"         ✅ 文件下载成功")
            elif result == "skipped":
                skipped_count += 1
        except Exception as fe:
            log_exception(f"文件下载失败: file_id={file_id}, file_name={file_name}, topic_id={topic_id}")
            add_task_log(task_id, f"         ⚠️ 文件下载失败: {fe}")

    return downloaded_count, skipped_count, requests_made


def _cache_topic_images(task_id: str, group_id: str, topic_detail: Dict[str, Any], db: ZSXQColumnsDatabase) -> int:
    cached_count = 0
    talk = topic_detail.get("talk", {}) if "talk" in topic_detail else {}
    topic_images = talk.get("images", [])

    for image in topic_images:
        if is_task_stopped(task_id):
            break

        original_url = image.get("original", {}).get("url")
        image_id = image.get("image_id")

        if original_url and image_id:
            try:
                cache_manager = get_image_cache_manager(group_id)
                success, local_path, error_msg = cache_manager.download_and_cache(original_url)
                if success and local_path:
                    db.update_image_local_path(image_id, str(local_path))
                    cached_count += 1
                elif error_msg:
                    add_task_log(task_id, f"      ⚠️ 图片缓存失败: {error_msg}")
            except Exception as ie:
                log_exception(f"图片缓存失败: image_id={image_id}, url={original_url}")
                add_task_log(task_id, f"      ⚠️ 图片缓存失败: {ie}")

    return cached_count


def _get_topic_video(topic_detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    talk = topic_detail.get("talk", {}) if "talk" in topic_detail else {}
    video = talk.get("video")
    if video and video.get("video_id"):
        return video
    return None


def _cache_video_cover(
    task_id: str,
    group_id: str,
    video_id: int,
    cover_url: Optional[str],
    db: ZSXQColumnsDatabase,
) -> bool:
    if not cover_url:
        return False

    try:
        cache_manager = get_image_cache_manager(group_id)
        success, cover_local, error_msg = cache_manager.download_and_cache(cover_url)
        if success and cover_local:
            db.update_video_cover_path(video_id, str(cover_local))
            add_task_log(task_id, f"      ✅ 视频封面缓存成功")
            return True
        if error_msg:
            log_warning(f"视频封面缓存失败: video_id={video_id}, url={cover_url}, error={error_msg}")
            add_task_log(task_id, f"      ⚠️ 视频封面缓存失败: {error_msg}")
    except Exception as ve:
        log_exception(f"视频封面缓存失败: video_id={video_id}, url={cover_url}")
        add_task_log(task_id, f"      ⚠️ 视频封面缓存失败: {ve}")

    return False


async def _download_column_video(group_id: str, video_id: int, video_size: int, video_duration: int,
                                 topic_id: int, db: ZSXQColumnsDatabase, headers: dict, task_id: str = None) -> str:
    """下载专栏视频（m3u8格式）"""
    import os
    import queue
    import subprocess
    import threading
    import time

    path_manager = get_db_path_manager()
    group_dir = path_manager.get_group_dir(group_id)
    videos_dir = os.path.join(group_dir, "column_videos")
    video_filename = f"video_{video_id}.mp4"
    local_path = os.path.join(videos_dir, video_filename)

    if os.path.exists(local_path):
        existing_size = os.path.getsize(local_path)
        if existing_size > 0:
            db.update_video_download_status(video_id, "completed", "", local_path)
            if task_id:
                add_task_log(task_id, f"         ⏭️ 视频已存在，跳过下载 ({existing_size/(1024*1024):.1f}MB)")
            return "skipped"

    video_url_api = f"https://api.zsxq.com/v2/videos/{video_id}/url"
    max_retries = 10
    m3u8_url = None

    for retry in range(max_retries):
        try:
            resp = requests.get(video_url_api, headers=headers, timeout=30)
        except Exception as req_err:
            if retry < max_retries - 1:
                wait_time = 2 if retry < 3 else (5 if retry < 6 else 10)
                await asyncio.sleep(wait_time)
                continue
            log_exception(f"获取视频链接请求异常: video_id={video_id}")
            raise Exception(f"获取视频链接请求异常: {req_err}")

        if resp.status_code != 200:
            if retry < max_retries - 1:
                wait_time = 2 if retry < 3 else (5 if retry < 6 else 10)
                await asyncio.sleep(wait_time)
                continue
            error_msg = f"获取视频链接失败: HTTP {resp.status_code}, URL={video_url_api}, Response={_redact_response_for_log(resp.text)}"
            log_error(error_msg)
            raise Exception(error_msg)

        data = resp.json()
        if not data.get("succeeded"):
            error_code = data.get("code")
            error_message = data.get("error_message", "未知错误")

            if error_code == 1059:
                if retry < max_retries - 1:
                    wait_time = 2 if retry < 3 else (5 if retry < 6 else 10)
                    await asyncio.sleep(wait_time)
                    continue
                log_error(f"获取视频链接重试{max_retries}次后仍失败: video_id={video_id}, code={error_code}")
                raise Exception(f"获取视频链接失败，重试{max_retries}次后仍遇到反爬限制")

            error_msg = f"获取视频链接失败: code={error_code}, message={error_message}, video_id={video_id}, topic_id={topic_id}"
            log_error(error_msg)
            raise Exception(f"获取视频链接失败: {error_message} (code={error_code})")

        m3u8_url = data.get("resp_data", {}).get("url")
        break

    if not m3u8_url:
        raise Exception("视频链接为空")

    os.makedirs(videos_dir, exist_ok=True)
    db.update_video_download_status(video_id, "downloading", m3u8_url)

    try:
        ffmpeg_check = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if ffmpeg_check.returncode != 0:
            raise Exception("ffmpeg not available")

        ffmpeg_headers = ""
        if headers.get("Cookie"):
            ffmpeg_headers += f"Cookie: {headers['Cookie']}\r\n"
        if headers.get("cookie"):
            ffmpeg_headers += f"Cookie: {headers['cookie']}\r\n"
        ffmpeg_headers += "Referer: https://wx.zsxq.com/\r\n"
        ffmpeg_headers += "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
        ffmpeg_headers += "Origin: https://wx.zsxq.com\r\n"

        cmd = [
            "ffmpeg", "-y",
            "-headers", ffmpeg_headers,
            "-i", m3u8_url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-progress", "pipe:1",
            local_path,
        ]

        log_info(f"开始下载视频: video_id={video_id}, url={m3u8_url[:100]}...")
        if task_id:
            add_task_log(task_id, f"         🎬 开始下载视频 (预计时长: {video_duration}秒, 大小: {video_size/(1024*1024):.1f}MB)")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stderr_output = []
        stdout_queue = queue.Queue()

        def read_stdout():
            try:
                for line in iter(process.stdout.readline, ""):
                    if line:
                        stdout_queue.put(line)
                    if process.poll() is not None:
                        break
            except Exception:
                pass

        def read_stderr():
            try:
                for line in iter(process.stderr.readline, ""):
                    if line:
                        stderr_output.append(line)
            except Exception:
                pass

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        last_log_time = time.time()
        start_time = time.time()

        try:
            while process.poll() is None:
                try:
                    line = stdout_queue.get(timeout=1)
                    if line.startswith("out_time_ms="):
                        try:
                            time_ms = int(line.split("=")[1].strip())
                            current_seconds = time_ms / 1000000
                            now = time.time()
                            if task_id and (now - last_log_time) >= 3:
                                if video_duration > 0:
                                    progress_pct = min(100, (current_seconds / video_duration) * 100)
                                    bar_length = 20
                                    filled = int(bar_length * progress_pct / 100)
                                    bar = "█" * filled + "░" * (bar_length - filled)
                                    add_task_log(task_id, f"         📊 下载进度: [{bar}] {progress_pct:.1f}% ({current_seconds:.0f}s/{video_duration}s)")
                                else:
                                    add_task_log(task_id, f"         📊 下载进度: {current_seconds:.0f}秒")
                                last_log_time = now
                        except Exception:
                            pass
                except queue.Empty:
                    now = time.time()
                    elapsed = now - start_time
                    if task_id and (now - last_log_time) >= 5:
                        add_task_log(task_id, f"         ⏳ 下载中... (已用时 {elapsed:.0f}秒)")
                        last_log_time = now
                    continue

            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
        except Exception as e:
            process.kill()
            raise Exception(f"视频下载异常: {e}")

        returncode = process.returncode
        stderr_text = "".join(stderr_output)

        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            db.update_video_download_status(video_id, "completed", m3u8_url, local_path)
            final_size = os.path.getsize(local_path)
            log_info(f"视频下载成功: video_id={video_id}, path={local_path}, size={final_size}")
            if task_id:
                add_task_log(task_id, f"         ✅ 视频下载完成 ({final_size/(1024*1024):.1f}MB)")
            return "downloaded"

        db.update_video_download_status(video_id, "failed", m3u8_url)
        stderr_lines = stderr_text.strip().split("\n")
        error_lines = [line for line in stderr_lines if "error" in line.lower() or "failed" in line.lower() or "invalid" in line.lower()]
        if error_lines:
            error_msg = "; ".join(error_lines[-3:])
        else:
            error_msg = "; ".join(stderr_lines[-3:]) if stderr_lines else "unknown error"
        log_error(f"ffmpeg下载失败: video_id={video_id}, returncode={returncode}, error={error_msg}")
        raise Exception(f"ffmpeg下载失败: {error_msg[:300]}")

    except FileNotFoundError:
        db.update_video_download_status(video_id, "pending_manual", m3u8_url)
        m3u8_link_file = os.path.join(videos_dir, f"video_{video_id}.m3u8.txt")
        with open(m3u8_link_file, "w", encoding="utf-8") as f:
            f.write(f"Video ID: {video_id}\n")
            f.write(f"Duration: {video_duration} seconds\n")
            f.write(f"Size: {video_size} bytes\n")
            f.write(f"M3U8 URL: {m3u8_url}\n")
        raise Exception("ffmpeg未安装，已保存m3u8链接到文件，请手动下载")
    except subprocess.TimeoutExpired:
        db.update_video_download_status(video_id, "failed", m3u8_url)
        raise Exception("视频下载超时")


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
    request_count = current_request_count
    video_id = video.get("video_id")
    video_size = video.get("size", 0)
    video_duration = video.get("duration", 0)

    if request_count > 0 and request_count % items_per_batch == 0:
        sleep_time = random.uniform(long_sleep_min, long_sleep_max)
        add_task_log(task_id, f"      😴 已完成 {request_count} 次请求，休眠 {sleep_time:.1f} 秒...")
        await asyncio.sleep(sleep_time)

    delay = random.uniform(crawl_interval_min, crawl_interval_max)
    await asyncio.sleep(delay)

    try:
        result = await _download_column_video(
            group_id, video_id, video_size, video_duration,
            topic_id, db, headers, task_id
        )
        if result == "downloaded":
            return 1, 0, 1
        if result == "skipped":
            return 0, 1, 0
    except Exception as ve:
        log_exception(f"视频下载失败: video_id={video_id}, topic_id={topic_id}, size={video_size}")
        add_task_log(task_id, f"      ⚠️ 视频下载失败: {ve}")

    return 0, 0, 0


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
