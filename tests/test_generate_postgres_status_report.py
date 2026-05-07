import unittest
from unittest.mock import patch

from scripts.generate_postgres_status_report import build_report


class GeneratePostgresStatusReportTests(unittest.TestCase):
    def test_build_report_includes_internal_schema_and_public_views(self):
        with (
            patch("scripts.generate_postgres_status_report._internal_schema_summary", return_value=[("zsxq_topics_a", 2, 10)]),
            patch("scripts.generate_postgres_status_report._view_count", return_value=0),
        ):
            report = build_report(object())

        self.assertIn("PostgreSQL Internal Schemas", report)
        self.assertIn("`zsxq_topics_a`", report)
        self.assertIn("`zsxq_public.topics`", report)
        self.assertNotIn("SQLite", report)


if __name__ == "__main__":
    unittest.main()
