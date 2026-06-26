import unittest
from datetime import date
from unittest.mock import patch


class FakeResult:
    def __init__(self, rows=None, rowcount=0):
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.delete_counts = {
            "file_ai_analyses": 3,
            "files": 2,
            "comments": 4,
            "topics": 2,
        }

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, tuple(params or ())))
        if normalized.startswith("SELECT COUNT(*) AS topic_count"):
            return FakeResult(
                [
                    {
                        "topic_count": 2,
                        "oldest_create_time": "2024-01-01T08:00:00+0800",
                        "newest_create_time": "2025-06-20T08:00:00+0800",
                    }
                ]
            )
        if normalized.startswith("SELECT COUNT(*) AS row_count FROM"):
            return FakeResult([{"row_count": 7}])
        if normalized.startswith("DELETE FROM"):
            table = normalized.split()[2]
            return FakeResult(rowcount=self.delete_counts.get(table, 0))
        return FakeResult()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def call_indexes(calls, prefix):
    return [index for index, (sql, _params) in enumerate(calls) if sql.startswith(prefix)]


class RetentionCleanupServiceTests(unittest.TestCase):
    def test_preview_group_retention_cleanup_counts_without_deleting(self):
        from backend.services.retention_cleanup_service import preview_group_retention_cleanup

        conn = FakeConnection()

        result = preview_group_retention_cleanup(
            "303",
            retention_days=365,
            today=date(2026, 6, 26),
            connect_func=lambda: conn,
        )

        self.assertEqual("303", result["group_id"])
        self.assertEqual(365, result["retention_days"])
        self.assertEqual("2025-06-26", result["cutoff_date"])
        self.assertEqual(2, result["matched_topics"])
        self.assertEqual("2024-01-01T08:00:00+0800", result["oldest_topic_create_time"])
        self.assertIn("file_ai_analyses", result["estimated"])
        self.assertIn("stock_topic_processed_states", result["estimated"])
        self.assertFalse(any(sql.startswith("DELETE FROM") for sql, _params in conn.calls))
        self.assertFalse(conn.committed)
        self.assertTrue(conn.closed)

    def test_run_group_retention_cleanup_deletes_children_before_topics_and_commits(self):
        from backend.services.retention_cleanup_service import run_group_retention_cleanup

        conn = FakeConnection()
        logs = []

        result = run_group_retention_cleanup(
            "303",
            retention_days=365,
            today=date(2026, 6, 26),
            connect_func=lambda: conn,
            log_callback=logs.append,
        )

        self.assertEqual(2, result["matched_topics"])
        self.assertEqual(2, result["deleted"]["topics"])
        self.assertEqual(3, result["deleted"]["file_ai_analyses"])
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertTrue(conn.closed)
        self.assertLess(
            call_indexes(conn.calls, "DELETE FROM file_ai_analyses")[0],
            call_indexes(conn.calls, "DELETE FROM files")[0],
        )
        self.assertLess(
            call_indexes(conn.calls, "DELETE FROM comments")[0],
            call_indexes(conn.calls, "DELETE FROM topics")[0],
        )
        self.assertTrue(any("删除完成" in message for message in logs))

    def test_create_retention_cleanup_task_uses_ingestion_lock_recipe(self):
        from backend.services import retention_cleanup_service as service

        with patch(
            "backend.services.retention_cleanup_service.launch_task_recipe",
            return_value={"task_id": "task-retention"},
        ) as launch:
            response = service.create_retention_cleanup_task("303", retention_days=400)

        self.assertEqual({"task_id": "task-retention"}, response)
        recipe = launch.call_args.args[0]
        self.assertEqual("retention_cleanup", recipe.task_type)
        self.assertEqual("303", recipe.ingestion_group_id)
        self.assertEqual(service.run_retention_cleanup_task, recipe.task_func)
        self.assertEqual(400, recipe.args[0].retention_days)


if __name__ == "__main__":
    unittest.main()
