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
    _clear_group_topic_data,
    _delete_group_topic_rows,
    _delete_single_topic_rows,
)
from backend.storage.zsxq_database import ZSXQDatabase

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


def _build_single_topic_response(topic_id: int, group_id: str, imported: str, comments_fetched: int, message: Optional[str] = None) -> dict:
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


def _build_pagination(page: int, per_page: int, total: int) -> dict:
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
    }


def _format_topic_row(topic) -> dict:
    return {
        "topic_id": topic[0],
        "title": topic[1],
        "create_time": topic[2],
        "likes_count": topic[3],
        "comments_count": topic[4],
        "reading_count": topic[5],
    }


def _format_group_topic_row(topic) -> dict:
    topic_data = {
        "topic_id": str(topic[0]) if topic[0] is not None else None,
        "title": topic[1],
        "create_time": topic[2],
        "likes_count": topic[3],
        "comments_count": topic[4],
        "reading_count": topic[5],
        "type": topic[6],
        "digested": bool(topic[7]) if topic[7] is not None else False,
        "sticky": bool(topic[8]) if topic[8] is not None else False,
        "imported_at": topic[15] if len(topic) > 15 else None,
    }

    if topic[6] == "q&a":
        topic_data["question_text"] = topic[9] if topic[9] else ""
        topic_data["answer_text"] = topic[10] if topic[10] else ""
    else:
        topic_data["talk_text"] = topic[11] if topic[11] else ""
        if topic[12]:
            topic_data["author"] = {
                "user_id": topic[12],
                "name": topic[13],
                "avatar_url": topic[14],
            }

    return topic_data


def _build_topics_query(page: int, per_page: int, search: Optional[str]) -> tuple[str, tuple, str, tuple]:
    offset = (page - 1) * per_page
    if search:
        search_param = f"%{search}%"
        return (
            """
            SELECT topic_id, title, create_time, likes_count, comments_count, reading_count
            FROM topics
            WHERE title LIKE ?
            ORDER BY create_time DESC
            LIMIT ? OFFSET ?
            """,
            (search_param, per_page, offset),
            "SELECT COUNT(*) FROM topics WHERE title LIKE ?",
            (search_param,),
        )

    return (
        """
        SELECT topic_id, title, create_time, likes_count, comments_count, reading_count
        FROM topics
        ORDER BY create_time DESC
        LIMIT ? OFFSET ?
        """,
        (per_page, offset),
        "SELECT COUNT(*) FROM topics",
        (),
    )


def _build_group_topics_query(group_id: int, page: int, per_page: int, search: Optional[str]) -> tuple[str, tuple, str, tuple]:
    offset = (page - 1) * per_page
    base_select = """
        SELECT
            t.topic_id, t.title, t.create_time, t.likes_count, t.comments_count,
            t.reading_count, t.type, t.digested, t.sticky,
            q.text as question_text,
            a.text as answer_text,
            tk.text as talk_text,
            u.user_id, u.name, u.avatar_url, t.imported_at
        FROM topics t
        LEFT JOIN questions q ON t.topic_id = q.topic_id
        LEFT JOIN answers a ON t.topic_id = a.topic_id
        LEFT JOIN talks tk ON t.topic_id = tk.topic_id
        LEFT JOIN users u ON tk.owner_user_id = u.user_id
    """

    if search:
        search_param = f"%{search}%"
        return (
            f"""
            {base_select}
            WHERE t.group_id = ? AND (t.title LIKE ? OR q.text LIKE ? OR tk.text LIKE ?)
            ORDER BY t.create_time DESC
            LIMIT ? OFFSET ?
            """,
            (group_id, search_param, search_param, search_param, per_page, offset),
            "SELECT COUNT(*) FROM topics WHERE group_id = ? AND title LIKE ?",
            (group_id, search_param),
        )

    return (
        f"""
        {base_select}
        WHERE t.group_id = ?
        ORDER BY t.create_time DESC
        LIMIT ? OFFSET ?
        """,
        (group_id, per_page, offset),
        "SELECT COUNT(*) FROM topics WHERE group_id = ?",
        (group_id,),
    )


