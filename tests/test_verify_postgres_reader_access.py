import unittest
from contextlib import redirect_stdout
from io import StringIO

from scripts.verify_postgres_reader_access import ReaderCheck, _first_internal_schema, print_checks


class VerifyPostgresReaderAccessTests(unittest.TestCase):
    def test_print_checks_returns_zero_when_all_pass(self):
        output = StringIO()
        with redirect_stdout(output):
            code = print_checks([ReaderCheck("select view", True, "1 rows")])

        self.assertEqual(0, code)
        self.assertIn("[ok] select view: 1 rows", output.getvalue())

    def test_print_checks_returns_one_when_any_check_fails(self):
        output = StringIO()
        with redirect_stdout(output):
            code = print_checks(
                [
                    ReaderCheck("select view", True, "1 rows"),
                    ReaderCheck("public write blocked", False, "created table"),
                ]
            )

        self.assertEqual(1, code)
        self.assertIn("[fail] public write blocked: created table", output.getvalue())

    def test_first_internal_schema_passes_like_pattern_as_parameter(self):
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
                return ("zsxq_topics_123",)

        class FakeConn:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def cursor(self):
                return self.cursor_obj

        conn = FakeConn()

        self.assertEqual("zsxq_topics_123", _first_internal_schema(conn))
        self.assertEqual(("zsxq_%", "zsxq_public"), conn.cursor_obj.params)


if __name__ == "__main__":
    unittest.main()
