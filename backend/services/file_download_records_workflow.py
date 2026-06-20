"""Workflow for downloading selected or filtered file records."""

from __future__ import annotations

from typing import Any, Dict, NamedTuple, Optional, Sequence

from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.services.file_downloader_runtime import (
    _create_file_downloader,
    _safe_remove_file_downloader,
)
from backend.services.task_runtime import add_task_log, is_task_stopped, update_task


_COMPLETED_DOWNLOAD_STATUSES = ("completed", "downloaded", "skipped")

_FILE_SEARCH_CONDITION = """
        (
            LOWER(COALESCE(f.name, '')) LIKE ?
            OR EXISTS (
                SELECT 1
                FROM file_topic_relations fr
                LEFT JOIN topics t ON t.topic_id = fr.topic_id
                LEFT JOIN talks tk ON tk.topic_id = fr.topic_id
                LEFT JOIN articles ar ON ar.topic_id = fr.topic_id
                WHERE fr.file_id = f.file_id
                  AND (
                      LOWER(COALESCE(t.title, '')) LIKE ?
                      OR LOWER(COALESCE(t.annotation, '')) LIKE ?
                      OR LOWER(COALESCE(tk.text, '')) LIKE ?
                      OR LOWER(COALESCE(ar.title, '')) LIKE ?
                  )
            )
            OR EXISTS (
                SELECT 1
                FROM topic_files tf
                LEFT JOIN topics t2 ON t2.topic_id = tf.topic_id
                WHERE tf.file_id = f.file_id
                  AND (
                      LOWER(COALESCE(tf.name, '')) LIKE ?
                      OR LOWER(COALESCE(t2.title, '')) LIKE ?
                      OR LOWER(COALESCE(t2.annotation, '')) LIKE ?
                  )
            )
        )
        """


def _query_group_id(group_id: str) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


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
    return {
        "file": {
            "id": file_id,
            "name": file_name,
            "size": file_size,
            "download_count": download_count,
        }
    }


class DownloadFileRecord(NamedTuple):
    file_id: int
    name: str
    size: int
    download_count: int = 0

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "DownloadFileRecord":
        file_id = int(row[0])
        return cls(
            file_id=file_id,
            name=str(row[1] or f"file_{file_id}"),
            size=int(row[2] or 0),
            download_count=int(row[3] or 0),
        )

    def to_downloader_payload(self) -> Dict[str, Dict[str, Any]]:
        return _build_download_file_info(
            self.file_id,
            self.name,
            self.size,
            self.download_count,
        )


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


def _add_file_download_status_condition(
    conditions: list[str],
    params: list[Any],
    status: Optional[str],
    *,
    strip_status: bool = False,
    treat_all_as_empty: bool = False,
    exclude_completed_when_empty: bool = False,
) -> None:
    requested_status = str(status or "")
    if strip_status:
        requested_status = requested_status.strip()
    if treat_all_as_empty and requested_status == "all":
        requested_status = ""

    if requested_status:
        if requested_status == "completed":
            conditions.append("f.download_status IN (?, ?, ?)")
            params.extend(_COMPLETED_DOWNLOAD_STATUSES)
        else:
            conditions.append("f.download_status = ?")
            params.append(requested_status)
    elif exclude_completed_when_empty:
        conditions.append("(f.download_status IS NULL OR f.download_status NOT IN (?, ?, ?))")
        params.extend(_COMPLETED_DOWNLOAD_STATUSES)


def _unique_int_file_ids(file_ids: Sequence[int]) -> list[int]:
    return list(dict.fromkeys(int(file_id) for file_id in file_ids))


def _build_selected_download_file_records_query(
    group_id: str,
    ordered_ids: Sequence[int],
) -> tuple[str, tuple[Any, ...]]:
    placeholders = ", ".join("?" for _ in ordered_ids)
    return (
        f"""
        SELECT file_id, name, size, download_count
        FROM files
        WHERE group_id = ? AND file_id IN ({placeholders})
        """,
        (_query_group_id(group_id), *ordered_ids),
    )


def _fetch_download_file_rows(
    downloader: ZSXQFileDownloader,
    query: str,
    params: Sequence[Any],
) -> Sequence[Sequence[Any]]:
    downloader.file_db.cursor.execute(query, params)
    return downloader.file_db.cursor.fetchall()


def _load_download_file_records(
    downloader: ZSXQFileDownloader,
    group_id: str,
    file_ids: Sequence[int],
) -> tuple[list[DownloadFileRecord], list[int]]:
    ordered_ids = _unique_int_file_ids(file_ids)
    query, params = _build_selected_download_file_records_query(
        group_id,
        ordered_ids,
    )
    rows = _fetch_download_file_rows(downloader, query, params)
    by_file_id = {int(row[0]): row for row in rows}
    records = [
        _normalize_download_file_record(row)
        for row in (by_file_id[file_id] for file_id in ordered_ids if file_id in by_file_id)
    ]
    missing = [file_id for file_id in ordered_ids if file_id not in by_file_id]
    return records, missing


def _normalize_download_file_record(row: Sequence[Any]) -> DownloadFileRecord:
    return DownloadFileRecord.from_row(row)


def _add_file_search_condition(conditions: list[str], params: list[Any], search: Optional[str]) -> None:
    search_text = (search or "").strip()
    if not search_text:
        return

    search_pattern = f"%{search_text.lower()}%"
    conditions.append(_FILE_SEARCH_CONDITION)
    params.extend([search_pattern] * 8)


def _build_filtered_download_file_records_query(
    group_id: str,
    status: Optional[str],
    search: Optional[str],
    max_files: Optional[int],
) -> tuple[str, tuple[Any, ...]]:
    conditions = ["f.group_id = ?"]
    params: list[Any] = [_query_group_id(group_id)]
    _add_file_download_status_condition(
        conditions,
        params,
        status,
        strip_status=True,
        treat_all_as_empty=True,
        exclude_completed_when_empty=True,
    )

    _add_file_search_condition(conditions, params, search)
    limit_clause = "LIMIT ?" if max_files else ""
    if max_files:
        params.append(int(max_files))

    return (
        f"""
        SELECT f.file_id, f.name, f.size, f.download_count
        FROM files f
        WHERE {' AND '.join(conditions)}
        ORDER BY f.create_time DESC, f.download_count DESC
        {limit_clause}
        """,
        tuple(params),
    )


def _load_filtered_download_file_records(
    downloader: ZSXQFileDownloader,
    group_id: str,
    *,
    status: Optional[str] = None,
    search: Optional[str] = None,
    max_files: Optional[int] = None,
) -> list[DownloadFileRecord]:
    query, params = _build_filtered_download_file_records_query(
        group_id,
        status,
        search,
        max_files,
    )
    rows = _fetch_download_file_rows(downloader, query, params)
    return [_normalize_download_file_record(row) for row in rows]


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
