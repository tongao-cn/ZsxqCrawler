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
        self.max_sequence = 0

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def list_tasks(self, limit=None):
        tasks = list(self.tasks.values())
        return tasks[:limit] if limit is not None else tasks

    def max_task_sequence(self):
        return self.max_sequence

    def cleanup_completed(self, keep_latest=100):
        return {"deleted_tasks": 0, "deleted_logs": 0}

    def set_stop_flag(self, task_id, stopped=True):
        self.stop_flags[task_id] = stopped

    def is_stopped(self, task_id):
        return self.stop_flags.get(task_id, False)

    def add_log(self, task_id, message):
        self.logs.append((task_id, message))
        return message

    def get_logs(self, task_id):
        return []

    def update_task(self, task_id, status, message, result=None, updated_at=None):
        self.tasks[task_id].update({"status": status, "message": message, "result": result, "updated_at": updated_at})
        return self.tasks[task_id]

    def create_task(self, task_id, task_type, status, message, result=None, metadata=None, created_at=None, updated_at=None):
        task = {
            "task_id": task_id,
            "type": task_type,
            "status": status,
            "message": message,
            "result": result,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        if metadata:
            task.update(metadata)
        self.tasks[task_id] = task
        return task

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


class FailingSubscriber:
    def put_nowait(self, _message):
        raise RuntimeError("subscriber failed")


class StopFlagObserver:
    def __init__(self, flags, task_id):
        self.flags = flags
        self.task_id = task_id
        self.flag_when_stopped = None

    def set_stop_flag(self):
        self.flag_when_stopped = self.flags.get(self.task_id)


class TaskRuntimeHelperTests(unittest.TestCase):
    def test_columns_fetch_is_ingestion_locked(self):
        from backend.services.task_runtime import INGESTION_LOCK_TYPES

        self.assertIn("columns_fetch", INGESTION_LOCK_TYPES)
        self.assertIn("download_single_file", INGESTION_LOCK_TYPES)

    def test_runtime_status_helpers_preserve_task_state_contract(self):
        from backend.services.task_runtime import (
            _is_active_task_status,
            _is_runtime_terminal_status,
            _normalize_task,
        )

        self.assertTrue(_is_active_task_status("pending"))
        self.assertTrue(_is_active_task_status("running"))
        self.assertFalse(_is_active_task_status("completed"))

        self.assertTrue(_is_runtime_terminal_status("completed"))
        self.assertTrue(_is_runtime_terminal_status("failed"))
        self.assertTrue(_is_runtime_terminal_status("cancelled"))
        self.assertTrue(_is_runtime_terminal_status("stopped"))
        self.assertFalse(_is_runtime_terminal_status("running"))

        normalized = _normalize_task({"task_id": "task-1", "status": "stopped"})
        self.assertEqual("cancelled", normalized["status"])

    def test_create_task_uses_persisted_sequence_and_initializes_runtime_state(self):
        from backend.services import task_runtime
        from backend.services.task_runtime import create_task

        store = FakeTaskStore()
        store.max_sequence = 41
        original_counter = task_runtime.task_counter
        task_id = None

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            task_runtime.task_counter = 0
            try:
                task_id = create_task("daily_analysis", "run daily", metadata={"group_id": "155"})

                self.assertTrue(task_id.startswith("task_42_"))
                self.assertEqual("pending", store.tasks[task_id]["status"])
                self.assertEqual("155", store.tasks[task_id]["group_id"])
                self.assertEqual(False, store.stop_flags[task_id])
                self.assertEqual([(task_id, "任务创建: run daily")], store.logs)
                self.assertEqual("pending", task_runtime.current_tasks[task_id]["status"])
                self.assertEqual(["任务创建: run daily"], task_runtime.task_logs[task_id])
                self.assertEqual(False, task_runtime.task_stop_flags[task_id])
            finally:
                if task_id:
                    task_runtime.current_tasks.pop(task_id, None)
                    task_runtime.task_logs.pop(task_id, None)
                    task_runtime.task_stop_flags.pop(task_id, None)
                task_runtime.task_counter = original_counter

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
        task_id = None
        runtime_logs = None
        runtime_stop_flag = None

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_id, conflict = create_ingestion_task("collect_files", "collect", "166")
                runtime_logs = list(task_runtime.task_logs[task_id])
                runtime_stop_flag = task_runtime.task_stop_flags[task_id]
            finally:
                for task_id_to_remove in list(store.tasks):
                    task_runtime.current_tasks.pop(task_id_to_remove, None)
                    task_runtime.task_logs.pop(task_id_to_remove, None)
                    task_runtime.task_stop_flags.pop(task_id_to_remove, None)

        self.assertTrue(task_id.startswith("task_"))
        self.assertIsNone(conflict)
        self.assertEqual("166", store.tasks[task_id]["group_id"])
        self.assertEqual("ingestion", store.tasks[task_id]["ingestion_lock_key"])
        self.assertEqual(False, store.stop_flags[task_id])
        self.assertEqual([(task_id, "任务创建: collect")], store.logs)
        self.assertEqual(["任务创建: collect"], runtime_logs)
        self.assertEqual(False, runtime_stop_flag)

    def test_create_ingestion_task_builds_memory_task_when_store_returns_no_task(self):
        from backend.services import task_runtime
        from backend.services.task_runtime import create_ingestion_task

        store = FakeTaskStore()
        original_counter = task_runtime.task_counter
        task_id = None
        memory_task = None
        runtime_logs = None
        runtime_stop_flag = None

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch.object(
                store,
                "create_task_with_lock",
                return_value=(None, None),
            ) as create_with_lock,
        ):
            task_runtime.task_counter = 0
            try:
                task_id, conflict = create_ingestion_task("collect_files", "collect", "166")
                memory_task = dict(task_runtime.current_tasks[task_id])
                runtime_logs = list(task_runtime.task_logs[task_id])
                runtime_stop_flag = task_runtime.task_stop_flags[task_id]
            finally:
                if task_id:
                    task_runtime.current_tasks.pop(task_id, None)
                    task_runtime.task_logs.pop(task_id, None)
                    task_runtime.task_stop_flags.pop(task_id, None)
                task_runtime.task_counter = original_counter

        self.assertTrue(task_id.startswith("task_1_"))
        self.assertIsNone(conflict)
        create_with_lock.assert_called_once()
        self.assertEqual(task_id, memory_task["task_id"])
        self.assertEqual("collect_files", memory_task["type"])
        self.assertEqual("pending", memory_task["status"])
        self.assertEqual("collect", memory_task["message"])
        self.assertIsNone(memory_task["result"])
        self.assertEqual(memory_task["created_at"], memory_task["updated_at"])
        self.assertEqual("166", memory_task["group_id"])
        self.assertEqual("ingestion", memory_task["ingestion_lock_key"])
        self.assertEqual(False, store.stop_flags[task_id])
        self.assertEqual([(task_id, "任务创建: collect")], store.logs)
        self.assertEqual(["任务创建: collect"], runtime_logs)
        self.assertEqual(False, runtime_stop_flag)

    def test_cleanup_tasks_forgets_removed_runtime_tracking(self):
        from backend.services import task_runtime
        from backend.services.task_runtime import cleanup_tasks

        store = FakeTaskStore()
        tasks_before = [
            {"task_id": "task-removed", "status": "completed"},
            {"task_id": "task-kept", "status": "completed"},
        ]
        remaining_tasks = [{"task_id": "task-kept", "status": "completed"}]

        try:
            with (
                patch("backend.services.task_runtime.get_task_store", return_value=store),
                patch.object(store, "list_tasks", side_effect=[tasks_before, remaining_tasks]),
                patch.object(
                    store,
                    "cleanup_completed",
                    return_value={"deleted_tasks": 1, "deleted_logs": 2},
                ) as cleanup_completed,
            ):
                task_runtime.current_tasks["task-removed"] = {"task_id": "task-removed"}
                task_runtime.task_logs["task-removed"] = ["removed-log"]
                task_runtime.task_stop_flags["task-removed"] = True
                task_runtime.sse_connections["task-removed"] = [object()]
                task_runtime.current_tasks["task-kept"] = {"task_id": "task-kept"}
                task_runtime.task_logs["task-kept"] = ["kept-log"]
                task_runtime.task_stop_flags["task-kept"] = False
                task_runtime.sse_connections["task-kept"] = [object()]

                result = cleanup_tasks(keep_latest=-5)

                cleanup_completed.assert_called_once_with(keep_latest=0)
                self.assertEqual({"deleted_tasks": 1, "deleted_logs": 2}, result)
                self.assertNotIn("task-removed", task_runtime.current_tasks)
                self.assertNotIn("task-removed", task_runtime.task_logs)
                self.assertNotIn("task-removed", task_runtime.task_stop_flags)
                self.assertNotIn("task-removed", task_runtime.sse_connections)
                self.assertIn("task-kept", task_runtime.current_tasks)
                self.assertIn("task-kept", task_runtime.task_logs)
                self.assertIn("task-kept", task_runtime.task_stop_flags)
                self.assertIn("task-kept", task_runtime.sse_connections)
        finally:
            for task_id_to_remove in ("task-removed", "task-kept"):
                task_runtime.current_tasks.pop(task_id_to_remove, None)
                task_runtime.task_logs.pop(task_id_to_remove, None)
                task_runtime.task_stop_flags.pop(task_id_to_remove, None)
                task_runtime.sse_connections.pop(task_id_to_remove, None)

    def test_stop_task_stops_registered_task_crawler(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}
        crawler = Stoppable()
        downloader = Stoppable()

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_runtime.register_task_crawler("task-1", crawler)
                task_runtime.file_downloader_instances["task-1"] = downloader

                stopped = task_runtime.stop_task("task-1")
            finally:
                task_runtime.unregister_task_crawler("task-1")
                task_runtime.file_downloader_instances.pop("task-1", None)
                task_runtime.task_stop_flags.pop("task-1", None)

        self.assertTrue(stopped)
        self.assertTrue(crawler.stopped)
        self.assertTrue(downloader.stopped)
        self.assertTrue(store.stop_flags["task-1"])
        self.assertEqual("cancelled", store.tasks["task-1"]["status"])
        self.assertEqual([("task-1", "cancelled")], store.released_locks)

    def test_stop_task_marks_memory_stop_flag_before_stopping_resources(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}
        crawler = StopFlagObserver(task_runtime.task_stop_flags, "task-1")

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_runtime.register_task_crawler("task-1", crawler)

                stopped = task_runtime.stop_task("task-1")
            finally:
                task_runtime.unregister_task_crawler("task-1")
                task_runtime.task_stop_flags.pop("task-1", None)

        self.assertTrue(stopped)
        self.assertTrue(crawler.flag_when_stopped)

    def test_stop_task_uses_global_crawler_fallback_when_no_registered_crawler(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}
        crawler = Stoppable()

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch.object(task_runtime.crawler_runtime, "crawler_instance", crawler),
        ):
            try:
                stopped = task_runtime.stop_task("task-1")
            finally:
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

    def test_update_task_logs_lock_release_failure(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch.object(store, "release_task_lock", side_effect=RuntimeError("boom")),
        ):
            task_runtime.current_tasks["task-1"] = dict(store.tasks["task-1"])
            try:
                task_runtime.update_task("task-1", "completed", "done")
            finally:
                task_runtime.current_tasks.pop("task-1", None)
                task_runtime.task_stop_flags.pop("task-1", None)

        self.assertEqual("completed", store.tasks["task-1"]["status"])
        self.assertEqual(
            [
                ("task-1", "状态更新: done"),
                ("task-1", "⚠️ 释放任务锁失败: boom"),
            ],
            store.logs,
        )

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

    def test_get_task_logs_state_prefers_persisted_logs_over_memory_logs(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch.object(store, "get_logs", return_value=["persisted"]),
        ):
            task_runtime.task_logs["task-1"] = ["memory"]
            try:
                self.assertEqual(["persisted"], task_runtime.get_task_logs_state("task-1"))
            finally:
                task_runtime.task_logs.pop("task-1", None)

    def test_get_task_logs_state_returns_none_for_unknown_task_without_memory_logs(self):
        from backend.services import task_runtime

        store = FakeTaskStore()

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch.object(store, "get_logs", side_effect=AssertionError("logs should not be read")),
        ):
            self.assertIsNone(task_runtime.get_task_logs_state("missing-task"))

    def test_add_task_log_uses_persisted_log_text_for_memory_and_broadcast(self):
        from backend.services import task_runtime

        store = FakeTaskStore()

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch.object(store, "add_log", return_value="persisted:first") as add_log,
            patch("backend.services.task_runtime.broadcast_log") as broadcast_log,
        ):
            try:
                task_runtime.add_task_log("task-1", "first")

                add_log.assert_called_once_with("task-1", "first")
                self.assertEqual(["persisted:first"], task_runtime.task_logs["task-1"])
                broadcast_log.assert_called_once_with("task-1", "persisted:first")
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

    def test_broadcast_log_ignores_failing_subscriber(self):
        from backend.services import task_runtime

        subscriber = queue.Queue()
        task_runtime.sse_connections["task-1"] = [FailingSubscriber(), subscriber]

        try:
            task_runtime.broadcast_log("task-1", "first")

            self.assertEqual("first", subscriber.get_nowait())
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

    def test_is_task_stopped_short_circuits_when_memory_flag_is_set(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        task_runtime.task_stop_flags["task-1"] = True

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch.object(store, "is_stopped", side_effect=AssertionError("store should not be read")),
        ):
            try:
                self.assertTrue(task_runtime.is_task_stopped("task-1"))
            finally:
                task_runtime.task_stop_flags.pop("task-1", None)

    def test_is_task_stopped_falls_back_to_persisted_stop_flag(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.stop_flags["task-1"] = True

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            self.assertTrue(task_runtime.is_task_stopped("task-1"))
            self.assertFalse(task_runtime.is_task_stopped("task-2"))

    def test_request_stop_for_resources_ignores_objects_without_stop_flag(self):
        from backend.services.task_runtime import _request_stop_for_resources

        stoppable = Stoppable()

        _request_stop_for_resources([object(), stoppable])

        self.assertTrue(stoppable.stopped)

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
        self.assertEqual({}, task_runtime.crawler_instances)
        self.assertEqual({}, task_runtime.file_downloader_instances)

    def test_request_runtime_shutdown_marks_stop_flags_before_stopping_resources(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}
        crawler = StopFlagObserver(task_runtime.task_stop_flags, "task-1")

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_runtime.current_tasks["task-1"] = dict(store.tasks["task-1"])
                task_runtime.register_task_crawler("task-1", crawler)

                task_runtime.request_runtime_shutdown()

                self.assertTrue(crawler.flag_when_stopped)
            finally:
                task_runtime.current_tasks.clear()
                task_runtime.task_stop_flags.clear()
                task_runtime.crawler_instances.clear()
                task_runtime.file_downloader_instances.clear()
                task_runtime.sse_connections.clear()

    def test_request_runtime_shutdown_stops_heartbeats_and_clears_runtime_threads(self):
        from backend.services import task_runtime

        heartbeat = Event()

        try:
            task_runtime.runtime_task_heartbeats["task-1"] = heartbeat
            task_runtime.runtime_task_threads["task-1"] = object()

            task_runtime.request_runtime_shutdown()

            self.assertTrue(heartbeat.is_set())
            self.assertEqual({}, task_runtime.runtime_task_heartbeats)
            self.assertEqual({}, task_runtime.runtime_task_threads)
        finally:
            task_runtime.runtime_task_heartbeats.clear()
            task_runtime.runtime_task_threads.clear()

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
