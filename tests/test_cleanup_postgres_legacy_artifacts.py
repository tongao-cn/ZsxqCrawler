import unittest

from scripts.cleanup_postgres_legacy_artifacts import CleanupPlan, apply_cleanup_plan, build_cleanup_plan


class CleanupPostgresLegacyArtifactsTests(unittest.TestCase):
    def test_plan_text_includes_safety_header_and_cleanup_sql(self):
        plan = CleanupPlan(
            statements=[
                'DROP SCHEMA IF EXISTS "zsxq_public" CASCADE;',
                'DROP SCHEMA IF EXISTS "zsxq_old" CASCADE;',
                'ALTER TABLE "zsxq_core"."topics" DROP COLUMN IF EXISTS "source_schema";',
            ],
            legacy_schema_count=1,
            tracked_rows=10,
            untracked_rows=0,
            active_writers=0,
        )

        text = plan.text()

        self.assertIn("-- legacy_schema_count: 1", text)
        self.assertIn("-- untracked_rows: 0", text)
        self.assertIn('DROP SCHEMA IF EXISTS "zsxq_public" CASCADE;', text)
        self.assertIn('DROP SCHEMA IF EXISTS "zsxq_old" CASCADE;', text)
        self.assertIn('DROP COLUMN IF EXISTS "source_schema"', text)

    def test_apply_refuses_untracked_legacy_rows(self):
        plan = CleanupPlan([], legacy_schema_count=1, tracked_rows=0, untracked_rows=1, active_writers=0)

        with self.assertRaisesRegex(RuntimeError, "untracked legacy rows"):
            apply_cleanup_plan(object(), plan)

    def test_apply_refuses_active_writer_sessions(self):
        plan = CleanupPlan([], legacy_schema_count=0, tracked_rows=0, untracked_rows=0, active_writers=1)

        with self.assertRaisesRegex(RuntimeError, "active writer sessions"):
            apply_cleanup_plan(object(), plan)

    def test_apply_commits_each_statement_to_avoid_large_lock_batches(self):
        class FakeCursor:
            def __init__(self, conn):
                self.conn = conn

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, statement):
                self.conn.executed.append(statement)

        class FakeConn:
            def __init__(self):
                self.executed = []
                self.commits = 0

            def cursor(self):
                return FakeCursor(self)

            def commit(self):
                self.commits += 1

        conn = FakeConn()
        plan = CleanupPlan(
            ["DROP SCHEMA one;", "DROP SCHEMA two;"],
            legacy_schema_count=2,
            tracked_rows=2,
            untracked_rows=0,
            active_writers=0,
        )

        apply_cleanup_plan(conn, plan)

        self.assertEqual(["DROP SCHEMA one;", "DROP SCHEMA two;"], conn.executed)
        self.assertEqual(2, conn.commits)

    def test_build_plan_discovers_public_legacy_and_tracking_columns(self):
        class FakeCursor:
            def __init__(self, conn):
                self.conn = conn
                self.result = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                if "information_schema.schemata" in sql and "schema_name = %s" in sql:
                    self.result = [(1,)] if params == ("zsxq_public",) else []
                elif "information_schema.schemata" in sql and "LIKE" in sql:
                    self.result = [("zsxq_old",)]
                elif "information_schema.tables" in sql and params == ("zsxq_old",):
                    self.result = [("topics",)]
                elif "information_schema.tables" in sql and params == ("zsxq_core",):
                    self.result = [("topics",)]
                elif "table_name = 'record_sources'" in sql:
                    self.result = [(1,)]
                elif "record_sources" in sql:
                    self.result = [(2,)]
                elif "pg_stat_activity" in sql:
                    self.result = [(0,)]
                elif "count(*)" in sql:
                    self.result = [(2,)]
                else:
                    self.result = []

            def fetchone(self):
                return self.result[0] if self.result else None

            def fetchall(self):
                return self.result

        class FakeConn:
            def cursor(self):
                return FakeCursor(self)

        plan = build_cleanup_plan(FakeConn())
        text = plan.text()

        self.assertEqual(1, plan.legacy_schema_count)
        self.assertEqual(0, plan.untracked_rows)
        self.assertIn('DROP SCHEMA IF EXISTS "zsxq_public" CASCADE;', text)
        self.assertIn('DROP SCHEMA IF EXISTS "zsxq_old" CASCADE;', text)
        self.assertIn('DROP TABLE IF EXISTS "zsxq_core"."record_sources" CASCADE;', text)
        self.assertIn('ALTER TABLE "zsxq_core"."topics" DROP COLUMN IF EXISTS "source_schema";', text)


if __name__ == "__main__":
    unittest.main()
