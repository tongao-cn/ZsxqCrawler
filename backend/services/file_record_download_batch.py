"""Batch semantics for downloading file records."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Dict

from backend.storage.zsxq_file_database import DownloadFileRecord


AddTaskLog = Callable[[str, str], None]
IsTaskStopped = Callable[[str], bool]
RunDownloadRecords = Callable[[str, Any, Sequence[DownloadFileRecord], Dict[str, int]], Dict[str, int]]
SkipCompletion = Callable[[], Any]
DownloaderFactory = Callable[[], Any]
DownloaderCleanup = Callable[[Any], None]


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


def _download_records_with_worker_downloader(
    task_id: str,
    downloader_factory: DownloaderFactory,
    downloader_cleanup: DownloaderCleanup,
    indexed_records: Sequence[tuple[int, DownloadFileRecord]],
    total_records: int,
    stats: Dict[str, int],
    stats_lock: Lock,
    *,
    is_stopped: IsTaskStopped,
    add_log: AddTaskLog,
) -> None:
    downloader = downloader_factory()
    try:
        for index, record in indexed_records:
            if is_stopped(task_id):
                add_log(task_id, "🛑 下载任务被停止")
                return
            try:
                add_log(task_id, f"【{index}/{total_records}】{record.name}")
                result = downloader.download_file(record.to_downloader_payload())
                stat_key = download_result_stat_key(result)
            except Exception as exc:
                add_log(task_id, f"   ❌ 处理文件异常: {exc}")
                stat_key = "failed"
            with stats_lock:
                stats[stat_key] += 1
    finally:
        downloader_cleanup(downloader)


def _partition_indexed_records(
    records: Sequence[DownloadFileRecord],
    worker_count: int,
) -> list[list[tuple[int, DownloadFileRecord]]]:
    partitions: list[list[tuple[int, DownloadFileRecord]]] = [[] for _ in range(worker_count)]
    for offset, record in enumerate(records):
        partitions[offset % worker_count].append((offset + 1, record))
    return partitions


def run_download_records_concurrent(
    task_id: str,
    downloader_factory: DownloaderFactory,
    downloader_cleanup: DownloaderCleanup,
    records: Sequence[DownloadFileRecord],
    stats: Dict[str, int],
    *,
    concurrency: int,
    is_stopped: IsTaskStopped,
    add_log: AddTaskLog,
) -> Dict[str, int]:
    worker_count = max(1, min(int(concurrency or 1), len(records)))
    if worker_count <= 1:
        downloader = downloader_factory()
        try:
            return run_download_records(
                task_id,
                downloader,
                records,
                stats,
                is_stopped=is_stopped,
                add_log=add_log,
            )
        finally:
            downloader_cleanup(downloader)

    stats_lock = Lock()
    partitions = _partition_indexed_records(records, worker_count)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = []
        for indexed_records in partitions:
            if is_stopped(task_id):
                add_log(task_id, "🛑 下载任务被停止")
                break
            future = executor.submit(
                _download_records_with_worker_downloader,
                task_id,
                downloader_factory,
                downloader_cleanup,
                indexed_records,
                len(records),
                stats,
                stats_lock,
                is_stopped=is_stopped,
                add_log=add_log,
            )
            futures.append(future)

        for future in as_completed(futures):
            future.result()
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
