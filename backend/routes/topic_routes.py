from __future__ import annotations

import gc
import json
import os
import time
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException

from backend.core.crawler_runtime import get_crawler, get_crawler_for_group
from backend.storage.db_compat import connect

router = APIRouter(prefix="/api", tags=["topics"])


def _log_topic_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")

TOPIC_DETAIL_TABLES = [
    "user_liked_emojis",
    "like_emojis",
    "likes",
    "images",
    "comments",
    "answers",
    "questions",
    "articles",
    "talks",
    "topic_files",
    "topic_tags",
]

GROUP_TOPIC_TABLES = [(table, "topic_id") for table in TOPIC_DETAIL_TABLES] + [("topics", "group_id")]


def _close_crawler_databases(crawler) -> None:
    if hasattr(crawler, "db") and crawler.db:
        crawler.db.close()
    if hasattr(crawler, "file_downloader") and crawler.file_downloader:
        if hasattr(crawler.file_downloader, "file_db") and crawler.file_downloader.file_db:
            crawler.file_downloader.file_db.close()


def _rollback_crawler_db(crawler) -> None:
    try:
        if crawler and hasattr(crawler, "db") and crawler.db:
            crawler.db.conn.rollback()
    except Exception:
        pass


def _delete_single_topic_rows(db, topic_id: int, group_id: int) -> bool:
    for table in TOPIC_DETAIL_TABLES:
        db.cursor.execute(f"DELETE FROM {table} WHERE topic_id = ?", (topic_id,))

    db.cursor.execute("DELETE FROM topics WHERE topic_id = ? AND group_id = ?", (topic_id, group_id))
    return db.cursor.rowcount > 0


def _delete_group_topic_rows(db, group_id: int) -> dict:
    deleted_counts = {}

    for table, id_column in GROUP_TOPIC_TABLES:
        if id_column == "group_id":
            db.cursor.execute(f"DELETE FROM {table} WHERE {id_column} = ?", (group_id,))
        else:
            db.cursor.execute(
                f"""
                DELETE FROM {table}
                WHERE {id_column} IN (
                    SELECT topic_id FROM topics WHERE group_id = ?
                )
                """,
                (group_id,),
            )

        deleted_counts[table] = db.cursor.rowcount

    return deleted_counts


def _clear_group_topic_data(group_id: str) -> dict:
    conn = connect()
    try:
        db = type("_TopicClearDb", (), {})()
        db.cursor = conn.cursor()
        deleted_counts = _delete_group_topic_rows(db, int(group_id))
        conn.commit()
        return deleted_counts
    finally:
        conn.close()


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


def _fetch_and_import_topic_comments(crawler, topic_id: int, comments_count: int) -> int:
    if comments_count <= 0:
        return 0

    try:
        additional_comments = crawler.fetch_all_comments(topic_id, comments_count)
        if additional_comments:
            crawler.db.import_additional_comments(topic_id, additional_comments)
            crawler.db.conn.commit()
            return len(additional_comments)
    except Exception as e:
        _log_topic_event("WARN", f"单话题评论获取失败: {e}")

    return 0


def _build_refresh_topic_failure(message: str) -> dict:
    return {"success": False, "message": message}


def _parse_refresh_topic_response(response) -> tuple[Optional[dict], Optional[dict]]:
    if response.status_code != 200:
        return None, _build_refresh_topic_failure(f"API请求失败: {response.status_code}")

    data = response.json()
    if data.get("succeeded") and data.get("resp_data"):
        return data["resp_data"]["topic"], None

    return None, _build_refresh_topic_failure("API返回数据格式错误")


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


def _import_more_comments(crawler, topic_id: int, comments_count: int) -> int:
    additional_comments = crawler.fetch_all_comments(topic_id, comments_count)
    if not additional_comments:
        return 0

    crawler.db.import_additional_comments(topic_id, additional_comments)
    crawler.db.conn.commit()
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


