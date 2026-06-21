"""Workflow for clearing group file data and image cache."""

from __future__ import annotations

from backend.services.group_image_cache_clear import clear_group_image_cache
from backend.storage.zsxq_file_database import ZSXQFileDatabase


def _log_file_route_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _clear_group_file_data(group_id: str) -> dict:
    file_db = ZSXQFileDatabase(group_id)
    try:
        return file_db.clear_group_file_records()
    finally:
        file_db.close()


def _clear_file_database_response(group_id: str) -> dict:
    deleted_counts = _clear_group_file_data(group_id)
    clear_group_image_cache(group_id, _log_file_route_event)
    return {"message": f"群组 {group_id} 的文件数据和图片缓存已删除", "deleted": deleted_counts}
