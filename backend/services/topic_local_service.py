from __future__ import annotations

from typing import Optional

from backend.services.group_image_cache_clear import clear_group_image_cache
from backend.services.topic_workflow_service import TopicWorkflowError, _clear_group_topic_data
from backend.storage.zsxq_database import TagNotFoundInGroupError, ZSXQDatabase


def _log_topic_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _close_topic_db(db) -> None:
    try:
        if db:
            db.close()
    except Exception:
        pass


def _rollback_topic_db(db) -> None:
    try:
        if db and getattr(db, "conn", None):
            db.conn.rollback()
    except Exception:
        pass


def get_topics_response(page: int = 1, per_page: int = 20, search: Optional[str] = None) -> dict:
    db = None
    try:
        db = ZSXQDatabase()
        return db.get_topics(page, per_page, search)
    finally:
        _close_topic_db(db)


def get_group_topics_response(group_id: int, page: int = 1, per_page: int = 20, search: Optional[str] = None) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))
        return db.get_group_topics(group_id, page, per_page, search)
    finally:
        _close_topic_db(db)


def get_topic_detail_response(topic_id: int, group_id: str) -> dict:
    db = None
    try:
        db = ZSXQDatabase(group_id)
        topic_detail = db.get_topic_detail(topic_id)
        if not topic_detail:
            raise TopicWorkflowError(404, "话题不存在")
        return topic_detail
    finally:
        _close_topic_db(db)


def clear_topic_database_response(group_id: str) -> dict:
    deleted_counts = _clear_group_topic_data(group_id)
    clear_group_image_cache(group_id, _log_topic_event)
    return {"message": f"群组 {group_id} 的话题数据和图片缓存已删除", "deleted": deleted_counts}


def delete_single_topic_response(topic_id: int, group_id: int) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))
        if not db.topic_exists(topic_id):
            return {"success": False, "message": "话题不存在"}

        deleted = db.delete_single_topic_records(topic_id, group_id)
        db.conn.commit()

        return {"success": True, "deleted_topic_id": topic_id, "deleted": deleted}
    except Exception:
        _rollback_topic_db(db)
        raise
    finally:
        _close_topic_db(db)


def get_group_tags_response(group_id: str) -> dict:
    db = None
    try:
        db = ZSXQDatabase(group_id)
        tags = db.get_tags_by_group(int(group_id))
        return {"tags": tags, "total": len(tags)}
    finally:
        _close_topic_db(db)


def get_topics_by_tag_response(group_id: int, tag_id: int, page: int = 1, per_page: int = 20) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))
        try:
            return db.get_group_topics_by_tag(group_id, tag_id, page, per_page)
        except TagNotFoundInGroupError:
            raise TopicWorkflowError(404, "标签在该群组中不存在")
    finally:
        _close_topic_db(db)


def delete_group_topics_response(group_id: int) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))
        topics_count = db.count_topics(group_id)

        if topics_count == 0:
            return {"message": "该群组没有话题数据", "deleted_count": 0}

        deleted_counts = db.delete_group_topic_records(group_id)
        db.conn.commit()

        return {
            "message": f"成功删除群组 {group_id} 的所有话题数据",
            "deleted_topics_count": topics_count,
            "deleted_details": deleted_counts,
        }
    except Exception:
        _rollback_topic_db(db)
        raise
    finally:
        _close_topic_db(db)
