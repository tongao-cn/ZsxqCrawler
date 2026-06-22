from __future__ import annotations

from typing import Any, Optional

from backend.storage.zsxq_database_scope import group_id_param, nullable_group_id_param


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


def group_stats_queries(group_id: Optional[str]) -> tuple[tuple[str, str, tuple[Any, ...]], ...]:
    scoped_group_id = group_id_param(group_id)
    return (
        (
            "topics_count",
            "SELECT COUNT(*) FROM topics WHERE group_id = ?",
            (scoped_group_id,),
        ),
        (
            "users_count",
            """
            SELECT COUNT(DISTINCT t.owner_user_id)
            FROM talks t
            JOIN topics tp ON t.topic_id = tp.topic_id
            WHERE tp.group_id = ?
            """,
            (scoped_group_id,),
        ),
        (
            "latest_topic_time",
            "SELECT MAX(create_time) FROM topics WHERE group_id = ?",
            (scoped_group_id,),
        ),
        (
            "earliest_topic_time",
            "SELECT MIN(create_time) FROM topics WHERE group_id = ?",
            (scoped_group_id,),
        ),
        (
            "total_likes",
            "SELECT SUM(likes_count) FROM topics WHERE group_id = ?",
            (scoped_group_id,),
        ),
        (
            "total_comments",
            "SELECT SUM(comments_count) FROM topics WHERE group_id = ?",
            (scoped_group_id,),
        ),
        (
            "total_readings",
            "SELECT SUM(reading_count) FROM topics WHERE group_id = ?",
            (scoped_group_id,),
        ),
    )


def local_group_topic_time_range_query(group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        SELECT MIN(create_time), MAX(create_time)
        FROM topics
        WHERE group_id = ? AND create_time IS NOT NULL AND create_time != ''
        """,
        (group_id_param(group_id),),
    )


def local_group_topic_count_query(group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    return (
        "SELECT COUNT(*) FROM topics WHERE group_id = ?",
        (group_id_param(group_id),),
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
