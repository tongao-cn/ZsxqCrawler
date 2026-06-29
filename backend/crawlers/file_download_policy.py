"""Download execution policy and local-file helpers for ZSXQ files."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

from backend.services.file_local_paths import (
    download_target_path as _download_target_path,
    safe_download_filename as _safe_download_filename,
)


DOWNLOAD_PROGRESS_INTERVAL_BYTES = 10 * 1024 * 1024


def safe_download_filename(file_name: Any, file_id: Any) -> str:
    return _safe_download_filename(file_name, file_id)


def download_target_path(download_dir: str, file_name: Any, file_id: Any) -> tuple[str, str]:
    return _download_target_path(download_dir, file_name, file_id)


def download_file_data(file_info: Dict[str, Any]) -> Dict[str, Any]:
    file_data = file_info.get("file", {}) or {}
    return {
        "file_id": file_data.get("id") or file_data.get("file_id"),
        "file_name": file_data.get("name", "Unknown"),
        "file_size": file_data.get("size", 0),
        "download_count": file_data.get("download_count", 0),
    }


def download_result_stats(total_files: int = 0) -> Dict[str, int]:
    return {
        "total_files": int(total_files),
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
    }


def existing_file_matches(file_path: str, expected_size: int) -> tuple[bool, bool, int]:
    if not os.path.exists(file_path):
        return False, False, 0
    existing_size = os.path.getsize(file_path)
    matches = existing_size == expected_size or (expected_size == 0 and existing_size > 0)
    return True, matches, existing_size


def remove_partial_download(temp_path: str) -> bool:
    if not os.path.exists(temp_path):
        return False
    os.remove(temp_path)
    return True


def download_progress_message(downloaded_size: int, total_size: int) -> Optional[str]:
    if downloaded_size % DOWNLOAD_PROGRESS_INTERVAL_BYTES == 0 or downloaded_size == total_size:
        if total_size > 0:
            progress = (downloaded_size / total_size) * 100
            return f"   📊 进度: {progress:.1f}% ({downloaded_size:,}/{total_size:,} bytes)"

    if downloaded_size % DOWNLOAD_PROGRESS_INTERVAL_BYTES != 0 and downloaded_size != total_size:
        if total_size == 0:
            return f"   📊 已下载: {downloaded_size:,} bytes"

    return None


def download_url_failure_detail(error_detail: Optional[Dict[str, Any]]) -> tuple[str, str]:
    detail = error_detail or {
        "code": "download_url_unavailable",
        "message": "无法获取下载链接",
    }
    return (
        str(detail.get("code") or "download_url_unavailable"),
        str(detail.get("message") or "无法获取下载链接"),
    )


def download_retry_wait(attempt: int, download_retries: int) -> tuple[int, str]:
    retry_delay = 2 * attempt
    return (
        retry_delay,
        f"   🔄 文件下载重试 {attempt + 1}/{download_retries}，等待 {retry_delay} 秒...",
    )


def download_interval_plan(
    current_batch_count: int,
    files_per_batch: int,
    download_interval: float,
    long_sleep_interval: float,
) -> tuple[Optional[float], tuple[str, ...], bool]:
    if current_batch_count >= files_per_batch:
        return (
            long_sleep_interval,
            (
                f"⏰ 已下载 {current_batch_count} 个文件，开始长休眠 {long_sleep_interval} 秒...",
                "😴 长休眠结束，继续下载",
            ),
            True,
        )
    if download_interval > 0:
        return (
            download_interval,
            (f"⏱️ 下载间隔休眠 {download_interval} 秒...",),
            False,
        )
    return None, (), False


def download_size_mismatch_detail(expected_size: int, final_size: int) -> Optional[tuple[str, str]]:
    if expected_size <= 0 or final_size == expected_size:
        return None
    return (
        "size_mismatch",
        f"文件大小不匹配: 预期{expected_size:,}, 实际{final_size:,}",
    )


def download_http_failure_detail(status_code: int) -> tuple[str, str]:
    return "http_status", f"HTTP {status_code}"


def download_exception_detail(exc: Exception) -> tuple[str, str]:
    return "download_exception", str(exc)


def download_final_failure_detail(
    last_error_code: Optional[str],
    last_error: Optional[str],
) -> tuple[str, str]:
    return last_error_code or "download_failed", last_error or "文件下载失败"


def download_expected_size(file_size: int, total_size: int) -> int:
    return file_size if file_size > 0 else total_size


def download_total_size(response_headers: Dict[str, Any]) -> int:
    return int(response_headers.get("content-length", 0))


def partial_download_path(file_path: str) -> str:
    return f"{file_path}.part"


def content_disposition_filename(content_disposition: str) -> Optional[str]:
    if "filename=" not in content_disposition:
        return None
    filename_match = re.search(r"filename[*]?=([^;]+)", content_disposition)
    if not filename_match:
        return None
    real_filename = filename_match.group(1).strip('"\'')
    return real_filename or None


def response_filename_override(
    file_name: str,
    file_id: Any,
    download_dir: str,
    response_headers: Dict[str, Any],
) -> Optional[Tuple[str, str, str]]:
    if not file_name.startswith("file_") or "content-disposition" not in response_headers:
        return None

    real_filename = content_disposition_filename(response_headers["content-disposition"])
    if not real_filename:
        return None

    safe_filename = safe_download_filename(real_filename, file_id)
    file_path = os.path.join(download_dir, safe_filename)
    return real_filename, safe_filename, file_path


__all__ = [
    "DOWNLOAD_PROGRESS_INTERVAL_BYTES",
    "content_disposition_filename",
    "download_exception_detail",
    "download_expected_size",
    "download_file_data",
    "download_final_failure_detail",
    "download_http_failure_detail",
    "download_interval_plan",
    "download_progress_message",
    "download_result_stats",
    "download_retry_wait",
    "download_size_mismatch_detail",
    "download_target_path",
    "download_total_size",
    "download_url_failure_detail",
    "existing_file_matches",
    "partial_download_path",
    "remove_partial_download",
    "response_filename_override",
    "safe_download_filename",
]
