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


if __name__ == "__main__":
    unittest.main()
