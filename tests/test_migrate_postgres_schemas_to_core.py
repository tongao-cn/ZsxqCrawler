import unittest

from scripts.migrate_postgres_schemas_to_core import _record_key, discover_legacy_schemas


class MigratePostgresSchemasToCoreTests(unittest.TestCase):
    def test_record_key_joins_conflict_columns(self):
        self.assertEqual("g1|2026-05-07", _record_key({"group_id": "g1", "report_date": "2026-05-07"}, ("group_id", "report_date")))

    def test_discover_legacy_schemas_excludes_public_and_core(self):
        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                self.params = params

            def fetchall(self):
                return [("zsxq_a",), ("zsxq_tasks_1",)]

        class FakeConn:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def cursor(self):
                return self.cursor_obj

        conn = FakeConn()

        self.assertEqual(["zsxq_a", "zsxq_tasks_1"], discover_legacy_schemas(conn))
        self.assertEqual(("zsxq_%", "zsxq_public", "zsxq_core"), conn.cursor_obj.params)


if __name__ == "__main__":
    unittest.main()
