import unittest

from backend.storage.zsxq_file_database import (
    _FILE_AI_ANALYSIS_FIELDS,
    _close_connection,
    _count_tables,
    _file_ai_analysis_params,
    _file_attachment_params,
    _file_download_status_params,
    _file_record_params,
    _group_record_params,
    _new_import_stats,
    _row_to_file_ai_analysis,
    _topic_record_params,
    _user_record_params,
)


class FakeCursor:
    def __init__(self, counts):
        self.counts = counts
        self.executed = []
        self.current_table = None

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT COUNT(*) FROM files"):
            self.current_table = "files"
        elif normalized.startswith("SELECT COUNT(*) FROM topics"):
            self.current_table = "topics"
        elif normalized.startswith("SELECT COUNT(*) FROM talks"):
            self.current_table = "talks"
        else:
            self.current_table = normalized.rsplit(" ", 1)[-1]

    def fetchone(self):
        return (self.counts[self.current_table],)


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeImportDatabase:
    def __init__(self):
        self.calls = []
        self.cursor = self
        self.conn = self
        self.lastrowid = 1

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        if normalized.startswith("INSERT INTO api_responses"):
            self.calls.append(("api_response", params))
        elif normalized.startswith("DELETE FROM file_topic_relations"):
            self.calls.append(("delete_relation", params))
        elif normalized.startswith("INSERT INTO file_topic_relations"):
            self.calls.append(("insert_relation", params))
        return self

    def insert_group(self, group_data):
        self.calls.append(("group", group_data.get("group_id")))
        return group_data.get("group_id")

    def insert_topic(self, topic_data):
        self.calls.append(("topic", topic_data.get("topic_id")))
        return topic_data.get("topic_id")

    def insert_file(self, file_data, group_id=None, topic_id=None):
        self.calls.append(("file", file_data.get("file_id"), group_id, topic_id))
        return file_data.get("file_id")

    def insert_talk(self, topic_id, talk_data):
        self.calls.append(("talk", topic_id))

    def insert_topic_files(self, topic_id, files_data):
        self.calls.append(("topic_files", topic_id, [item.get("file_id") for item in files_data]))

    def commit(self):
        self.calls.append(("commit",))

    def rollback(self):
        self.calls.append(("rollback",))


class FakeAnalysisCursor:
    def __init__(self):
        self.calls = []
        self.row = None

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        return self

    def fetchone(self):
        return self.row


class FakeAnalysisConnection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakeCommentCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        return self

    def fetchone(self):
        return None


