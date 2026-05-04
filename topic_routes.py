from __future__ import annotations

import gc
import json
import os
import sys
import time
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["topics"])


def _main_module():
    return sys.modules.get("main") or sys.modules.get("__main__")


def _get_main_attr(name: str):
    module = _main_module()
    if module is None or not hasattr(module, name):
        raise RuntimeError(f"主模块未初始化，无法访问 {name}")
    return getattr(module, name)


@router.get("/topics")
async def get_topics(page: int = 1, per_page: int = 20, search: Optional[str] = None):
    """获取话题列表"""
    try:
        crawler = _get_main_attr("get_crawler")()

        offset = (page - 1) * per_page

        if search:
            query = """
                SELECT topic_id, title, create_time, likes_count, comments_count, reading_count
                FROM topics
                WHERE title LIKE ?
                ORDER BY create_time DESC
                LIMIT ? OFFSET ?
            """
            params = (f"%{search}%", per_page, offset)
        else:
            query = """
                SELECT topic_id, title, create_time, likes_count, comments_count, reading_count
                FROM topics
                ORDER BY create_time DESC
                LIMIT ? OFFSET ?
            """
            params = (per_page, offset)

        crawler.db.cursor.execute(query, params)
        topics = crawler.db.cursor.fetchall()

        if search:
            crawler.db.cursor.execute("SELECT COUNT(*) FROM topics WHERE title LIKE ?", (f"%{search}%",))
        else:
            crawler.db.cursor.execute("SELECT COUNT(*) FROM topics")
        total = crawler.db.cursor.fetchone()[0]

        return {
            "topics": [
                {
                    "topic_id": topic[0],
                    "title": topic[1],
                    "create_time": topic[2],
                    "likes_count": topic[3],
                    "comments_count": topic[4],
                    "reading_count": topic[5],
                }
                for topic in topics
            ],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取话题列表失败: {str(e)}")


@router.get("/groups/{group_id}/topics")
async def get_group_topics(group_id: int, page: int = 1, per_page: int = 20, search: Optional[str] = None):
    """获取指定群组的话题列表"""
    try:
        crawler = _get_main_attr("get_crawler_for_group")(str(group_id))

        try:
            db_path = getattr(getattr(crawler, "db", None), "db_path", None)
            print(f"[DEBUG get_group_topics] group_id={group_id}, db_path={db_path}, page={page}, per_page={per_page}")
        except Exception as e:
            print(f"[DEBUG get_group_topics] failed to print db_path: {e}")

        offset = (page - 1) * per_page

        if search:
            query = """
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
                WHERE t.group_id = ? AND (t.title LIKE ? OR q.text LIKE ? OR tk.text LIKE ?)
                ORDER BY t.create_time DESC
                LIMIT ? OFFSET ?
            """
            params = (group_id, f"%{search}%", f"%{search}%", f"%{search}%", per_page, offset)
        else:
            query = """
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
                WHERE t.group_id = ?
                ORDER BY t.create_time DESC
                LIMIT ? OFFSET ?
            """
            params = (group_id, per_page, offset)

        crawler.db.cursor.execute(query, params)
        topics = crawler.db.cursor.fetchall()

        try:
            debug_rows = topics[:10]
            debug_list = [(row[0], row[1]) for row in debug_rows]
            print(f"[DEBUG get_group_topics] first topics from DB (topic_id, title): {debug_list}")

            for row in debug_rows:
                title = row[1] or ""
                if isinstance(title, str) and title.startswith("Offer选择"):
                    print(f"[DEBUG get_group_topics] Offer topic row from DB: topic_id={row[0]}, title={title}")
        except Exception as e:
            print(f"[DEBUG get_group_topics] failed to debug topics: {e}")

        if search:
            crawler.db.cursor.execute("SELECT COUNT(*) FROM topics WHERE group_id = ? AND title LIKE ?", (group_id, f"%{search}%"))
        else:
            crawler.db.cursor.execute("SELECT COUNT(*) FROM topics WHERE group_id = ?", (group_id,))
        total = crawler.db.cursor.fetchone()[0]

        topics_list = []
        for topic in topics:
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

            topics_list.append(topic_data)

        return {
            "topics": topics_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取群组话题失败: {str(e)}")


@router.post("/topics/clear/{group_id}")
async def clear_topic_database(group_id: str):
    """删除指定群组的话题数据库文件"""
    try:
        path_manager = _get_main_attr("get_db_path_manager")()
        db_path = path_manager.get_topics_db_path(group_id)

        print(f"🗑️ 尝试删除话题数据库: {db_path}")

        if os.path.exists(db_path):
            try:
                crawler = _get_main_attr("get_crawler_for_group")(group_id)
                if hasattr(crawler, "db") and crawler.db:
                    crawler.db.close()
                if hasattr(crawler, "file_downloader") and crawler.file_downloader:
                    if hasattr(crawler.file_downloader, "file_db") and crawler.file_downloader.file_db:
                        crawler.file_downloader.file_db.close()
                print("✅ 已关闭爬虫实例的数据库连接")
            except Exception as e:
                print(f"⚠️ 关闭爬虫数据库连接时出错: {e}")

            gc.collect()
            time.sleep(0.5)

            try:
                os.remove(db_path)
                print(f"✅ 话题数据库已删除: {db_path}")

                try:
                    from image_cache_manager import clear_group_cache_manager, get_image_cache_manager

                    cache_manager = get_image_cache_manager(group_id)
                    success, message = cache_manager.clear_cache()
                    if success:
                        print(f"✅ 图片缓存已清空: {message}")
                    else:
                        print(f"⚠️ 清空图片缓存失败: {message}")
                    clear_group_cache_manager(group_id)
                except Exception as cache_error:
                    print(f"⚠️ 清空图片缓存时出错: {cache_error}")

                return {"message": f"群组 {group_id} 的话题数据库和图片缓存已删除"}
            except PermissionError as pe:
                print(f"❌ 文件被占用，无法删除: {pe}")
                raise HTTPException(status_code=500, detail="文件被占用，无法删除数据库文件。请稍后重试。")
        else:
            print(f"ℹ️ 话题数据库不存在: {db_path}")
            return {"message": f"群组 {group_id} 的话题数据库不存在"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 删除话题数据库失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除话题数据库失败: {str(e)}")


@router.get("/topics/{topic_id}/{group_id}")
async def get_topic_detail(topic_id: int, group_id: str):
    """获取话题详情（仅从本地数据库读取，不主动爬取）"""
    try:
        crawler = _get_main_attr("get_crawler_for_group")(group_id)
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
        crawler = _get_main_attr("get_crawler_for_group")(group_id)

        url = f"https://api.zsxq.com/v2/topics/{topic_id}/info"
        headers = crawler.get_stealth_headers()
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()
            if data.get("succeeded") and data.get("resp_data"):
                topic_data = data["resp_data"]["topic"]
                success = crawler.db.update_topic_stats(topic_data)
                if not success:
                    return {"success": False, "message": "话题不存在或更新失败"}

                crawler.db.conn.commit()
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
            return {"success": False, "message": "API返回数据格式错误"}
        return {"success": False, "message": f"API请求失败: {response.status_code}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新话题失败: {str(e)}")


@router.post("/topics/{topic_id}/{group_id}/fetch-comments")
async def fetch_more_comments(topic_id: int, group_id: str):
    """手动获取话题的更多评论（在已存在本地话题记录的前提下）"""
    try:
        crawler = _get_main_attr("get_crawler_for_group")(group_id)
        topic_detail = crawler.db.get_topic_detail(topic_id)
        if not topic_detail:
            raise HTTPException(status_code=404, detail="话题不存在")

        comments_count = topic_detail.get("comments_count", 0)
        if comments_count <= 8:
            return {
                "success": True,
                "message": f"话题只有 {comments_count} 条评论，无需获取更多",
                "comments_fetched": 0,
            }

        try:
            additional_comments = crawler.fetch_all_comments(topic_id, comments_count)
            if additional_comments:
                crawler.db.import_additional_comments(topic_id, additional_comments)
                crawler.db.conn.commit()
                return {
                    "success": True,
                    "message": f"成功获取并导入 {len(additional_comments)} 条评论",
                    "comments_fetched": len(additional_comments),
                }
            return {
                "success": False,
                "message": "获取评论失败，可能是权限限制或网络问题",
                "comments_fetched": 0,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"获取评论时出错: {str(e)}",
                "comments_fetched": 0,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取更多评论失败: {str(e)}")


@router.delete("/topics/{topic_id}/{group_id}")
async def delete_single_topic(topic_id: int, group_id: int):
    """删除单个话题及其所有关联数据"""
    crawler = None
    try:
        crawler = _get_main_attr("get_crawler_for_group")(str(group_id))
        crawler.db.cursor.execute(
            "SELECT COUNT(*) FROM topics WHERE topic_id = ? AND group_id = ?",
            (topic_id, group_id),
        )
        exists = crawler.db.cursor.fetchone()[0] > 0
        if not exists:
            return {"success": False, "message": "话题不存在"}

        tables_to_clean = [
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

        for table in tables_to_clean:
            crawler.db.cursor.execute(f"DELETE FROM {table} WHERE topic_id = ?", (topic_id,))

        crawler.db.cursor.execute("DELETE FROM topics WHERE topic_id = ? AND group_id = ?", (topic_id, group_id))

        deleted = crawler.db.cursor.rowcount
        crawler.db.conn.commit()

        return {"success": True, "deleted_topic_id": topic_id, "deleted": deleted > 0}
    except Exception as e:
        try:
            if crawler and hasattr(crawler, "db") and crawler.db:
                crawler.db.conn.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"删除话题失败: {str(e)}")


@router.post("/topics/fetch-single/{group_id}/{topic_id}")
async def fetch_single_topic(group_id: str, topic_id: int, fetch_comments: bool = True):
    """爬取并导入单个话题（用于特殊话题测试），可选拉取完整评论"""
    try:
        crawler = _get_main_attr("get_crawler_for_group")(str(group_id))

        crawler.db.cursor.execute(
            "SELECT 1 FROM topics WHERE topic_id = ? AND group_id = ? LIMIT 1",
            (topic_id, group_id),
        )
        if crawler.db.cursor.fetchone():
            return {
                "success": True,
                "topic_id": topic_id,
                "group_id": int(group_id),
                "imported": "skipped",
                "message": "话题已存在，跳过采集",
                "comments_fetched": 0,
            }

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

        topic_group_id = str((topic.get("group") or {}).get("group_id", ""))
        if topic_group_id and topic_group_id != str(group_id):
            raise HTTPException(status_code=400, detail="该话题不属于当前群组")

        crawler.db.import_topic_data(topic)
        crawler.db.conn.commit()

        comments_fetched = 0
        if fetch_comments:
            comments_count = topic.get("comments_count", 0) or 0
            if comments_count > 0:
                try:
                    additional_comments = crawler.fetch_all_comments(topic_id, comments_count)
                    if additional_comments:
                        crawler.db.import_additional_comments(topic_id, additional_comments)
                        crawler.db.conn.commit()
                        comments_fetched = len(additional_comments)
                except Exception as e:
                    print(f"⚠️ 单话题评论获取失败: {e}")

        return {
            "success": True,
            "topic_id": topic_id,
            "group_id": int(group_id),
            "imported": "created",
            "comments_fetched": comments_fetched,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"单个话题采集失败: {str(e)}")


@router.get("/groups/{group_id}/tags")
async def get_group_tags(group_id: str):
    """获取指定群组的所有标签"""
    try:
        crawler = _get_main_attr("get_crawler_for_group")(group_id)
        tags = crawler.db.get_tags_by_group(int(group_id))
        return {"tags": tags, "total": len(tags)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取标签列表失败: {str(e)}")


@router.get("/groups/{group_id}/tags/{tag_id}/topics")
async def get_topics_by_tag(group_id: int, tag_id: int, page: int = 1, per_page: int = 20):
    """根据标签获取指定群组的话题列表"""
    try:
        crawler = _get_main_attr("get_crawler_for_group")(str(group_id))
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
    try:
        crawler = _get_main_attr("get_crawler_for_group")(str(group_id))
        crawler.db.cursor.execute("SELECT COUNT(*) FROM topics WHERE group_id = ?", (group_id,))
        topics_count = crawler.db.cursor.fetchone()[0]

        if topics_count == 0:
            return {"message": "该群组没有话题数据", "deleted_count": 0}

        tables_to_clean = [
            ("user_liked_emojis", "topic_id"),
            ("like_emojis", "topic_id"),
            ("likes", "topic_id"),
            ("images", "topic_id"),
            ("comments", "topic_id"),
            ("answers", "topic_id"),
            ("questions", "topic_id"),
            ("articles", "topic_id"),
            ("talks", "topic_id"),
            ("topic_files", "topic_id"),
            ("topic_tags", "topic_id"),
            ("topics", "group_id"),
        ]

        deleted_counts = {}

        for table, id_column in tables_to_clean:
            if id_column == "group_id":
                crawler.db.cursor.execute(f"DELETE FROM {table} WHERE {id_column} = ?", (group_id,))
            else:
                crawler.db.cursor.execute(
                    f"""
                    DELETE FROM {table}
                    WHERE {id_column} IN (
                        SELECT topic_id FROM topics WHERE group_id = ?
                    )
                    """,
                    (group_id,),
                )

            deleted_counts[table] = crawler.db.cursor.rowcount

        crawler.db.conn.commit()

        return {
            "message": f"成功删除群组 {group_id} 的所有话题数据",
            "deleted_topics_count": topics_count,
            "deleted_details": deleted_counts,
        }
    except Exception as e:
        crawler = _get_main_attr("get_crawler_for_group")(str(group_id))
        crawler.db.conn.rollback()
        raise HTTPException(status_code=500, detail=f"删除话题数据失败: {str(e)}")
