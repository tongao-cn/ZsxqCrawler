from __future__ import annotations

import asyncio
import random
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.services.columns_fetch_summary import ColumnFetchStats


def collect_topic_files(topic_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    talk = topic_detail.get("talk", {}) or {}
    all_files = list(talk.get("files", []) or [])
    content_voice = topic_detail.get("content_voice")
    if content_voice:
        all_files.append(content_voice)
    return all_files


def get_topic_video(topic_detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    talk = topic_detail.get("talk", {}) if "talk" in topic_detail else {}
    video = talk.get("video")
    if video and video.get("video_id"):
        return video
    return None


async def download_topic_files(
    *,
    add_task_log: Callable[[str, str], None],
    crawl_interval_max: float,
    crawl_interval_min: float,
    current_request_count: int,
    db: Any,
    download_column_file: Callable[..., Awaitable[str]],
    group_id: str,
    headers: Dict[str, str],
    is_task_stopped: Callable[[str], bool],
    items_per_batch: int,
    log_exception: Callable[[str], None],
    long_sleep_max: float,
    long_sleep_min: float,
    random_uniform: Callable[[float, float], float] = random.uniform,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    task_id: str,
    topic_detail: Dict[str, Any],
    topic_id: int,
) -> tuple[int, int, int]:
    request_count = current_request_count
    downloaded_count = 0
    skipped_count = 0
    requests_made = 0

    for file_info in collect_topic_files(topic_detail):
        if is_task_stopped(task_id):
            break

        file_id = file_info.get("file_id")
        file_name = file_info.get("name", "")
        file_size = file_info.get("size", 0)

        if not file_id:
            continue

        add_task_log(task_id, f"      📥 下载文件: {file_name[:40]}...")

        if request_count > 0 and request_count % items_per_batch == 0:
            sleep_time = random_uniform(long_sleep_min, long_sleep_max)
            add_task_log(task_id, f"      😴 已完成 {request_count} 次请求，休眠 {sleep_time:.1f} 秒...")
            await sleep(sleep_time)

        delay = random_uniform(crawl_interval_min, crawl_interval_max)
        await sleep(delay)

        try:
            result = await download_column_file(
                group_id=group_id,
                file_id=file_id,
                file_name=file_name,
                file_size=file_size,
                topic_id=topic_id,
                db=db,
                headers=headers,
                task_id=task_id,
            )
            if result == "downloaded":
                downloaded_count += 1
                request_count += 1
                requests_made += 1
                add_task_log(task_id, f"         ✅ 文件下载成功")
            elif result == "skipped":
                skipped_count += 1
        except Exception as exc:
            log_exception(f"文件下载失败: file_id={file_id}, file_name={file_name}, topic_id={topic_id}")
            add_task_log(task_id, f"         ⚠️ 文件下载失败: {exc}")

    return downloaded_count, skipped_count, requests_made


async def download_topic_video(
    *,
    add_task_log: Callable[[str, str], None],
    crawl_interval_max: float,
    crawl_interval_min: float,
    current_request_count: int,
    db: Any,
    download_column_video: Callable[..., Awaitable[str]],
    group_id: str,
    headers: Dict[str, str],
    items_per_batch: int,
    log_exception: Callable[[str], None],
    long_sleep_max: float,
    long_sleep_min: float,
    random_uniform: Callable[[float, float], float] = random.uniform,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    task_id: str,
    topic_id: int,
    video: Dict[str, Any],
) -> tuple[int, int, int]:
    request_count = current_request_count
    video_id = video.get("video_id")
    video_size = video.get("size", 0)
    video_duration = video.get("duration", 0)

    if request_count > 0 and request_count % items_per_batch == 0:
        sleep_time = random_uniform(long_sleep_min, long_sleep_max)
        add_task_log(task_id, f"      😴 已完成 {request_count} 次请求，休眠 {sleep_time:.1f} 秒...")
        await sleep(sleep_time)

    delay = random_uniform(crawl_interval_min, crawl_interval_max)
    await sleep(delay)

    try:
        result = await download_column_video(
            group_id=group_id,
            video_id=video_id,
            video_size=video_size,
            video_duration=video_duration,
            topic_id=topic_id,
            db=db,
            headers=headers,
            task_id=task_id,
        )
        if result == "downloaded":
            return 1, 0, 1
        if result == "skipped":
            return 0, 1, 0
    except Exception as exc:
        log_exception(f"视频下载失败: video_id={video_id}, topic_id={topic_id}, size={video_size}")
        add_task_log(task_id, f"      ⚠️ 视频下载失败: {exc}")

    return 0, 0, 0


async def process_topic_resources(
    *,
    add_task_log: Callable[[str, str], None],
    cache_topic_images: Callable[[str, str, Dict[str, Any], Any], int],
    cache_video_cover: Callable[[str, str, int, Optional[str], Any], bool],
    config: Dict[str, Any],
    current_request_count: int,
    db: Any,
    download_topic_files: Callable[..., Awaitable[tuple[int, int, int]]],
    download_topic_video: Callable[..., Awaitable[tuple[int, int, int]]],
    get_topic_video_fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]] = get_topic_video,
    group_id: str,
    headers: Dict[str, str],
    task_id: str,
    topic_detail: Dict[str, Any],
    topic_id: int,
) -> ColumnFetchStats:
    stats = ColumnFetchStats()
    request_count = current_request_count

    if config["download_files"]:
        downloaded_files, skipped_files, file_request_count = await download_topic_files(
            task_id=task_id,
            group_id=group_id,
            topic_id=topic_id,
            topic_detail=topic_detail,
            db=db,
            headers=headers,
            current_request_count=request_count,
            items_per_batch=config["items_per_batch"],
            long_sleep_min=config["long_sleep_min"],
            long_sleep_max=config["long_sleep_max"],
            crawl_interval_min=config["crawl_interval_min"],
            crawl_interval_max=config["crawl_interval_max"],
        )
        stats.files_count += downloaded_files
        stats.files_skipped += skipped_files
        request_count += file_request_count
        stats.request_count += file_request_count

    if config["cache_images"]:
        stats.images_count += cache_topic_images(
            task_id=task_id,
            group_id=group_id,
            topic_detail=topic_detail,
            db=db,
        )

    video = get_topic_video_fn(topic_detail)
    if not video:
        return stats

    video_id = video.get("video_id")
    video_size = video.get("size", 0)
    video_duration = video.get("duration", 0)
    cover = video.get("cover", {})
    cover_url = cover.get("url")

    add_task_log(task_id, f"      🎬 发现视频: ID={video_id}, 大小={video_size/(1024*1024):.1f}MB, 时长={video_duration}秒")

    if config["cache_images"] and cover_url:
        cache_video_cover(
            task_id=task_id,
            group_id=group_id,
            video_id=video_id,
            cover_url=cover_url,
            db=db,
        )

    if config["download_videos"]:
        downloaded_videos, skipped_videos, video_request_count = await download_topic_video(
            task_id=task_id,
            group_id=group_id,
            topic_id=topic_id,
            video=video,
            db=db,
            headers=headers,
            current_request_count=request_count,
            items_per_batch=config["items_per_batch"],
            long_sleep_min=config["long_sleep_min"],
            long_sleep_max=config["long_sleep_max"],
            crawl_interval_min=config["crawl_interval_min"],
            crawl_interval_max=config["crawl_interval_max"],
        )
        stats.videos_count += downloaded_videos
        stats.videos_skipped += skipped_videos
        stats.request_count += video_request_count
    else:
        add_task_log(task_id, f"      ⏭️ 跳过视频下载（已禁用）")

    return stats
