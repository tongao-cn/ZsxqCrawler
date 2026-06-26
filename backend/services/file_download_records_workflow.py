"""Workflow for downloading selected or filtered file records."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from backend.core.account_context import get_cookie_for_group
from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.services.file_record_download_batch import (
    build_download_file_info,
    build_download_task_stats,
    complete_download_records_task,
    complete_empty_download_records_task,
    download_record_for_task,
    download_result_stat_key,
    run_download_records,
    run_download_records_concurrent,
)
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
from backend.storage.zsxq_file_database import (
    DownloadFileRecord,
    DownloadFileSelection,
)


def _build_download_task_stats(total_files: int, found: int, missing: int = 0) -> Dict[str, int]:
    return build_download_task_stats(total_files, found, missing)


def _build_download_file_info(
    file_id: int,
    file_name: str,
    file_size: int,
    download_count: int = 0,
) -> Dict[str, Dict[str, Any]]:
    return build_download_file_info(file_id, file_name, file_size, download_count)


def _download_result_stat_key(result: Any) -> str:
    return download_result_stat_key(result)


def _file_task_stopped_after_init(task_id: str) -> bool:
    return _file_task_stopped_after_init_impl(
        task_id,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
    )


def _load_download_file_records(
    downloader: ZSXQFileDownloader,
    group_id: str,
    file_ids: Sequence[int],
) -> DownloadFileSelection:
    return downloader.file_db.select_download_file_records(file_ids, group_id=group_id)


def _load_filtered_download_file_records(
    downloader: ZSXQFileDownloader,
    group_id: str,
    *,
    status: Optional[str] = None,
    search: Optional[str] = None,
    max_files: Optional[int] = None,
) -> list[DownloadFileRecord]:
    return downloader.file_db.load_filtered_download_file_records(
        status=status,
        search=search,
        max_files=max_files,
        group_id=group_id,
    )


def _run_download_records(
    task_id: str,
    downloader: ZSXQFileDownloader,
    records: Sequence[DownloadFileRecord],
    stats: Dict[str, int],
) -> Dict[str, int]:
    return run_download_records(
        task_id,
        downloader,
        records,
        stats,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
    )


def _create_download_worker(task_id: str, group_id: str) -> ZSXQFileDownloader:
    downloader = ZSXQFileDownloader(
        cookie=get_cookie_for_group(group_id),
        group_id=group_id,
        download_interval=0,
        long_sleep_interval=10,
        files_per_batch=100,
    )
    downloader.log_callback = lambda message: add_task_log(task_id, message)
    downloader.stop_check_func = lambda: is_task_stopped(task_id)
    return downloader


def _safe_close_worker_downloader(downloader: ZSXQFileDownloader) -> None:
    try:
        if getattr(downloader, "file_db", None):
            downloader.file_db.close()
    finally:
        pass


def _run_download_records_concurrent(
    task_id: str,
    group_id: str,
    records: Sequence[DownloadFileRecord],
    stats: Dict[str, int],
    concurrency: int,
) -> Dict[str, int]:
    return run_download_records_concurrent(
        task_id,
        lambda: _create_download_worker(task_id, group_id),
        _safe_close_worker_downloader,
        records,
        stats,
        concurrency=concurrency,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
    )


def _download_record_for_task(
    task_id: str,
    downloader: ZSXQFileDownloader,
    record: DownloadFileRecord,
    index: int,
    total_records: int,
    stats: Dict[str, int],
) -> None:
    download_record_for_task(
        task_id,
        downloader,
        record,
        index,
        total_records,
        stats,
        add_log=add_task_log,
    )


def _complete_download_records_task(
    task_id: str,
    downloader: ZSXQFileDownloader,
    records: Sequence[DownloadFileRecord],
    stats: Dict[str, int],
) -> Any:
    return complete_download_records_task(
        task_id,
        downloader,
        records,
        stats,
        is_stopped=is_task_stopped,
        run_records=_run_download_records,
        skip_completion=skip_workflow_completion,
    )


def _complete_download_records_task_concurrent(
    task_id: str,
    group_id: str,
    records: Sequence[DownloadFileRecord],
    stats: Dict[str, int],
    concurrency: int,
) -> Any:
    _run_download_records_concurrent(task_id, group_id, records, stats, concurrency)
    if is_task_stopped(task_id):
        return skip_workflow_completion()
    return {"downloaded_files": stats}


def _complete_empty_download_records_task(
    stats: Dict[str, int],
) -> Dict[str, Dict[str, int]]:
    return complete_empty_download_records_task(stats)


def _download_selected_file_records(
    task_id: str,
    group_id: str,
    file_ids: Sequence[int],
    concurrency: int,
    workflow_state: Dict[str, str],
) -> Any:
    try:
        downloader = _create_file_downloader(task_id, group_id)

        if _file_task_stopped_after_init(task_id):
            return skip_workflow_completion()

        selection = _load_download_file_records(downloader, group_id, file_ids)
        stats = _build_download_task_stats(
            total_files=selection.requested_count,
            found=len(selection.records),
            missing=len(selection.missing),
        )
        if selection.missing:
            add_task_log(task_id, f"⚠️ {len(selection.missing)} 个文件未在文件库中找到，已跳过")
        if not selection.records:
            workflow_state["completed_message"] = "没有可下载的文件记录"
            return _complete_empty_download_records_task(stats)

        workflow_state["completed_message"] = "选中文件下载完成"
        if int(concurrency or 1) <= 1:
            return _complete_download_records_task(task_id, downloader, selection.records, stats)
        return _complete_download_records_task_concurrent(task_id, group_id, selection.records, stats, concurrency)
    finally:
        _safe_remove_file_downloader(task_id)


def run_selected_file_download_task(task_id: str, group_id: str, file_ids: Sequence[int], concurrency: int = 1):
    workflow_state = {"completed_message": "选中文件下载完成"}
    worker_count = max(1, int(concurrency or 1))
    running_message = f"开始下载选中的 {len(file_ids)} 个文件..."
    if worker_count > 1:
        running_message = f"开始下载选中的 {len(file_ids)} 个文件，并发={worker_count}..."

    run_workflow(
        task_id,
        running_message=running_message,
        completed_message=lambda _result: workflow_state["completed_message"],
        failure_label="选中文件下载",
        work=lambda: _download_selected_file_records(task_id, group_id, file_ids, concurrency, workflow_state),
    )


def _download_filtered_file_records(
    task_id: str,
    group_id: str,
    workflow_state: Dict[str, str],
    *,
    status: Optional[str] = None,
    search: Optional[str] = None,
    max_files: Optional[int] = None,
) -> Any:
    try:
        downloader = _create_file_downloader(task_id, group_id)

        if _file_task_stopped_after_init(task_id):
            return skip_workflow_completion()

        records = _load_filtered_download_file_records(
            downloader,
            group_id,
            status=status,
            search=search,
            max_files=max_files,
        )
        stats = _build_download_task_stats(total_files=len(records), found=len(records))
        if not records:
            workflow_state["completed_message"] = "当前筛选下没有可下载文件"
            return _complete_empty_download_records_task(stats)

        workflow_state["completed_message"] = "筛选结果下载完成"
        return _complete_download_records_task(task_id, downloader, records, stats)
    finally:
        _safe_remove_file_downloader(task_id)


def run_filtered_file_download_task(
    task_id: str,
    group_id: str,
    status: Optional[str] = None,
    search: Optional[str] = None,
    max_files: Optional[int] = None,
):
    workflow_state = {"completed_message": "筛选结果下载完成"}

    run_workflow(
        task_id,
        running_message="开始下载当前筛选结果...",
        completed_message=lambda _result: workflow_state["completed_message"],
        failure_label="筛选结果下载",
        work=lambda: _download_filtered_file_records(
            task_id,
            group_id,
            workflow_state,
            status=status,
            search=search,
            max_files=max_files,
        ),
    )
