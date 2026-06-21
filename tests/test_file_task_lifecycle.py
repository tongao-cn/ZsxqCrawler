import unittest

from backend.services.file_task_lifecycle import (
    file_task_stopped_after_init,
)


class FileTaskLifecycleTests(unittest.TestCase):
    def test_file_task_stopped_after_init_logs_when_stopped(self):
        logs = []

        stopped = file_task_stopped_after_init(
            "task-1",
            is_stopped=lambda _task_id: True,
            add_log=lambda task_id, message: logs.append((task_id, message)),
        )

        self.assertTrue(stopped)
        self.assertEqual([("task-1", "🛑 任务在初始化过程中被停止")], logs)

    def test_file_task_stopped_after_init_skips_log_when_running(self):
        logs = []

        stopped = file_task_stopped_after_init(
            "task-1",
            is_stopped=lambda _task_id: False,
            add_log=lambda task_id, message: logs.append((task_id, message)),
        )

        self.assertFalse(stopped)
        self.assertEqual([], logs)


if __name__ == "__main__":
    unittest.main()
