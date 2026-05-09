import unittest
from unittest.mock import patch

from backend.storage.db_compat import (
    CompatRow,
    connect,
    PostgresCompatConnection,
    _should_bootstrap_schema_on_connect,
    _reject_sqlite_only_sql,
    _strip_env_value,
    _translate_sql,
)
from backend.storage.postgres_core_schema import CORE_SCHEMA


class DbCompatTests(unittest.TestCase):
    def test_runtime_schema_is_fixed_core_schema(self):
        self.assertEqual("zsxq_core", CORE_SCHEMA)

    def test_rejects_sqlite_only_sql_patterns(self):
        cases = [
            "PRAGMA table_info(files)",
            "INSERT OR REPLACE INTO topics (topic_id) VALUES (?)",
            "INSERT OR IGNORE INTO topics (topic_id) VALUES (?)",
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
        ]

        for raw_sql in cases:
            with self.subTest(raw_sql=raw_sql):
                with self.assertRaisesRegex(RuntimeError, "SQLite-only SQL"):
                    _translate_sql(raw_sql)

    def test_translate_sql_only_handles_params_and_limit_offset(self):
        query_sql = _translate_sql("SELECT * FROM task_runs LIMIT -1 OFFSET ?")
        insert_sql = _translate_sql(
            "INSERT INTO topics (topic_id, group_id) VALUES (?, ?) "
            "ON CONFLICT(topic_id) DO UPDATE SET group_id = excluded.group_id"
        )

        self.assertEqual("SELECT * FROM task_runs OFFSET %s", query_sql)
        self.assertIn("VALUES (%s, %s)", insert_sql)
        self.assertIn("ON CONFLICT(topic_id)", insert_sql)

    def test_env_value_strip_removes_matching_outer_quotes(self):
        self.assertEqual("postgres", _strip_env_value('"postgres"'))
        self.assertEqual("sqlite", _strip_env_value("'sqlite'"))
        self.assertEqual('"mixed', _strip_env_value('"mixed'))

    def test_connect_rejects_removed_sqlite_backend(self):
        with patch("backend.storage.db_compat.get_database_backend", return_value="sqlite"):
            with self.assertRaisesRegex(RuntimeError, "SQLite backend has been removed"):
                connect()

    def test_bootstrap_schema_on_connect_is_opt_in(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_should_bootstrap_schema_on_connect())
        with patch.dict("os.environ", {"ZSXQ_BOOTSTRAP_SCHEMA_ON_CONNECT": "true"}, clear=True):
            self.assertTrue(_should_bootstrap_schema_on_connect())

    def test_postgres_connection_sets_search_path_without_default_bootstrap(self):
        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((sql, params))

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()
                self.commits = 0

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.commits += 1

        fake_conn = FakeConnection()

        with patch.dict("os.environ", {}, clear=True), patch(
            "psycopg2.connect", return_value=fake_conn
        ), patch("backend.storage.db_compat.ensure_core_schema") as ensure_core_schema:
            PostgresCompatConnection("postgresql://example")

        ensure_core_schema.assert_not_called()
        self.assertEqual(fake_conn.cursor_obj.calls, [('SET search_path TO "zsxq_core"', ())])
        self.assertEqual(fake_conn.commits, 1)

    def test_missing_schema_error_is_wrapped_with_setup_hint(self):
        class MissingSchemaCursor:
            rowcount = -1

            def execute(self, sql, params=()):
                raise Exception('relation "topics" does not exist')

        class FakeConnection:
            schema_name = CORE_SCHEMA

        compat_cursor = __import__("backend.storage.db_compat", fromlist=["PostgresCompatCursor"]).PostgresCompatCursor(
            FakeConnection(),
            MissingSchemaCursor(),
        )

        with self.assertRaisesRegex(RuntimeError, "manage-postgres-core-schema --apply"):
            compat_cursor.execute("SELECT 1 FROM topics")

    def test_compat_row_supports_index_and_column_access(self):
        row = CompatRow(("task-1", "running"), ("task_id", "status"))

        self.assertEqual("task-1", row[0])
        self.assertEqual("running", row["status"])
        self.assertEqual(["task_id", "status"], row.keys())

    def test_reject_sqlite_only_sql_names_the_unsupported_pattern(self):
        with self.assertRaisesRegex(RuntimeError, "INSERT OR IGNORE"):
            _reject_sqlite_only_sql("INSERT OR IGNORE INTO topics (topic_id) VALUES (?)")


if __name__ == "__main__":
    unittest.main()
