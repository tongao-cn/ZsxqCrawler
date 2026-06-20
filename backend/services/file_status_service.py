"""Read helpers for file status and file statistics."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional, Sequence

from backend.core.db_path_manager import get_db_path_manager
from backend.services.file_ai_analysis_service import resolve_local_file_path
from backend.services.file_download_records_workflow import _query_group_id
from backend.storage.zsxq_file_database import ZSXQFileDatabase


def _safe_filename(file_name: str, fallback: str) -> str:
    safe = "".join(c for c in file_name if c.isalnum() or c in "._-（）()[]{}")
    return safe or fallback


def _open_file_db(group_id: str) -> ZSXQFileDatabase:
    return ZSXQFileDatabase(group_id)


@contextmanager
def _file_db(group_id: str) -> Iterator[ZSXQFileDatabase]:
    file_db = _open_file_db(group_id)
    try:
        yield file_db
    finally:
        file_db.close()


def _get_download_file_status(group_id: str, file_name: str, file_size: int, fallback: str) -> Dict[str, Any]:
    safe_filename = _safe_filename(file_name, fallback)
    download_dir = os.path.join(get_db_path_manager().get_group_dir(group_id), "downloads")
    file_path = os.path.join(download_dir, safe_filename)
    local_exists = os.path.exists(file_path)
    local_size = os.path.getsize(file_path) if local_exists else 0
    return {
        "safe_filename": safe_filename,
        "local_exists": local_exists,
        "local_size": local_size,
        "local_path": file_path if local_exists else None,
        "is_complete": local_exists and (file_size == 0 or local_size == file_size),
        "download_dir": download_dir,
    }


def _resolve_download_record_status(
    group_id: str,
    file_id: int,
    file_name: str,
    stored_status: Optional[str],
    stored_local_path: Optional[str],
) -> Dict[str, Any]:
    resolved_local_path = resolve_local_file_path(group_id, file_id, file_name, stored_local_path)
    local_exists = resolved_local_path is not None
    effective_local_path = str(resolved_local_path) if resolved_local_path else None
    return {
        "download_status": "completed" if local_exists else (stored_status or "unknown"),
        "local_exists": local_exists,
        "local_path": effective_local_path,
    }


def _build_file_status_response(
    file_id: int,
    result: Optional[tuple],
    local_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not result:
        return {
            "file_id": file_id,
            "name": f"file_{file_id}",
            "size": 0,
            "download_status": "not_collected",
            "local_exists": False,
            "local_size": 0,
            "local_path": None,
            "is_complete": False,
            "message": "文件信息未收集，请先运行文件收集任务",
        }

    file_name, file_size, download_status = result
    local_status = local_status or {}
    return {
        "file_id": file_id,
        "name": file_name,
        "size": file_size,
        "download_status": download_status or "pending",
        "local_exists": local_status["local_exists"],
        "local_size": local_status["local_size"],
        "local_path": local_status["local_path"],
        "is_complete": local_status["is_complete"],
    }


def _build_check_local_file_status_response(
    file_name: str,
    file_size: int,
    local_status: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "file_name": file_name,
        "safe_filename": local_status["safe_filename"],
        "expected_size": file_size,
        "local_exists": local_status["local_exists"],
        "local_size": local_status["local_size"],
        "local_path": local_status["local_path"],
        "is_complete": local_status["is_complete"],
        "download_dir": local_status["download_dir"],
    }


def _build_sync_files_response(group_id: str, stats: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "success": True,
        "group_id": group_id,
        "stats": stats,
    }


_FILE_STATUS_QUERY = """
            SELECT name, size, download_status
            FROM files
            WHERE file_id = ? AND group_id = ?
        """


def _fetch_file_status_row(
    file_db: ZSXQFileDatabase,
    group_id: str,
    file_id: int,
) -> Optional[tuple]:
    file_db.cursor.execute(_FILE_STATUS_QUERY, (file_id, _query_group_id(group_id)))
    return file_db.cursor.fetchone()


def _get_file_status_response(group_id: str, file_id: int) -> dict:
    with _file_db(group_id) as file_db:
        result = _fetch_file_status_row(file_db, group_id, file_id)

        if not result:
            return _build_file_status_response(file_id, result)

        file_name, file_size, _download_status = result
        local_status = _get_download_file_status(group_id, file_name, file_size, f"file_{file_id}")
        return _build_file_status_response(file_id, result, local_status)


def _check_local_file_status_response(group_id: str, file_name: str, file_size: int) -> dict:
    local_status = _get_download_file_status(group_id, file_name, file_size, file_name)
    return _build_check_local_file_status_response(file_name, file_size, local_status)


def _build_file_stats_response(stats: Dict[str, Any], download_stats: Optional[Sequence[Any]]) -> Dict[str, Any]:
    return {
        "database_stats": stats,
        "download_stats": {
            "total_files": download_stats[0] if download_stats else 0,
            "downloaded": download_stats[1] if download_stats else 0,
            "pending": download_stats[2] if download_stats else 0,
            "failed": download_stats[3] if download_stats else 0,
        },
    }


_FILE_DOWNLOAD_STATS_QUERY = """
            SELECT
                COUNT(*) as total_files,
                COUNT(CASE WHEN download_status IN ('completed', 'downloaded', 'skipped') THEN 1 END) as downloaded,
                COUNT(CASE WHEN download_status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN download_status = 'failed' THEN 1 END) as failed
            FROM files
            WHERE group_id = ?
            """


def _fetch_file_download_stats(file_db: ZSXQFileDatabase, group_id: str) -> Optional[Sequence[Any]]:
    file_db.cursor.execute(_FILE_DOWNLOAD_STATS_QUERY, (_query_group_id(group_id),))
    return file_db.cursor.fetchone()


def _get_file_stats_response(group_id: str) -> dict:
    with _file_db(group_id) as file_db:
        stats = file_db.get_database_stats()
        download_stats = _fetch_file_download_stats(file_db, group_id)
        return _build_file_stats_response(stats, download_stats)
