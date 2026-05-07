import unittest
from unittest.mock import patch

from scripts.generate_postgres_migration_report import _issues_to_markdown, build_report
from scripts.audit_postgres_migration import AuditIssue


class GeneratePostgresMigrationReportTests(unittest.TestCase):
    def test_issues_to_markdown_reports_pass_when_empty(self):
        self.assertEqual(["- PostgreSQL migration audit passed."], _issues_to_markdown([]))

    def test_issues_to_markdown_formats_issues(self):
        self.assertEqual(["- [warn] no db"], _issues_to_markdown([AuditIssue("warn", "no db")]))

    def test_build_report_includes_empty_sqlite_note_and_public_views(self):
        with (
            patch("scripts.generate_postgres_migration_report._sqlite_summary", return_value=[]),
            patch("scripts.generate_postgres_migration_report._internal_schema_summary", return_value=[]),
            patch("scripts.generate_postgres_migration_report.audit_migration", return_value=[AuditIssue("warn", "No .db files")]),
            patch("scripts.generate_postgres_migration_report._view_count", return_value=0),
        ):
            report = build_report(__import__("pathlib").Path("missing-root"), object())

        self.assertIn("No SQLite `.db` files found", report)
        self.assertIn("`zsxq_public.topics`", report)
        self.assertIn("[warn] SQLite root not found: missing-root", report)


if __name__ == "__main__":
    unittest.main()
