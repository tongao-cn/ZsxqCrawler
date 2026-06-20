"""Workflow for clearing group file data and image cache."""

from __future__ import annotations

from backend.storage.db_compat import connect


def _log_file_route_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _clear_group_file_data(group_id: str) -> dict:
    conn = connect()
    try:
        cursor = conn.cursor()
        deleted_counts = {}
        topic_ids_sql = "SELECT topic_id FROM topics WHERE group_id = ?"
        file_ids_sql = f"""
            SELECT file_id FROM files WHERE group_id = ?
            UNION
            SELECT file_id FROM file_topic_relations WHERE topic_id IN ({topic_ids_sql})
            UNION
            SELECT file_id FROM topic_files WHERE topic_id IN ({topic_ids_sql})
        """
        cursor.execute(
            f"DELETE FROM file_ai_analyses WHERE file_id IN ({file_ids_sql})",
            (group_id, group_id, group_id),
        )
        deleted_counts["file_ai_analyses"] = cursor.rowcount
        cursor.execute(
            f"DELETE FROM files WHERE file_id IN ({file_ids_sql})",
            (group_id, group_id, group_id),
        )
        deleted_counts["files"] = cursor.rowcount
        cursor.execute(
            f"DELETE FROM file_topic_relations WHERE topic_id IN ({topic_ids_sql})",
            (group_id,),
        )
        deleted_counts["file_topic_relations"] = cursor.rowcount
        cursor.execute(
            f"DELETE FROM topic_files WHERE topic_id IN ({topic_ids_sql})",
            (group_id,),
        )
        deleted_counts["topic_files"] = cursor.rowcount
        conn.commit()
        return deleted_counts
    finally:
        conn.close()


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
