"""Topic loading helpers for daily AI reports."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Tuple


BJ_TZ = timezone(timedelta(hours=8))


def date_bounds(report_date: date) -> Tuple[str, str]:
    start_dt = datetime.combine(report_date, time.min, tzinfo=BJ_TZ)
    end_dt = start_dt + timedelta(days=1)
    return (
        start_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800",
        end_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800",
    )


def clip_text(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n...[内容过长，已截断]"


def image_row_to_payload(row: Any, image_ref: str) -> Dict[str, Any]:
    url = row["large_url"] or row["original_url"] or row["thumbnail_url"] or ""
    return {
        "image_ref": image_ref,
        "image_id": row["image_id"],
        "url": url,
        "width": row["large_width"] or row["original_width"] or row["thumbnail_width"] or 0,
        "height": row["large_height"] or row["original_height"] or row["thumbnail_height"] or 0,
        "size": row["original_size"] or 0,
    }


def fetch_topics_for_date(
    conn: Any,
    *,
    group_id: str,
    report_date: date,
    comments_per_topic: int,
    max_topic_chars: int,
    max_images_per_topic: int,
) -> List[Dict[str, Any]]:
    start_time, end_time = date_bounds(report_date)
    rows = conn.execute(
        """
        SELECT
            t.topic_id, t.group_id, t.type, t.title, t.create_time,
            t.likes_count, t.comments_count, t.reading_count, t.readers_count,
            t.digested, t.sticky,
            talk.text AS talk_text,
            talk_owner.name AS talk_owner_name,
            q.text AS question_text,
            q_owner.name AS question_owner_name,
            a.text AS answer_text,
            a_owner.name AS answer_owner_name
        FROM topics t
        LEFT JOIN talks talk ON t.topic_id = talk.topic_id
        LEFT JOIN users talk_owner ON talk.owner_user_id = talk_owner.user_id
        LEFT JOIN questions q ON t.topic_id = q.topic_id
        LEFT JOIN users q_owner ON q.owner_user_id = q_owner.user_id
        LEFT JOIN answers a ON t.topic_id = a.topic_id
        LEFT JOIN users a_owner ON a.owner_user_id = a_owner.user_id
        WHERE t.group_id = ?
          AND t.create_time >= ?
          AND t.create_time < ?
        ORDER BY t.create_time ASC
        """,
        (group_id, start_time, end_time),
    ).fetchall()

    topics: List[Dict[str, Any]] = []
    for row in rows:
        topic_id = row["topic_id"]
        comments = conn.execute(
            """
            SELECT c.comment_id, c.text, c.create_time, c.likes_count, c.sticky, u.name AS owner_name
            FROM comments c
            LEFT JOIN users u ON c.owner_user_id = u.user_id
            WHERE c.topic_id = ?
              AND c.group_id = ?
            ORDER BY c.sticky DESC, c.likes_count DESC, c.create_time ASC
            LIMIT ?
            """,
            (topic_id, group_id, comments_per_topic),
        ).fetchall()
        tags = conn.execute(
            """
            SELECT tags.tag_name
            FROM topic_tags tt
            INNER JOIN tags ON tt.tag_id = tags.tag_id
            WHERE tt.topic_id = ?
              AND tt.topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
            ORDER BY tags.tag_name ASC
            """,
            (topic_id, group_id),
        ).fetchall()
        topic_image_rows = conn.execute(
            """
            SELECT
                image_id, thumbnail_url, thumbnail_width, thumbnail_height,
                large_url, large_width, large_height,
                original_url, original_width, original_height, original_size
            FROM images
            WHERE topic_id = ? AND comment_id IS NULL
              AND topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
            ORDER BY image_id ASC
            LIMIT ?
            """,
            (topic_id, group_id, max_images_per_topic),
        ).fetchall()

        comment_ids = [comment["comment_id"] for comment in comments]
        comment_images_map: Dict[int, List[Dict[str, Any]]] = {}
        if comment_ids:
            placeholders = ",".join("?" for _ in comment_ids)
            comment_image_rows = conn.execute(
                f"""
                SELECT
                    comment_id, image_id, thumbnail_url, thumbnail_width, thumbnail_height,
                    large_url, large_width, large_height,
                    original_url, original_width, original_height, original_size
                FROM images
                WHERE comment_id IN ({placeholders})
                  AND topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                ORDER BY comment_id ASC, image_id ASC
                """,
                [*comment_ids, group_id],
            ).fetchall()
            for image_index, image_row in enumerate(comment_image_rows, start=1):
                comment_id = image_row["comment_id"]
                images = comment_images_map.setdefault(comment_id, [])
                if len(images) < max_images_per_topic:
                    images.append(
                        image_row_to_payload(image_row, f"topic_{topic_id}_comment_{comment_id}_image_{image_index}")
                    )

        topic_images = [
            image_row_to_payload(image_row, f"topic_{topic_id}_image_{index}")
            for index, image_row in enumerate(topic_image_rows, start=1)
        ]

        topics.append(
            {
                "topic_id": topic_id,
                "type": row["type"],
                "title": row["title"] or "",
                "create_time": row["create_time"],
                "author": row["talk_owner_name"] or row["question_owner_name"] or row["answer_owner_name"] or "",
                "metrics": {
                    "likes_count": row["likes_count"] or 0,
                    "comments_count": row["comments_count"] or 0,
                    "reading_count": row["reading_count"] or 0,
                    "readers_count": row["readers_count"] or 0,
                    "digested": bool(row["digested"]),
                    "sticky": bool(row["sticky"]),
                },
                "tags": [tag["tag_name"] for tag in tags],
                "talk_text": clip_text(row["talk_text"], max_topic_chars),
                "question_text": clip_text(row["question_text"], max_topic_chars),
                "answer_text": clip_text(row["answer_text"], max_topic_chars),
                "images": topic_images,
                "comments": [
                    {
                        "owner": comment["owner_name"] or "",
                        "text": clip_text(comment["text"], 1200),
                        "likes_count": comment["likes_count"] or 0,
                        "sticky": bool(comment["sticky"]),
                        "create_time": comment["create_time"],
                        "images": comment_images_map.get(comment["comment_id"], []),
                    }
                    for comment in comments
                    if str(comment["text"] or "").strip() or comment_images_map.get(comment["comment_id"])
                ],
            }
        )
    return topics
