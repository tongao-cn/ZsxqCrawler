"""Workflow for collecting and downloading files from the file database."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.services.file_downloader_runtime import (
    _create_file_downloader,
    _safe_remove_file_downloader,
)
from backend.services.file_task_lifecycle import (
    fail_file_task as _fail_file_task_impl,
    file_task_stopped_after_init as _file_task_stopped_after_init_impl,
)
from backend.services.task_runtime import add_task_log, is_task_stopped, update_task


def _fail_file_task(
    task_id: str,
    log_message: str,
    task_message: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    _fail_file_task_impl(
        task_id,
        log_message,
        task_message,
        result,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
        update=update_task,
    )


def _file_task_stopped_after_init(task_id: str) -> bool:
    return _file_task_stopped_after_init_impl(
        task_id,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
    )


def _build_file_download_range_log(
    sort_by: str,
    start_time: Optional[str],
    end_time: Optional[str],
    last_days: Optional[int],
) -> Optional[str]:
    if sort_by != "create_time":
        return None
    if start_time or end_time:
        return f"   📅 下载区间: {start_time or '-'} ~ {end_time or '-'}"
    if last_days:
        return f"   📅 下载最近天数: {last_days}天"
    return None


def _log_file_download_config(
    task_id: str,
    sort_by: str,
    start_time: Optional[str],
    end_time: Optional[str],
    last_days: Optional[int],
    download_interval: float,
    long_sleep_interval: float,
    files_per_batch: int,
) -> None:
    add_task_log(task_id, "⚙️ 下载配置:")
    add_task_log(task_id, f"   ⏱️ 单次下载间隔: {download_interval}秒")
    add_task_log(task_id, f"   😴 长休眠间隔: {long_sleep_interval}秒")
    add_task_log(task_id, f"   📦 批次大小: {files_per_batch}个文件")
    range_log = _build_file_download_range_log(sort_by, start_time, end_time, last_days)
    if range_log:
        add_task_log(task_id, range_log)


def _collect_files_for_download(
    downloader: ZSXQFileDownloader,
    sort_by: str,
    start_time: Optional[str],
    end_time: Optional[str],
    last_days: Optional[int],
) -> Any:
    if sort_by == "create_time":
        return downloader.collect_files_for_date_range(
            start_date=start_time,
            end_date=end_time,
            last_days=last_days,
        )
    return downloader.collect_incremental_files()


def _prepare_files_for_download(
    task_id: str,
    downloader: ZSXQFileDownloader,
    group_id: str,
    sort_by: str,
    start_time: Optional[str],
    end_time: Optional[str],
    last_days: Optional[int],
) -> Any:
    add_task_log(task_id, "📡 连接到知识星球API...")
    existing_files_count = _count_existing_file_records(downloader, group_id)

    if existing_files_count == 0:
        add_task_log(task_id, "📍 阶段一：收集文件列表")
        add_task_log(task_id, "🔍 文件库为空，开始收集文件列表...")
        return _collect_files_for_download(
            downloader,
            sort_by,
            start_time,
            end_time,
            last_days,
        )

    add_task_log(task_id, f"📚 文件库已有 {existing_files_count} 条记录，跳过收集阶段，直接下载")
    return None


def _build_file_download_options(
    sort_by: str,
    max_files: Optional[int],
    start_time: Optional[str],
    end_time: Optional[str],
    last_days: Optional[int],
) -> Dict[str, Any]:
    if sort_by == "download_count":
        return {
            "max_files": max_files,
            "status_filter": "pending",
            "sort_by": "download_count",
        }
    return {
        "max_files": max_files,
        "status_filter": "pending",
        "sort_by": "create_time",
        "start_date": start_time,
        "end_date": end_time,
        "last_days": last_days,
    }


def _count_existing_file_records(downloader: ZSXQFileDownloader, group_id: str) -> int:
    return downloader.file_db.count_files(group_id=group_id)


def _download_prepared_files(
    task_id: str,
    downloader: ZSXQFileDownloader,
    collect_result: Any,
    sort_by: str,
    max_files: Optional[int],
    start_time: Optional[str],
    end_time: Optional[str],
    last_days: Optional[int],
) -> Any:
    if collect_result is not None:
        add_task_log(task_id, f"📊 文件收集完成: {collect_result}")
    add_task_log(task_id, "📍 阶段二：下载文件本体")
    add_task_log(task_id, "🚀 开始下载文件...")

    return downloader.download_files_from_database(
        **_build_file_download_options(
            sort_by,
            max_files,
            start_time,
            end_time,
            last_days,
        )
    )


def _complete_file_download_task(task_id: str, result: Any) -> None:
    add_task_log(task_id, "✅ 文件下载完成！")
    update_task(task_id, "completed", "文件下载完成", {"downloaded_files": result})


def run_file_download_task(
    task_id: str,
    group_id: str,
    max_files: Optional[int],
    sort_by: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    last_days: Optional[int] = None,
    download_interval: float = 1.0,
    long_sleep_interval: float = 60.0,
    files_per_batch: int = 10,
    download_interval_min: Optional[float] = None,
    download_interval_max: Optional[float] = None,
    long_sleep_interval_min: Optional[float] = None,
    long_sleep_interval_max: Optional[float] = None,
):
    try:
        update_task(task_id, "running", "开始文件下载...")
        downloader = _create_file_downloader(
            task_id,
            group_id,
            download_interval=download_interval,
            long_sleep_interval=long_sleep_interval,
            files_per_batch=files_per_batch,
            download_interval_min=download_interval_min,
            download_interval_max=download_interval_max,
            long_sleep_interval_min=long_sleep_interval_min,
            long_sleep_interval_max=long_sleep_interval_max,
        )

        _log_file_download_config(
            task_id,
            sort_by,
            start_time,
            end_time,
            last_days,
            download_interval,
            long_sleep_interval,
            files_per_batch,
        )

        if _file_task_stopped_after_init(task_id):
            return

        collect_result = _prepare_files_for_download(
            task_id,
            downloader,
            group_id,
            sort_by,
            start_time,
            end_time,
            last_days,
        )

        if is_task_stopped(task_id):
            return

        result = _download_prepared_files(
            task_id,
            downloader,
            collect_result,
            sort_by,
            max_files,
            start_time,
            end_time,
            last_days,
        )

        if is_task_stopped(task_id):
            return

        _complete_file_download_task(task_id, result)
    except Exception as e:
        _fail_file_task(task_id, f"文件下载失败: {e}", f"文件下载失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)
