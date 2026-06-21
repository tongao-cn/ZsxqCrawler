from __future__ import annotations

import asyncio
import os
from typing import Any, Callable

import requests

from backend.services.columns_remote_service import fetch_column_file_download_url
from backend.services.file_local_paths import column_download_target_path


async def download_column_file(
    *,
    add_task_log: Callable[[str, str], None] = lambda _task_id, _message: None,
    db: Any,
    file_id: int,
    file_name: str,
    file_size: int,
    group_dir: str,
    headers: dict,
    log_error: Callable[[str], None] = lambda _message: None,
    log_exception: Callable[[str], None] = lambda _message: None,
    log_warning: Callable[[str], None] = lambda _message: None,
    request_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], Any] = asyncio.sleep,
    task_id: str | None = None,
) -> str:
    _safe_filename, local_path = column_download_target_path(group_dir, file_name, file_id)
    downloads_dir = os.path.dirname(local_path)

    if os.path.exists(local_path):
        existing_size = os.path.getsize(local_path)
        if existing_size == file_size or (file_size == 0 and existing_size > 0):
            db.update_file_download_status(file_id, "completed", local_path)
            if task_id:
                add_task_log(task_id, f"         ⏭️ 文件已存在，跳过下载 ({existing_size/(1024*1024):.2f}MB)")
            return "skipped"

    real_url = await fetch_column_file_download_url(
        file_id=file_id,
        file_name=file_name,
        headers=headers,
        request_get=request_get,
        log_error=log_error,
        log_exception=log_exception,
        sleep=sleep,
    )
    if not real_url:
        raise Exception("下载链接为空")

    os.makedirs(downloads_dir, exist_ok=True)

    download_retries = 3
    last_error = None

    for download_attempt in range(download_retries):
        try:
            file_resp = request_get(real_url, headers=headers, stream=True, timeout=300)
            if file_resp.status_code == 200:
                with open(local_path, "wb") as f:
                    for chunk in file_resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                db.update_file_download_status(file_id, "completed", local_path)
                return "downloaded"

            last_error = f"HTTP {file_resp.status_code}"
            if download_attempt < download_retries - 1:
                log_warning(f"文件下载失败 (尝试 {download_attempt + 1}/{download_retries}): {last_error}, file_id={file_id}")
                await sleep(2 * (download_attempt + 1))
                continue
        except requests.exceptions.SSLError as ssl_err:
            last_error = f"SSL错误: {ssl_err}"
            if download_attempt < download_retries - 1:
                log_warning(f"文件下载SSL错误 (尝试 {download_attempt + 1}/{download_retries}): file_id={file_id}, error={ssl_err}")
                await sleep(3 * (download_attempt + 1))
                continue
        except requests.exceptions.RequestException as req_err:
            last_error = f"网络错误: {req_err}"
            if download_attempt < download_retries - 1:
                log_warning(f"文件下载网络错误 (尝试 {download_attempt + 1}/{download_retries}): file_id={file_id}, error={req_err}")
                await sleep(2 * (download_attempt + 1))
                continue

    db.update_file_download_status(file_id, "failed")
    raise Exception(f"下载失败 (重试{download_retries}次): {last_error}")
