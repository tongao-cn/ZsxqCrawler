"""Workflow for clearing group file data and image cache."""

from __future__ import annotations

from backend.storage.zsxq_file_database import ZSXQFileDatabase


def _log_file_route_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _clear_group_file_data(group_id: str) -> dict:
    file_db = ZSXQFileDatabase(group_id)
    try:
        return file_db.clear_group_file_records()
    finally:
        file_db.close()


def _clear_group_image_cache(group_id: str) -> None:
    try:
        from backend.core.image_cache_manager import clear_group_cache_manager, get_image_cache_manager

        cache_manager = get_image_cache_manager(group_id)
        success, message = cache_manager.clear_cache()
        if success:
            _log_file_route_event("INFO", f"图片缓存已清空: {message}")
        else:
            _log_file_route_event("WARN", f"清空图片缓存失败: {message}")
        clear_group_cache_manager(group_id)
    except Exception as cache_error:
        _log_file_route_event("WARN", f"清空图片缓存时出错: {cache_error}")


def _clear_file_database_response(group_id: str) -> dict:
    deleted_counts = _clear_group_file_data(group_id)
    _clear_group_image_cache(group_id)
    return {"message": f"群组 {group_id} 的文件数据和图片缓存已删除", "deleted": deleted_counts}
