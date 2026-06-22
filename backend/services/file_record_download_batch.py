"""Batch semantics for downloading file records."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Dict

from backend.storage.zsxq_file_database import DownloadFileRecord


AddTaskLog = Callable[[str, str], None]
IsTaskStopped = Callable[[str], bool]
RunDownloadRecords = Callable[[str, Any, Sequence[DownloadFileRecord], Dict[str, int]], Dict[str, int]]
SkipCompletion = Callable[[], Any]


def build_download_task_stats(total_files: int, found: int, missing: int = 0) -> Dict[str, int]:
    return {
        "total_files": int(total_files),
        "found": int(found),
        "missing": int(missing),
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
    }


def build_download_file_info(
    file_id: int,
    file_name: str,
    file_size: int,
    download_count: int = 0,
) -> Dict[str, Dict[str, Any]]:
    return DownloadFileRecord(file_id, file_name, file_size, download_count).to_downloader_payload()


def download_result_stat_key(result: Any) -> str:
    if result == "skipped":
        return "skipped"
    if result:
        return "downloaded"
    return "failed"


def download_record_for_task(
    task_id: str,
    downloader: Any,
    record: DownloadFileRecord,
    index: int,
    total_records: int,
    stats: Dict[str, int],
    *,
    add_log: AddTaskLog,
) -> None:
    add_log(task_id, f"【{index}/{total_records}】{record.name}")
    result = downloader.download_file(record.to_downloader_payload())
    stats[download_result_stat_key(result)] += 1


def run_download_records(
    task_id: str,
    downloader: Any,
    records: Sequence[DownloadFileRecord],
    stats: Dict[str, int],
    *,
    is_stopped: IsTaskStopped,
    add_log: AddTaskLog,
) -> Dict[str, int]:
    total_records = len(records)
    for index, record in enumerate(records, 1):
        if is_stopped(task_id):
            add_log(task_id, "🛑 下载任务被停止")
            return stats

        download_record_for_task(
            task_id,
            downloader,
            record,
            index,
            total_records,
            stats,
            add_log=add_log,
        )
    return stats


def complete_download_records_task(
    task_id: str,
    downloader: Any,
    records: Sequence[DownloadFileRecord],
    stats: Dict[str, int],
    *,
    is_stopped: IsTaskStopped,
    run_records: RunDownloadRecords,
    skip_completion: SkipCompletion,
) -> Any:
    run_records(task_id, downloader, records, stats)
    if is_stopped(task_id):
        return skip_completion()
    return {"downloaded_files": stats}


def complete_empty_download_records_task(stats: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    return {"downloaded_files": stats}
