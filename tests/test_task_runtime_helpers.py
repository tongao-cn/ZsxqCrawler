import unittest
from unittest.mock import patch


class TaskRuntimeHelperTests(unittest.TestCase):
    def test_columns_fetch_is_ingestion_locked(self):
        from backend.services.task_runtime import INGESTION_LOCK_TYPES

        self.assertIn("columns_fetch", INGESTION_LOCK_TYPES)

    def test_find_running_ingestion_task_matches_same_group(self):
        from backend.services.task_runtime import find_running_ingestion_task

        running = {
            "task_id": "task-1",
            "type": "crawl_latest_until_complete",
            "status": "running",
            "group_id": "155",
            "ingestion_lock_key": "ingestion",
        }
        other_group = {
            "task_id": "task-2",
            "type": "collect_files",
            "status": "running",
            "group_id": "166",
            "ingestion_lock_key": "ingestion",
        }

        with patch("backend.services.task_runtime.list_tasks", return_value=[other_group, running]):
            self.assertEqual(running, find_running_ingestion_task("155"))
            self.assertIsNone(find_running_ingestion_task("177"))

    def test_create_ingestion_task_rejects_existing_same_group(self):
        from backend.services.task_runtime import create_ingestion_task

        existing = {"task_id": "task-1", "status": "running", "group_id": "155"}

        with (
            patch("backend.services.task_runtime.find_running_ingestion_task", return_value=existing),
            patch("backend.services.task_runtime.create_task") as create_task,
        ):
            task_id, conflict = create_ingestion_task("collect_files", "collect", "155")

        self.assertIsNone(task_id)
        self.assertEqual(existing, conflict)
        create_task.assert_not_called()

    def test_create_ingestion_task_allows_different_group_when_no_conflict(self):
        from backend.services.task_runtime import create_ingestion_task

        with (
            patch("backend.services.task_runtime.find_running_ingestion_task", return_value=None),
            patch("backend.services.task_runtime.create_task", return_value="task-2") as create_task,
        ):
            task_id, conflict = create_ingestion_task("collect_files", "collect", "166")

        self.assertEqual("task-2", task_id)
        self.assertIsNone(conflict)
        create_task.assert_called_once_with(
            "collect_files",
            "collect",
            metadata={"group_id": "166", "ingestion_lock_key": "ingestion"},
        )


if __name__ == "__main__":
    unittest.main()
