import unittest

from scripts.backfill_postgres_core_group_ids import build_group_id_backfill_steps, group_id_quality_counts


class BackfillPostgresCoreGroupIdsTests(unittest.TestCase):
    def test_build_steps_cover_expected_fields(self):
        names = [step.name for step in build_group_id_backfill_steps()]

        self.assertEqual(["comments.group_id", "files.group_id", "file_ai_analyses.group_id"], names)

    def test_quality_counts_checks_null_and_ambiguous_files(self):
        executed_sql = []

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql):
                executed_sql.append(sql)

            def fetchone(self):
                return (0,)

        class FakeConn:
            def cursor(self):
                return FakeCursor()

        counts = group_id_quality_counts(FakeConn())

        self.assertEqual(0, counts["files_ambiguous_group_id"])
        self.assertTrue(any("HAVING COUNT(DISTINCT group_id) > 1" in sql for sql in executed_sql))


if __name__ == "__main__":
    unittest.main()
