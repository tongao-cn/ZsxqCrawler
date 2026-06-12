"""Small row and parameter helpers for ZSXQ topic storage."""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, Optional


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


def group_insert_statement(group_data: Dict[str, Any], created_at: str) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO groups
            (group_id, name, type, background_url, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(group_id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                background_url = excluded.background_url,
                created_at = excluded.created_at
        """,
        (
            group_data.get("group_id"),
            group_data.get("name", ""),
            group_data.get("type", ""),
            group_data.get("background_url", ""),
            created_at,
        ),
    )


def user_insert_statement(user_data: Dict[str, Any], created_at: str) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO users
            (user_id, name, alias, avatar_url, location, description, ai_comment_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                alias = excluded.alias,
                avatar_url = excluded.avatar_url,
                location = excluded.location,
                description = excluded.description,
                ai_comment_url = excluded.ai_comment_url,
                created_at = excluded.created_at
        """,
        (
            user_data.get("user_id"),
            user_data.get("name", ""),
            user_data.get("alias", ""),
            user_data.get("avatar_url", ""),
            user_data.get("location", ""),
            user_data.get("description", ""),
            user_data.get("ai_comment_url", ""),
            created_at,
        ),
    )


def topic_insert_statement(topic_data: Dict[str, Any], imported_at: str) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO topics
            (topic_id, group_id, type, title, create_time, digested, sticky,
             likes_count, tourist_likes_count, rewards_count, comments_count,
             reading_count, readers_count, answered, silenced, annotation,
             user_liked, user_subscribed, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_id) DO UPDATE SET
                group_id = excluded.group_id,
                type = excluded.type,
                title = excluded.title,
                create_time = excluded.create_time,
                digested = excluded.digested,
                sticky = excluded.sticky,
                likes_count = excluded.likes_count,
                tourist_likes_count = excluded.tourist_likes_count,
                rewards_count = excluded.rewards_count,
                comments_count = excluded.comments_count,
                reading_count = excluded.reading_count,
                readers_count = excluded.readers_count,
                answered = excluded.answered,
                silenced = excluded.silenced,
                annotation = excluded.annotation,
                user_liked = excluded.user_liked,
                user_subscribed = excluded.user_subscribed,
                imported_at = excluded.imported_at
        """,
        (
            topic_data.get("topic_id"),
            topic_data.get("group", {}).get("group_id", ""),
            topic_data.get("type", ""),
            topic_data.get("title", ""),
            topic_data.get("create_time", ""),
            topic_data.get("digested", False),
            topic_data.get("sticky", False),
            topic_data.get("likes_count", 0),
            topic_data.get("tourist_likes_count", 0),
            topic_data.get("rewards_count", 0),
            topic_data.get("comments_count", 0),
            topic_data.get("reading_count", 0),
            topic_data.get("readers_count", 0),
            topic_data.get("answered", False),
            topic_data.get("silenced", False),
            topic_data.get("annotation", ""),
            topic_data.get("user_liked", False),
            topic_data.get("user_subscribed", False),
            imported_at,
        ),
    )


def topic_stats_update_statement(
    topic_data: Dict[str, Any],
    topic_id: int,
    scoped_group_id: Any,
    imported_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                UPDATE topics
                SET likes_count = ?, tourist_likes_count = ?, rewards_count = ?,
                    comments_count = ?, reading_count = ?, readers_count = ?,
                    digested = ?, sticky = ?, user_liked = ?, user_subscribed = ?,
                    imported_at = ?
                WHERE topic_id = ?
                  AND (? IS NULL OR group_id = ?)
            """,
        (
            topic_data.get("likes_count", 0),
            topic_data.get("tourist_likes_count", 0),
            topic_data.get("rewards_count", 0),
            topic_data.get("comments_count", 0),
            topic_data.get("reading_count", 0),
            topic_data.get("readers_count", 0),
            topic_data.get("digested", False),
            topic_data.get("sticky", False),
            topic_data.get("user_specific", {}).get("liked", False),
            topic_data.get("user_specific", {}).get("subscribed", False),
            imported_at,
            topic_id,
            scoped_group_id,
            scoped_group_id,
        ),
    )


