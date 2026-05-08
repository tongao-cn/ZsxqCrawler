import unittest
import os

from backend.storage.db_compat import get_postgres_dsn
from backend.storage.task_store import TaskStore


class TaskStoreHelperTests(unittest.TestCase):
    def test_runtime_init_db_is_noop(self):
        store = object.__new__(TaskStore)
        store._lock = None

        self.assertIsNone(TaskStore._init_db(store))


@unittest.skipUnless(
    get_postgres_dsn() and os.getenv("ZSXQ_RUN_PG_INTEGRATION_TESTS") == "1",
    "PostgreSQL integration tests are disabled",
)
class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = TaskStore()

    def create_task_with_logs(self, task_id, status, created_at, log_count=1):
        self.store.create_task(
            task_id,
            "crawl_latest",
            status,
            f"{status} task",
            created_at=created_at,
            updated_at=created_at,
        )
        for index in range(log_count):
            self.store.add_log(
                task_id,
                f"log {index}",
                created_at=created_at,
            )

    def test_create_task_expands_metadata(self):
        task = self.store.create_task(
            "task-1",
            "crawl_latest",
            "running",
            "started",
            metadata={"group_id": "group-1", "source": "manual"},
            created_at="2026-05-06T10:00:00",
            updated_at="2026-05-06T10:00:00",
        )

        self.assertEqual("task-1", task["task_id"])
        self.assertEqual("crawl_latest", task["type"])
        self.assertEqual("running", task["status"])
        self.assertEqual("started", task["message"])
        self.assertEqual("group-1", task["group_id"])
        self.assertEqual("manual", task["source"])
        self.assertEqual("2026-05-06T10:00:00", task["created_at"])
        self.assertEqual("2026-05-06T10:00:00", task["updated_at"])

    def test_update_task_persists_result(self):
        self.store.create_task("task-1", "crawl_latest", "running", "started")

        updated = self.store.update_task(
            "task-1",
            "completed",
            "done",
            result={"new_topics": 2, "ids": ["topic-1", "topic-2"]},
            updated_at="2026-05-06T10:05:00",
        )

        self.assertEqual("completed", updated["status"])
        self.assertEqual("done", updated["message"])
        self.assertEqual(
            {"new_topics": 2, "ids": ["topic-1", "topic-2"]},
            updated["result"],
        )
        self.assertEqual("2026-05-06T10:05:00", updated["updated_at"])

        fetched = self.store.get_task("task-1")
        self.assertEqual(updated["result"], fetched["result"])

    def test_logs_are_returned_in_insert_order(self):
        self.store.create_task("task-1", "crawl_latest", "running", "started")

        first = self.store.add_log(
            "task-1",
            "first step",
            created_at="2026-05-06T10:00:00",
        )
        second = self.store.add_log(
            "task-1",
            "second step",
            created_at="2026-05-06T10:00:01",
        )

        self.assertEqual([first, second], self.store.get_logs("task-1"))
        self.assertTrue(first.endswith("first step"))
        self.assertTrue(second.endswith("second step"))

    def test_stop_flag_can_be_set_and_cleared(self):
        self.store.create_task("task-1", "crawl_latest", "running", "started")

        self.assertFalse(self.store.is_stopped("task-1"))
        self.store.set_stop_flag("task-1")
        self.assertTrue(self.store.is_stopped("task-1"))
        self.store.set_stop_flag("task-1", stopped=False)
        self.assertFalse(self.store.is_stopped("task-1"))

    def test_data_survives_reinstantiation(self):
        self.store.create_task(
            "task-1",
            "crawl_latest",
            "running",
            "started",
            metadata={"group_id": "group-1"},
            created_at="2026-05-06T10:00:00",
        )
        self.store.update_task(
            "task-1",
            "completed",
            "done",
            result={"new_topics": 1},
            updated_at="2026-05-06T10:05:00",
        )
        log = self.store.add_log("task-1", "persisted log")
        self.store.set_stop_flag("task-1")

        reopened = TaskStore()

        task = reopened.get_task("task-1")
        self.assertEqual("completed", task["status"])
        self.assertEqual("group-1", task["group_id"])
        self.assertEqual({"new_topics": 1}, task["result"])
        self.assertEqual([task], reopened.list_tasks())
        self.assertEqual([log], reopened.get_logs("task-1"))
        self.assertTrue(reopened.is_stopped("task-1"))

    def test_max_task_sequence_returns_largest_standard_task_number(self):
        self.store.create_task("task_1_1778000000", "crawl_latest", "completed", "done")
        self.store.create_task("task_12_1778000001", "crawl_latest", "completed", "done")
        self.store.create_task("task_3_1778000002", "crawl_latest", "completed", "done")

        self.assertEqual(12, self.store.max_task_sequence())

    def test_max_task_sequence_ignores_nonstandard_task_ids(self):
        self.store.create_task("columns_x_1", "crawl_latest", "completed", "done")
        self.store.create_task("task_bad", "crawl_latest", "completed", "done")
        self.store.create_task("task_abc_123", "crawl_latest", "completed", "done")
        self.store.create_task("task_7_1778000000", "crawl_latest", "completed", "done")

        self.assertEqual(7, self.store.max_task_sequence())

    def test_max_task_sequence_returns_zero_for_empty_store(self):
        self.assertEqual(0, self.store.max_task_sequence())

    def test_list_tasks_limit_returns_latest_task(self):
        older = self.store.create_task(
            "task_1_1778000000",
            "crawl_latest",
            "completed",
            "older",
            created_at="2026-05-06T10:00:00",
        )
        newer = self.store.create_task(
            "task_2_1778000001",
            "crawl_latest",
            "completed",
            "newer",
            created_at="2026-05-06T10:01:00",
        )

        self.assertEqual([newer], self.store.list_tasks(limit=1))
        self.assertEqual(older, self.store.list_tasks(limit=2)[1])

    def test_cleanup_completed_deletes_old_terminal_tasks_and_logs(self):
        terminal_tasks = [
            ("task-0", "completed"),
            ("task-1", "failed"),
            ("task-2", "cancelled"),
            ("task-3", "stopped"),
            ("task-4", "completed"),
            ("task-5", "failed"),
        ]
        for index, (task_id, status) in enumerate(terminal_tasks):
            self.create_task_with_logs(
                task_id,
                status,
                f"2026-05-06T10:0{index}:00",
                log_count=2,
            )
        self.create_task_with_logs(
            "task-pending",
            "pending",
            "2026-05-06T09:00:00",
            log_count=2,
        )
        self.create_task_with_logs(
            "task-running",
            "running",
            "2026-05-06T09:01:00",
            log_count=2,
        )

        result = self.store.cleanup_completed(keep_latest=2)

        self.assertEqual(
            {"tasks_deleted": 4, "logs_deleted": 8, "kept_latest": 2},
            result,
        )
        remaining_ids = {task["task_id"] for task in self.store.list_tasks()}
        self.assertEqual(
            {"task-4", "task-5", "task-pending", "task-running"},
            remaining_ids,
        )
        for task_id in ["task-0", "task-1", "task-2", "task-3"]:
            self.assertIsNone(self.store.get_task(task_id))
            self.assertEqual([], self.store.get_logs(task_id))
        for task_id in ["task-4", "task-5", "task-pending", "task-running"]:
            self.assertEqual(2, len(self.store.get_logs(task_id)))

    def test_cleanup_completed_keep_latest_zero_deletes_all_terminal_tasks(self):
        self.create_task_with_logs(
            "task-completed",
            "completed",
            "2026-05-06T10:00:00",
        )
        self.create_task_with_logs(
            "task-failed",
            "failed",
            "2026-05-06T10:01:00",
        )
        self.create_task_with_logs(
            "task-pending",
            "pending",
            "2026-05-06T10:02:00",
        )
        self.create_task_with_logs(
            "task-running",
            "running",
            "2026-05-06T10:03:00",
        )

        result = self.store.cleanup_completed(keep_latest=0)

        self.assertEqual(
            {"tasks_deleted": 2, "logs_deleted": 2, "kept_latest": 0},
            result,
        )
        self.assertIsNone(self.store.get_task("task-completed"))
        self.assertIsNone(self.store.get_task("task-failed"))
        self.assertIsNotNone(self.store.get_task("task-pending"))
        self.assertIsNotNone(self.store.get_task("task-running"))
        self.assertEqual(1, len(self.store.get_logs("task-pending")))
        self.assertEqual(1, len(self.store.get_logs("task-running")))

    def test_cleanup_completed_negative_keep_latest_is_zero(self):
        self.create_task_with_logs(
            "task-cancelled",
            "cancelled",
            "2026-05-06T10:00:00",
        )
        self.create_task_with_logs(
            "task-stopped",
            "stopped",
            "2026-05-06T10:01:00",
        )
        self.create_task_with_logs(
            "task-running",
            "running",
            "2026-05-06T10:02:00",
        )

        result = self.store.cleanup_completed(keep_latest=-1)

        self.assertEqual(
            {"tasks_deleted": 2, "logs_deleted": 2, "kept_latest": 0},
            result,
        )
        self.assertEqual(
            ["task-running"],
            [task["task_id"] for task in self.store.list_tasks()],
        )
        self.assertEqual(1, len(self.store.get_logs("task-running")))

    def test_chunk_values_splits_values_without_dropping_tail(self):
        from backend.storage.task_store import _chunk_values

        self.assertEqual([[1, 2], [3, 4], [5]], _chunk_values([1, 2, 3, 4, 5], 2))
        self.assertEqual([], _chunk_values([], 2))

    def test_cleanup_result_keeps_existing_shape(self):
        from backend.storage.task_store import _cleanup_result

        self.assertEqual(
            {"tasks_deleted": 2, "logs_deleted": 3, "kept_latest": 1},
            _cleanup_result(tasks_deleted=2, logs_deleted=3, kept_latest=1),
        )

if __name__ == "__main__":
    unittest.main()
