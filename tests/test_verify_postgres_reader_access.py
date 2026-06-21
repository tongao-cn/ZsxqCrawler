import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from scripts.verify_postgres_reader_access import (
    CORE_SCHEMA,
    ReaderCheck,
    _core_select_allowed,
    _first_legacy_schema_table,
    print_checks,
)


class VerifyPostgresReaderAccessTests(unittest.TestCase):
    def test_print_checks_returns_zero_when_all_pass(self):
        output = StringIO()
        with redirect_stdout(output):
            code = print_checks([ReaderCheck("core select allowed", True, "1 rows")])

        self.assertEqual(0, code)
        self.assertIn("[ok] core select allowed: 1 rows", output.getvalue())

    def test_print_checks_returns_one_when_any_check_fails(self):
        output = StringIO()
        with redirect_stdout(output):
            code = print_checks(
                [
                    ReaderCheck("core select allowed", True, "1 rows"),
                    ReaderCheck("core write blocked", False, "created table"),
                ]
            )

        self.assertEqual(1, code)
        self.assertIn("[fail] core write blocked: created table", output.getvalue())

    def test_first_legacy_schema_table_passes_like_pattern_as_parameter(self):
        class FakeCursor:
            def __init__(self):
                self.params = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, _sql, params=None):
                self.params = params

            def fetchone(self):
                return ("zsxq_topics_123", "topics")

        class FakeConn:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def cursor(self):
                return self.cursor_obj

        conn = FakeConn()

        self.assertEqual(("zsxq_topics_123", "topics"), _first_legacy_schema_table(conn))
        self.assertEqual(("zsxq_%", CORE_SCHEMA), conn.cursor_obj.params)

    def test_core_select_allowed_uses_reader_contract_probe_table(self):
        class FakeCursor:
            def __init__(self):
                self.sql = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                self.sql = sql

            def fetchone(self):
                return (3,)

        class FakeConn:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def cursor(self):
                return self.cursor_obj

        conn = FakeConn()
        with patch("scripts.verify_postgres_reader_access.reader_probe_table_name", return_value="groups"):
            check = _core_select_allowed(conn)

        self.assertTrue(check.passed)
        self.assertEqual("zsxq_core.groups: 3 rows", check.detail)
        self.assertIn('"zsxq_core"."groups"', conn.cursor_obj.sql)


if __name__ == "__main__":
    unittest.main()
