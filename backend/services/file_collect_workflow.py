"""Workflow for collecting file metadata."""

from __future__ import annotations

from typing import Any

from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.schemas.files import FileCollectRequest
from backend.services.file_downloader_runtime import (
    _create_file_downloader,
    _safe_remove_file_downloader,
)
from backend.services.file_task_lifecycle import (
    file_task_stopped_after_init as _file_task_stopped_after_init_impl,
)
from backend.services.task_runtime import (
    add_task_log,
    is_task_stopped,
    run_workflow,
    skip_workflow_completion,
)


def _file_task_stopped_after_init(task_id: str) -> bool:
    return _file_task_stopped_after_init_impl(
        task_id,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
    )


def _collect_files_for_request(
    task_id: str,
    downloader: ZSXQFileDownloader,
    request: FileCollectRequest,
) -> Any:
    add_task_log(task_id, "📍 阶段一：收集文件列表")
    if request.start_time or request.end_time or request.last_days:
        add_task_log(
            task_id,
            f"📅 收集范围: {request.start_time or '-'} ~ {request.end_time or '-'}"
            if (request.start_time or request.end_time)
            else f"📅 收集最近天数: {request.last_days}天",
        )
        return downloader.collect_files_for_date_range(
            start_date=request.start_time,
            end_date=request.end_time,
            last_days=request.last_days,
        )
    return downloader.collect_incremental_files()


def _collect_files(task_id: str, group_id: str, request: FileCollectRequest) -> Any:
    try:
        downloader = _create_file_downloader(task_id, group_id)

        if _file_task_stopped_after_init(task_id):
            return skip_workflow_completion()

        add_task_log(task_id, "📡 连接到知识星球API...")
        result = _collect_files_for_request(task_id, downloader, request)

        if is_task_stopped(task_id):
            return skip_workflow_completion()

        add_task_log(task_id, "✅ 文件列表收集完成！")
        return result
    finally:
        _safe_remove_file_downloader(task_id)


def run_collect_files_task(task_id: str, group_id: str, request: FileCollectRequest):
    run_workflow(
        task_id,
        running_message="开始收集文件列表...",
        completed_message="文件列表收集完成",
        failure_label="文件列表收集",
        work=lambda: _collect_files(task_id, group_id, request),
    )
