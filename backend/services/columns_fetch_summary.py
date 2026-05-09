from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ColumnFetchStats:
    columns_count: int = 0
    topics_count: int = 0
    details_count: int = 0
    files_count: int = 0
    images_count: int = 0
    videos_count: int = 0
    skipped_count: int = 0
    files_skipped: int = 0
    videos_skipped: int = 0
    request_count: int = 0

    def add(self, other: "ColumnFetchStats") -> None:
        self.columns_count += other.columns_count
        self.topics_count += other.topics_count
        self.details_count += other.details_count
        self.files_count += other.files_count
        self.images_count += other.images_count
        self.videos_count += other.videos_count
        self.skipped_count += other.skipped_count
        self.files_skipped += other.files_skipped
        self.videos_skipped += other.videos_skipped
        self.request_count += other.request_count


def combined_column_stats(first: ColumnFetchStats, second: ColumnFetchStats) -> ColumnFetchStats:
    combined = ColumnFetchStats()
    combined.add(first)
    combined.add(second)
    return combined


def resolve_columns_fetch_config(settings: Any) -> Dict[str, Any]:
    return {
        "crawl_interval_min": settings.crawlIntervalMin or 2.0,
        "crawl_interval_max": settings.crawlIntervalMax or 5.0,
        "long_sleep_min": settings.longSleepIntervalMin or 30.0,
        "long_sleep_max": settings.longSleepIntervalMax or 60.0,
        "items_per_batch": settings.itemsPerBatch or 10,
        "download_files": settings.downloadFiles if settings.downloadFiles is not None else True,
        "download_videos": settings.downloadVideos if settings.downloadVideos is not None else True,
        "cache_images": settings.cacheImages if settings.cacheImages is not None else True,
        "incremental_mode": settings.incrementalMode if settings.incrementalMode is not None else False,
    }


def build_columns_fetch_result(
    columns_count: int,
    topics_count: int,
    details_count: int,
    files_count: int,
    images_count: int,
    videos_count: int,
    skipped_count: int,
    files_skipped: int,
    videos_skipped: int,
) -> tuple[str, Dict[str, int]]:
    result_msg = f"采集完成: {columns_count} 个专栏, {details_count} 篇新文章, {files_count} 个文件, {videos_count} 个视频"
    if skipped_count:
        result_msg += f", 跳过 {skipped_count} 篇已存在文章"

    return result_msg, {
        "columns_count": columns_count,
        "topics_count": topics_count,
        "details_count": details_count,
        "files_count": files_count,
        "images_count": images_count,
        "videos_count": videos_count,
        "skipped_count": skipped_count,
        "files_skipped": files_skipped,
        "videos_skipped": videos_skipped,
    }


def build_columns_progress_message(
    details_count: int,
    files_count: int,
    videos_count: int,
    images_count: int,
) -> str:
    return f"进度: {details_count} 篇文章, {files_count} 个文件, {videos_count} 个视频, {images_count} 张图片"
