"""Small row and parameter helpers for ZSXQ topic storage."""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, Optional

from backend.storage.zsxq_database_scope import group_id_param, nullable_group_id_param
from backend.storage.zsxq_database_stats_queries import (
    database_stats_count_query,
    group_stats_queries,
    local_group_topic_count_query,
    local_group_topic_time_range_query,
    newest_topic_create_time_query,
    oldest_topic_create_time_query,
    topic_count_query,
)
from backend.storage.zsxq_database_write_statements import (
    answer_insert_statement,
    article_insert_statement,
    comment_insert_statement,
    delete_latest_likes_statement,
    group_insert_statement,
    image_insert_statement,
    insert_tag_statement,
    insert_topic_tag_statement,
    latest_like_insert_statement,
    like_emoji_insert_statement,
    like_insert_statement,
    like_insert_statement_pair,
    question_insert_statement,
    refresh_tag_topic_count_statement,
    talk_insert_statement,
    topic_file_insert_statement,
    topic_insert_statement,
    topic_stats_update_statement,
    update_tag_hid_statement,
    user_insert_statement,
    user_liked_emoji_insert_statement,
)
from backend.storage.topic_detail_payloads import (
    build_topic_detail_comments,
    build_topic_detail_latest_likes,
    build_topic_detail_likes_detail,
    build_topic_detail_qa,
    build_topic_detail_talk,
    load_topic_comment_images_map,
    load_topic_detail_base,
    load_topic_detail_comments,
    load_topic_detail_latest_likes,
    load_topic_detail_likes_detail,
    load_topic_detail_qa,
    load_topic_detail_talk,
    load_topic_detail_talk_payload,
    topic_detail_answer_payload,
    topic_detail_article_payload,
    topic_detail_base_payload,
    topic_detail_comment_payload,
    topic_detail_emoji_payload,
    topic_detail_file_payload,
    topic_detail_image_payload,
    topic_detail_like_payload,
    topic_detail_question_payload,
    topic_detail_talk_payload,
)


def beijing_now_timestamp() -> str:
    beijing_tz = timezone(timedelta(hours=8))
    return datetime.now(beijing_tz).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"


def build_pagination(page: int, per_page: int, total: int) -> Dict[str, int]:
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
    }


def iter_topic_user_payloads_from_data(topic_data: Dict[str, Any]) -> Iterator[Any]:
    if "talk" in topic_data and topic_data["talk"] and "owner" in topic_data["talk"]:
        yield topic_data["talk"]["owner"]

    if "question" in topic_data and topic_data["question"]:
        if "owner" in topic_data["question"] and not topic_data["question"].get("anonymous", False):
            yield topic_data["question"]["owner"]
        if "questionee" in topic_data["question"]:
            yield topic_data["question"]["questionee"]

    if "answer" in topic_data and topic_data["answer"] and "owner" in topic_data["answer"]:
        yield topic_data["answer"]["owner"]

    if "latest_likes" in topic_data:
        for like in topic_data["latest_likes"]:
            if "owner" in like:
                yield like["owner"]

    if "show_comments" in topic_data:
        for comment in topic_data["show_comments"]:
            if "owner" in comment:
                yield comment["owner"]
            if "repliee" in comment:
                yield comment["repliee"]


def topic_image_payloads_from_data(topic_data: Dict[str, Any]) -> list[tuple[Any, Optional[Any]]]:
    images_to_import = []

    if "talk" in topic_data and topic_data["talk"] and "images" in topic_data["talk"]:
        for img in topic_data["talk"]["images"]:
            images_to_import.append((img, None))

    if "show_comments" in topic_data:
        for comment in topic_data["show_comments"]:
            if "images" in comment:
                comment_id = comment.get("comment_id")
                for img in comment["images"]:
                    images_to_import.append((img, comment_id))

    return images_to_import


def iter_valid_like_emoji_payloads(emojis) -> Iterator[Any]:
    for emoji in emojis:
        if emoji.get("emoji_key"):
            yield emoji


def iter_valid_user_liked_emoji_keys(emoji_keys) -> Iterator[Any]:
    for emoji_key in emoji_keys:
        if emoji_key:
            yield emoji_key


def iter_valid_latest_like_payloads(latest_likes) -> Iterator[tuple[Any, Any]]:
    for like in latest_likes:
        owner = like.get("owner", {})
        user_id = owner.get("user_id")
        if user_id:
            yield like, user_id


