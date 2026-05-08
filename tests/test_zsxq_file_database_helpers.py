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

    def execute(self, sql):
        self.executed.append(sql)
        self.current_table = sql.rsplit(" ", 1)[-1]

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
        elif normalized.startswith("INSERT OR IGNORE INTO file_topic_relations"):
            self.calls.append(("insert_relation", params))
        return self

    def insert_group(self, group_data):
        self.calls.append(("group", group_data.get("group_id")))
        return group_data.get("group_id")

    def insert_topic(self, topic_data):
        self.calls.append(("topic", topic_data.get("topic_id")))
        return topic_data.get("topic_id")

    def insert_file(self, file_data):
        self.calls.append(("file", file_data.get("file_id")))
        return file_data.get("file_id")

    def insert_talk(self, topic_id, talk_data):
        self.calls.append(("talk", topic_id))

    def insert_topic_files(self, topic_id, files_data):
        self.calls.append(("topic_files", topic_id, [item.get("file_id") for item in files_data]))

    def commit(self):
        self.calls.append(("commit",))

    def rollback(self):
        self.calls.append(("rollback",))


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
        self.assertEqual(["SELECT COUNT(*) FROM files", "SELECT COUNT(*) FROM topics"], cursor.executed)

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


if __name__ == "__main__":
    unittest.main()
