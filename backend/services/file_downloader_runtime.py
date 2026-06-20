"""Runtime helpers for file downloader task instances."""

from __future__ import annotations

from typing import Any, Optional

from backend.core.account_context import get_cookie_for_group
from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.services.task_runtime import add_task_log, file_downloader_instances, is_task_stopped


def _create_file_downloader(
    task_id: str,
    group_id: str,
    **kwargs,
) -> ZSXQFileDownloader:
    def log_callback(message: str):
        add_task_log(task_id, message)

    def stop_check():
        return is_task_stopped(task_id)

    cookie = get_cookie_for_group(group_id)
    downloader = ZSXQFileDownloader(cookie=cookie, group_id=group_id, **kwargs)
    downloader.log_callback = log_callback
    downloader.stop_check_func = stop_check
    file_downloader_instances[task_id] = downloader
    return downloader


def _remove_file_downloader(task_id: str) -> None:
    file_downloader_instances.pop(task_id, None)


def _safe_remove_file_downloader(task_id: str) -> None:
    try:
        _remove_file_downloader(task_id)
    except Exception:
        pass


def _close_quietly(resource: Any) -> None:
    if not resource:
        return
    try:
        resource.close()
    except Exception:
        pass


def _rollback_downloader_file_db(downloader: Optional[ZSXQFileDownloader]) -> None:
    try:
        if downloader and getattr(downloader, "file_db", None):
            downloader.file_db.conn.rollback()
    except Exception:
        pass