def iter_valid_comment_image_payloads(images) -> Iterator[Any]:
    for image in images:
        if image.get("image_id"):
            yield image


def comment_image_batch_from_comment(comment) -> Optional[tuple[Any, Any]]:
    if "images" in comment and comment["images"]:
        return comment["comment_id"], comment["images"]
    return None


def iter_additional_comment_user_payloads(comment) -> Iterator[Any]:
    for key in ("owner", "repliee"):
        if key in comment and comment[key]:
            yield comment[key]


def format_tag_row(row) -> Dict[str, Any]:
    return {
        "tag_id": row[0],
        "tag_name": row[1],
        "hid": row[2],
        "topic_count": row[3],
        "created_at": row[4],
    }


def format_tag_topic_row(topic) -> Dict[str, Any]:
    topic_data = {
        "topic_id": topic[0],
        "title": topic[1],
        "create_time": topic[2],
        "likes_count": topic[3],
        "comments_count": topic[4],
        "reading_count": topic[5],
        "type": topic[6],
        "digested": bool(topic[7]) if topic[7] is not None else False,
        "sticky": bool(topic[8]) if topic[8] is not None else False,
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


def format_group_topic_row(topic) -> Dict[str, Any]:
    topic_data = format_tag_topic_row(topic)
    topic_data["topic_id"] = str(topic[0]) if topic[0] is not None else None
    topic_data["imported_at"] = topic[15] if len(topic) > 15 else None
    return topic_data


def format_topic_row(topic) -> Dict[str, Any]:
    return {
        "topic_id": topic[0],
        "title": topic[1],
        "create_time": topic[2],
        "likes_count": topic[3],
        "comments_count": topic[4],
        "reading_count": topic[5],
    }


def topic_tags_from_data(topic_data: Dict[str, Any]) -> set[tuple[str, str]]:
    text_contents = []

    if "talk" in topic_data and topic_data["talk"] and "text" in topic_data["talk"]:
        text_contents.append(topic_data["talk"]["text"])

    if "question" in topic_data and topic_data["question"] and "text" in topic_data["question"]:
        text_contents.append(topic_data["question"]["text"])

    if "answer" in topic_data and topic_data["answer"] and "text" in topic_data["answer"]:
        text_contents.append(topic_data["answer"]["text"])

    if "show_comments" in topic_data:
        for comment in topic_data["show_comments"]:
            if "text" in comment:
                text_contents.append(comment["text"])

    tags = set()
    for text in text_contents:
        if not text:
            continue

        tag_pattern = r'<e\s+type="hashtag"\s+hid="([^"]+)"\s+title="([^"]+)"\s*/>'
        matches = re.findall(tag_pattern, text)
        for hid, encoded_title in matches:
            try:
                tag_name = urllib.parse.unquote(encoded_title)
                tag_name = tag_name.strip("#")
                if tag_name:
                    tags.add((tag_name, hid))
            except Exception as e:
                print(f"解码标签失败: {e}")

    return tags


def tag_id_by_name_query(group_id: int, tag_name: str) -> tuple[str, tuple[Any, ...]]:
    return "SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?", (group_id, tag_name)


def tags_by_group_query(group_id: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                SELECT tag_id, tag_name, hid, topic_count, created_at
                FROM tags
                WHERE group_id = ?
                ORDER BY topic_count DESC, tag_name ASC
            """,
        (group_id,),
    )


def topics_by_tag_query(tag_id: int, per_page: int, offset: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                SELECT
                    t.topic_id, t.title, t.create_time, t.likes_count, t.comments_count,
                    t.reading_count, t.type, t.digested, t.sticky,
                    q.text as question_text,
                    a.text as answer_text,
                    tk.text as talk_text,
                    u.user_id, u.name, u.avatar_url
                FROM topics t
                INNER JOIN topic_tags tt ON t.topic_id = tt.topic_id
                LEFT JOIN questions q ON t.topic_id = q.topic_id
                LEFT JOIN answers a ON t.topic_id = a.topic_id
                LEFT JOIN talks tk ON t.topic_id = tk.topic_id
                LEFT JOIN users u ON tk.owner_user_id = u.user_id
                WHERE tt.tag_id = ?
                ORDER BY t.create_time DESC
                LIMIT ? OFFSET ?
            """,
        (tag_id, per_page, offset),
    )


def topic_count_by_tag_query(tag_id: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                SELECT COUNT(*)
                FROM topic_tags
                WHERE tag_id = ?
            """,
        (tag_id,),
    )


def tag_exists_in_group_query(group_id: Any, tag_id: int) -> tuple[str, tuple[Any, ...]]:
    return (
        "SELECT 1 FROM tags WHERE tag_id = ? AND group_id = ? LIMIT 1",
        (tag_id, group_id),
    )


def group_topics_by_tag_query(group_id: Any, tag_id: int, per_page: int, offset: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                SELECT
                    t.topic_id, t.title, t.create_time, t.likes_count, t.comments_count,
                    t.reading_count, t.type, t.digested, t.sticky,
                    q.text as question_text,
                    a.text as answer_text,
                    tk.text as talk_text,
                    u.user_id, u.name, u.avatar_url
                FROM topics t
                INNER JOIN topic_tags tt ON t.topic_id = tt.topic_id
                LEFT JOIN questions q ON t.topic_id = q.topic_id
                LEFT JOIN answers a ON t.topic_id = a.topic_id
                LEFT JOIN talks tk ON t.topic_id = tk.topic_id
                LEFT JOIN users u ON tk.owner_user_id = u.user_id
                WHERE tt.tag_id = ? AND t.group_id = ?
                ORDER BY t.create_time DESC
                LIMIT ? OFFSET ?
            """,
        (tag_id, group_id, per_page, offset),
    )


def group_topic_count_by_tag_query(group_id: Any, tag_id: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                SELECT COUNT(DISTINCT t.topic_id)
                FROM topics t
                INNER JOIN topic_tags tt ON t.topic_id = tt.topic_id
                WHERE tt.tag_id = ? AND t.group_id = ?
            """,
        (tag_id, group_id),
    )


def group_topics_query(group_id: Any, per_page: int, offset: int, search: Optional[str]) -> tuple[str, tuple[Any, ...]]:
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
        )

    return (
        f"""
                {base_select}
                WHERE t.group_id = ?
                ORDER BY t.create_time DESC
                LIMIT ? OFFSET ?
            """,
        (group_id, per_page, offset),
    )


def group_topics_count_query(group_id: Any, search: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    if search:
        search_param = f"%{search}%"
        return (
            """
                SELECT COUNT(DISTINCT t.topic_id)
                FROM topics t
                LEFT JOIN questions q ON t.topic_id = q.topic_id
                LEFT JOIN talks tk ON t.topic_id = tk.topic_id
                WHERE t.group_id = ? AND (t.title LIKE ? OR q.text LIKE ? OR tk.text LIKE ?)
            """,
            (group_id, search_param, search_param, search_param),
        )

    return (
        """
                SELECT COUNT(*)
                FROM topics
                WHERE group_id = ?
            """,
        (group_id,),
    )


def topics_query(per_page: int, offset: int, search: Optional[str]) -> tuple[str, tuple[Any, ...]]:
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
        )

    return (
        """
                SELECT topic_id, title, create_time, likes_count, comments_count, reading_count
                FROM topics
                ORDER BY create_time DESC
                LIMIT ? OFFSET ?
            """,
        (per_page, offset),
    )


def topics_count_query(search: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    if search:
        search_param = f"%{search}%"
        return "SELECT COUNT(*) FROM topics WHERE title LIKE ?", (search_param,)

    return "SELECT COUNT(*) FROM topics", ()


def topic_detail_scope(topic_id: int, group_id: Optional[str]) -> tuple[Any, str, list[Any]]:
    scoped_group_id = group_id_param(group_id) if group_id is not None else None
    topic_scope_sql = "t.topic_id = ?"
    topic_scope_params = [topic_id]
    if scoped_group_id is not None:
        topic_scope_sql += " AND t.group_id = ?"
        topic_scope_params.append(scoped_group_id)
    return scoped_group_id, topic_scope_sql, topic_scope_params


def topic_exists_query(topic_id: int, group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    scoped_group_id = group_id_param(group_id)
    return (
        "SELECT 1 FROM topics WHERE topic_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1",
        (topic_id, scoped_group_id, scoped_group_id),
    )


def file_exists_query(file_id: int, group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    scoped_group_id = group_id_param(group_id)
    return (
        "SELECT 1 FROM files WHERE file_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1",
        (file_id, scoped_group_id, scoped_group_id),
    )


def topic_group_id_query(topic_id: int) -> tuple[str, tuple[Any, ...]]:
    return "SELECT group_id FROM topics WHERE topic_id = ? LIMIT 1", (topic_id,)


def topic_create_time_by_id_query(topic_id: int) -> tuple[str, tuple[Any, ...]]:
    return "SELECT create_time FROM topics WHERE topic_id = ?", (topic_id,)


def local_group_record_query(group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    return (
        "SELECT name, type, background_url FROM groups WHERE group_id = ? LIMIT 1",
        (group_id_param(group_id),),
    )


def local_group_ids_query(limit: int) -> tuple[str, tuple[Any, ...]]:
    return "SELECT group_id FROM groups LIMIT ?", (int(limit),)


def replace_file_topic_relation(file_db, file_id: int, topic_id: int) -> int:
    file_db.cursor.execute(
        """
        DELETE FROM file_topic_relations
        WHERE file_id = ? AND topic_id = ?
        """,
        (file_id, topic_id),
    )
    file_db.cursor.execute(
        """
        INSERT INTO file_topic_relations (file_id, topic_id)
        VALUES (?, ?)
        ON CONFLICT(file_id, topic_id) DO NOTHING
        """,
        (file_id, topic_id),
    )
    return file_db.cursor.rowcount


def upsert_core_file(cursor, group_id: Optional[int], topic_id: int, file_data: Dict[str, Any]) -> Optional[int]:
    file_id = file_data.get("file_id")
    if not file_id:
        return None

    cursor.execute(
        """
        INSERT INTO files
        (file_id, group_id, topic_id, name, hash, size, duration, download_count, create_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_id) DO UPDATE SET
            group_id = COALESCE(excluded.group_id, files.group_id),
            topic_id = COALESCE(excluded.topic_id, files.topic_id),
            name = excluded.name,
            hash = excluded.hash,
            size = excluded.size,
            duration = excluded.duration,
            download_count = excluded.download_count,
            create_time = excluded.create_time
        """,
        (
            file_id,
            group_id,
            topic_id,
            file_data.get("name", ""),
            file_data.get("hash"),
            file_data.get("size"),
            file_data.get("duration"),
            file_data.get("download_count"),
            file_data.get("create_time"),
        ),
    )
    return file_id


def topic_files_backfill_query(group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    scoped_group_id = group_id_param(group_id)
    return (
        """
                SELECT
                    tf.topic_id, tf.file_id, tf.name, tf.hash, tf.size, tf.duration,
                    tf.download_count, tf.create_time,
                    t.group_id, t.type, t.title, t.annotation, t.create_time,
                    t.likes_count, t.tourist_likes_count, t.rewards_count,
                    t.comments_count, t.reading_count, t.readers_count,
                    t.digested, t.sticky, t.user_liked, t.user_subscribed,
                    g.name, g.type, g.background_url
                FROM topic_files tf
                LEFT JOIN topics t ON t.topic_id = tf.topic_id
                LEFT JOIN groups g ON g.group_id = t.group_id
                WHERE tf.file_id IS NOT NULL
                  AND (? IS NULL OR t.group_id = ?)
                ORDER BY tf.topic_id ASC, tf.file_id ASC
            """,
        (scoped_group_id, scoped_group_id),
    )


def topic_file_payload_from_row(row) -> Dict[str, Any]:
    return {
        "file_id": row[1],
        "name": row[2] or "",
        "hash": row[3],
        "size": row[4],
        "duration": row[5],
        "download_count": row[6],
        "create_time": row[7],
    }


def topic_file_backfill_ids_from_row(row) -> tuple[Any, Any, Any]:
    return row[0], row[1], row[8]


def topic_file_group_payload_from_row(row) -> Optional[Dict[str, Any]]:
    group_id = row[8]
    group_name = row[23]
    if not group_id or not group_name:
        return None
    return {
        "group_id": group_id,
        "name": group_name or "",
        "type": row[24],
        "background_url": row[25],
    }


def topic_talk_files_from_data(topic_data: Dict[str, Any]) -> tuple[bool, Any]:
    talk_data = topic_data.get("talk")
    if talk_data and "files" in talk_data:
        return True, talk_data["files"]
    return False, None


def topic_article_payload_from_data(topic_id: int, topic_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    talk_data = topic_data.get("talk")
    if talk_data and "article" in talk_data:
        article_data = talk_data["article"]
        if article_data:
            return article_data

    article_data = topic_data.get("article")
    if article_data:
        return article_data

    if topic_data.get("type", "") == "article" and topic_data.get("title"):
        return {
            "title": topic_data.get("title", ""),
            "article_id": str(topic_id),
            "article_url": "",
            "inline_article_url": "",
        }
    return None
