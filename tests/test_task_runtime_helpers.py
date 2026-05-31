import unittest
import asyncio
import queue
from threading import Event
from unittest.mock import patch


class FakeTaskStore:
    def __init__(self):
        self.tasks = {}
        self.stop_flags = {}
        self.logs = []
        self.released_locks = []
        self.heartbeats = []

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def max_task_sequence(self):
        return 0

    def set_stop_flag(self, task_id, stopped=True):
        self.stop_flags[task_id] = stopped

    def add_log(self, task_id, message):
        self.logs.append((task_id, message))
        return message

    def get_logs(self, task_id):
        return []

    def update_task(self, task_id, status, message, result=None, updated_at=None):
        self.tasks[task_id].update({"status": status, "message": message, "result": result, "updated_at": updated_at})
        return self.tasks[task_id]

    def create_task_with_lock(self, task_id, task_type, message, group_id, category, metadata=None, lease_minutes=30, created_at=None):
        task = {
            "task_id": task_id,
            "type": task_type,
            "status": "pending",
            "message": message,
            "result": None,
            "created_at": created_at,
            "updated_at": created_at,
        }
        if metadata:
            task.update(metadata)
        self.tasks[task_id] = task
        return task, None

    def release_task_lock(self, task_id, reason, released_at=None):
        self.released_locks.append((task_id, reason))

    def heartbeat_task_lock(self, task_id, lease_minutes=30, heartbeat_at=None):
        self.heartbeats.append(task_id)


class Stoppable:
    def __init__(self):
        self.stopped = False

    def set_stop_flag(self):
        self.stopped = True


