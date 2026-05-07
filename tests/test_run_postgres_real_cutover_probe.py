import unittest

from scripts.run_postgres_real_cutover_probe import ProbeCounts, _delta


class RunPostgresRealCutoverProbeTests(unittest.TestCase):
    def test_delta_compares_probe_counts(self):
        before = ProbeCounts(legacy_schema_count=1, core_topics=2, core_files=3, core_comments=4, core_tasks=5)
        after = ProbeCounts(legacy_schema_count=1, core_topics=4, core_files=3, core_comments=6, core_tasks=5)

        self.assertEqual(2, _delta(before, after, "core_topics"))
        self.assertEqual(0, _delta(before, after, "legacy_schema_count"))


if __name__ == "__main__":
    unittest.main()
