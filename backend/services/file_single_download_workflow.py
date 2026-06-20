"""Workflow for downloading one file by id."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.services.file_download_records_workflow import (
    _build_download_file_info,
    _query_group_id,
)
from backend.services.file_downloader_runtime import (
    _create_file_downloader,
    _rollback_downloader_file_db,
    _safe_remove_file_downloader,
)
from backend.services.task_runtime import add_task_log, is_task_stopped, update_task


def _safe_filename(file_name: str, fallback: str) -> str:
    safe = "".join(c for c in file_name if c.isalnum() or c in "._-（）()[]{}")
    return safe or fallback


def _fail_file_task(
    task_id: str,
    log_message: str,
    task_message: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        if is_task_stopped(task_id):
            return
        add_task_log(task_id, f"❌ {log_message}")
        if result is None:
            update_task(task_id, "failed", task_message)
        else:
            update_task(task_id, "failed", task_message, result)
    except Exception:
        pass


def _file_task_stopped_after_init(task_id: str) -> bool:
    if is_task_stopped(task_id):
        add_task_log(task_id, "🛑 任务在初始化过程中被停止")
        return True
    return False


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


def _fetch_single_download_file_row(
    downloader: ZSXQFileDownloader,
    group_id: str,
    file_id: int,
) -> Any:
    downloader.file_db.cursor.execute(
        """
        SELECT file_id, name, size, download_count
        FROM files
        WHERE file_id = ? AND group_id = ?
        """,
        (file_id, _query_group_id(group_id)),
    )
    return downloader.file_db.cursor.fetchone()


def _resolve_single_download_file_info(
    task_id: str,
    downloader: ZSXQFileDownloader,
    group_id: str,
    file_id: int,
    file_name: Optional[str],
    file_size: Optional[int],
) -> Dict[str, Dict[str, Any]]:
    result = _fetch_single_download_file_row(downloader, group_id, file_id)
    if result:
        _, db_file_name, db_file_size, download_count = result
        add_task_log(task_id, f"📄 从数据库获取文件信息: {db_file_name} ({db_file_size} bytes)")
        return _build_download_file_info(file_id, db_file_name, db_file_size, download_count)
    return _build_single_download_fallback_info(task_id, file_id, file_name, file_size)


def _single_file_download_local_path(
    downloader: ZSXQFileDownloader,
    file_id: int,
    file_info: Dict[str, Dict[str, Any]],
) -> str:
    actual_file_info = file_info["file"]
    actual_file_name = actual_file_info.get("name", f"file_{file_id}")
    safe_filename = _safe_filename(actual_file_name, f"file_{file_id}")
    return os.path.join(downloader.download_dir, safe_filename)


def _complete_successful_single_file_download(
    task_id: str,
    downloader: ZSXQFileDownloader,
    file_id: int,
    file_info: Dict[str, Dict[str, Any]],
) -> None:
    add_task_log(task_id, "✅ 文件下载成功")
    local_path = _single_file_download_local_path(downloader, file_id, file_info)
    downloader.file_db.update_file_download_status(file_id, "completed", local_path)
    update_task(task_id, "completed", "下载成功")


def _complete_skipped_single_file_download(task_id: str) -> None:
    add_task_log(task_id, "✅ 文件已存在，跳过下载")
    update_task(task_id, "completed", "文件已存在")


def _complete_failed_single_file_download(task_id: str) -> None:
    add_task_log(task_id, "❌ 文件下载失败")
    update_task(task_id, "failed", "下载失败")


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
