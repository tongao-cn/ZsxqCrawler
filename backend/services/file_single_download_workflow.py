"""Workflow for downloading one file by id."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.services.file_download_records_workflow import _build_download_file_info
from backend.services.file_downloader_runtime import (
    _create_file_downloader,
    _rollback_downloader_file_db,
    _safe_remove_file_downloader,
)
from backend.services.file_task_lifecycle import (
    fail_file_task as _fail_file_task_impl,
    file_task_stopped_after_init as _file_task_stopped_after_init_impl,
    finish_file_task as _finish_file_task_impl,
)
from backend.services.file_local_paths import download_target_path
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


def _build_single_download_fallback_info(
    task_id: str,
    file_id: int,
    file_name: Optional[str],
    file_size: Optional[int],
) -> Dict[str, Dict[str, Any]]:
    if file_name and file_size is not None:
        add_task_log(task_id, f"📄 文件库未命中，使用请求中的文件信息: {file_name} ({file_size} bytes)")
        return _build_download_file_info(file_id, file_name, file_size)

    add_task_log(task_id, f"📄 直接下载文件 ID: {file_id}")
    return _build_download_file_info(file_id, f"file_{file_id}", 0)


def _fetch_single_download_file_record(
    downloader: ZSXQFileDownloader,
    group_id: str,
    file_id: int,
) -> Any:
    return downloader.file_db.get_download_file_record(file_id, group_id=group_id)


def _resolve_single_download_file_info(
    task_id: str,
    downloader: ZSXQFileDownloader,
    group_id: str,
    file_id: int,
    file_name: Optional[str],
    file_size: Optional[int],
) -> Dict[str, Dict[str, Any]]:
    record = _fetch_single_download_file_record(downloader, group_id, file_id)
    if record:
        add_task_log(task_id, f"📄 从数据库获取文件信息: {record.name} ({record.size} bytes)")
        return record.to_downloader_payload()
    return _build_single_download_fallback_info(task_id, file_id, file_name, file_size)


def _single_file_download_local_path(
    downloader: ZSXQFileDownloader,
    file_id: int,
    file_info: Dict[str, Dict[str, Any]],
) -> str:
    actual_file_info = file_info["file"]
    actual_file_name = actual_file_info.get("name", f"file_{file_id}")
    _safe_filename, local_path = download_target_path(downloader.download_dir, actual_file_name, file_id)
    return local_path


def _complete_successful_single_file_download(
    task_id: str,
    downloader: ZSXQFileDownloader,
    file_id: int,
    file_info: Dict[str, Dict[str, Any]],
) -> None:
    add_task_log(task_id, "✅ 文件下载成功")
    local_path = _single_file_download_local_path(downloader, file_id, file_info)
    downloader.file_db.update_file_download_status(file_id, "completed", local_path)
    _finish_file_task_impl(task_id, "completed", "下载成功", update=update_task)


def _complete_skipped_single_file_download(task_id: str) -> None:
    _finish_file_task_impl(
        task_id,
        "completed",
        "文件已存在",
        log_message="✅ 文件已存在，跳过下载",
        add_log=add_task_log,
        update=update_task,
    )


def _complete_failed_single_file_download(task_id: str) -> None:
    _finish_file_task_impl(
        task_id,
        "failed",
        "下载失败",
        log_message="❌ 文件下载失败",
        add_log=add_task_log,
        update=update_task,
    )


def _complete_single_file_download(
    task_id: str,
    downloader: ZSXQFileDownloader,
    file_id: int,
    file_info: Dict[str, Dict[str, Any]],
    result: Any,
) -> None:
    if result == "skipped":
        _complete_skipped_single_file_download(task_id)
    elif result:
        _complete_successful_single_file_download(task_id, downloader, file_id, file_info)
    else:
        _complete_failed_single_file_download(task_id)


def _download_and_complete_single_file(
    task_id: str,
    downloader: ZSXQFileDownloader,
    file_id: int,
    file_info: Dict[str, Dict[str, Any]],
) -> None:
    result = downloader.download_file(file_info)
    _complete_single_file_download(task_id, downloader, file_id, file_info, result)


def run_single_file_download_task_with_info(
    task_id: str,
    group_id: str,
    file_id: int,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
):
    downloader = None
    try:
        update_task(task_id, "running", f"开始下载文件 (ID: {file_id})...")
        downloader = _create_file_downloader(task_id, group_id)

        if _file_task_stopped_after_init(task_id):
            return

        file_info = _resolve_single_download_file_info(
            task_id,
            downloader,
            group_id,
            file_id,
            file_name,
            file_size,
        )
        _download_and_complete_single_file(task_id, downloader, file_id, file_info)
    except Exception as e:
        _rollback_downloader_file_db(downloader)
        _fail_file_task(task_id, f"任务执行失败: {e}", f"任务失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)
