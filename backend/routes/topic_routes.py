from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.crawlers.official_topic_client import (
    OfficialTopicClient,
    normalize_official_topic,
    official_payload_topic,
)
from backend.services.topic_workflow_service import (
    TopicWorkflowError,
    _clear_group_topic_data,
    fetch_single_topic as fetch_single_topic_workflow,
)
from backend.storage.zsxq_database import TagNotFoundInGroupError, ZSXQDatabase

router = APIRouter(prefix="/api", tags=["topics"])


def _log_topic_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _topic_route_error(message: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


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


def _query_group_id(group_id: int | str) -> int | str:
    return int(group_id) if str(group_id).isdigit() else str(group_id)


def _validate_topic_group(topic: dict, group_id: str) -> None:
    topic_group_id = str((topic.get("group") or {}).get("group_id", ""))
    if topic_group_id and topic_group_id != str(group_id):
        raise HTTPException(status_code=400, detail="该话题不属于当前群组")


def _fetch_and_import_topic_comments(db, topic_id: int, comments_count: int, client: Optional[OfficialTopicClient] = None) -> int:
    if comments_count <= 0:
        return 0

    try:
        additional_comments = (client or OfficialTopicClient()).get_topic_comments(topic_id)
        if additional_comments:
            db.import_additional_comments(topic_id, additional_comments)
            db.conn.commit()
            return len(additional_comments)
    except Exception as e:
        _log_topic_event("WARN", f"单话题评论获取失败: {e}")

    return 0


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


def _import_more_comments(db, topic_id: int, comments_count: int, client: Optional[OfficialTopicClient] = None) -> int:
    additional_comments = (client or OfficialTopicClient()).get_topic_comments(topic_id)
    if not additional_comments:
        return 0

    db.import_additional_comments(topic_id, additional_comments)
    db.conn.commit()
    return len(additional_comments)


def _get_topics_response(page: int = 1, per_page: int = 20, search: Optional[str] = None) -> dict:
    db = None
    try:
        db = ZSXQDatabase()
        return db.get_topics(page, per_page, search)
    finally:
        _close_topic_db(db)


def _get_group_topics_response(group_id: int, page: int = 1, per_page: int = 20, search: Optional[str] = None) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))
        return db.get_group_topics(group_id, page, per_page, search)
    finally:
        _close_topic_db(db)


def _get_topic_detail_response(topic_id: int, group_id: str) -> dict:
    db = None
    try:
        db = ZSXQDatabase(group_id)
        topic_detail = db.get_topic_detail(topic_id)

        if not topic_detail:
            raise HTTPException(status_code=404, detail="话题不存在")

        return topic_detail
    finally:
        _close_topic_db(db)


def _clear_topic_database_response(group_id: str) -> dict:
    deleted_counts = _clear_group_topic_data(group_id)
    try:
        from backend.core.image_cache_manager import clear_group_cache_manager, get_image_cache_manager

        cache_manager = get_image_cache_manager(group_id)
        success, message = cache_manager.clear_cache()
        if success:
            _log_topic_event("INFO", f"图片缓存已清空: {message}")
        else:
            _log_topic_event("WARN", f"清空图片缓存失败: {message}")
        clear_group_cache_manager(group_id)
    except Exception as cache_error:
        _log_topic_event("WARN", f"清空图片缓存时出错: {cache_error}")

    return {"message": f"群组 {group_id} 的话题数据和图片缓存已删除", "deleted": deleted_counts}


def _refresh_topic_response(topic_id: int, group_id: str) -> dict:
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
    finally:
        _close_topic_db(db)


def _fetch_more_comments_response(topic_id: int, group_id: str) -> dict:
    db = None
    try:
        db = ZSXQDatabase(group_id)
        topic_detail = db.get_topic_detail(topic_id)
        if not topic_detail:
            raise HTTPException(status_code=404, detail="话题不存在")

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
        except Exception as e:
            return _build_fetch_comments_response(False, f"获取评论时出错: {str(e)}", 0)
    finally:
        _close_topic_db(db)


def _delete_single_topic_response(topic_id: int, group_id: int) -> dict:
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


def _get_group_tags_response(group_id: str) -> dict:
    db = None
    try:
        db = ZSXQDatabase(group_id)
        tags = db.get_tags_by_group(int(group_id))
        return {"tags": tags, "total": len(tags)}
    finally:
        _close_topic_db(db)


def _get_topics_by_tag_response(group_id: int, tag_id: int, page: int = 1, per_page: int = 20) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))
        try:
            return db.get_group_topics_by_tag(group_id, tag_id, page, per_page)
        except TagNotFoundInGroupError:
            raise HTTPException(status_code=404, detail="标签在该群组中不存在")
    finally:
        _close_topic_db(db)


def _delete_group_topics_response(group_id: int) -> dict:
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