def talk_insert_statement(topic_id: int, talk_data: Dict[str, Any], created_at: str) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO talks
            (topic_id, owner_user_id, text, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(topic_id) DO UPDATE SET
                owner_user_id = excluded.owner_user_id,
                text = excluded.text,
                created_at = excluded.created_at
        """,
        (
            topic_id,
            talk_data.get("owner", {}).get("user_id"),
            talk_data.get("text", ""),
            created_at,
        ),
    )


def image_insert_statement(
    topic_id: int,
    image_data: Dict[str, Any],
    comment_id: Optional[int],
    created_at: str,
    *,
    missing_numeric_default: Any = None,
) -> tuple[str, tuple[Any, ...]]:
    thumbnail = image_data.get("thumbnail", {})
    large = image_data.get("large", {})
    original = image_data.get("original", {})
    return (
        """
            INSERT INTO images
            (image_id, topic_id, comment_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
             large_url, large_width, large_height, original_url, original_width, original_height,
             original_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(image_id) DO UPDATE SET
                topic_id = excluded.topic_id,
                comment_id = excluded.comment_id,
                type = excluded.type,
                thumbnail_url = excluded.thumbnail_url,
                thumbnail_width = excluded.thumbnail_width,
                thumbnail_height = excluded.thumbnail_height,
                large_url = excluded.large_url,
                large_width = excluded.large_width,
                large_height = excluded.large_height,
                original_url = excluded.original_url,
                original_width = excluded.original_width,
                original_height = excluded.original_height,
                original_size = excluded.original_size,
                created_at = excluded.created_at
        """,
        (
            image_data.get("image_id"),
            topic_id,
            comment_id,
            image_data.get("type", ""),
            thumbnail.get("url", ""),
            thumbnail.get("width", missing_numeric_default),
            thumbnail.get("height", missing_numeric_default),
            large.get("url", ""),
            large.get("width", missing_numeric_default),
            large.get("height", missing_numeric_default),
            original.get("url", ""),
            original.get("width", missing_numeric_default),
            original.get("height", missing_numeric_default),
            original.get("size", missing_numeric_default),
            created_at,
        ),
    )


def delete_latest_likes_statement(topic_id: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            DELETE FROM latest_likes
            WHERE topic_id = ?
        """,
        (topic_id,),
    )


def like_insert_statement(
    topic_id: int,
    user_id: Any,
    like_data: Dict[str, Any],
    imported_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO likes
            (topic_id, user_id, create_time, imported_at)
            VALUES (?, ?, ?, ?)
        """,
        (
            topic_id,
            user_id,
            like_data.get("create_time", ""),
            imported_at,
        ),
    )


def latest_like_insert_statement(
    topic_id: int,
    user_id: Any,
    like_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO latest_likes
            (topic_id, owner_user_id, create_time, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(topic_id, owner_user_id, create_time) DO UPDATE SET
                created_at = excluded.created_at
        """,
        (
            topic_id,
            user_id,
            like_data.get("create_time", ""),
            created_at,
        ),
    )


def like_emoji_insert_statement(
    topic_id: int,
    emoji_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO like_emojis
            (topic_id, emoji_key, likes_count, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(topic_id, emoji_key) DO UPDATE SET
                likes_count = excluded.likes_count,
                created_at = excluded.created_at
        """,
        (
            topic_id,
            emoji_data.get("emoji_key"),
            emoji_data.get("likes_count", 0),
            created_at,
        ),
    )


def user_liked_emoji_insert_statement(topic_id: int, emoji_key: str) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO user_liked_emojis
            (topic_id, emoji_key)
            VALUES (?, ?)
            ON CONFLICT(topic_id, emoji_key) DO NOTHING
        """,
        (topic_id, emoji_key),
    )


def comment_insert_statement(
    topic_id: int,
    comment_id: Any,
    group_id: Any,
    owner_user_id: Any,
    repliee_user_id: Any,
    comment_data: Dict[str, Any],
    imported_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO comments
            (comment_id, group_id, topic_id, owner_user_id, parent_comment_id, repliee_user_id,
             text, create_time, likes_count, rewards_count, replies_count, sticky, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(comment_id) DO UPDATE SET
                group_id = excluded.group_id,
                topic_id = excluded.topic_id,
                owner_user_id = excluded.owner_user_id,
                parent_comment_id = excluded.parent_comment_id,
                repliee_user_id = excluded.repliee_user_id,
                text = excluded.text,
                create_time = excluded.create_time,
                likes_count = excluded.likes_count,
                rewards_count = excluded.rewards_count,
                replies_count = excluded.replies_count,
                sticky = excluded.sticky,
                imported_at = excluded.imported_at
        """,
        (
            comment_id,
            group_id,
            topic_id,
            owner_user_id,
            comment_data.get("parent_comment_id"),
            repliee_user_id,
            comment_data.get("text", ""),
            comment_data.get("create_time", ""),
            comment_data.get("likes_count", 0),
            comment_data.get("rewards_count", 0),
            comment_data.get("replies_count", 0),
            comment_data.get("sticky", False),
            imported_at,
        ),
    )


def question_insert_statement(
    topic_id: int,
    owner_user_id: Any,
    questionee_user_id: Any,
    is_anonymous: bool,
    question_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    owner_detail = question_data.get("owner_detail", {})
    return (
        """
            INSERT INTO questions
            (topic_id, owner_user_id, questionee_user_id, text, expired, anonymous,
             owner_questions_count, owner_join_time, owner_status, owner_location, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_id) DO UPDATE SET
                owner_user_id = excluded.owner_user_id,
                questionee_user_id = excluded.questionee_user_id,
                text = excluded.text,
                expired = excluded.expired,
                anonymous = excluded.anonymous,
                owner_questions_count = excluded.owner_questions_count,
                owner_join_time = excluded.owner_join_time,
                owner_status = excluded.owner_status,
                owner_location = excluded.owner_location,
                created_at = excluded.created_at
        """,
        (
            topic_id,
            owner_user_id,
            questionee_user_id,
            question_data.get("text", ""),
            question_data.get("expired", False),
            is_anonymous,
            owner_detail.get("questions_count"),
            owner_detail.get("join_time", owner_detail.get("estimated_join_time", "")),
            owner_detail.get("status", ""),
            question_data.get("owner_location", ""),
            created_at,
        ),
    )


def answer_insert_statement(
    topic_id: int,
    owner_user_id: Any,
    answer_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO answers
            (topic_id, owner_user_id, text, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(topic_id) DO UPDATE SET
                owner_user_id = excluded.owner_user_id,
                text = excluded.text,
                created_at = excluded.created_at
        """,
        (
            topic_id,
            owner_user_id,
            answer_data.get("text", ""),
            created_at,
        ),
    )


def article_insert_statement(
    topic_id: int,
    title: str,
    article_id: Any,
    article_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return (
        """
            INSERT INTO articles
            (topic_id, title, article_id, article_url, inline_article_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_id) DO UPDATE SET
                title = excluded.title,
                article_id = excluded.article_id,
                article_url = excluded.article_url,
                inline_article_url = excluded.inline_article_url,
                created_at = excluded.created_at
        """,
        (
            topic_id,
            title,
            article_id,
            article_data.get("article_url", ""),
            article_data.get("inline_article_url", ""),
            created_at,
        ),
    )


def topic_file_insert_statement(
    topic_id: int,
    file_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                INSERT INTO topic_files
                (topic_id, file_id, name, hash, size, duration, download_count, create_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic_id, file_id) DO UPDATE SET
                    name = excluded.name,
                    hash = excluded.hash,
                    size = excluded.size,
                    duration = excluded.duration,
                    download_count = excluded.download_count,
                    create_time = excluded.create_time,
                    created_at = excluded.created_at
            """,
        (
            topic_id,
            file_data.get("file_id"),
            file_data.get("name", ""),
            file_data.get("hash", ""),
            file_data.get("size", 0),
            file_data.get("duration", 0),
            file_data.get("download_count", 0),
            file_data.get("create_time", ""),
            created_at,
        ),
    )


def update_tag_hid_statement(tag_id: int, hid: str) -> tuple[str, tuple[Any, ...]]:
    return "UPDATE tags SET hid = ? WHERE tag_id = ?", (hid, tag_id)


def insert_tag_statement(
    group_id: int, tag_name: str, hid: Optional[str], created_at: str
) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                    INSERT INTO tags (group_id, tag_name, hid, created_at)
                    VALUES (?, ?, ?, ?)
                    RETURNING tag_id
                """,
        (group_id, tag_name, hid, created_at),
    )


def insert_topic_tag_statement(topic_id: int, tag_id: int, created_at: str) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                INSERT INTO topic_tags (topic_id, tag_id, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(topic_id, tag_id) DO NOTHING
            """,
        (topic_id, tag_id, created_at),
    )


def refresh_tag_topic_count_statement(tag_id: int) -> tuple[str, tuple[Any, ...]]:
    return (
        """
                UPDATE tags SET topic_count = (
                    SELECT COUNT(*) FROM topic_tags WHERE tag_id = ?
                ) WHERE tag_id = ?
            """,
        (tag_id, tag_id),
    )


def group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def nullable_group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    if not value:
        return None
    return int(value) if value.isdigit() else value


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


def newest_topic_create_time_query(group_id: Optional[str], *, nullable_scope: bool = False) -> tuple[str, tuple[Any, ...]]:
    scoped_group_id = nullable_group_id_param(group_id) if nullable_scope else group_id_param(group_id)
    return (
        """
                SELECT create_time FROM topics
                WHERE (? IS NULL OR group_id = ?)
                  AND create_time IS NOT NULL AND create_time != ''
                ORDER BY create_time DESC LIMIT 1
            """,
        (scoped_group_id, scoped_group_id),
    )


def oldest_topic_create_time_query(group_id: Optional[str], *, nullable_scope: bool = False) -> tuple[str, tuple[Any, ...]]:
    scoped_group_id = nullable_group_id_param(group_id) if nullable_scope else group_id_param(group_id)
    return (
        """
                SELECT create_time FROM topics
                WHERE (? IS NULL OR group_id = ?)
                  AND create_time IS NOT NULL AND create_time != ''
                ORDER BY create_time ASC LIMIT 1
            """,
        (scoped_group_id, scoped_group_id),
    )


def topic_count_query(group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    scoped_group_id = nullable_group_id_param(group_id)
    return (
        "SELECT COUNT(*) FROM topics WHERE (? IS NULL OR group_id = ?)",
        (scoped_group_id, scoped_group_id),
    )


def database_stats_count_query(table: str, group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    if group_id is None:
        return f"SELECT COUNT(*) FROM {table}", ()

    scoped_group_id = group_id_param(group_id)
    if table in {"groups", "topics", "comments"}:
        return f"SELECT COUNT(*) FROM {table} WHERE group_id = ?", (scoped_group_id,)

    if table == "users":
        return (
            """
                        SELECT COUNT(DISTINCT user_id)
                        FROM (
                            SELECT owner_user_id AS user_id FROM talks WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                            UNION
                            SELECT owner_user_id AS user_id FROM comments WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                            UNION
                            SELECT owner_user_id AS user_id FROM questions WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                            UNION
                            SELECT questionee_user_id AS user_id FROM questions WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                            UNION
                            SELECT owner_user_id AS user_id FROM answers WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                        ) scoped_users
                        WHERE user_id IS NOT NULL
                        """,
            (scoped_group_id, scoped_group_id, scoped_group_id, scoped_group_id, scoped_group_id),
        )

    return (
        f"SELECT COUNT(*) FROM {table} WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)",
        (scoped_group_id,),
    )


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


def topic_detail_image_payload(row, *, offset: int = 0) -> Dict[str, Any]:
    return {
        "image_id": row[offset],
        "type": row[offset + 1],
        "thumbnail": {
            "url": row[offset + 2],
            "width": row[offset + 3],
            "height": row[offset + 4],
        },
        "large": {
            "url": row[offset + 5],
            "width": row[offset + 6],
            "height": row[offset + 7],
        },
        "original": {
            "url": row[offset + 8],
            "width": row[offset + 9],
            "height": row[offset + 10],
            "size": row[offset + 11],
        },
    }


def topic_detail_file_payload(row) -> Dict[str, Any]:
    return {
        "file_id": row[0],
        "name": row[1],
        "hash": row[2],
        "size": row[3],
        "duration": row[4],
        "download_count": row[5],
        "create_time": row[6],
    }


def topic_detail_base_payload(row) -> Dict[str, Any]:
    return {
        "topic_id": row[0],
        "type": row[1],
        "title": row[2],
        "create_time": row[3],
        "digested": bool(row[4]),
        "sticky": bool(row[5]),
        "likes_count": row[6],
        "tourist_likes_count": row[7],
        "rewards_count": row[8],
        "comments_count": row[9],
        "reading_count": row[10],
        "readers_count": row[11],
        "answered": bool(row[12]),
        "silenced": bool(row[13]),
        "annotation": row[14],
        "group": {
            "group_id": row[17],
            "name": row[18],
            "type": row[19],
            "background_url": row[20],
        },
        "user_specific": {
            "liked": bool(row[15]),
            "liked_emojis": [],
            "subscribed": bool(row[16]),
        },
    }


def load_topic_detail_base(cursor, topic_scope_sql: str, topic_scope_params: list[Any]) -> Optional[Dict[str, Any]]:
    cursor.execute(f'''
        SELECT
            t.topic_id, t.type, t.title, t.create_time, t.digested, t.sticky,
            t.likes_count, t.tourist_likes_count, t.rewards_count, t.comments_count,
            t.reading_count, t.readers_count, t.answered, t.silenced, t.annotation,
            t.user_liked, t.user_subscribed,
            g.group_id, g.name as group_name, g.type as group_type, g.background_url
        FROM topics t
        LEFT JOIN groups g ON t.group_id = g.group_id
        WHERE {topic_scope_sql}
    ''', tuple(topic_scope_params))

    topic_row = cursor.fetchone()
    if not topic_row:
        return None
    return topic_detail_base_payload(topic_row)


def topic_detail_talk_payload(row) -> Dict[str, Any]:
    return {
        "text": row[0],
        "owner": {
            "user_id": row[1],
            "name": row[2],
            "alias": row[3],
            "avatar_url": row[4],
            "location": row[5],
            "description": row[6],
        },
    }


def topic_detail_article_payload(row) -> Dict[str, Any]:
    return {
        "title": row[0],
        "article_id": row[1],
        "article_url": row[2],
        "inline_article_url": row[3],
    }


def build_topic_detail_talk(
    talk_row,
    images: list[Dict[str, Any]],
    files: list[Dict[str, Any]],
    article_row,
) -> Dict[str, Any]:
    talk_data = topic_detail_talk_payload(talk_row)
    if images:
        talk_data["images"] = images
    if files:
        talk_data["files"] = files
    if article_row:
        talk_data["article"] = topic_detail_article_payload(article_row)
    return talk_data


def load_topic_detail_talk(cursor, topic_id: int, scoped_group_id: Any, talk_row) -> Dict[str, Any]:
    cursor.execute('''
        SELECT
            image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
            large_url, large_width, large_height,
            original_url, original_width, original_height, original_size
        FROM images
        WHERE topic_id = ? AND comment_id IS NULL
          AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?))
        ORDER BY image_id
    ''', (topic_id, scoped_group_id, scoped_group_id))

    images = [topic_detail_image_payload(img_row) for img_row in cursor.fetchall()]

    cursor.execute('''
        SELECT
            tf.file_id, tf.name, tf.hash, tf.size, tf.duration, tf.download_count, tf.create_time
        FROM topic_files tf
        WHERE tf.topic_id = ?
          AND (? IS NULL OR tf.topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?))
        ORDER BY file_id
    ''', (topic_id, scoped_group_id, scoped_group_id))

    files = [topic_detail_file_payload(file_row) for file_row in cursor.fetchall()]

    cursor.execute('''
        SELECT title, article_id, article_url, inline_article_url
        FROM articles
        WHERE topic_id = ?
          AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?))
        LIMIT 1
    ''', (topic_id, scoped_group_id, scoped_group_id))
    article_row = cursor.fetchone()

    return build_topic_detail_talk(talk_row, images, files, article_row)


def load_topic_detail_talk_payload(cursor, topic_id: int, scoped_group_id: Any) -> Optional[Dict[str, Any]]:
    cursor.execute('''
        SELECT
            t.text,
            u.user_id, u.name, u.alias, u.avatar_url, u.location, u.description
        FROM talks t
        LEFT JOIN users u ON t.owner_user_id = u.user_id
        WHERE t.topic_id = ?
        LIMIT 1
    ''', (topic_id,))

    talk_row = cursor.fetchone()
    if not talk_row:
        return None
    return load_topic_detail_talk(cursor, topic_id, scoped_group_id, talk_row)


def topic_detail_like_payload(row) -> Dict[str, Any]:
    return {
        "create_time": row[0],
        "owner": {
            "user_id": row[1],
            "name": row[2],
            "avatar_url": row[3],
        },
    }


def topic_detail_emoji_payload(row) -> Dict[str, Any]:
    return {
        "emoji_key": row[0],
        "likes_count": row[1],
    }


def build_topic_detail_latest_likes(like_rows) -> list[Dict[str, Any]]:
    return [topic_detail_like_payload(like_row) for like_row in like_rows]


def build_topic_detail_likes_detail(emoji_rows) -> Dict[str, list[Dict[str, Any]]]:
    return {
        "emojis": [topic_detail_emoji_payload(emoji_row) for emoji_row in emoji_rows],
    }


def load_topic_detail_latest_likes(cursor, topic_id: int, scoped_group_id: Any) -> list[Dict[str, Any]]:
    cursor.execute('''
        SELECT
            l.create_time,
            u.user_id, u.name, u.avatar_url
        FROM likes l
        LEFT JOIN users u ON l.user_id = u.user_id
        WHERE l.topic_id = ?
          AND (? IS NULL OR l.topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?))
        ORDER BY l.create_time DESC
        LIMIT 5
    ''', (topic_id, scoped_group_id, scoped_group_id))

    return build_topic_detail_latest_likes(cursor.fetchall())


def load_topic_detail_likes_detail(cursor, topic_id: int, scoped_group_id: Any) -> Dict[str, list[Dict[str, Any]]]:
    cursor.execute('''
        SELECT emoji_key, likes_count
        FROM like_emojis
        WHERE topic_id = ?
          AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?))
    ''', (topic_id, scoped_group_id, scoped_group_id))

    return build_topic_detail_likes_detail(cursor.fetchall())


def topic_detail_comment_payload(row, images: list[Dict[str, Any]]) -> Dict[str, Any]:
    comment_data = {
        "comment_id": row[0],
        "text": row[1],
        "create_time": row[2],
        "likes_count": row[3],
        "rewards_count": row[4],
        "sticky": bool(row[5]),
        "parent_comment_id": row[6],
        "replies_count": row[7],
        "owner": {
            "user_id": row[8],
            "name": row[9],
            "alias": row[10],
            "avatar_url": row[11],
            "location": row[12],
            "description": row[13],
        },
    }
    if row[14]:
        comment_data["repliee"] = {
            "user_id": row[14],
            "name": row[15],
            "avatar_url": row[16],
        }
    if images:
        comment_data["images"] = images
    return comment_data


def build_topic_detail_comments(comment_rows, comment_images_map: Dict[Any, list[Dict[str, Any]]]) -> list[Dict[str, Any]]:
    all_comments = {}
    parent_comments = []
    child_comments = []

    for comment_row in comment_rows:
        comment_id = comment_row[0]
        parent_comment_id = comment_row[6]

        images = comment_images_map.get(comment_id, [])
        comment_data = topic_detail_comment_payload(comment_row, images)

        all_comments[comment_id] = comment_data
        if parent_comment_id:
            child_comments.append(comment_data)
        else:
            parent_comments.append(comment_data)

    for child in child_comments:
        parent_id = child.get("parent_comment_id")
        if parent_id and parent_id in all_comments:
            parent = all_comments[parent_id]
            if "replied_comments" not in parent:
                parent["replied_comments"] = []
            parent["replied_comments"].append(child)

    return parent_comments


def load_topic_comment_images_map(
    cursor,
    comment_ids: list[Any],
    scoped_group_id: Any,
    *,
    chunk_size: int = 500,
) -> Dict[Any, list[Dict[str, Any]]]:
    comment_images_map = {}
    if not comment_ids:
        return comment_images_map

    for start in range(0, len(comment_ids), chunk_size):
        chunk_ids = comment_ids[start:start + chunk_size]
        placeholders = ','.join('?' for _ in chunk_ids)
        cursor.execute(f'''
            SELECT
                comment_id, image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
                large_url, large_width, large_height,
                original_url, original_width, original_height, original_size
            FROM images
            WHERE comment_id IN ({placeholders})
              AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?))
            ORDER BY comment_id ASC, image_id ASC
        ''', [*chunk_ids, scoped_group_id, scoped_group_id])

        for img_row in cursor.fetchall():
            comment_images_map.setdefault(img_row[0], []).append(
                topic_detail_image_payload(img_row, offset=1)
            )

    return comment_images_map


def load_topic_detail_comments(cursor, topic_id: int, scoped_group_id: Any) -> list[Dict[str, Any]]:
    cursor.execute('''
        SELECT
            c.comment_id, c.text, c.create_time, c.likes_count, c.rewards_count, c.sticky,
            c.parent_comment_id, c.replies_count,
            u.user_id, u.name, u.alias, u.avatar_url, u.location, u.description,
            r.user_id as repliee_user_id, r.name as repliee_name, r.avatar_url as repliee_avatar_url
        FROM comments c
        LEFT JOIN users u ON c.owner_user_id = u.user_id
        LEFT JOIN users r ON c.repliee_user_id = r.user_id
        WHERE c.topic_id = ?
          AND (? IS NULL OR c.group_id = ?)
        ORDER BY c.create_time ASC
    ''', (topic_id, scoped_group_id, scoped_group_id))

    comment_rows = cursor.fetchall()
    comment_ids = [row[0] for row in comment_rows]
    comment_images_map = load_topic_comment_images_map(cursor, comment_ids, scoped_group_id)
    return build_topic_detail_comments(comment_rows, comment_images_map)


def topic_detail_question_payload(row) -> Dict[str, Any]:
    question_data = {
        "text": row[0],
        "expired": bool(row[1]),
        "anonymous": bool(row[2]),
        "owner_detail": {
            "questions_count": row[3],
            "estimated_join_time": row[4],
            "status": row[5],
        },
        "owner_location": row[6],
    }

    if row[12]:
        question_data["questionee"] = {
            "user_id": row[12],
            "name": row[13],
            "alias": row[14],
            "avatar_url": row[15],
            "location": row[16],
            "description": row[17],
        }

    if not question_data["anonymous"] and row[7]:
        question_data["owner"] = {
            "user_id": row[7],
            "name": row[8],
            "alias": row[9],
            "avatar_url": row[10],
            "location": row[11],
            "description": row[11],
        }

    return question_data


def topic_detail_answer_payload(row) -> Dict[str, Any]:
    return {
        "text": row[0],
        "owner": {
            "user_id": row[1],
            "name": row[2],
            "alias": row[3],
            "avatar_url": row[4],
            "location": row[5],
            "description": row[6],
        },
    }


def build_topic_detail_qa(question_row, answer_row) -> Dict[str, Any]:
    qa_data = {}
    if question_row:
        qa_data["question"] = topic_detail_question_payload(question_row)
    if answer_row:
        qa_data["answer"] = topic_detail_answer_payload(answer_row)
    return qa_data


def load_topic_detail_qa(cursor, topic_id: int, scoped_group_id: Any) -> Dict[str, Any]:
    cursor.execute('''
        SELECT
            q.text, q.expired, q.anonymous, q.owner_questions_count,
            q.owner_join_time, q.owner_status, q.owner_location,
            owner.user_id as owner_user_id, owner.name as owner_name,
            owner.alias as owner_alias, owner.avatar_url as owner_avatar_url,
            owner.location as owner_location_detail, owner.description as owner_description,
            questionee.user_id as questionee_user_id, questionee.name as questionee_name,
            questionee.alias as questionee_alias, questionee.avatar_url as questionee_avatar_url,
            questionee.location as questionee_location, questionee.description as questionee_description
        FROM questions q
        LEFT JOIN users owner ON q.owner_user_id = owner.user_id
        LEFT JOIN users questionee ON q.questionee_user_id = questionee.user_id
        WHERE q.topic_id = ?
          AND (? IS NULL OR q.topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?))
        LIMIT 1
    ''', (topic_id, scoped_group_id, scoped_group_id))

    question_row = cursor.fetchone()

    cursor.execute('''
        SELECT
            a.text,
            u.user_id, u.name, u.alias, u.avatar_url, u.location, u.description
        FROM answers a
        LEFT JOIN users u ON a.owner_user_id = u.user_id
        WHERE a.topic_id = ?
          AND (? IS NULL OR a.topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?))
        LIMIT 1
    ''', (topic_id, scoped_group_id, scoped_group_id))

    answer_row = cursor.fetchone()
    return build_topic_detail_qa(question_row, answer_row)
