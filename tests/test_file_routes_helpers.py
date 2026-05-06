import unittest
from unittest.mock import patch

from backend.routes.file_routes import (
    _enqueue_file_task,
    _get_download_file_status,
    _resolve_download_record_status,
)
from backend.services.task_runtime import get_task_state


class FakeBackgroundTasks:
    def __init__(self):
        self.calls = []

    def add_task(self, func, *args):
        self.calls.append((func, args))


def fake_task(*args):
    return args


class FileRoutesHelperTests(unittest.TestCase):
    def test_enqueue_file_task_creates_task_and_schedules_callback(self):
        background_tasks = FakeBackgroundTasks()

        response = _enqueue_file_task(
            background_tasks,
            "unit_file_task",
            "测试文件任务",
            fake_task,
            "group-1",
            123,
            message="已创建",
        )

        task_id = response["task_id"]
        self.assertEqual({"task_id": task_id, "message": "已创建"}, response)
        self.assertEqual([(fake_task, (task_id, "group-1", 123))], background_tasks.calls)
        self.assertEqual("unit_file_task", get_task_state(task_id)["type"])

    def test_get_download_file_status_handles_missing_file(self):
        with patch("backend.routes.file_routes.get_db_path_manager") as mocked_manager:
            mocked_manager.return_value.get_group_dir.return_value = r"C:\tmp\group-1"

            status = _get_download_file_status("group-1", "missing.pdf", 123, "fallback.pdf")

        self.assertEqual("missing.pdf", status["safe_filename"])
        self.assertFalse(status["local_exists"])
        self.assertEqual(0, status["local_size"])
        self.assertIsNone(status["local_path"])
        self.assertFalse(status["is_complete"])

    def test_resolve_download_record_status_marks_existing_file_completed(self):
        with patch("backend.routes.file_routes.resolve_local_file_path") as mocked_resolve:
            mocked_resolve.return_value = r"C:\tmp\group-1\downloads\file.pdf"

            status = _resolve_download_record_status(
                "group-1",
                123,
                "file.pdf",
                "pending",
                None,
            )

        self.assertEqual("completed", status["download_status"])
        self.assertTrue(status["local_exists"])
        self.assertEqual(r"C:\tmp\group-1\downloads\file.pdf", status["local_path"])


if __name__ == "__main__":
    unittest.main()
