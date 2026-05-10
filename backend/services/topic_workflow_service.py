from __future__ import annotations

from backend.storage.db_compat import connect


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
