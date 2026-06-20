"""Route-facing read models for group file workflows."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from backend.services.file_clear_workflow import _clear_file_database_response
from backend.services.file_status_service import (
    _check_local_file_status_response,
    _file_db,
    _get_file_stats_response,
    _get_file_status_response,
    _resolve_download_record_status,
)


def get_file_status_response(group_id: str, file_id: int) -> dict:
    return _get_file_status_response(group_id, file_id)


def check_local_file_status_response(group_id: str, file_name: str, file_size: int) -> dict:
    return _check_local_file_status_response(group_id, file_name, file_size)


def get_file_stats_response(group_id: str) -> dict:
    return _get_file_stats_response(group_id)


def clear_file_database_response(group_id: str) -> dict:
    return _clear_file_database_response(group_id)


def normalize_file_list_row(group_id: str, file: Any) -> Dict[str, Any]:
    file_id = file.file_id
    file_name = file.name
    stored_status = file.download_status
    stored_local_path = file.local_path

    local_status = _resolve_download_record_status(
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
