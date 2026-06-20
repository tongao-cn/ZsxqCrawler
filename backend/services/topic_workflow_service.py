from __future__ import annotations

from typing import Optional

from backend.crawlers.official_topic_client import (
    OfficialTopicClient,
    normalize_official_topic,
    official_payload_topic,
)
from backend.storage.zsxq_database import ZSXQDatabase


class TopicWorkflowError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _build_single_topic_response(
    topic_id: int,
    group_id: str,
    imported: str,
    comments_fetched: int,
    message: Optional[str] = None,
) -> dict:
    response = {
        "success": True,
        "topic_id": topic_id,
        "group_id": int(group_id),
        "imported": imported,
        "comments_fetched": comments_fetched,
    }
    if message:
        response["message"] = message
    return response


def _validate_topic_group(topic: dict, group_id: str) -> None:
    topic_group_id = str((topic.get("group") or {}).get("group_id", ""))
    if topic_group_id and topic_group_id != str(group_id):
        raise TopicWorkflowError(400, "该话题不属于当前群组")


def _rollback_topic_db(db) -> None:
    try:
        if db and getattr(db, "conn", None):
            db.conn.rollback()
    except Exception:
        pass


def _clear_group_topic_data(group_id: str) -> dict:
    db = ZSXQDatabase(group_id)
    try:
        deleted_counts = db.delete_group_topic_records()
        db.conn.commit()
        return deleted_counts
    finally:
        db.close()


def fetch_single_topic(group_id: str, topic_id: int, fetch_comments: bool = True) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))
        client = OfficialTopicClient()

        if db.topic_exists(topic_id):
            return _build_single_topic_response(topic_id, group_id, "skipped", 0, "话题已存在，跳过采集")

        topic = official_payload_topic(client.get_topic_info(topic_id))
        if not topic:
            raise TopicWorkflowError(404, "未获取到有效话题数据")

        _validate_topic_group(topic, group_id)

        topic_data = normalize_official_topic(topic, group_id)

        comments_fetched = 0
        if fetch_comments:
            comments_count = topic_data.get("comments_count", 0) or 0
            comments = client.get_topic_comments(topic_id) if comments_count > 0 else []
            if comments:
                topic_data["show_comments"] = comments
                comments_fetched = len(comments)

        import_result = db.import_topic_data_with_result(topic_data)
        if not import_result.succeeded:
            message = import_result.error_message or "unknown error"
            raise TopicWorkflowError(500, f"话题导入失败: {message}")
        db.conn.commit()

        if import_result.status == "existing":
            return _build_single_topic_response(topic_id, group_id, "skipped", comments_fetched, "话题已存在，跳过采集")
        return _build_single_topic_response(topic_id, group_id, "created", comments_fetched)
    except Exception:
        _rollback_topic_db(db)
        raise
    finally:
        if db:
            db.close()
