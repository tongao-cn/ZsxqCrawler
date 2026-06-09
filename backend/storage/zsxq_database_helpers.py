"""Small row and parameter helpers for ZSXQ topic storage."""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_pagination(page: int, per_page: int, total: int) -> Dict[str, int]:
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
    }


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


def group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def nullable_group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    if not value:
        return None
    return int(value) if value.isdigit() else value


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
