import unittest
from datetime import datetime


class RecordingStore:
    def __init__(self):
        self.updates = []
        self.releases = []
        self.release_error = None

    def update_task(self, *args, **kwargs):
        self.updates.append((args, kwargs))

    def release_task_lock(self, *args, **kwargs):
        if self.release_error:
            raise self.release_error
        self.releases.append((args, kwargs))


class TaskTransitionRecorderTests(unittest.TestCase):
    def test_record_task_transition_updates_store_and_logs_non_terminal_status(self):
        from backend.services.task_transition_recorder import record_task_transition

        store = RecordingStore()
        logs = []
        now = datetime(2026, 6, 29, 10, 30)

        record_task_transition(
            store,
            "task-1",
            "running",
            "working",
            {"ok": True},
            now,
            add_task_log=lambda *args: logs.append(args),
            is_terminal_status=lambda status: status in {"completed", "failed"},
        )

        self.assertEqual(
            [(("task-1", "running", "working"), {"result": {"ok": True}, "updated_at": now})],
            store.updates,
        )
        self.assertEqual([("task-1", "状态更新: working")], logs)
        self.assertEqual([], store.releases)

    def test_record_task_transition_releases_lock_for_terminal_status(self):
        from backend.services.task_transition_recorder import record_task_transition

        store = RecordingStore()
        logs = []
        now = datetime(2026, 6, 29, 10, 30)

        record_task_transition(
            store,
            "task-1",
            "completed",
            "done",
            {"ok": True},
            now,
            add_task_log=lambda *args: logs.append(args),
            is_terminal_status=lambda status: status in {"completed", "failed"},
        )

        self.assertEqual([("task-1", "状态更新: done")], logs)
        self.assertEqual(
            [(("task-1", "completed"), {"released_at": now})],
            store.releases,
        )

    def test_record_task_transition_logs_lock_release_failure(self):
        from backend.services.task_transition_recorder import record_task_transition

        store = RecordingStore()
        store.release_error = RuntimeError("boom")
        logs = []

        record_task_transition(
            store,
            "task-1",
            "failed",
            "failed now",
            None,
            datetime(2026, 6, 29, 10, 30),
            add_task_log=lambda *args: logs.append(args),
            is_terminal_status=lambda status: status in {"completed", "failed"},
        )

        self.assertEqual(
            [
                ("task-1", "状态更新: failed now"),
                ("task-1", "⚠️ 释放任务锁失败: boom"),
            ],
            logs,
        )


if __name__ == "__main__":
    unittest.main()
