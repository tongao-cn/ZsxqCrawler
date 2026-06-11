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


def topic_detail_scope(topic_id: int, group_id: Optional[str]) -> tuple[Any, str, list[Any]]:
    scoped_group_id = group_id_param(group_id) if group_id is not None else None
    topic_scope_sql = "t.topic_id = ?"
    topic_scope_params = [topic_id]
    if scoped_group_id is not None:
        topic_scope_sql += " AND t.group_id = ?"
        topic_scope_params.append(scoped_group_id)
    return scoped_group_id, topic_scope_sql, topic_scope_params


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
