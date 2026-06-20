"""Workflow for downloading selected or filtered file records."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.services.file_downloader_runtime import (
    _create_file_downloader,
    _safe_remove_file_downloader,
)
from backend.services.task_runtime import add_task_log, is_task_stopped, update_task
from backend.storage.zsxq_file_database import (
    DownloadFileRecord,
    _add_file_download_status_condition,
    _add_file_search_condition,
    _build_filtered_download_file_records_query,
    _build_selected_download_file_records_query,
    _fetch_download_file_rows,
    _normalize_download_file_record,
    _query_group_id,
    _unique_int_file_ids,
)


def _build_download_task_stats(total_files: int, found: int, missing: int = 0) -> Dict[str, int]:
    return {
        "total_files": int(total_files),
        "found": int(found),
        "missing": int(missing),
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
    }


def _build_download_file_info(
    file_id: int,
    file_name: str,
    file_size: int,
    download_count: int = 0,
) -> Dict[str, Dict[str, Any]]:
    return DownloadFileRecord(file_id, file_name, file_size, download_count).to_downloader_payload()


def _download_result_stat_key(result: Any) -> str:
    if result == "skipped":
        return "skipped"
    if result:
        return "downloaded"
    return "failed"


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


def _load_download_file_records(
    downloader: ZSXQFileDownloader,
    group_id: str,
    file_ids: Sequence[int],
) -> tuple[list[DownloadFileRecord], list[int]]:
    return downloader.file_db.load_download_file_records(file_ids, group_id=group_id)


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
    total_records = len(records)
    for index, record in enumerate(records, 1):
        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 下载任务被停止")
            return stats

        _download_record_for_task(task_id, downloader, record, index, total_records, stats)
    return stats


def _download_record_for_task(
    task_id: str,
    downloader: ZSXQFileDownloader,
    record: DownloadFileRecord,
    index: int,
    total_records: int,
    stats: Dict[str, int],
) -> None:
    add_task_log(task_id, f"【{index}/{total_records}】{record.name}")
    result = downloader.download_file(record.to_downloader_payload())
    stats[_download_result_stat_key(result)] += 1


def _complete_download_records_if_running(
    task_id: str,
    stats: Dict[str, int],
    completed_message: str,
) -> None:
    if is_task_stopped(task_id):
        return
    update_task(task_id, "completed", completed_message, {"downloaded_files": stats})


def _complete_download_records_task(
    task_id: str,
    downloader: ZSXQFileDownloader,
    records: Sequence[DownloadFileRecord],
    stats: Dict[str, int],
    completed_message: str,
) -> None:
    _run_download_records(task_id, downloader, records, stats)
    _complete_download_records_if_running(task_id, stats, completed_message)


def _complete_empty_download_records_task(
    task_id: str,
    stats: Dict[str, int],
    completed_message: str,
) -> None:
    update_task(task_id, "completed", completed_message, {"downloaded_files": stats})


def run_selected_file_download_task(task_id: str, group_id: str, file_ids: Sequence[int]):
    try:
        update_task(task_id, "running", f"开始下载选中的 {len(file_ids)} 个文件...")
        downloader = _create_file_downloader(task_id, group_id)

        if _file_task_stopped_after_init(task_id):
            return

        records, missing = _load_download_file_records(downloader, group_id, file_ids)
        stats = _build_download_task_stats(
            total_files=len(_unique_int_file_ids(file_ids)),
            found=len(records),
            missing=len(missing),
        )
        if missing:
            add_task_log(task_id, f"⚠️ {len(missing)} 个文件未在文件库中找到，已跳过")
        if not records:
            _complete_empty_download_records_task(task_id, stats, "没有可下载的文件记录")
            return

        _complete_download_records_task(task_id, downloader, records, stats, "选中文件下载完成")
    except Exception as e:
        _fail_file_task(task_id, f"选中文件下载失败: {e}", f"选中文件下载失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)


def run_filtered_file_download_task(
    task_id: str,
    group_id: str,
    status: Optional[str] = None,
    search: Optional[str] = None,
    max_files: Optional[int] = None,
):
    try:
        update_task(task_id, "running", "开始下载当前筛选结果...")
        downloader = _create_file_downloader(task_id, group_id)

        if _file_task_stopped_after_init(task_id):
            return

        records = _load_filtered_download_file_records(
            downloader,
            group_id,
            status=status,
            search=search,
            max_files=max_files,
        )
        stats = _build_download_task_stats(total_files=len(records), found=len(records))
        if not records:
            _complete_empty_download_records_task(task_id, stats, "当前筛选下没有可下载文件")
            return

        _complete_download_records_task(task_id, downloader, records, stats, "筛选结果下载完成")
    except Exception as e:
        _fail_file_task(task_id, f"筛选结果下载失败: {e}", f"筛选结果下载失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)
