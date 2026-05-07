import unittest

from scripts.generate_postgres_legacy_archive_report import LegacySchemaSummary, build_drop_sql, build_report


class GeneratePostgresLegacyArchiveReportTests(unittest.TestCase):
    def test_build_report_includes_summary_and_drop_sql(self):
        summaries = [
            LegacySchemaSummary("zsxq_a", 2, 10),
            LegacySchemaSummary("zsxq_b", 1, 5),
        ]

        report = build_report(summaries)

        self.assertIn("Legacy schema count: 2", report)
        self.assertIn("Legacy row count: 15", report)
        self.assertIn("DROP SCHEMA IF EXISTS", report)
        self.assertIn('"zsxq_a"', report)

    def test_build_drop_sql_quotes_schema_names(self):
        sql = build_drop_sql([LegacySchemaSummary('zsxq_weird"name', 0, 0)])

        self.assertEqual(['DROP SCHEMA IF EXISTS "zsxq_weird""name" CASCADE;'], sql)


if __name__ == "__main__":
    unittest.main()
