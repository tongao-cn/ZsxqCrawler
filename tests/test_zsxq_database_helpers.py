import unittest
from unittest.mock import patch

from backend.storage.zsxq_database import (
    _build_pagination,
    _file_exists_query,
    _format_tag_row,
    _format_tag_topic_row,
    _group_id_param,
    _nullable_group_id_param,
    _replace_file_topic_relation,
    _topic_detail_scope,
    _topic_exists_query,
    _topic_file_payload_from_row,
    _upsert_core_file,
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
