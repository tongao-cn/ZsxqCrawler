import unittest
from unittest.mock import patch

from scripts.generate_postgres_status_report import build_report


class GeneratePostgresStatusReportTests(unittest.TestCase):
    def test_build_report_includes_core_schema_and_quality_notes(self):
        with (
            patch("scripts.generate_postgres_status_report._schema_summary", return_value=[("zsxq_core", 2, 10)]),
            patch("scripts.generate_postgres_status_report._group_id_quality_summary", return_value={"files_null_group_id": 0}),
        ):
            report = build_report(object())

        self.assertIn("PostgreSQL Core Schema", report)
        self.assertIn("`zsxq_core`", report)
        self.assertIn("Group ID Quality", report)
        self.assertIn("`files_null_group_id`", report)
        self.assertIn("Other projects should use a read-only role with SELECT on `zsxq_core`.", report)
        self.assertNotIn("zsxq_public", report)
        self.assertNotIn("Legacy archived", report)
        self.assertNotIn("SQLite", report)

    def test_build_report_uses_reader_contract_status_tables(self):
        with (
            patch("scripts.generate_postgres_status_report._schema_summary", return_value=[("zsxq_core", 2, 10)]),
            patch("scripts.generate_postgres_status_report._group_id_quality_summary", return_value={}),
            patch("scripts.generate_postgres_status_report.status_report_table_names", return_value=("groups", "topics")),
            patch(
                "scripts.generate_postgres_status_report._table_count",
                side_effect=lambda _conn, _schema, table_name: {"groups": 1, "topics": 2}[table_name],
            ),
        ):
            report = build_report(object())

        self.assertIn("| `groups` | 1 |", report)
        self.assertIn("| `topics` | 2 |", report)


if __name__ == "__main__":
    unittest.main()