def _fetch_rows_and_total(cursor, query: str, params: tuple, count_query: str, count_params: tuple) -> tuple[list, int]:
    cursor.execute(query, params)
    rows = cursor.fetchall()

    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]

    return rows, total


def _build_topic_page_response(
    cursor,
    query: str,
    params: tuple,
    count_query: str,
    count_params: tuple,
    formatter,
    page: int,
    per_page: int,
) -> dict:
    topics, total = _fetch_rows_and_total(cursor, query, params, count_query, count_params)
    return {
        "topics": [formatter(topic) for topic in topics],
        "pagination": _build_pagination(page, per_page, total),
    }


def _get_topics_response(page: int = 1, per_page: int = 20, search: Optional[str] = None) -> dict:
    db = None
    try:
        db = ZSXQDatabase()

        query, params, count_query, count_params = _build_topics_query(page, per_page, search)
        return _build_topic_page_response(
            db.cursor,
            query,
            params,
            count_query,
            count_params,
            _format_topic_row,
            page,
            per_page,
        )
    finally:
        _close_topic_db(db)


def _get_group_topics_response(group_id: int, page: int = 1, per_page: int = 20, search: Optional[str] = None) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))

        query, params, count_query, count_params = _build_group_topics_query(group_id, page, per_page, search)
        return _build_topic_page_response(
            db.cursor,
            query,
            params,
            count_query,
            count_params,
            _format_group_topic_row,
            page,
            per_page,
        )
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
        db.cursor.execute(
            "SELECT COUNT(*) FROM topics WHERE topic_id = ? AND group_id = ?",
            (topic_id, group_id),
        )
        exists = db.cursor.fetchone()[0] > 0
        if not exists:
            return {"success": False, "message": "话题不存在"}

        deleted = _delete_single_topic_rows(db, topic_id, group_id)
        db.conn.commit()

        return {"success": True, "deleted_topic_id": topic_id, "deleted": deleted}
    except Exception:
        _rollback_topic_db(db)
        raise
    finally:
        _close_topic_db(db)


def _fetch_single_topic_response(group_id: str, topic_id: int, fetch_comments: bool = True) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))
        client = OfficialTopicClient()

        db.cursor.execute(
            "SELECT 1 FROM topics WHERE topic_id = ? AND group_id = ? LIMIT 1",
            (topic_id, _query_group_id(group_id)),
        )
        if db.cursor.fetchone():
            return _build_single_topic_response(topic_id, group_id, "skipped", 0, "话题已存在，跳过采集")

        topic = official_payload_topic(client.get_topic_info(topic_id))
        if not topic:
            raise HTTPException(status_code=404, detail="未获取到有效话题数据")

        _validate_topic_group(topic, group_id)

        topic_data = normalize_official_topic(topic, group_id)

        comments_fetched = 0
        if fetch_comments:
            comments_count = topic_data.get("comments_count", 0) or 0
            comments = client.get_topic_comments(topic_id) if comments_count > 0 else []
            if comments:
                topic_data["show_comments"] = comments
                comments_fetched = len(comments)

        db.import_topic_data(topic_data)
        db.conn.commit()

        return _build_single_topic_response(topic_id, group_id, "created", comments_fetched)
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
        db.cursor.execute(
            "SELECT COUNT(*) FROM tags WHERE tag_id = ? AND group_id = ?",
            (tag_id, group_id),
        )
        tag_count = db.cursor.fetchone()[0]

        if tag_count == 0:
            raise HTTPException(status_code=404, detail="标签在该群组中不存在")

        return db.get_topics_by_tag(tag_id, page, per_page)
    finally:
        _close_topic_db(db)


def _delete_group_topics_response(group_id: int) -> dict:
    db = None
    try:
        db = ZSXQDatabase(str(group_id))
        db.cursor.execute("SELECT COUNT(*) FROM topics WHERE group_id = ?", (group_id,))
        topics_count = db.cursor.fetchone()[0]

        if topics_count == 0:
            return {"message": "该群组没有话题数据", "deleted_count": 0}

        deleted_counts = _delete_group_topic_rows(db, group_id)
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
    return await asyncio.to_thread(_fetch_single_topic_response, group_id, topic_id, fetch_comments)


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
