import unittest
from unittest.mock import patch

from backend.storage.zsxq_database import (
    _build_pagination,
    _delete_latest_likes_statement,
    _file_exists_query,
    _format_tag_row,
    _format_tag_topic_row,
    _group_id_param,
    _group_insert_statement,
    _image_insert_statement,
    _insert_tag_statement,
    _insert_topic_tag_statement,
    _latest_like_insert_statement,
    _like_insert_statement,
    _newest_topic_create_time_query,
    _nullable_group_id_param,
    _oldest_topic_create_time_query,
    _refresh_tag_topic_count_statement,
    _replace_file_topic_relation,
    _talk_insert_statement,
    _tag_id_by_name_query,
    _tags_by_group_query,
    _topic_create_time_by_id_query,
    _topic_count_by_tag_query,
    _topic_detail_scope,
    _topic_count_query,
    _topic_exists_query,
    _topic_file_payload_from_row,
    _topic_group_id_query,
    _topic_insert_statement,
    _topic_stats_update_statement,
    _topics_by_tag_query,
    _update_tag_hid_statement,
    _upsert_core_file,
    _user_insert_statement,
)


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 0
        self.row = None

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        if "INSERT INTO file_topic_relations" in query:
            self.rowcount = 1
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []


class FakeTimestampCursor(FakeCursor):
    def __init__(self, rows):
        super().__init__()
        self.rows = list(rows)

    def fetchone(self):
        if self.rows:
            return self.rows.pop(0)
        return None


class FakeSequenceCursor(FakeTimestampCursor):
    pass


class FakeFailingExecuteCursor(FakeCursor):
    def execute(self, query, params=()):
        super().execute(query, params)
        raise RuntimeError("temporary tag-link failure")


class FakeTagReadCursor(FakeCursor):
    def __init__(self, tag_rows=None, topic_rows=None, total=0, raises=False):
        super().__init__()
        self.tag_rows = list(tag_rows or [])
        self.topic_rows = list(topic_rows or [])
        self.total = total
        self.raises = raises
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        super().execute(query, params)
        if self.raises:
            raise RuntimeError("temporary tag read failure")
        return self

    def fetchall(self):
        if "FROM tags" in self.last_query:
            return self.tag_rows
        if "FROM topics t" in self.last_query:
            return self.topic_rows
        return []

    def fetchone(self):
        return (self.total,)


class FakeFileDatabase:
    def __init__(self):
        self.cursor = FakeCursor()


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


class FakeBackfillCursor(FakeCursor):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchall(self):
        if "FROM topic_files" in self.last_query:
            return self.rows
        return []

    def fetchone(self):
        if "SELECT 1 FROM files" in self.last_query:
            return None
        return self.row


class FakeTopicDetailCursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchone(self):
        if "FROM topics t LEFT JOIN groups" in self.last_query:
            return (
                202,
                "talk",
                "title",
                "2026-05-07T10:00:00.000+0800",
                0,
                1,
                3,
                0,
                0,
                2,
                5,
                6,
                0,
                0,
                "note",
                0,
                1,
                303,
                "group",
                "paid",
                "bg",
            )
        if "FROM talks" in self.last_query:
            return None
        return None

    def fetchall(self):
        if "FROM comments c" in self.last_query:
            return [
                (
                    10,
                    "parent",
                    "2026-05-07T11:00:00.000+0800",
                    1,
                    0,
                    0,
                    None,
                    1,
                    901,
                    "Alice",
                    "A",
                    "a.png",
                    "SH",
                    "parent owner",
                    None,
                    None,
                    None,
                ),
                (
                    11,
                    "child",
                    "2026-05-07T11:01:00.000+0800",
                    2,
                    0,
                    1,
                    10,
                    0,
                    902,
                    "Bob",
                    "B",
                    "b.png",
                    "BJ",
                    "child owner",
                    901,
                    "Alice",
                    "a.png",
                ),
            ]
        if "FROM images WHERE comment_id IN" in self.last_query:
            return [
                (
                    11,
                    701,
                    "image",
                    "thumb.jpg",
                    100,
                    80,
                    "large.jpg",
                    1000,
                    800,
                    "origin.jpg",
                    2000,
                    1600,
                    12345,
                )
            ]
        if "FROM likes" in self.last_query or "FROM like_emojis" in self.last_query:
            return []
        return []


class FakeTopicDetailTalkCursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchone(self):
        if "FROM topics t LEFT JOIN groups" in self.last_query:
            return (
                202,
                "talk",
                "title",
                "2026-05-07T10:00:00.000+0800",
                0,
                0,
                1,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
                0,
                0,
                303,
                "group",
                "paid",
                "bg",
            )
        if "FROM talks" in self.last_query:
            return ("body", 901, "Alice", "A", "a.png", "SH", "owner description")
        if "FROM articles" in self.last_query:
            return ("article title", 401, "article-url", "inline-url")
        return None

    def fetchall(self):
        if "FROM images WHERE topic_id = ?" in self.last_query and "comment_id IS NULL" in self.last_query:
            return [
                (
                    701,
                    "image",
                    "thumb.jpg",
                    100,
                    80,
                    "large.jpg",
                    1000,
                    800,
                    "origin.jpg",
                    2000,
                    1600,
                    12345,
                )
            ]
        if "FROM topic_files tf" in self.last_query:
            return [
                (
                    501,
                    "memo.pdf",
                    "hash-1",
                    123,
                    0,
                    7,
                    "2026-05-07T09:00:00.000+0800",
                )
            ]
        if "FROM likes" in self.last_query or "FROM comments c" in self.last_query or "FROM like_emojis" in self.last_query:
            return []
        return []


class FakeTopicDetailEngagementCursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchone(self):
        if "FROM topics t LEFT JOIN groups" in self.last_query:
            return (
                202,
                "talk",
                "title",
                "2026-05-07T10:00:00.000+0800",
                0,
                0,
                2,
                1,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
                0,
                0,
                303,
                "group",
                "paid",
                "bg",
            )
        if "FROM talks" in self.last_query:
            return None
        return None

    def fetchall(self):
        if "FROM likes l" in self.last_query:
            return [
                ("2026-05-07T12:00:00.000+0800", 901, "Alice", "a.png"),
                ("2026-05-07T11:00:00.000+0800", 902, "Bob", "b.png"),
            ]
        if "FROM like_emojis" in self.last_query:
            return [("[like]", 3), ("[ok]", 2)]
        if "FROM comments c" in self.last_query:
            return []
        return []


class FakeTopicDetailQACursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchone(self):
        if "FROM topics t LEFT JOIN groups" in self.last_query:
            return (
                202,
                "q&a",
                "title",
                "2026-05-07T10:00:00.000+0800",
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
                "",
                0,
                0,
                303,
                "group",
                "paid",
                "bg",
            )
        if "FROM talks" in self.last_query:
            return None
        if "FROM questions q" in self.last_query:
            return (
                "question text",
                0,
                0,
                7,
                "2026-01-01T00:00:00.000+0800",
                "active",
                "question owner location",
                901,
                "Question Owner",
                "QO",
                "owner.png",
                "SH",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        if "FROM answers a" in self.last_query:
            return ("answer text", 902, "Answer Owner", "AO", "answer.png", "BJ", "answer owner")
        return None

    def fetchall(self):
        if "FROM likes l" in self.last_query or "FROM comments c" in self.last_query or "FROM like_emojis" in self.last_query:
            return []
        return []


class ZSXQDatabaseHelperTests(unittest.TestCase):
    def test_build_pagination_calculates_pages(self):
        self.assertEqual(
            {'page': 2, 'per_page': 20, 'total': 41, 'pages': 3},
            _build_pagination(2, 20, 41),
        )

    def test_format_tag_row_keeps_existing_fields(self):
        row = (1, "tag", "hid-1", 7, "2026-01-01")

        self.assertEqual(
            {
                'tag_id': 1,
                'tag_name': "tag",
                'hid': "hid-1",
                'topic_count': 7,
                'created_at': "2026-01-01",
            },
            _format_tag_row(row),
        )

    def test_format_tag_topic_row_maps_talk_author(self):
        row = (
            10,
            "title",
            "2026-01-01",
            1,
            2,
            3,
            "talk",
            0,
            1,
            None,
            None,
            "body",
            99,
            "author",
            "avatar.png",
        )

        topic = _format_tag_topic_row(row)

        self.assertEqual(10, topic["topic_id"])
        self.assertEqual("body", topic["talk_text"])
        self.assertFalse(topic["digested"])
        self.assertTrue(topic["sticky"])
        self.assertEqual({"user_id": 99, "name": "author", "avatar_url": "avatar.png"}, topic["author"])

    def test_format_tag_topic_row_maps_qa_texts(self):
        row = (
            11,
            "title",
            "2026-01-01",
            1,
            2,
            3,
            "q&a",
            None,
            None,
            "question",
            "",
            None,
            None,
            None,
            None,
        )

        topic = _format_tag_topic_row(row)

        self.assertEqual("question", topic["question_text"])
        self.assertEqual("", topic["answer_text"])
        self.assertNotIn("talk_text", topic)
        self.assertFalse(topic["digested"])
        self.assertFalse(topic["sticky"])

    def test_tag_statement_helpers_preserve_sql_shape_and_params(self):
        lookup_sql, lookup_params = _tag_id_by_name_query(303, "AI")
        self.assertEqual("SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?", lookup_sql)
        self.assertEqual((303, "AI"), lookup_params)

        update_sql, update_params = _update_tag_hid_statement(7, "hid-1")
        self.assertEqual("UPDATE tags SET hid = ? WHERE tag_id = ?", update_sql)
        self.assertEqual(("hid-1", 7), update_params)

        insert_sql, insert_params = _insert_tag_statement(
            303,
            "AI",
            "hid-1",
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO tags (group_id, tag_name, hid, created_at) VALUES (?, ?, ?, ?) RETURNING tag_id",
            " ".join(insert_sql.split()),
        )
        self.assertEqual((303, "AI", "hid-1", "2026-06-12T10:00:00.000+0800"), insert_params)

        topic_tag_sql, topic_tag_params = _insert_topic_tag_statement(
            202,
            7,
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO topic_tags (topic_id, tag_id, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(topic_id, tag_id) DO NOTHING",
            " ".join(topic_tag_sql.split()),
        )
        self.assertEqual((202, 7, "2026-06-12T10:00:00.000+0800"), topic_tag_params)

        count_sql, count_params = _refresh_tag_topic_count_statement(7)
        self.assertEqual(
            "UPDATE tags SET topic_count = ( SELECT COUNT(*) FROM topic_tags WHERE tag_id = ? ) "
            "WHERE tag_id = ?",
            " ".join(count_sql.split()),
        )
        self.assertEqual((7, 7), count_params)

    def test_tag_read_query_helpers_preserve_sql_shape_and_params(self):
        tags_sql, tags_params = _tags_by_group_query(303)
        self.assertEqual(
            "SELECT tag_id, tag_name, hid, topic_count, created_at FROM tags "
            "WHERE group_id = ? ORDER BY topic_count DESC, tag_name ASC",
            " ".join(tags_sql.split()),
        )
        self.assertEqual((303,), tags_params)

        topics_sql, topics_params = _topics_by_tag_query(7, 5, 10)
        self.assertEqual(
            "SELECT t.topic_id, t.title, t.create_time, t.likes_count, t.comments_count, "
            "t.reading_count, t.type, t.digested, t.sticky, q.text as question_text, "
            "a.text as answer_text, tk.text as talk_text, u.user_id, u.name, u.avatar_url "
            "FROM topics t INNER JOIN topic_tags tt ON t.topic_id = tt.topic_id "
            "LEFT JOIN questions q ON t.topic_id = q.topic_id "
            "LEFT JOIN answers a ON t.topic_id = a.topic_id "
            "LEFT JOIN talks tk ON t.topic_id = tk.topic_id "
            "LEFT JOIN users u ON tk.owner_user_id = u.user_id "
            "WHERE tt.tag_id = ? ORDER BY t.create_time DESC LIMIT ? OFFSET ?",
            " ".join(topics_sql.split()),
        )
        self.assertEqual((7, 5, 10), topics_params)

        count_sql, count_params = _topic_count_by_tag_query(7)
        self.assertEqual(
            "SELECT COUNT(*) FROM topic_tags WHERE tag_id = ?",
            " ".join(count_sql.split()),
        )
        self.assertEqual((7,), count_params)

    def test_group_and_user_insert_statement_helpers_preserve_sql_shape_and_params(self):
        group_sql, group_params = _group_insert_statement(
            {
                "group_id": 303,
                "name": "group",
                "type": "paid",
                "background_url": "bg.png",
            },
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO groups (group_id, name, type, background_url, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(group_id) DO UPDATE SET "
            "name = excluded.name, type = excluded.type, background_url = excluded.background_url, "
            "created_at = excluded.created_at",
            " ".join(group_sql.split()),
        )
        self.assertEqual((303, "group", "paid", "bg.png", "2026-06-12T10:00:00.000+0800"), group_params)

        user_sql, user_params = _user_insert_statement(
            {
                "user_id": 901,
                "name": "Alice",
                "alias": "A",
                "avatar_url": "a.png",
                "location": "SH",
                "description": "owner",
                "ai_comment_url": "ai-url",
            },
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO users (user_id, name, alias, avatar_url, location, description, ai_comment_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "name = excluded.name, alias = excluded.alias, avatar_url = excluded.avatar_url, "
            "location = excluded.location, description = excluded.description, "
            "ai_comment_url = excluded.ai_comment_url, created_at = excluded.created_at",
            " ".join(user_sql.split()),
        )
        self.assertEqual(
            (901, "Alice", "A", "a.png", "SH", "owner", "ai-url", "2026-06-12T10:00:00.000+0800"),
            user_params,
        )

    def test_topic_insert_statement_helper_preserves_sql_shape_and_params(self):
        topic_sql, topic_params = _topic_insert_statement(
            {
                "topic_id": 202,
                "group": {"group_id": 303},
                "type": "talk",
                "title": "title",
                "create_time": "2026-05-07T10:00:00.000+0800",
                "digested": True,
                "sticky": True,
                "likes_count": 1,
                "tourist_likes_count": 2,
                "rewards_count": 3,
                "comments_count": 4,
                "reading_count": 5,
                "readers_count": 6,
                "answered": True,
                "silenced": True,
                "annotation": "note",
                "user_liked": True,
                "user_subscribed": True,
            },
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO topics (topic_id, group_id, type, title, create_time, digested, sticky, "
            "likes_count, tourist_likes_count, rewards_count, comments_count, reading_count, "
            "readers_count, answered, silenced, annotation, user_liked, user_subscribed, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(topic_id) DO UPDATE SET group_id = excluded.group_id, type = excluded.type, "
            "title = excluded.title, create_time = excluded.create_time, digested = excluded.digested, "
            "sticky = excluded.sticky, likes_count = excluded.likes_count, "
            "tourist_likes_count = excluded.tourist_likes_count, rewards_count = excluded.rewards_count, "
            "comments_count = excluded.comments_count, reading_count = excluded.reading_count, "
            "readers_count = excluded.readers_count, answered = excluded.answered, "
            "silenced = excluded.silenced, annotation = excluded.annotation, "
            "user_liked = excluded.user_liked, user_subscribed = excluded.user_subscribed, "
            "imported_at = excluded.imported_at",
            " ".join(topic_sql.split()),
        )
        self.assertEqual(
            (
                202,
                303,
                "talk",
                "title",
                "2026-05-07T10:00:00.000+0800",
                True,
                True,
                1,
                2,
                3,
                4,
                5,
                6,
                True,
                True,
                "note",
                True,
                True,
                "2026-06-12T10:00:00.000+0800",
            ),
            topic_params,
        )

    def test_topic_stats_update_statement_helper_preserves_sql_shape_and_params(self):
        sql, params = _topic_stats_update_statement(
            {
                "likes_count": 1,
                "tourist_likes_count": 2,
                "rewards_count": 3,
                "comments_count": 4,
                "reading_count": 5,
                "readers_count": 6,
                "digested": True,
                "sticky": True,
                "user_specific": {"liked": True, "subscribed": True},
            },
            202,
            303,
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "UPDATE topics SET likes_count = ?, tourist_likes_count = ?, rewards_count = ?, "
            "comments_count = ?, reading_count = ?, readers_count = ?, digested = ?, sticky = ?, "
            "user_liked = ?, user_subscribed = ?, imported_at = ? WHERE topic_id = ? "
            "AND (? IS NULL OR group_id = ?)",
            " ".join(sql.split()),
        )
        self.assertEqual(
            (
                1,
                2,
                3,
                4,
                5,
                6,
                True,
                True,
                True,
                True,
                "2026-06-12T10:00:00.000+0800",
                202,
                303,
                303,
            ),
            params,
        )

    def test_talk_insert_statement_helper_preserves_sql_shape_and_params(self):
        sql, params = _talk_insert_statement(
            202,
            {"owner": {"user_id": 901}, "text": "body"},
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO talks (topic_id, owner_user_id, text, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id) DO UPDATE SET "
            "owner_user_id = excluded.owner_user_id, text = excluded.text, "
            "created_at = excluded.created_at",
            " ".join(sql.split()),
        )
        self.assertEqual((202, 901, "body", "2026-06-12T10:00:00.000+0800"), params)

    def test_image_insert_statement_helper_preserves_sql_shape_and_default_params(self):
        sql, params = _image_insert_statement(
            202,
            {
                "image_id": 701,
                "type": "image",
                "thumbnail": {"url": "thumb.jpg"},
                "large": {"url": "large.jpg"},
                "original": {"url": "origin.jpg"},
            },
            None,
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO images (image_id, topic_id, comment_id, type, thumbnail_url, "
            "thumbnail_width, thumbnail_height, large_url, large_width, large_height, "
            "original_url, original_width, original_height, original_size, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(image_id) DO UPDATE SET topic_id = excluded.topic_id, "
            "comment_id = excluded.comment_id, type = excluded.type, "
            "thumbnail_url = excluded.thumbnail_url, thumbnail_width = excluded.thumbnail_width, "
            "thumbnail_height = excluded.thumbnail_height, large_url = excluded.large_url, "
            "large_width = excluded.large_width, large_height = excluded.large_height, "
            "original_url = excluded.original_url, original_width = excluded.original_width, "
            "original_height = excluded.original_height, original_size = excluded.original_size, "
            "created_at = excluded.created_at",
            " ".join(sql.split()),
        )
        self.assertEqual(
            (
                701,
                202,
                None,
                "image",
                "thumb.jpg",
                None,
                None,
                "large.jpg",
                None,
                None,
                "origin.jpg",
                None,
                None,
                None,
                "2026-06-12T10:00:00.000+0800",
            ),
            params,
        )

        _comment_sql, comment_params = _image_insert_statement(
            202,
            {"image_id": 702},
            11,
            "2026-06-12T10:00:00.000+0800",
            missing_numeric_default=0,
        )
        self.assertEqual(
            (
                702,
                202,
                11,
                "",
                "",
                0,
                0,
                "",
                0,
                0,
                "",
                0,
                0,
                0,
                "2026-06-12T10:00:00.000+0800",
            ),
            comment_params,
        )

    def test_like_statement_helpers_preserve_sql_shape_and_params(self):
        self.assertEqual(
            ("DELETE FROM latest_likes WHERE topic_id = ?", (202,)),
            (
                " ".join(_delete_latest_likes_statement(202)[0].split()),
                _delete_latest_likes_statement(202)[1],
            ),
        )

        like_sql, like_params = _like_insert_statement(
            202,
            901,
            {"create_time": "2026-01-01T10:00:00.000+0800"},
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO likes (topic_id, user_id, create_time, imported_at) VALUES (?, ?, ?, ?)",
            " ".join(like_sql.split()),
        )
        self.assertEqual(
            (202, 901, "2026-01-01T10:00:00.000+0800", "2026-06-12T10:00:00.000+0800"),
            like_params,
        )

        latest_sql, latest_params = _latest_like_insert_statement(
            202,
            901,
            {},
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO latest_likes (topic_id, owner_user_id, create_time, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id, owner_user_id, create_time) "
            "DO UPDATE SET created_at = excluded.created_at",
            " ".join(latest_sql.split()),
        )
        self.assertEqual((202, 901, "", "2026-06-12T10:00:00.000+0800"), latest_params)

    def test_replace_file_topic_relation_deletes_then_inserts(self):
        file_db = FakeFileDatabase()

        rowcount = _replace_file_topic_relation(file_db, 101, 202)

        self.assertEqual(1, rowcount)
        self.assertEqual(
            [
                (
                    "DELETE FROM file_topic_relations WHERE file_id = ? AND topic_id = ?",
                    (101, 202),
                ),
                (
                    "INSERT INTO file_topic_relations (file_id, topic_id) VALUES (?, ?) ON CONFLICT(file_id, topic_id) DO NOTHING",
                    (101, 202),
                ),
            ],
            file_db.cursor.calls,
        )

    def test_upsert_core_file_uses_current_cursor(self):
        cursor = FakeCursor()

        file_id = _upsert_core_file(
            cursor,
            155,
            202,
            {
                "file_id": 101,
                "name": "memo.pdf",
                "hash": "abc",
                "size": 12,
                "duration": 0,
                "download_count": 3,
                "create_time": "2026-05-07T12:00:00.000+0800",
            },
        )

        self.assertEqual(101, file_id)
        self.assertEqual(1, len(cursor.calls))
        query, params = cursor.calls[0]
        self.assertIn("INSERT INTO files", query)
        self.assertIn("ON CONFLICT(file_id) DO UPDATE SET", query)
        self.assertEqual((101, 155, 202, "memo.pdf", "abc", 12, 0, 3, "2026-05-07T12:00:00.000+0800"), params)

    def test_topic_file_payload_from_row_maps_backfill_columns(self):
        row = (202, 101, "memo.pdf", "abc", 12, 0, 3, "2026-05-07T12:00:00.000+0800")

        self.assertEqual(
            {
                "file_id": 101,
                "name": "memo.pdf",
                "hash": "abc",
                "size": 12,
                "duration": 0,
                "download_count": 3,
                "create_time": "2026-05-07T12:00:00.000+0800",
            },
            _topic_file_payload_from_row(row),
        )

    def test_backfill_topic_files_to_core_tables_uses_current_database_cursor(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        row = (
            202,
            101,
            "memo.pdf",
            "abc",
            12,
            0,
            3,
            "2026-05-07T12:00:00.000+0800",
            303,
            "talk",
            "title",
            "",
            "2026-05-07T10:00:00.000+0800",
            1,
            0,
            0,
            2,
            3,
            4,
            False,
            False,
            False,
            False,
            "group",
            "paid",
            "bg",
        )
        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeBackfillCursor([row])
        db.conn = FakeConnection()
        db.group_id = "303"

        stats = ZSXQDatabase.backfill_topic_files_to_core_tables(db, batch_size=1)

        self.assertEqual({"scanned": 1, "new_files": 1, "relations": 1, "topic_files": 1}, stats)
        self.assertGreaterEqual(db.conn.commits, 1)
        calls = "\n".join(sql for sql, _params in db.cursor.calls)
        self.assertIn("INSERT INTO groups", calls)
        self.assertIn("INSERT INTO files", calls)
        self.assertIn("INSERT INTO file_topic_relations", calls)

    def test_group_id_param_casts_numeric_ids_for_scoped_queries(self):
        self.assertEqual(155, _group_id_param("155"))
        self.assertEqual("group-x", _group_id_param("group-x"))
        self.assertEqual("", _group_id_param(None))

    def test_nullable_group_id_param_uses_none_for_unscoped_queries(self):
        self.assertIsNone(_nullable_group_id_param(None))
        self.assertIsNone(_nullable_group_id_param(""))
        self.assertEqual(155, _nullable_group_id_param("155"))
        self.assertEqual("group-x", _nullable_group_id_param("group-x"))

    def test_topic_detail_scope_preserves_existing_group_id_semantics(self):
        self.assertEqual(
            (None, "t.topic_id = ?", [202]),
            _topic_detail_scope(202, None),
        )
        self.assertEqual(
            (303, "t.topic_id = ? AND t.group_id = ?", [202, 303]),
            _topic_detail_scope(202, "303"),
        )
        self.assertEqual(
            ("", "t.topic_id = ? AND t.group_id = ?", [202, ""]),
            _topic_detail_scope(202, ""),
        )

    def test_existence_query_helpers_preserve_group_id_param_semantics(self):
        topic_sql, topic_params = _topic_exists_query(202, "303")
        self.assertEqual(
            "SELECT 1 FROM topics WHERE topic_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1",
            topic_sql,
        )
        self.assertEqual((202, 303, 303), topic_params)
        self.assertEqual((202, "", ""), _topic_exists_query(202, None)[1])

        file_sql, file_params = _file_exists_query(101, "303")
        self.assertEqual(
            "SELECT 1 FROM files WHERE file_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1",
            file_sql,
        )
        self.assertEqual((101, 303, 303), file_params)
        self.assertEqual((101, "", ""), _file_exists_query(101, None)[1])

        group_sql, group_params = _topic_group_id_query(202)
        self.assertEqual("SELECT group_id FROM topics WHERE topic_id = ? LIMIT 1", group_sql)
        self.assertEqual((202,), group_params)

        create_time_sql, create_time_params = _topic_create_time_by_id_query(202)
        self.assertEqual("SELECT create_time FROM topics WHERE topic_id = ?", create_time_sql)
        self.assertEqual((202,), create_time_params)

    def test_topic_timestamp_query_helpers_preserve_existing_scope_semantics(self):
        newest_sql, newest_params = _newest_topic_create_time_query(None, nullable_scope=True)
        self.assertIn("ORDER BY create_time DESC LIMIT 1", " ".join(newest_sql.split()))
        self.assertEqual((None, None), newest_params)

        oldest_sql, oldest_params = _oldest_topic_create_time_query(None)
        self.assertIn("ORDER BY create_time ASC LIMIT 1", " ".join(oldest_sql.split()))
        self.assertEqual(("", ""), oldest_params)

        count_sql, count_params = _topic_count_query("303")
        self.assertEqual("SELECT COUNT(*) FROM topics WHERE (? IS NULL OR group_id = ?)", count_sql)
        self.assertEqual((303, 303), count_params)
        self.assertEqual((None, None), _topic_count_query(None)[1])

    def test_timestamp_range_info_uses_nullable_scope_and_preserves_response_shape(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTimestampCursor([("new-time",), ("old-time",), (2,)])
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = None

        self.assertEqual(
            {
                "newest_time": "new-time",
                "oldest_time": "old-time",
                "newest_timestamp": "new-time",
                "oldest_timestamp": "old-time",
                "total_topics": 2,
                "has_data": True,
            },
            ZSXQDatabase.get_timestamp_range_info(db),
        )
        self.assertEqual(
            [
                (
                    "SELECT create_time FROM topics WHERE (? IS NULL OR group_id = ?) "
                    "AND create_time IS NOT NULL AND create_time != '' ORDER BY create_time DESC LIMIT 1",
                    (None, None),
                ),
                (
                    "SELECT create_time FROM topics WHERE (? IS NULL OR group_id = ?) "
                    "AND create_time IS NOT NULL AND create_time != '' ORDER BY create_time ASC LIMIT 1",
                    (None, None),
                ),
                ("SELECT COUNT(*) FROM topics WHERE (? IS NULL OR group_id = ?)", (None, None)),
            ],
            cursor.calls,
        )

    def test_topic_timestamp_methods_keep_legacy_group_scope_for_empty_group(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        newest_db = object.__new__(ZSXQDatabase)
        newest_db.cursor = FakeTimestampCursor([("new-time",)])
        newest_db.group_id = None
        self.assertEqual("new-time", ZSXQDatabase.get_newest_topic_timestamp(newest_db))
        self.assertEqual(("", ""), newest_db.cursor.calls[0][1])

        oldest_db = object.__new__(ZSXQDatabase)
        oldest_db.cursor = FakeTimestampCursor([("old-time",)])
        oldest_db.group_id = None
        self.assertEqual("old-time", ZSXQDatabase.get_oldest_topic_timestamp(oldest_db))
        self.assertEqual(("", ""), oldest_db.cursor.calls[0][1])

    def test_import_topic_data_existing_topic_preserves_skip_and_file_sync(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeCursor()
        cursor.row = (1,)
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.conn = FakeConnection()
        db.group_id = "303"
        synced = []
        db._sync_topic_files_to_core_tables = lambda topic, files: synced.append((topic, files))

        topic_data = {"topic_id": 202, "talk": {"files": [{"file_id": 101}]}}
        with patch("builtins.print"):
            self.assertTrue(ZSXQDatabase.import_topic_data(db, topic_data))

        self.assertEqual(
            [
                (
                    "SELECT 1 FROM topics WHERE topic_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1",
                    (202, 303, 303),
                )
            ],
            cursor.calls,
        )
        self.assertEqual([(topic_data, [{"file_id": 101}])], synced)
        self.assertEqual(0, db.conn.commits)
        self.assertEqual(0, db.conn.rollbacks)

    def test_upsert_group_and_user_preserve_skip_and_insert_params(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        group_db = object.__new__(ZSXQDatabase)
        group_db.cursor = FakeCursor()
        ZSXQDatabase._upsert_group(group_db, {})
        self.assertEqual([], group_db.cursor.calls)

        ZSXQDatabase._upsert_group(
            group_db,
            {
                "group_id": 303,
                "name": "group",
                "type": "paid",
                "background_url": "bg.png",
            },
        )
        group_sql, group_params = group_db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO groups (group_id, name, type, background_url, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(group_id) DO UPDATE SET "
            "name = excluded.name, type = excluded.type, background_url = excluded.background_url, "
            "created_at = excluded.created_at",
            group_sql,
        )
        self.assertEqual((303, "group", "paid", "bg.png"), group_params[:4])
        self.assertRegex(group_params[4], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        user_db = object.__new__(ZSXQDatabase)
        user_db.cursor = FakeCursor()
        ZSXQDatabase._upsert_user(user_db, {})
        self.assertEqual([], user_db.cursor.calls)

        ZSXQDatabase._upsert_user(user_db, {"user_id": 901, "name": "Alice"})
        user_sql, user_params = user_db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO users (user_id, name, alias, avatar_url, location, description, ai_comment_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "name = excluded.name, alias = excluded.alias, avatar_url = excluded.avatar_url, "
            "location = excluded.location, description = excluded.description, "
            "ai_comment_url = excluded.ai_comment_url, created_at = excluded.created_at",
            user_sql,
        )
        self.assertEqual((901, "Alice", "", "", "", "", ""), user_params[:7])
        self.assertRegex(user_params[7], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_upsert_topic_preserves_skip_defaults_and_insert_params(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_topic(db, {})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._upsert_topic(db, {"topic_id": 202, "title": "title"})

        topic_sql, topic_params = db.cursor.calls[0]
        self.assertIn("INSERT INTO topics", topic_sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", topic_sql)
        self.assertEqual(
            (
                202,
                "",
                "",
                "title",
                "",
                False,
                False,
                0,
                0,
                0,
                0,
                0,
                0,
                False,
                False,
                "",
                False,
                False,
            ),
            topic_params[:18],
        )
        self.assertRegex(topic_params[18], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_upsert_talk_preserves_skip_and_insert_params(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_talk(db, 202, {})
        ZSXQDatabase._upsert_talk(db, 202, {"owner": {}})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._upsert_talk(db, 202, {"owner": {"user_id": 901}, "text": "body"})

        talk_sql, talk_params = db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO talks (topic_id, owner_user_id, text, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id) DO UPDATE SET "
            "owner_user_id = excluded.owner_user_id, text = excluded.text, "
            "created_at = excluded.created_at",
            talk_sql,
        )
        self.assertEqual((202, 901, "body"), talk_params[:3])
        self.assertRegex(talk_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_image_writes_preserve_skip_paths_and_distinct_numeric_defaults(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_image(db, 202, {})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._upsert_image(
            db,
            202,
            {
                "image_id": 701,
                "type": "image",
                "thumbnail": {"url": "thumb.jpg"},
                "large": {"url": "large.jpg"},
                "original": {"url": "origin.jpg"},
            },
        )
        image_sql, image_params = db.cursor.calls[0]
        self.assertIn("INSERT INTO images", image_sql)
        self.assertIn("ON CONFLICT(image_id) DO UPDATE SET", image_sql)
        self.assertEqual(
            (
                701,
                202,
                None,
                "image",
                "thumb.jpg",
                None,
                None,
                "large.jpg",
                None,
                None,
                "origin.jpg",
                None,
                None,
                None,
            ),
            image_params[:14],
        )
        self.assertRegex(image_params[14], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        comment_db = object.__new__(ZSXQDatabase)
        comment_db.cursor = FakeCursor()

        ZSXQDatabase._import_comment_images(comment_db, 202, 11, [{}, {"image_id": 702}])

        comment_sql, comment_params = comment_db.cursor.calls[0]
        self.assertIn("INSERT INTO images", comment_sql)
        self.assertEqual(
            (
                702,
                202,
                11,
                "",
                "",
                0,
                0,
                "",
                0,
                0,
                "",
                0,
                0,
                0,
            ),
            comment_params[:14],
        )
        self.assertRegex(comment_params[14], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_import_likes_preserves_delete_skip_and_insert_order(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._import_likes(db, 202, {})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._import_likes(db, 202, {"latest_likes": []})
        self.assertEqual([("DELETE FROM latest_likes WHERE topic_id = ?", (202,))], db.cursor.calls)

        active_db = object.__new__(ZSXQDatabase)
        active_db.cursor = FakeCursor()

        ZSXQDatabase._import_likes(
            active_db,
            202,
            {
                "latest_likes": [
                    {"owner": {}, "create_time": "skipped"},
                    {"owner": {"user_id": 901}, "create_time": "2026-01-01T10:00:00.000+0800"},
                ]
            },
        )

        self.assertEqual("DELETE FROM latest_likes WHERE topic_id = ?", active_db.cursor.calls[0][0])
        self.assertEqual((202,), active_db.cursor.calls[0][1])

        likes_sql, likes_params = active_db.cursor.calls[1]
        self.assertEqual(
            "INSERT INTO likes (topic_id, user_id, create_time, imported_at) VALUES (?, ?, ?, ?)",
            likes_sql,
        )
        self.assertEqual((202, 901, "2026-01-01T10:00:00.000+0800"), likes_params[:3])
        self.assertRegex(likes_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        latest_sql, latest_params = active_db.cursor.calls[2]
        self.assertEqual(
            "INSERT INTO latest_likes (topic_id, owner_user_id, create_time, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id, owner_user_id, create_time) "
            "DO UPDATE SET created_at = excluded.created_at",
            latest_sql,
        )
        self.assertEqual((202, 901, "2026-01-01T10:00:00.000+0800"), latest_params[:3])
        self.assertRegex(latest_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_update_topic_stats_preserves_skip_rowcount_and_exception_branches(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        empty_db = object.__new__(ZSXQDatabase)
        empty_db.cursor = FakeCursor()
        empty_db.group_id = "303"
        self.assertFalse(ZSXQDatabase.update_topic_stats(empty_db, {}))
        self.assertEqual([], empty_db.cursor.calls)

        success_db = object.__new__(ZSXQDatabase)
        success_db.cursor = FakeCursor()
        success_db.cursor.rowcount = 1
        success_db.group_id = "303"
        self.assertTrue(
            ZSXQDatabase.update_topic_stats(
                success_db,
                {
                    "topic_id": 202,
                    "likes_count": 1,
                    "tourist_likes_count": 2,
                    "rewards_count": 3,
                    "comments_count": 4,
                    "reading_count": 5,
                    "readers_count": 6,
                    "digested": True,
                    "sticky": True,
                    "user_specific": {"liked": True, "subscribed": True},
                },
            )
        )
        stats_sql, stats_params = success_db.cursor.calls[0]
        self.assertEqual(
            "UPDATE topics SET likes_count = ?, tourist_likes_count = ?, rewards_count = ?, "
            "comments_count = ?, reading_count = ?, readers_count = ?, digested = ?, sticky = ?, "
            "user_liked = ?, user_subscribed = ?, imported_at = ? WHERE topic_id = ? "
            "AND (? IS NULL OR group_id = ?)",
            stats_sql,
        )
        self.assertEqual((1, 2, 3, 4, 5, 6, True, True, True, True), stats_params[:10])
        self.assertRegex(stats_params[10], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")
        self.assertEqual((202, 303, 303), stats_params[11:])

        missing_db = object.__new__(ZSXQDatabase)
        missing_db.cursor = FakeCursor()
        missing_db.group_id = None
        with patch("builtins.print") as mocked_print:
            self.assertFalse(ZSXQDatabase.update_topic_stats(missing_db, {"topic_id": 202}))
        mocked_print.assert_called_once_with("警告：话题 202 不存在，无法更新")
        self.assertEqual((202, "", ""), missing_db.cursor.calls[0][1][11:])

        failing_db = object.__new__(ZSXQDatabase)
        failing_db.cursor = FakeFailingExecuteCursor()
        failing_db.group_id = "303"
        with patch("builtins.print") as mocked_print, patch("traceback.print_exc") as mocked_traceback:
            self.assertFalse(ZSXQDatabase.update_topic_stats(failing_db, {"topic_id": 202}))
        mocked_print.assert_called_once()
        mocked_traceback.assert_called_once()

    def test_resolve_topic_group_id_preserves_explicit_scope_lookup_and_exception_fallback(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        class GroupLookupCursor:
            def __init__(self, row=None, raises=False):
                self.calls = []
                self.row = row
                self.raises = raises

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                if self.raises:
                    raise RuntimeError("temporary storage failure")
                return self

            def fetchone(self):
                return self.row

        explicit_db = object.__new__(ZSXQDatabase)
        explicit_db.cursor = GroupLookupCursor((999,))
        explicit_db.group_id = "303"
        self.assertEqual(404, ZSXQDatabase._resolve_topic_group_id(explicit_db, 202, explicit_group_id="404"))
        self.assertEqual([], explicit_db.cursor.calls)

        scoped_db = object.__new__(ZSXQDatabase)
        scoped_db.cursor = GroupLookupCursor((999,))
        scoped_db.group_id = "303"
        self.assertEqual(303, ZSXQDatabase._resolve_topic_group_id(scoped_db, 202))
        self.assertEqual([], scoped_db.cursor.calls)

        lookup_db = object.__new__(ZSXQDatabase)
        lookup_db.cursor = GroupLookupCursor((303,))
        lookup_db.group_id = None
        self.assertEqual(303, ZSXQDatabase._resolve_topic_group_id(lookup_db, 202))
        self.assertEqual(
            [("SELECT group_id FROM topics WHERE topic_id = ? LIMIT 1", (202,))],
            lookup_db.cursor.calls,
        )

        missing_db = object.__new__(ZSXQDatabase)
        missing_db.cursor = GroupLookupCursor(None)
        missing_db.group_id = None
        self.assertIsNone(ZSXQDatabase._resolve_topic_group_id(missing_db, 202))

        failing_db = object.__new__(ZSXQDatabase)
        failing_db.cursor = GroupLookupCursor(raises=True)
        failing_db.group_id = None
        self.assertIsNone(ZSXQDatabase._resolve_topic_group_id(failing_db, 202))

    def test_upsert_comment_writes_group_id_from_runtime_scope(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()
        db.group_id = "303"

        ZSXQDatabase._upsert_comment(db, 202, {"comment_id": 101, "text": "ok"})

        sql, params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO comments", sql)
        self.assertIn("ON CONFLICT(comment_id) DO UPDATE SET", sql)
        self.assertIn("comment_id, group_id, topic_id", sql)
        self.assertEqual((101, 303, 202), params[:3])

    def test_upsert_article_uses_topic_create_time_and_preserves_empty_payload_skip(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        empty_db = object.__new__(ZSXQDatabase)
        empty_db.cursor = FakeCursor()
        ZSXQDatabase._upsert_article(empty_db, 202, {})
        self.assertEqual([], empty_db.cursor.calls)

        article_db = object.__new__(ZSXQDatabase)
        article_db.cursor = FakeCursor()
        article_db.cursor.row = ("2026-05-07T10:00:00.000+0800",)

        ZSXQDatabase._upsert_article(
            article_db,
            202,
            {
                "title": "article title",
                "article_id": "401",
                "article_url": "article-url",
                "inline_article_url": "inline-url",
            },
        )

        self.assertEqual(
            ("SELECT create_time FROM topics WHERE topic_id = ?", (202,)),
            article_db.cursor.calls[0],
        )
        article_sql, article_params = article_db.cursor.calls[1]
        self.assertIn("INSERT INTO articles", article_sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", article_sql)
        self.assertEqual(
            (
                202,
                "article title",
                "401",
                "article-url",
                "inline-url",
                "2026-05-07T10:00:00.000+0800",
            ),
            article_params,
        )

    def test_upsert_tag_preserves_existing_update_insert_and_missing_return_branches(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        existing_db = object.__new__(ZSXQDatabase)
        existing_db.cursor = FakeSequenceCursor([(7,)])
        self.assertEqual(7, ZSXQDatabase._upsert_tag(existing_db, 303, "AI", "hid-1"))
        self.assertEqual(
            [
                ("SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?", (303, "AI")),
                ("UPDATE tags SET hid = ? WHERE tag_id = ?", ("hid-1", 7)),
            ],
            existing_db.cursor.calls,
        )

        no_hid_db = object.__new__(ZSXQDatabase)
        no_hid_db.cursor = FakeSequenceCursor([(8,)])
        self.assertEqual(8, ZSXQDatabase._upsert_tag(no_hid_db, 303, "AI", None))
        self.assertEqual(
            [("SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?", (303, "AI"))],
            no_hid_db.cursor.calls,
        )

        new_db = object.__new__(ZSXQDatabase)
        new_db.cursor = FakeSequenceCursor([None, (9,)])
        self.assertEqual(9, ZSXQDatabase._upsert_tag(new_db, 303, "AI", "hid-2"))
        self.assertEqual("SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?", new_db.cursor.calls[0][0])
        insert_sql, insert_params = new_db.cursor.calls[1]
        self.assertEqual(
            "INSERT INTO tags (group_id, tag_name, hid, created_at) VALUES (?, ?, ?, ?) RETURNING tag_id",
            insert_sql,
        )
        self.assertEqual((303, "AI", "hid-2"), insert_params[:3])
        self.assertRegex(insert_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        missing_return_db = object.__new__(ZSXQDatabase)
        missing_return_db.cursor = FakeSequenceCursor([None, None])
        self.assertIsNone(ZSXQDatabase._upsert_tag(missing_return_db, 303, "AI", "hid-3"))

    def test_link_topic_tag_inserts_relation_refreshes_count_and_swallows_errors(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._link_topic_tag(db, 202, 7)

        self.assertEqual(2, len(db.cursor.calls))
        insert_sql, insert_params = db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO topic_tags (topic_id, tag_id, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(topic_id, tag_id) DO NOTHING",
            insert_sql,
        )
        self.assertEqual((202, 7), insert_params[:2])
        self.assertRegex(insert_params[2], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")
        self.assertEqual(
            (
                "UPDATE tags SET topic_count = ( SELECT COUNT(*) FROM topic_tags WHERE tag_id = ? ) "
                "WHERE tag_id = ?",
                (7, 7),
            ),
            db.cursor.calls[1],
        )

        failing_db = object.__new__(ZSXQDatabase)
        failing_db.cursor = FakeFailingExecuteCursor()
        with patch("builtins.print") as mocked_print:
            self.assertIsNone(ZSXQDatabase._link_topic_tag(failing_db, 202, 7))
        mocked_print.assert_called_once()
        self.assertEqual(1, len(failing_db.cursor.calls))

    def test_get_tags_by_group_uses_helper_query_and_preserves_response_shape(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeTagReadCursor(
            tag_rows=[(7, "AI", "hid-1", 12, "2026-06-12T10:00:00.000+0800")]
        )

        self.assertEqual(
            [
                {
                    "tag_id": 7,
                    "tag_name": "AI",
                    "hid": "hid-1",
                    "topic_count": 12,
                    "created_at": "2026-06-12T10:00:00.000+0800",
                }
            ],
            ZSXQDatabase.get_tags_by_group(db, 303),
        )
        self.assertEqual(
            [
                (
                    "SELECT tag_id, tag_name, hid, topic_count, created_at FROM tags "
                    "WHERE group_id = ? ORDER BY topic_count DESC, tag_name ASC",
                    (303,),
                )
            ],
            db.cursor.calls,
        )

    def test_get_topics_by_tag_uses_helper_queries_and_preserves_pagination(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeTagReadCursor(
            topic_rows=[
                (
                    202,
                    "title",
                    "2026-05-07",
                    1,
                    2,
                    3,
                    "talk",
                    0,
                    1,
                    None,
                    None,
                    "body",
                    901,
                    "Alice",
                    "a.png",
                )
            ],
            total=12,
        )

        self.assertEqual(
            {
                "topics": [
                    {
                        "topic_id": 202,
                        "title": "title",
                        "create_time": "2026-05-07",
                        "likes_count": 1,
                        "comments_count": 2,
                        "reading_count": 3,
                        "type": "talk",
                        "digested": False,
                        "sticky": True,
                        "talk_text": "body",
                        "author": {"user_id": 901, "name": "Alice", "avatar_url": "a.png"},
                    }
                ],
                "pagination": {"page": 2, "per_page": 5, "total": 12, "pages": 3},
            },
            ZSXQDatabase.get_topics_by_tag(db, 7, page=2, per_page=5),
        )
        self.assertEqual((7, 5, 5), db.cursor.calls[0][1])
        self.assertIn("FROM topics t INNER JOIN topic_tags tt", db.cursor.calls[0][0])
        self.assertEqual(("SELECT COUNT(*) FROM topic_tags WHERE tag_id = ?", (7,)), db.cursor.calls[1])

    def test_get_topics_by_tag_preserves_exception_fallback_shape(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeTagReadCursor(raises=True)

        with patch("builtins.print") as mocked_print:
            result = ZSXQDatabase.get_topics_by_tag(db, 7, page=2, per_page=5)

        self.assertEqual({"topics": [], "pagination": {"page": 2, "per_page": 5, "total": 0, "pages": 0}}, result)
        mocked_print.assert_called_once()
        self.assertEqual(1, len(db.cursor.calls))

    def test_content_child_writes_use_explicit_unique_semantics(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_talk(db, 202, {"owner": {"user_id": 9}, "text": "body"})
        talk_sql, _talk_params = db.cursor.calls[-1]
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", talk_sql)

        ZSXQDatabase._import_likes(
            db,
            202,
            {"latest_likes": [{"owner": {"user_id": 9}, "create_time": "2026-01-01"}]},
        )
        calls = "\n".join(sql for sql, _params in db.cursor.calls)
        self.assertIn("DELETE FROM latest_likes WHERE topic_id = ?", calls)
        self.assertIn("ON CONFLICT(topic_id, owner_user_id, create_time) DO UPDATE SET", calls)

        ZSXQDatabase._import_like_emojis(
            db,
            202,
            {"likes_detail": {"emojis": [{"emoji_key": "[ok]", "likes_count": 2}]}},
        )
        emoji_sql, _emoji_params = db.cursor.calls[-1]
        self.assertIn("ON CONFLICT(topic_id, emoji_key) DO UPDATE SET", emoji_sql)

    def test_get_topic_detail_scopes_child_queries_when_group_is_set(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeCursor()
        cursor.row = (
            202,
            "talk",
            "title",
            "2026-05-07T10:00:00.000+0800",
            0,
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            "",
            0,
            0,
            303,
            "group",
            "paid",
            "bg",
        )
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        self.assertEqual(202, detail["topic_id"])
        calls = "\n".join(sql for sql, _params in cursor.calls)
        self.assertIn("WHERE t.topic_id = ? AND t.group_id = ?", calls)
        self.assertIn("AND (? IS NULL OR c.group_id = ?)", calls)
        self.assertIn("topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", calls)

    def test_get_topic_detail_builds_nested_comments_with_images_and_repliee(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTopicDetailCursor()
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        comments = detail["show_comments"]
        self.assertEqual(1, len(comments))
        parent = comments[0]
        self.assertEqual(10, parent["comment_id"])
        self.assertEqual("parent", parent["text"])
        self.assertEqual(1, len(parent["replied_comments"]))
        child = parent["replied_comments"][0]
        self.assertEqual(11, child["comment_id"])
        self.assertEqual(10, child["parent_comment_id"])
        self.assertEqual({"user_id": 901, "name": "Alice", "avatar_url": "a.png"}, child["repliee"])
        self.assertEqual(
            [
                {
                    "image_id": 701,
                    "type": "image",
                    "thumbnail": {"url": "thumb.jpg", "width": 100, "height": 80},
                    "large": {"url": "large.jpg", "width": 1000, "height": 800},
                    "original": {
                        "url": "origin.jpg",
                        "width": 2000,
                        "height": 1600,
                        "size": 12345,
                    },
                }
            ],
            child["images"],
        )
        image_calls = [params for sql, params in cursor.calls if "FROM images WHERE comment_id IN" in sql]
        self.assertEqual([[10, 11, 303, 303]], image_calls)

    def test_get_topic_detail_builds_talk_with_images_files_and_article(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTopicDetailTalkCursor()
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        self.assertEqual(
            {
                "text": "body",
                "owner": {
                    "user_id": 901,
                    "name": "Alice",
                    "alias": "A",
                    "avatar_url": "a.png",
                    "location": "SH",
                    "description": "owner description",
                },
                "images": [
                    {
                        "image_id": 701,
                        "type": "image",
                        "thumbnail": {"url": "thumb.jpg", "width": 100, "height": 80},
                        "large": {"url": "large.jpg", "width": 1000, "height": 800},
                        "original": {
                            "url": "origin.jpg",
                            "width": 2000,
                            "height": 1600,
                            "size": 12345,
                        },
                    }
                ],
                "files": [
                    {
                        "file_id": 501,
                        "name": "memo.pdf",
                        "hash": "hash-1",
                        "size": 123,
                        "duration": 0,
                        "download_count": 7,
                        "create_time": "2026-05-07T09:00:00.000+0800",
                    }
                ],
                "article": {
                    "title": "article title",
                    "article_id": 401,
                    "article_url": "article-url",
                    "inline_article_url": "inline-url",
                },
            },
            detail["talk"],
        )
        scoped_attachment_calls = [
            params
            for sql, params in cursor.calls
            if (
                "FROM images WHERE topic_id = ?" in sql
                or "FROM topic_files tf" in sql
                or "FROM articles" in sql
            )
        ]
        self.assertEqual([(202, 303, 303), (202, 303, 303), (202, 303, 303)], scoped_attachment_calls)

    def test_get_topic_detail_builds_latest_likes_and_like_emojis(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTopicDetailEngagementCursor()
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        self.assertEqual(
            [
                {
                    "create_time": "2026-05-07T12:00:00.000+0800",
                    "owner": {"user_id": 901, "name": "Alice", "avatar_url": "a.png"},
                },
                {
                    "create_time": "2026-05-07T11:00:00.000+0800",
                    "owner": {"user_id": 902, "name": "Bob", "avatar_url": "b.png"},
                },
            ],
            detail["latest_likes"],
        )
        self.assertEqual(
            {"emojis": [{"emoji_key": "[like]", "likes_count": 3}, {"emoji_key": "[ok]", "likes_count": 2}]},
            detail["likes_detail"],
        )
        engagement_calls = [
            params
            for sql, params in cursor.calls
            if "FROM likes l" in sql or "FROM like_emojis" in sql
        ]
        self.assertEqual([(202, 303, 303), (202, 303, 303)], engagement_calls)

    def test_get_topic_detail_builds_question_and_answer_payloads(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTopicDetailQACursor()
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        self.assertEqual(
            {
                "text": "question text",
                "expired": False,
                "anonymous": False,
                "owner_detail": {
                    "questions_count": 7,
                    "estimated_join_time": "2026-01-01T00:00:00.000+0800",
                    "status": "active",
                },
                "owner_location": "question owner location",
                "owner": {
                    "user_id": 901,
                    "name": "Question Owner",
                    "alias": "QO",
                    "avatar_url": "owner.png",
                    "location": "SH",
                    "description": "SH",
                },
            },
            detail["question"],
        )
        self.assertEqual(
            {
                "text": "answer text",
                "owner": {
                    "user_id": 902,
                    "name": "Answer Owner",
                    "alias": "AO",
                    "avatar_url": "answer.png",
                    "location": "BJ",
                    "description": "answer owner",
                },
            },
            detail["answer"],
        )
        qa_calls = [
            params
            for sql, params in cursor.calls
            if "FROM questions q" in sql or "FROM answers a" in sql
        ]
        self.assertEqual([(202, 303, 303), (202, 303, 303)], qa_calls)

    def test_runtime_init_database_does_not_execute_ddl(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        self.assertIsNone(ZSXQDatabase._init_database(db))
        self.assertEqual([], db.cursor.calls)


if __name__ == "__main__":
    unittest.main()
