import unittest

from backend.storage.zsxq_file_database import (
    _FILE_AI_ANALYSIS_FIELDS,
    _close_connection,
    _count_tables,
    _new_import_stats,
    _row_to_file_ai_analysis,
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

    def test_runtime_create_tables_and_migration_are_noops(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()

        self.assertIsNone(ZSXQFileDatabase.create_tables(db))
        self.assertIsNone(ZSXQFileDatabase._migrate_database(db))
        self.assertEqual([], db.cursor.calls)


if __name__ == "__main__":
    unittest.main()
