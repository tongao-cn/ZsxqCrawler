import tempfile
import sqlite3
import unittest
from pathlib import Path

from scripts.audit_postgres_migration import AuditIssue, _sqlite_table_stats, print_audit_report


class AuditPostgresMigrationTests(unittest.TestCase):
    def test_print_audit_report_returns_zero_without_issues(self):
        self.assertEqual(0, print_audit_report([]))

    def test_print_audit_report_returns_one_for_errors(self):
        self.assertEqual(1, print_audit_report([AuditIssue("error", "row mismatch")]))

    def test_print_audit_report_returns_zero_for_warnings(self):
        self.assertEqual(0, print_audit_report([AuditIssue("warn", "no db files")]))

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
