import unittest

from backend.storage.zsxq_database import (
    _build_pagination,
    _format_tag_row,
    _format_tag_topic_row,
    _group_id_param,
    _nullable_group_id_param,
    _replace_file_topic_relation,
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

    def test_group_id_param_casts_numeric_ids_for_scoped_queries(self):
        self.assertEqual(155, _group_id_param("155"))
        self.assertEqual("group-x", _group_id_param("group-x"))
        self.assertEqual("", _group_id_param(None))

    def test_nullable_group_id_param_uses_none_for_unscoped_queries(self):
        self.assertIsNone(_nullable_group_id_param(None))
        self.assertIsNone(_nullable_group_id_param(""))
        self.assertEqual(155, _nullable_group_id_param("155"))
        self.assertEqual("group-x", _nullable_group_id_param("group-x"))

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

    def test_runtime_init_database_does_not_execute_ddl(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        self.assertIsNone(ZSXQDatabase._init_database(db))
        self.assertEqual([], db.cursor.calls)


if __name__ == "__main__":
    unittest.main()
