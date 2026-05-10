import unittest
from unittest.mock import patch


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args):
        self.tasks.append((func, args))


def fake_task(*args):
    return args


class IngestionHelpersTests(unittest.TestCase):
    def test_ingestion_conflict_detail_keeps_public_shape(self):
        from backend.routes.ingestion_helpers import ingestion_conflict_detail

        detail = ingestion_conflict_detail({"task_id": "task-1", "type": "crawl_all", "status": "running"})

        self.assertEqual(
            {
                "message": "该群组已有采集或同步任务正在运行",
                "task_id": "task-1",
                "type": "crawl_all",
                "status": "running",
            },
            detail,
        )

    def test_create_ingestion_task_or_raise_returns_new_task_id(self):
        from backend.routes.ingestion_helpers import create_ingestion_task_or_raise

        with patch("backend.routes.ingestion_helpers.create_ingestion_task", return_value=("task-2", None)) as create_task:
            task_id = create_ingestion_task_or_raise("columns_fetch", "desc", "123")

        self.assertEqual("task-2", task_id)
        create_task.assert_called_once_with("columns_fetch", "desc", "123")

    def test_create_ingestion_task_or_raise_rejects_conflict(self):
        from fastapi import HTTPException
        from backend.routes.ingestion_helpers import create_ingestion_task_or_raise

        existing = {"task_id": "task-1", "type": "crawl_all", "status": "running"}

        with patch("backend.routes.ingestion_helpers.create_ingestion_task", return_value=(None, existing)):
            with self.assertRaises(HTTPException) as raised:
                create_ingestion_task_or_raise("columns_fetch", "desc", "123")

        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual("task-1", raised.exception.detail["task_id"])

    def test_enqueue_ingestion_task_schedules_callback(self):
        from backend.routes.ingestion_helpers import enqueue_ingestion_task

        background_tasks = FakeBackgroundTasks()

        with patch("backend.routes.ingestion_helpers.create_ingestion_task_or_raise", return_value="task-2") as create_task:
            with patch("backend.routes.ingestion_helpers.enqueue_runtime_task") as enqueue_runtime_task:
                response = enqueue_ingestion_task(
                    background_tasks,
                    "columns_fetch",
                    "desc",
                    fake_task,
                    "123",
                    "request",
                    message="已启动",
                )

        create_task.assert_called_once_with("columns_fetch", "desc", "123")
        self.assertEqual({"task_id": "task-2", "message": "已启动"}, response)
        enqueue_runtime_task.assert_called_once_with(fake_task, "task-2", "123", "request")
        self.assertEqual([], background_tasks.tasks)


if __name__ == "__main__":
    unittest.main()