class ZSXQFileDatabaseHelperTests(unittest.TestCase):
    def test_new_import_stats_returns_expected_zero_counts(self):
        stats = _new_import_stats()

        self.assertEqual(
            {
                "files": 0,
                "topics": 0,
                "users": 0,
                "groups": 0,
                "images": 0,
                "comments": 0,
                "likes": 0,
                "columns": 0,
                "solutions": 0,
            },
            stats,
        )

    def test_row_to_file_ai_analysis_maps_columns_and_handles_missing_row(self):
        row = tuple(f"value-{index}" for index, _field in enumerate(_FILE_AI_ANALYSIS_FIELDS))

        self.assertIsNone(_row_to_file_ai_analysis(None))
        self.assertEqual(
            dict(zip(_FILE_AI_ANALYSIS_FIELDS, row)),
            _row_to_file_ai_analysis(row),
        )

    def test_file_attachment_params_keep_sql_column_order(self):
        params = _file_attachment_params(
            202,
            {
                "file_id": 101,
                "name": "memo.pdf",
                "hash": "abc",
                "size": 20,
                "duration": 3,
                "download_count": 4,
                "create_time": "2026-06-10T12:00:00",
            },
        )

        self.assertEqual(
            (202, 101, "memo.pdf", "abc", 20, 3, 4, "2026-06-10T12:00:00"),
            params,
        )

    def test_file_record_params_keep_insert_file_column_order(self):
        params = _file_record_params(
            {
                "file_id": 101,
                "hash": "abc",
                "size": 20,
                "duration": 3,
                "download_count": 4,
                "create_time": "2026-06-10T12:00:00",
            },
            group_id="303",
            topic_id=202,
        )

        self.assertEqual(
            (101, 303, 202, "", "abc", 20, 3, 4, "2026-06-10T12:00:00"),
            params,
        )
        self.assertEqual(None, _file_record_params({"file_id": 101}, group_id=None)[1])

    def test_file_download_status_params_keep_update_column_order(self):
        self.assertEqual(
            ("completed", r"C:\tmp\file.pdf", "completed", "completed", None, "completed", None, 101, 303, 303),
            _file_download_status_params("303", 101, "completed", r"C:\tmp\file.pdf"),
        )
        self.assertEqual(
            ("failed", None, "failed", "failed", "size_mismatch", "failed", "bad size", 101, 303, 303),
            _file_download_status_params("303", 101, "failed", error_code="size_mismatch", error_message="bad size"),
        )

    def test_file_ai_analysis_params_keep_upsert_column_order(self):
        self.assertEqual(
            (101, 303, "completed", None, None, None, None, None, None, None, None, None, None, None),
            _file_ai_analysis_params("303", 101),
        )
        self.assertEqual(
            (
                101,
                303,
                "failed",
                "summary",
                "full text",
                "preview",
                "application/pdf",
                r"C:\tmp\file.pdf",
                456,
                "model-a",
                "https://api.example.test",
                "responses",
                "low",
                "boom",
            ),
            _file_ai_analysis_params(
                "303",
                101,
                status="failed",
                summary="summary",
                extracted_text="full text",
                extracted_text_preview="preview",
                content_type="application/pdf",
                source_path=r"C:\tmp\file.pdf",
                source_size=456,
                model="model-a",
                api_base="https://api.example.test",
                wire_api="responses",
                reasoning_effort="low",
                error_message="boom",
            ),
        )

    def test_user_and_group_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (9, "Alice", "A", "avatar", "desc", "Shanghai", "ai-url"),
            _user_record_params(
                {
                    "user_id": 9,
                    "name": "Alice",
                    "alias": "A",
                    "avatar_url": "avatar",
                    "description": "desc",
                    "location": "Shanghai",
                    "ai_comment_url": "ai-url",
                }
            ),
        )
        self.assertEqual((9, "", None, None, None, None, None), _user_record_params({"user_id": 9}))
        self.assertEqual(
            (303, "group", "paid", "bg"),
            _group_record_params({"group_id": 303, "name": "group", "type": "paid", "background_url": "bg"}),
        )
        self.assertEqual((303, "", None, None), _group_record_params({"group_id": 303}))

    def test_topic_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (
                202,
                303,
                "talk",
                "title",
                "note",
                4,
                5,
                6,
                7,
                8,
                9,
                True,
                True,
                "2026-06-10T12:00:00",
                "2026-06-10T12:30:00",
                True,
                True,
            ),
            _topic_record_params(
                {
                    "topic_id": 202,
                    "group": {"group_id": 303},
                    "type": "talk",
                    "title": "title",
                    "annotation": "note",
                    "likes_count": 4,
                    "tourist_likes_count": 5,
                    "rewards_count": 6,
                    "comments_count": 7,
                    "reading_count": 8,
                    "readers_count": 9,
                    "digested": True,
                    "sticky": True,
                    "create_time": "2026-06-10T12:00:00",
                    "modify_time": "2026-06-10T12:30:00",
                    "user_specific": {"liked": True, "subscribed": True},
                }
            ),
        )
        self.assertEqual(
            (202, None, None, None, None, 0, 0, 0, 0, 0, 0, False, False, None, None, False, False),
            _topic_record_params({"topic_id": 202}),
        )

    def test_count_tables_builds_stats_from_cursor_counts(self):
        cursor = FakeCursor({"files": 3, "topics": 2})

        self.assertEqual({"files": 3, "topics": 2}, _count_tables(cursor, ("files", "topics")))
        self.assertEqual([("SELECT COUNT(*) FROM files", ()), ("SELECT COUNT(*) FROM topics", ())], cursor.executed)

    def test_count_tables_filters_direct_tables_by_group_scope(self):
        cursor = FakeCursor({"files": 3, "topics": 2})

        self.assertEqual({"files": 3, "topics": 2}, _count_tables(cursor, ("files", "topics"), group_id="303"))
        self.assertEqual(
            [
                ("SELECT COUNT(*) FROM files WHERE group_id = ?", (303,)),
                ("SELECT COUNT(*) FROM topics WHERE group_id = ?", (303,)),
            ],
            cursor.executed,
        )

    def test_count_tables_filters_child_tables_through_group_topics(self):
        cursor = FakeCursor({"talks": 4})

        self.assertEqual({"talks": 4}, _count_tables(cursor, ("talks",), group_id="303"))
        sql, params = cursor.executed[0]
        self.assertIn("WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", sql)
        self.assertEqual((303,), params)

    def test_close_connection_ignores_none_and_closes_connection(self):
        _close_connection(None)

        conn = FakeConnection()
        _close_connection(conn)

        self.assertTrue(conn.closed)

    def test_import_file_response_writes_topic_before_file_and_relation(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        fake = FakeImportDatabase()
        db.cursor = fake
        db.conn = fake
        db.insert_group = fake.insert_group
        db.insert_topic = fake.insert_topic
        db.insert_file = fake.insert_file
        db.insert_talk = fake.insert_talk
        db.insert_topic_files = fake.insert_topic_files

        stats = ZSXQFileDatabase.import_file_response(
            db,
            {
                "succeeded": True,
                "resp_data": {
                    "index": "next",
                    "files": [
                        {
                            "file": {"file_id": 101, "name": "memo.pdf"},
                            "topic": {
                                "topic_id": 202,
                                "group": {"group_id": 303, "name": "group"},
                                "talk": {"files": [{"file_id": 101, "name": "memo.pdf"}]},
                            },
                        }
                    ],
                },
            },
        )

        ordered = [call[0] for call in fake.calls]
        self.assertLess(ordered.index("group"), ordered.index("topic"))
        self.assertLess(ordered.index("topic"), ordered.index("file"))
        self.assertLess(ordered.index("file"), ordered.index("insert_relation"))
        self.assertEqual(1, stats["files"])
        self.assertEqual(1, stats["topics"])
        self.assertEqual(1, stats["groups"])
        self.assertIn(("file", 101, 303, 202), fake.calls)

    def test_insert_file_writes_group_and_topic_ids(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        cursor = FakeCommentCursor()
        db.cursor = cursor

        file_id = ZSXQFileDatabase.insert_file(
            db,
            {"file_id": 101, "name": "memo.pdf", "hash": "h", "size": 20},
            group_id="303",
            topic_id=202,
        )

        self.assertEqual(101, file_id)
        sql, params = cursor.calls[-1]
        self.assertIn("INSERT INTO files", sql)
        self.assertIn("file_id, group_id, topic_id", sql)
        self.assertIn("group_id = COALESCE", sql)
        self.assertEqual((101, 303, 202), params[:3])

    def test_insert_user_and_group_use_record_params(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()

        self.assertIsNone(ZSXQFileDatabase.insert_user(db, {}))
        self.assertIsNone(ZSXQFileDatabase.insert_group(db, {}))
        self.assertEqual([], db.cursor.calls)

        self.assertEqual(9, ZSXQFileDatabase.insert_user(db, {"user_id": 9, "name": "Alice"}))
        user_sql, user_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO users", user_sql)
        self.assertEqual((9, "Alice", None, None, None, None, None), user_params)

        self.assertEqual(303, ZSXQFileDatabase.insert_group(db, {"group_id": 303, "name": "group"}))
        group_sql, group_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO groups", group_sql)
        self.assertEqual((303, "group", None, None), group_params)

    def test_insert_topic_uses_record_params(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()

        self.assertIsNone(ZSXQFileDatabase.insert_topic(db, {}))
        self.assertEqual([], db.cursor.calls)

        self.assertEqual(
            202,
            ZSXQFileDatabase.insert_topic(
                db,
                {
                    "topic_id": 202,
                    "group": {"group_id": 303},
                    "type": "talk",
                    "title": "title",
                    "user_specific": {"liked": True},
                },
            ),
        )
        topic_sql, topic_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO topics", topic_sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", topic_sql)
        self.assertEqual((202, 303, "talk", "title", None), topic_params[:5])
        self.assertEqual((False, None, None, True, False), topic_params[12:])

    def test_update_file_download_status_casts_timestamp_to_text(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        cursor = FakeCommentCursor()
        db.cursor = cursor
        db.conn = FakeAnalysisConnection()
        db.group_id = "303"

        db.update_file_download_status(101, "completed", r"C:\tmp\file.pdf")

        sql, params = cursor.calls[-1]
        self.assertIn("CURRENT_TIMESTAMP::text", sql)
        self.assertIn("download_error_code", sql)
        self.assertIn("last_download_attempt_at", sql)
        self.assertEqual(
            ("completed", r"C:\tmp\file.pdf", "completed", "completed", None, "completed", None, 101, 303, 303),
            params,
        )
        self.assertEqual(1, db.conn.commits)

    def test_update_file_download_status_persists_failure_reason(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        cursor = FakeCommentCursor()
        db.cursor = cursor
        db.conn = FakeAnalysisConnection()
        db.group_id = "303"

        db.update_file_download_status(101, "failed", error_code="size_mismatch", error_message="bad size")

        _sql, params = cursor.calls[-1]
        self.assertEqual(
            ("failed", None, "failed", "failed", "size_mismatch", "failed", "bad size", 101, 303, 303),
            params,
        )
        self.assertEqual(1, db.conn.commits)

    def test_file_ai_analysis_queries_are_scoped_by_group(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        cursor = FakeAnalysisCursor()
        db.cursor = cursor
        db.conn = FakeAnalysisConnection()
        db.group_id = "303"

        db.get_file_ai_analysis(101)
        select_sql, select_params = cursor.calls[-1]
        self.assertIn("WHERE file_id = ? AND (? IS NULL OR group_id = ?)", select_sql)
        self.assertEqual((101, 303, 303), select_params)

        db.upsert_file_ai_analysis(101, status="completed", summary="ok")
        insert_sql, insert_params = cursor.calls[-1]
        self.assertIn("file_id, group_id, status", insert_sql)
        self.assertEqual((101, 303, "completed"), insert_params[:3])

    def test_insert_comments_writes_group_id_from_runtime_scope(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()
        db.group_id = "303"
        db.insert_user = lambda user: user.get("user_id") if user else None

        db.insert_comments(202, [{"comment_id": 101, "owner": {"user_id": 9}, "text": "ok"}])

        sql, params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO comments", sql)
        self.assertIn("ON CONFLICT(comment_id) DO UPDATE SET", sql)
        self.assertIn("comment_id, group_id, topic_id", sql)
        self.assertEqual((101, 303, 202), params[:3])

    def test_content_child_writes_use_explicit_unique_semantics(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()
        db.insert_user = lambda user: user.get("user_id") if user else None

        ZSXQFileDatabase.insert_talk(db, 202, {"owner": {"user_id": 9}, "text": "body"})
        talk_sql, _talk_params = db.cursor.calls[-1]
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", talk_sql)

        ZSXQFileDatabase.insert_latest_likes(
            db,
            202,
            [{"owner": {"user_id": 9}, "create_time": "2026-01-01"}],
        )
        calls = "\n".join(sql for sql, _params in db.cursor.calls)
        self.assertIn("DELETE FROM latest_likes WHERE topic_id = ?", calls)
        self.assertIn("ON CONFLICT(topic_id, owner_user_id, create_time) DO NOTHING", calls)

        ZSXQFileDatabase.insert_like_emojis(
            db,
            202,
            {"emojis": [{"emoji_key": "[ok]", "likes_count": 2}]},
        )
        emoji_sql, _emoji_params = db.cursor.calls[-1]
        self.assertIn("ON CONFLICT(topic_id, emoji_key) DO UPDATE SET", emoji_sql)

    def test_runtime_create_tables_and_migration_are_noops(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()

        self.assertIsNone(ZSXQFileDatabase.create_tables(db))
        self.assertIsNone(ZSXQFileDatabase._migrate_database(db))
        self.assertEqual([], db.cursor.calls)


if __name__ == "__main__":
    unittest.main()
