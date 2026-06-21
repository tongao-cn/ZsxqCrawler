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
from backend.services.file_local_paths import download_target_path
from backend.services.file_task_lifecycle import (
    file_task_stopped_after_init as _file_task_stopped_after_init_impl,
)
from backend.services.task_runtime import (
    WorkflowCompletionDecision,
    add_task_log,
    finish_workflow,
    is_task_stopped,
    run_workflow,
    skip_workflow_completion,
)


def _fail_file_task(
    task_id: str,
    log_message: str,
    task_message: str,
    result: Optional[Dict[str, Any]] = None,
) -> WorkflowCompletionDecision:
    if is_task_stopped(task_id):
        return skip_workflow_completion()
    add_task_log(task_id, f"❌ {log_message}")
    return finish_workflow(
        "failed",
        task_message,
        result,
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
) -> WorkflowCompletionDecision:
    add_task_log(task_id, "✅ 文件下载成功")
    local_path = _single_file_download_local_path(downloader, file_id, file_info)
    downloader.file_db.update_file_download_status(file_id, "completed", local_path)
    return finish_workflow("completed", "下载成功")


def _complete_skipped_single_file_download(task_id: str) -> WorkflowCompletionDecision:
    add_task_log(task_id, "✅ 文件已存在，跳过下载")
    return finish_workflow("completed", "文件已存在")


def _complete_failed_single_file_download(task_id: str) -> WorkflowCompletionDecision:
    add_task_log(task_id, "❌ 文件下载失败")
    return finish_workflow("failed", "下载失败")


def _complete_single_file_download(
    task_id: str,
    downloader: ZSXQFileDownloader,
    file_id: int,
    file_info: Dict[str, Dict[str, Any]],
    result: Any,
) -> WorkflowCompletionDecision:
    if result == "skipped":
        return _complete_skipped_single_file_download(task_id)
    if result:
        return _complete_successful_single_file_download(task_id, downloader, file_id, file_info)
    return _complete_failed_single_file_download(task_id)


def _download_and_complete_single_file(
    task_id: str,
    downloader: ZSXQFileDownloader,
    file_id: int,
    file_info: Dict[str, Dict[str, Any]],
) -> WorkflowCompletionDecision:
    result = downloader.download_file(file_info)
    return _complete_single_file_download(task_id, downloader, file_id, file_info, result)


def _run_single_file_download(
    task_id: str,
    group_id: str,
    file_id: int,
    file_name: Optional[str],
    file_size: Optional[int],
) -> WorkflowCompletionDecision:
    downloader = None
    try:
        downloader = _create_file_downloader(task_id, group_id)

        if _file_task_stopped_after_init(task_id):
            return skip_workflow_completion()

        file_info = _resolve_single_download_file_info(
            task_id,
            downloader,
            group_id,
            file_id,
            file_name,
            file_size,
        )
        return _download_and_complete_single_file(task_id, downloader, file_id, file_info)
    except Exception as e:
        _rollback_downloader_file_db(downloader)
        return _fail_file_task(task_id, f"任务执行失败: {e}", f"任务失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)


def run_single_file_download_task_with_info(
    task_id: str,
    group_id: str,
    file_id: int,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
):
    run_workflow(
        task_id,
        running_message=f"开始下载文件 (ID: {file_id})...",
        completed_message="下载成功",
        failure_label="单文件下载",
        work=lambda: _run_single_file_download(task_id, group_id, file_id, file_name, file_size),
    )
