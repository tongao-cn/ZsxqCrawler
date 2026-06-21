"""Local path helpers for downloaded group files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from backend.core.db_path_manager import get_db_path_manager


DOWNLOAD_FILENAME_CHARS = "._-（）()[]{}"


def sanitize_download_filename(file_name: Any) -> str:
    return "".join(c for c in str(file_name or "") if c.isalnum() or c in DOWNLOAD_FILENAME_CHARS)


def safe_download_filename(file_name: Any, file_id: Any) -> str:
    return sanitize_download_filename(file_name) or f"file_{file_id}"


def safe_download_filename_with_fallback(file_name: Any, fallback: Any) -> str:
    return sanitize_download_filename(file_name) or str(fallback)


def download_target_path(download_dir: str, file_name: Any, file_id: Any) -> tuple[str, str]:
    safe_filename = safe_download_filename(file_name, file_id)
    return safe_filename, os.path.join(download_dir, safe_filename)


def download_target_path_with_fallback(download_dir: str, file_name: Any, fallback: Any) -> tuple[str, str]:
    safe_filename = safe_download_filename_with_fallback(file_name, fallback)
    return safe_filename, os.path.join(download_dir, safe_filename)


def group_download_dir(group_id: str) -> str:
    return os.path.join(get_db_path_manager().get_group_dir(group_id), "downloads")


def expected_group_download_path(group_id: str, file_name: Any, file_id: Any) -> tuple[str, str]:
    return download_target_path(group_download_dir(group_id), file_name, file_id)


def resolve_local_file_path(
    group_id: str,
    file_id: int,
    file_name: str,
    local_path: Optional[str],
) -> Optional[Path]:
    candidates = []
    if local_path:
        candidates.append(Path(local_path))

    expected_path = expected_group_download_path(group_id, file_name, file_id)[1]
    candidates.append(Path(expected_path))

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None
