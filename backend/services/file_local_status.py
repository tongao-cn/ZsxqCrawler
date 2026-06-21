"""Local filesystem status for downloaded group files."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from backend.services.file_local_paths import (
    download_target_path_with_fallback,
    group_download_dir,
    resolve_local_file_path,
)


def get_download_file_status(group_id: str, file_name: str, file_size: int, fallback: str) -> Dict[str, Any]:
    download_dir = group_download_dir(group_id)
    safe_filename, file_path = download_target_path_with_fallback(download_dir, file_name, fallback)
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


def resolve_download_record_status(
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
