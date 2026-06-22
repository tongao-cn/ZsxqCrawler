from __future__ import annotations

from typing import Any, Dict, Optional


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


def like_insert_statement_pair(
    topic_id: int,
    user_id: Any,
    like_data: Dict[str, Any],
    timestamp: str,
) -> tuple[tuple[str, tuple[Any, ...]], tuple[str, tuple[Any, ...]]]:
    return (
        like_insert_statement(topic_id, user_id, like_data, timestamp),
        latest_like_insert_statement(topic_id, user_id, like_data, timestamp),
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
