import unittest
from threading import Event
from unittest.mock import patch


class FakeTaskStore:
    def __init__(self):
        self.tasks = {}
        self.stop_flags = {}
        self.logs = []

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def set_stop_flag(self, task_id, stopped=True):
        self.stop_flags[task_id] = stopped

    def add_log(self, task_id, message):
        self.logs.append((task_id, message))
        return message

    def update_task(self, task_id, status, message, result=None, updated_at=None):
        self.tasks[task_id].update({"status": status, "message": message, "result": result, "updated_at": updated_at})
        return self.tasks[task_id]


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
                task_runtime.current_tasks.pop("task-1", None)
                task_runtime.current_tasks.pop("task-2", None)
                task_runtime.task_stop_flags.pop("task-1", None)
                task_runtime.task_stop_flags.pop("task-2", None)
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


if __name__ == "__main__":
    unittest.main()