@router.get("/topics")
async def get_topics(page: int = 1, per_page: int = 20, search: Optional[str] = None):
    """获取话题列表"""
    try:
        crawler = get_crawler()

        query, params, count_query, count_params = _build_topics_query(page, per_page, search)
        topics, total = _fetch_rows_and_total(crawler.db.cursor, query, params, count_query, count_params)

        return {
            "topics": [_format_topic_row(topic) for topic in topics],
            "pagination": _build_pagination(page, per_page, total),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取话题列表失败: {str(e)}")


@router.get("/groups/{group_id}/topics")
async def get_group_topics(group_id: int, page: int = 1, per_page: int = 20, search: Optional[str] = None):
    """获取指定群组的话题列表"""
    try:
        crawler = get_crawler_for_group(str(group_id))

        query, params, count_query, count_params = _build_group_topics_query(group_id, page, per_page, search)
        topics, total = _fetch_rows_and_total(crawler.db.cursor, query, params, count_query, count_params)

        return {
            "topics": [_format_group_topic_row(topic) for topic in topics],
            "pagination": _build_pagination(page, per_page, total),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取群组话题失败: {str(e)}")


@router.post("/topics/clear/{group_id}")
async def clear_topic_database(group_id: str):
    """删除指定群组的 PostgreSQL 话题数据"""
    try:
        try:
            crawler = get_crawler_for_group(group_id)
            _close_crawler_databases(crawler)
            _log_topic_event("INFO", "已关闭爬虫实例的数据库连接")
        except Exception as e:
            _log_topic_event("WARN", f"关闭爬虫数据库连接时出错: {e}")

        gc.collect()
        time.sleep(0.1)

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
    except HTTPException:
        raise
    except Exception as e:
        _log_topic_event("ERROR", f"删除话题数据库失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除话题数据库失败: {str(e)}")


@router.get("/topics/{topic_id}/{group_id}")
async def get_topic_detail(topic_id: int, group_id: str):
    """获取话题详情（仅从本地数据库读取，不主动爬取）"""
    try:
        crawler = get_crawler_for_group(group_id)
        topic_detail = crawler.db.get_topic_detail(topic_id)

        if not topic_detail:
            raise HTTPException(status_code=404, detail="话题不存在")

        return topic_detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取话题详情失败: {str(e)}")


@router.post("/topics/{topic_id}/{group_id}/refresh")
async def refresh_topic(topic_id: int, group_id: str):
    """实时更新单个话题信息"""
    try:
        crawler = get_crawler_for_group(group_id)

        url = f"https://api.zsxq.com/v2/topics/{topic_id}/info"
        headers = crawler.get_stealth_headers()
        response = requests.get(url, headers=headers, timeout=30)

        topic_data, error_response = _parse_refresh_topic_response(response)
        if error_response:
            return error_response

        success = crawler.db.update_topic_stats(topic_data)
        if not success:
            return _build_refresh_topic_failure("话题不存在或更新失败")

        crawler.db.conn.commit()
        return _build_refresh_topic_success(topic_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新话题失败: {str(e)}")


@router.post("/topics/{topic_id}/{group_id}/fetch-comments")
async def fetch_more_comments(topic_id: int, group_id: str):
    """手动获取话题的更多评论（在已存在本地话题记录的前提下）"""
    try:
        crawler = get_crawler_for_group(group_id)
        topic_detail = crawler.db.get_topic_detail(topic_id)
        if not topic_detail:
            raise HTTPException(status_code=404, detail="话题不存在")

        comments_count = topic_detail.get("comments_count", 0)
        if not _should_fetch_more_comments(comments_count):
            return _build_fetch_comments_skip_response(comments_count)

        try:
            comments_fetched = _import_more_comments(crawler, topic_id, comments_count)
            if comments_fetched:
                return _build_fetch_comments_response(
                    True,
                    f"成功获取并导入 {comments_fetched} 条评论",
                    comments_fetched,
                )
            return _build_fetch_comments_response(False, "获取评论失败，可能是权限限制或网络问题", 0)
        except Exception as e:
            return _build_fetch_comments_response(False, f"获取评论时出错: {str(e)}", 0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取更多评论失败: {str(e)}")


@router.delete("/topics/{topic_id}/{group_id}")
async def delete_single_topic(topic_id: int, group_id: int):
    """删除单个话题及其所有关联数据"""
    crawler = None
    try:
        crawler = get_crawler_for_group(str(group_id))
        crawler.db.cursor.execute(
            "SELECT COUNT(*) FROM topics WHERE topic_id = ? AND group_id = ?",
            (topic_id, group_id),
        )
        exists = crawler.db.cursor.fetchone()[0] > 0
        if not exists:
            return {"success": False, "message": "话题不存在"}

        deleted = _delete_single_topic_rows(crawler.db, topic_id, group_id)
        crawler.db.conn.commit()

        return {"success": True, "deleted_topic_id": topic_id, "deleted": deleted}
    except Exception as e:
        _rollback_crawler_db(crawler)
        raise HTTPException(status_code=500, detail=f"删除话题失败: {str(e)}")


@router.post("/topics/fetch-single/{group_id}/{topic_id}")
async def fetch_single_topic(group_id: str, topic_id: int, fetch_comments: bool = True):
    """爬取并导入单个话题（用于特殊话题测试），可选拉取完整评论"""
    try:
        crawler = get_crawler_for_group(str(group_id))

        crawler.db.cursor.execute(
            "SELECT 1 FROM topics WHERE topic_id = ? AND group_id = ? LIMIT 1",
            (topic_id, group_id),
        )
        if crawler.db.cursor.fetchone():
            return _build_single_topic_response(topic_id, group_id, "skipped", 0, "话题已存在，跳过采集")

        url = f"https://api.zsxq.com/v2/topics/{topic_id}/info"
        headers = crawler.get_stealth_headers()
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="API请求失败")

        data = response.json()
        if not data.get("succeeded") or not data.get("resp_data"):
            raise HTTPException(status_code=400, detail="API返回失败")

        topic = (data.get("resp_data", {}) or {}).get("topic", {}) or {}
        if not topic:
            raise HTTPException(status_code=404, detail="未获取到有效话题数据")

        _validate_topic_group(topic, group_id)

        crawler.db.import_topic_data(topic)
        crawler.db.conn.commit()

        comments_fetched = 0
        if fetch_comments:
            comments_count = topic.get("comments_count", 0) or 0
            comments_fetched = _fetch_and_import_topic_comments(crawler, topic_id, comments_count)

        return _build_single_topic_response(topic_id, group_id, "created", comments_fetched)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"单个话题采集失败: {str(e)}")


@router.get("/groups/{group_id}/tags")
async def get_group_tags(group_id: str):
    """获取指定群组的所有标签"""
    try:
        crawler = get_crawler_for_group(group_id)
        tags = crawler.db.get_tags_by_group(int(group_id))
        return {"tags": tags, "total": len(tags)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取标签列表失败: {str(e)}")


@router.get("/groups/{group_id}/tags/{tag_id}/topics")
async def get_topics_by_tag(group_id: int, tag_id: int, page: int = 1, per_page: int = 20):
    """根据标签获取指定群组的话题列表"""
    try:
        crawler = get_crawler_for_group(str(group_id))
        crawler.db.cursor.execute(
            "SELECT COUNT(*) FROM tags WHERE tag_id = ? AND group_id = ?",
            (tag_id, group_id),
        )
        tag_count = crawler.db.cursor.fetchone()[0]

        if tag_count == 0:
            raise HTTPException(status_code=404, detail="标签在该群组中不存在")

        result = crawler.db.get_topics_by_tag(tag_id, page, per_page)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"根据标签获取话题失败: {str(e)}")


@router.delete("/groups/{group_id}/topics")
async def delete_group_topics(group_id: int):
    """删除指定群组的所有话题数据"""
    crawler = None
    try:
        crawler = get_crawler_for_group(str(group_id))
        crawler.db.cursor.execute("SELECT COUNT(*) FROM topics WHERE group_id = ?", (group_id,))
        topics_count = crawler.db.cursor.fetchone()[0]

        if topics_count == 0:
            return {"message": "该群组没有话题数据", "deleted_count": 0}

        deleted_counts = _delete_group_topic_rows(crawler.db, group_id)
        crawler.db.conn.commit()

        return {
            "message": f"成功删除群组 {group_id} 的所有话题数据",
            "deleted_topics_count": topics_count,
            "deleted_details": deleted_counts,
        }
    except Exception as e:
        _rollback_crawler_db(crawler)
        raise HTTPException(status_code=500, detail=f"删除话题数据失败: {str(e)}")
