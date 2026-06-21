import unittest

from backend.services.file_task_lifecycle import (
    fail_file_task,
    file_task_stopped_after_init,
    finish_file_task,
)


class FileTaskLifecycleTests(unittest.TestCase):
    def test_finish_file_task_logs_and_updates_with_result(self):
        logs = []
        updates = []

        updated = finish_file_task(
            "task-1",
            "completed",
            "文件下载完成",
            {"downloaded_files": {"downloaded": 1}},
            log_message="✅ 文件下载完成！",
            add_log=lambda task_id, message: logs.append((task_id, message)),
            update=lambda *args: updates.append(args),
        )

        self.assertTrue(updated)
        self.assertEqual([("task-1", "✅ 文件下载完成！")], logs)
        self.assertEqual(
            [("task-1", "completed", "文件下载完成", {"downloaded_files": {"downloaded": 1}})],
            updates,
        )

    def test_finish_file_task_uses_three_argument_update_without_result(self):
        updates = []

        updated = finish_file_task(
            "task-1",
            "completed",
            "完成",
            update=lambda *args: updates.append(args),
        )

        self.assertTrue(updated)
        self.assertEqual([("task-1", "completed", "完成")], updates)

    def test_finish_file_task_skips_stopped_task(self):
        logs = []
        updates = []

        updated = finish_file_task(
            "task-1",
            "completed",
            "完成",
            {"done": True},
            log_message="done",
            skip_if_stopped=True,
            is_stopped=lambda _task_id: True,
            add_log=lambda task_id, message: logs.append((task_id, message)),
            update=lambda *args: updates.append(args),
        )

        self.assertFalse(updated)
        self.assertEqual([], logs)
        self.assertEqual([], updates)

    def test_fail_file_task_logs_and_updates_failure_with_result(self):
        logs = []
        updates = []

        fail_file_task(
            "task-1",
            "下载失败: boom",
            "下载失败: boom",
            {"failed": 1},
            is_stopped=lambda _task_id: False,
            add_log=lambda task_id, message: logs.append((task_id, message)),
            update=lambda *args: updates.append(args),
        )

        self.assertEqual([("task-1", "❌ 下载失败: boom")], logs)
        self.assertEqual([("task-1", "failed", "下载失败: boom", {"failed": 1})], updates)

    def test_fail_file_task_skips_stopped_task(self):
        logs = []
        updates = []

        fail_file_task(
            "task-1",
            "下载失败: boom",
            "下载失败: boom",
            is_stopped=lambda _task_id: True,
            add_log=lambda task_id, message: logs.append((task_id, message)),
            update=lambda *args: updates.append(args),
        )

        self.assertEqual([], logs)
        self.assertEqual([], updates)

    def test_fail_file_task_swallows_lifecycle_errors(self):
        fail_file_task(
            "task-1",
            "下载失败: boom",
            "下载失败: boom",
            is_stopped=lambda _task_id: False,
            add_log=lambda _task_id, _message: (_ for _ in ()).throw(RuntimeError("log failed")),
            update=lambda *_args: (_ for _ in ()).throw(AssertionError("should not update")),
        )

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
