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


def _build_refresh_topic_failure(message: str) -> dict:
    return {"success": False, "message": message}


def _build_refresh_topic_success(topic_data: dict) -> dict:
    return {
        "success": True,
        "message": "话题信息已更新",
        "updated_data": {
            "likes_count": topic_data.get("likes_count", 0),
            "comments_count": topic_data.get("comments_count", 0),
            "reading_count": topic_data.get("reading_count", 0),
            "readers_count": topic_data.get("readers_count", 0),
        },
    }


def _should_fetch_more_comments(comments_count: int) -> bool:
    return comments_count > 8


def _build_fetch_comments_response(success: bool, message: str, comments_fetched: int) -> dict:
    return {
        "success": success,
        "message": message,
        "comments_fetched": comments_fetched,
    }


def _build_fetch_comments_skip_response(comments_count: int) -> dict:
    return _build_fetch_comments_response(
        True,
        f"话题只有 {comments_count} 条评论，无需获取更多",
        0,
    )


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


def refresh_topic_stats(topic_id: int, group_id: str) -> dict:
    db = None
    try:
        db = ZSXQDatabase(group_id)
        payload = OfficialTopicClient().get_topic_info(topic_id)
        topic = official_payload_topic(payload)
        if not topic:
            return _build_refresh_topic_failure("MCP返回数据格式错误")

        _validate_topic_group(topic, group_id)
        topic_data = normalize_official_topic(topic, group_id)

        success = db.update_topic_stats(topic_data)
        if not success:
            return _build_refresh_topic_failure("话题不存在或更新失败")

        db.conn.commit()
        return _build_refresh_topic_success(topic_data)
    except Exception:
        _rollback_topic_db(db)
        raise
    finally:
        if db:
            db.close()


def _import_more_comments(db, topic_id: int, comments_count: int, client: Optional[OfficialTopicClient] = None) -> int:
    additional_comments = (client or OfficialTopicClient()).get_topic_comments(topic_id)
    if not additional_comments:
        return 0

    db.import_additional_comments(topic_id, additional_comments)
    db.conn.commit()
    return len(additional_comments)


def fetch_more_comments(topic_id: int, group_id: str) -> dict:
    db = None
    try:
        db = ZSXQDatabase(group_id)
        topic_detail = db.get_topic_detail(topic_id)
        if not topic_detail:
            raise TopicWorkflowError(404, "话题不存在")

        comments_count = topic_detail.get("comments_count", 0)
        if not _should_fetch_more_comments(comments_count):
            return _build_fetch_comments_skip_response(comments_count)

        try:
            comments_fetched = _import_more_comments(db, topic_id, comments_count)
            if comments_fetched:
                return _build_fetch_comments_response(
                    True,
                    f"成功获取并导入 {comments_fetched} 条评论",
                    comments_fetched,
                )
            return _build_fetch_comments_response(False, "获取评论失败，可能是权限限制或网络问题", 0)
        except Exception as exc:
            _rollback_topic_db(db)
            return _build_fetch_comments_response(False, f"获取评论时出错: {str(exc)}", 0)
    finally:
        if db:
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
