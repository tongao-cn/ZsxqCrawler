"""Route-facing read models for group file workflows."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional, Sequence

from backend.services.file_clear_workflow import _clear_file_database_response
from backend.services.file_local_status import (
    get_download_file_status,
    resolve_download_record_status,
)
from backend.storage.zsxq_file_database import ZSXQFileDatabase


def _open_file_db(group_id: str) -> ZSXQFileDatabase:
    return ZSXQFileDatabase(group_id)


@contextmanager
def _file_db(group_id: str) -> Iterator[ZSXQFileDatabase]:
    file_db = _open_file_db(group_id)
    try:
        yield file_db
    finally:
        file_db.close()


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


def get_file_status_response(group_id: str, file_id: int) -> dict:
    with _file_db(group_id) as file_db:
        result = file_db.get_file_status_record(file_id)

        if not result:
            return _build_file_status_response(file_id, result)

        file_name, file_size, _download_status = result
        local_status = get_download_file_status(group_id, file_name, file_size, f"file_{file_id}")
        return _build_file_status_response(file_id, result, local_status)


def check_local_file_status_response(group_id: str, file_name: str, file_size: int) -> dict:
    local_status = get_download_file_status(group_id, file_name, file_size, file_name)
    return _build_check_local_file_status_response(file_name, file_size, local_status)


def get_file_stats_response(group_id: str) -> dict:
    with _file_db(group_id) as file_db:
        stats = file_db.get_database_stats()
        download_stats = file_db.get_file_download_stats()
        return _build_file_stats_response(stats, download_stats)


def clear_file_database_response(group_id: str) -> dict:
    return _clear_file_database_response(group_id)


def normalize_file_list_row(group_id: str, file: Any) -> Dict[str, Any]:
    file_id = file.file_id
    file_name = file.name
    stored_status = file.download_status
    stored_local_path = file.local_path

    local_status = resolve_download_record_status(
        group_id,
        file_id,
        file_name,
        stored_status,
        stored_local_path,
    )

    return {
        "file_id": file_id,
        "name": file_name,
        "size": file.size,
        "download_count": file.download_count,
        "create_time": file.create_time,
        "download_status": local_status["download_status"],
        "local_exists": local_status["local_exists"],
        "local_path": local_status["local_path"],
        "download_error_code": file.download_error_code,
        "download_error_message": file.download_error_message,
        "last_download_attempt_at": file.last_download_attempt_at,
        "has_ai_analysis": bool(file.analysis_updated_at),
        "analysis_updated_at": file.analysis_updated_at,
    }


def build_file_list_response(
    group_id: str,
    files: Sequence[Any],
    total: int,
    page: int,
    per_page: int,
) -> Dict[str, Any]:
    return {
        "files": [normalize_file_list_row(group_id, file) for file in files],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    }


def get_files_response(
    group_id: str,
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    analysis_status: Optional[str] = None,
) -> dict:
    with _file_db(group_id) as file_db:
        file_page = file_db.load_file_list_page(
            page=page,
            per_page=per_page,
            status=status,
            search=search,
            analysis_status=analysis_status,
        )
        return build_file_list_response(group_id, file_page.records, file_page.total, page, per_page)
