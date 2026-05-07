import unittest
from unittest.mock import patch

from scripts.generate_postgres_status_report import build_report


class GeneratePostgresStatusReportTests(unittest.TestCase):
    def test_build_report_includes_internal_schema_and_public_views(self):
        with (
            patch("scripts.generate_postgres_status_report._schema_summary", return_value=[("zsxq_core", 2, 10)]),
            patch("scripts.generate_postgres_status_report._legacy_schema_count", return_value=3),
            patch("scripts.generate_postgres_status_report._view_count", return_value=0),
        ):
            report = build_report(object())

        self.assertIn("PostgreSQL Core Schema", report)
        self.assertIn("`zsxq_core`", report)
        self.assertIn("`zsxq_public.topics`", report)
        self.assertIn("Legacy archived `zsxq_*` schema count: 3", report)
        self.assertNotIn("SQLite", report)


if __name__ == "__main__":
    unittest.main()