async def _topics_page(page: int, per_page: int, search: Optional[str]) -> dict:
    return await asyncio.to_thread(_get_topics_response, page, per_page, search)


async def _group_topics_page(group_id: int, page: int, per_page: int, search: Optional[str]) -> dict:
    return await asyncio.to_thread(_get_group_topics_response, group_id, page, per_page, search)


async def _topic_detail(topic_id: int, group_id: str) -> dict:
    return await asyncio.to_thread(_get_topic_detail_response, topic_id, group_id)


async def _cleared_topic_database(group_id: str) -> dict:
    return await asyncio.to_thread(_clear_topic_database_response, group_id)


async def _refreshed_topic(topic_id: int, group_id: str) -> dict:
    return await asyncio.to_thread(_refresh_topic_response, topic_id, group_id)


async def _more_comments(topic_id: int, group_id: str) -> dict:
    return await asyncio.to_thread(_fetch_more_comments_response, topic_id, group_id)


async def _deleted_single_topic(topic_id: int, group_id: int) -> dict:
    return await asyncio.to_thread(_delete_single_topic_response, topic_id, group_id)


async def _fetched_single_topic(group_id: str, topic_id: int, fetch_comments: bool) -> dict:
    try:
        return await asyncio.to_thread(fetch_single_topic_workflow, group_id, topic_id, fetch_comments)
    except TopicWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


async def _group_tags(group_id: str) -> dict:
    return await asyncio.to_thread(_get_group_tags_response, group_id)


async def _tagged_topics(group_id: int, tag_id: int, page: int, per_page: int) -> dict:
    return await asyncio.to_thread(_get_topics_by_tag_response, group_id, tag_id, page, per_page)


async def _deleted_group_topics(group_id: int) -> dict:
    return await asyncio.to_thread(_delete_group_topics_response, group_id)


@router.get("/topics")
async def get_topics(page: int = 1, per_page: int = 20, search: Optional[str] = None):
    """获取话题列表"""
    try:
        return await _topics_page(page, per_page, search)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取话题列表失败", e)


@router.get("/groups/{group_id}/topics")
async def get_group_topics(group_id: int, page: int = 1, per_page: int = 20, search: Optional[str] = None):
    """获取指定群组的话题列表"""
    try:
        return await _group_topics_page(group_id, page, per_page, search)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取群组话题失败", e)


@router.post("/topics/clear/{group_id}")
async def clear_topic_database(group_id: str):
    """删除指定群组的 PostgreSQL 话题数据"""
    try:
        return await _cleared_topic_database(group_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_topic_event("ERROR", f"删除话题数据库失败: {str(e)}")
        raise _topic_route_error("删除话题数据库失败", e)


@router.get("/topics/{topic_id}/{group_id}")
async def get_topic_detail(topic_id: int, group_id: str):
    """获取话题详情（仅从本地数据库读取，不主动爬取）"""
    try:
        return await _topic_detail(topic_id, group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取话题详情失败", e)


@router.post("/topics/{topic_id}/{group_id}/refresh")
async def refresh_topic(topic_id: int, group_id: str):
    """实时更新单个话题信息"""
    try:
        return await _refreshed_topic(topic_id, group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("更新话题失败", e)


@router.post("/topics/{topic_id}/{group_id}/fetch-comments")
async def fetch_more_comments(topic_id: int, group_id: str):
    """手动获取话题的更多评论（在已存在本地话题记录的前提下）"""
    try:
        return await _more_comments(topic_id, group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取更多评论失败", e)


@router.delete("/topics/{topic_id}/{group_id}")
async def delete_single_topic(topic_id: int, group_id: int):
    """删除单个话题及其所有关联数据"""
    try:
        return await _deleted_single_topic(topic_id, group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("删除话题失败", e)


@router.post("/topics/fetch-single/{group_id}/{topic_id}")
async def fetch_single_topic(group_id: str, topic_id: int, fetch_comments: bool = True):
    """爬取并导入单个话题（用于特殊话题测试），可选拉取完整评论"""
    try:
        return await _fetched_single_topic(group_id, topic_id, fetch_comments)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("单个话题采集失败", e)


@router.get("/groups/{group_id}/tags")
async def get_group_tags(group_id: str):
    """获取指定群组的所有标签"""
    try:
        return await _group_tags(group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("获取标签列表失败", e)


@router.get("/groups/{group_id}/tags/{tag_id}/topics")
async def get_topics_by_tag(group_id: int, tag_id: int, page: int = 1, per_page: int = 20):
    """根据标签获取指定群组的话题列表"""
    try:
        return await _tagged_topics(group_id, tag_id, page, per_page)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("根据标签获取话题失败", e)


@router.delete("/groups/{group_id}/topics")
async def delete_group_topics(group_id: int):
    """删除指定群组的所有话题数据"""
    try:
        return await _deleted_group_topics(group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _topic_route_error("删除话题数据失败", e)