class TaskRuntimeHelperTests(unittest.TestCase):
    def test_columns_fetch_is_ingestion_locked(self):
        from backend.services.task_runtime import INGESTION_LOCK_TYPES

        self.assertIn("columns_fetch", INGESTION_LOCK_TYPES)
        self.assertIn("download_single_file", INGESTION_LOCK_TYPES)

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
        store = FakeTaskStore()

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch.object(store, "create_task_with_lock", return_value=(None, existing)) as create_with_lock,
        ):
            task_id, conflict = create_ingestion_task("collect_files", "collect", "155")

        self.assertIsNone(task_id)
        self.assertEqual(existing, conflict)
        create_with_lock.assert_called_once()

    def test_create_ingestion_task_allows_different_group_when_no_conflict(self):
        from backend.services import task_runtime
        from backend.services.task_runtime import create_ingestion_task

        store = FakeTaskStore()

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_id, conflict = create_ingestion_task("collect_files", "collect", "166")
            finally:
                for task_id_to_remove in list(store.tasks):
                    task_runtime.current_tasks.pop(task_id_to_remove, None)
                    task_runtime.task_stop_flags.pop(task_id_to_remove, None)

        self.assertTrue(task_id.startswith("task_"))
        self.assertIsNone(conflict)
        self.assertEqual("166", store.tasks[task_id]["group_id"])
        self.assertEqual("ingestion", store.tasks[task_id]["ingestion_lock_key"])

    def test_stop_task_stops_registered_task_crawler(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}
        crawler = Stoppable()

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_runtime.register_task_crawler("task-1", crawler)

                stopped = task_runtime.stop_task("task-1")
            finally:
                task_runtime.unregister_task_crawler("task-1")
                task_runtime.task_stop_flags.pop("task-1", None)

        self.assertTrue(stopped)
        self.assertTrue(crawler.stopped)
        self.assertTrue(store.stop_flags["task-1"])
        self.assertEqual("cancelled", store.tasks["task-1"]["status"])
        self.assertEqual([("task-1", "cancelled")], store.released_locks)

    def test_update_task_releases_lock_on_terminal_status(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            task_runtime.current_tasks["task-1"] = dict(store.tasks["task-1"])
            try:
                task_runtime.update_task("task-1", "completed", "done")
            finally:
                task_runtime.current_tasks.pop("task-1", None)
                task_runtime.task_stop_flags.pop("task-1", None)

        self.assertEqual("completed", store.tasks["task-1"]["status"])
        self.assertEqual([("task-1", "completed")], store.released_locks)

    def test_get_task_logs_state_returns_memory_log_copy(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            task_runtime.task_logs["task-1"] = ["first"]
            try:
                logs = task_runtime.get_task_logs_state("task-1")
                logs.append("mutated")
                self.assertEqual(["first"], task_runtime.task_logs["task-1"])
            finally:
                task_runtime.task_logs.pop("task-1", None)

    def test_task_log_subscription_receives_broadcast_until_unsubscribed(self):
        from backend.services import task_runtime

        subscriber = task_runtime.subscribe_task_logs("task-1")
        try:
            task_runtime.broadcast_log("task-1", "first")
            self.assertEqual("first", subscriber.get_nowait())

            task_runtime.unsubscribe_task_logs("task-1", subscriber)
            task_runtime.broadcast_log("task-1", "second")

            with self.assertRaises(queue.Empty):
                subscriber.get_nowait()
            self.assertNotIn("task-1", task_runtime.sse_connections)
        finally:
            task_runtime.sse_connections.pop("task-1", None)

    def test_update_task_does_not_overwrite_cancelled_status(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "cancelled", "message": "stopped"}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            task_runtime.update_task("task-1", "completed", "done")

        self.assertEqual("cancelled", store.tasks["task-1"]["status"])
        self.assertEqual([], store.released_locks)

    def test_request_runtime_shutdown_cancels_running_resources(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}
        store.tasks["task-2"] = {"task_id": "task-2", "status": "completed", "message": "done"}
        crawler = Stoppable()
        downloader = Stoppable()

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_runtime.current_tasks["task-1"] = dict(store.tasks["task-1"])
                task_runtime.current_tasks["task-2"] = dict(store.tasks["task-2"])
                task_runtime.register_task_crawler("task-1", crawler)
                task_runtime.file_downloader_instances["task-1"] = downloader
                task_runtime.sse_connections["task-1"] = [object()]

                task_runtime.request_runtime_shutdown()
            finally:
                task_runtime.current_tasks.clear()
                task_runtime.task_stop_flags.clear()
                task_runtime.crawler_instances.clear()
                task_runtime.file_downloader_instances.clear()
                task_runtime.sse_connections.clear()

        self.assertTrue(crawler.stopped)
        self.assertTrue(downloader.stopped)
        self.assertTrue(store.stop_flags["task-1"])
        self.assertEqual("cancelled", store.tasks["task-1"]["status"])
        self.assertEqual("completed", store.tasks["task-2"]["status"])
        self.assertEqual({}, task_runtime.sse_connections)

    def test_enqueue_runtime_task_runs_daemon_thread_and_unregisters(self):
        from backend.services import task_runtime

        seen = []
        release = Event()
        finished = Event()

        def task_func(task_id, value):
            seen.append((task_id, value))
            release.wait(2)
            finished.set()

        try:
            task_runtime.enqueue_runtime_task(task_func, "task-thread", "payload")
            thread = task_runtime.runtime_task_threads["task-thread"]
            self.assertTrue(thread.daemon)
            release.set()
            self.assertTrue(finished.wait(2))
            thread.join(2)
        finally:
            task_runtime.runtime_task_threads.pop("task-thread", None)

        self.assertEqual([("task-thread", "payload")], seen)
        self.assertNotIn("task-thread", task_runtime.runtime_task_threads)

    def test_enqueue_runtime_task_awaits_coroutine_tasks(self):
        from backend.services import task_runtime

        seen = []
        finished = Event()

        async def task_func(task_id, value):
            await asyncio.sleep(0)
            seen.append((task_id, value))
            finished.set()

        try:
            task_runtime.enqueue_runtime_task(task_func, "task-async", "payload")
            thread = task_runtime.runtime_task_threads["task-async"]
            self.assertTrue(finished.wait(2))
            thread.join(2)
        finally:
            task_runtime.runtime_task_threads.pop("task-async", None)

        self.assertEqual([("task-async", "payload")], seen)
        self.assertNotIn("task-async", task_runtime.runtime_task_threads)


if __name__ == "__main__":
    unittest.main()
