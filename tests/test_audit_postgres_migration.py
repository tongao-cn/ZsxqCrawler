import tempfile
import sqlite3
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.audit_postgres_migration import AuditIssue, _sqlite_table_stats, print_audit_report


class AuditPostgresMigrationTests(unittest.TestCase):
    def _print_report(self, issues):
        output = StringIO()
        with redirect_stdout(output):
            code = print_audit_report(issues)
        return code, output.getvalue()

    def test_print_audit_report_returns_zero_without_issues(self):
        code, output = self._print_report([])

        self.assertEqual(0, code)
        self.assertIn("audit passed", output)

    def test_print_audit_report_returns_one_for_errors(self):
        code, output = self._print_report([AuditIssue("error", "row mismatch")])

        self.assertEqual(1, code)
        self.assertIn("[error] row mismatch", output)

    def test_print_audit_report_returns_zero_for_warnings(self):
        code, output = self._print_report([AuditIssue("warn", "no db files")])

        self.assertEqual(0, code)
        self.assertIn("[warn] no db files", output)

    def test_sqlite_table_stats_reads_rows_and_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "fixture.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE topics (topic_id TEXT, title TEXT)")
                conn.execute("INSERT INTO topics VALUES ('t1', 'Title')")
                conn.commit()
            finally:
                conn.close()

            stats = _sqlite_table_stats(db_path)

        self.assertEqual(1, stats["topics"].rows)
        self.assertEqual(frozenset({"topic_id", "title"}), stats["topics"].columns)


if __name__ == "__main__":
    unittest.main()
