import unittest
import asyncio
import queue
from datetime import datetime
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
    def test_group_identity_normalization_is_core_and_a_share_compatible(self):
        from backend.core.group_identity import normalize_group_id
        from backend.services.a_share_analysis_local_store import normalize_group_id as a_share_normalize_group_id

        self.assertIs(a_share_normalize_group_id, normalize_group_id)
        self.assertIsNone(normalize_group_id(None))
        self.assertIsNone(normalize_group_id("  "))
        self.assertEqual("155", normalize_group_id(155))
        self.assertEqual("00155", normalize_group_id(" 00155 "))

    def test_columns_fetch_is_ingestion_locked(self):
        from backend.services.task_runtime import INGESTION_LOCK_TYPES

        self.assertIn("columns_fetch", INGESTION_LOCK_TYPES)
        self.assertIn("download_single_file", INGESTION_LOCK_TYPES)

    def test_runtime_status_helpers_preserve_task_state_contract(self):
        from backend.services.task_runtime import (
            TaskQuery,
            _is_active_task_status,
            _is_runtime_terminal_status,
            _normalize_task,
            is_terminal_task_status,
            latest_task_for_query,
            query_tasks,
        )

        self.assertTrue(_is_active_task_status("pending"))
        self.assertTrue(_is_active_task_status("running"))
        self.assertFalse(_is_active_task_status("completed"))

        self.assertTrue(_is_runtime_terminal_status("completed"))
        self.assertTrue(_is_runtime_terminal_status("failed"))
        self.assertTrue(_is_runtime_terminal_status("cancelled"))
        self.assertTrue(_is_runtime_terminal_status("stopped"))
        self.assertFalse(_is_runtime_terminal_status("running"))
        self.assertTrue(is_terminal_task_status("stopped"))
        self.assertFalse(is_terminal_task_status("running"))

        normalized = _normalize_task({"task_id": "task-1", "type": "a_share_analysis", "status": "stopped"})
        self.assertEqual("cancelled", normalized["status"])
        self.assertEqual("股票推荐池", normalized["display_name"])
        self.assertFalse(normalized["cancellable"])

        tasks = [
            {
                "task_id": "task-old",
                "type": "daily_analysis",
                "status": "completed",
                "group_id": 155,
                "created_at": datetime(2026, 1, 1, 9, 0, 0),
            },
            {
                "task_id": "task-new",
                "type": "daily_analysis",
                "status": "stopped",
                "group_id": "155",
                "created_at": datetime(2026, 1, 2, 9, 0, 0),
            },
            {
                "task_id": "task-other",
                "type": "file_analysis",
                "status": "completed",
                "group_id": "155",
                "created_at": datetime(2026, 1, 3, 9, 0, 0),
            },
        ]

        query = TaskQuery(task_type="daily_analysis", group_id="155", group_filter_provided=True, limit=1)
        self.assertEqual(["task-old"], [task["task_id"] for task in query_tasks(tasks, query)])
        latest = latest_task_for_query(
            tasks,
            TaskQuery(
                task_type="daily_analysis",
                status="cancelled",
                group_id=155,
                group_filter_provided=True,
            ),
        )
        self.assertEqual("task-new", latest["task_id"])
        self.assertEqual("cancelled", latest["status"])

    def test_get_task_state_prefers_persisted_task_over_memory_fallback(self):
        from backend.services import task_runtime
        from backend.services.task_runtime import get_task_state

        store = FakeTaskStore()
        store.tasks["task-1"] = {
            "task_id": "task-1",
            "status": "pending",
            "message": "persisted",
        }

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_runtime.current_tasks["task-1"] = {
                    "task_id": "task-1",
                    "status": "running",
                    "message": "memory",
                }

                task = get_task_state("task-1")
            finally:
                task_runtime.current_tasks.pop("task-1", None)

        self.assertEqual("pending", task["status"])
        self.assertEqual("persisted", task["message"])

    def test_get_task_state_falls_back_to_normalized_memory_task(self):
        from backend.services import task_runtime
        from backend.services.task_runtime import get_task_state

        store = FakeTaskStore()

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_runtime.current_tasks["task-1"] = {
                    "task_id": "task-1",
                    "status": "stopped",
                    "message": "memory",
                }

                task = get_task_state("task-1")
                missing_task = get_task_state("missing-task")
            finally:
                task_runtime.current_tasks.pop("task-1", None)

        self.assertEqual("cancelled", task["status"])
        self.assertEqual("memory", task["message"])
        self.assertIsNone(missing_task)

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

    def test_list_tasks_filters_type_group_and_limits_after_filtering(self):
        from backend.services.task_runtime import list_tasks

        store = FakeTaskStore()
        store.tasks = {
            "task-other-group": {
                "task_id": "task-other-group",
                "type": "daily_analysis",
                "status": "running",
                "group_id": "166",
            },
            "task-match-old": {
                "task_id": "task-match-old",
                "type": "daily_analysis",
                "status": "running",
                "group_id": "155",
            },
            "task-match-new": {
                "task_id": "task-match-new",
                "type": "daily_analysis",
                "status": "running",
                "group_id": "155",
            },
            "task-other-type": {
                "task_id": "task-other-type",
                "type": "file_analysis",
                "status": "running",
                "group_id": "155",
            },
            "task-global": {
                "task_id": "task-global",
                "type": "daily_analysis",
                "status": "running",
                "group_id": None,
            },
        }

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            scoped_tasks = list_tasks(limit=1, group_id="155", task_type="daily_analysis")
            global_tasks = list_tasks(group_id=None, task_type="daily_analysis")

        self.assertEqual(["task-match-old"], [task["task_id"] for task in scoped_tasks])
        self.assertEqual(["task-global"], [task["task_id"] for task in global_tasks])

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

    def test_get_latest_task_by_type_filters_status_group_and_sorts_latest(self):
        from backend.services.task_runtime import get_latest_task_by_type

        store = FakeTaskStore()
        store.tasks = {
            "task-old": {
                "task_id": "task-old",
                "type": "daily_analysis",
                "status": "completed",
                "group_id": 155,
                "created_at": datetime(2026, 1, 1, 9, 0, 0),
            },
            "task-new": {
                "task_id": "task-new",
                "type": "daily_analysis",
                "status": "completed",
                "group_id": "155",
                "created_at": datetime(2026, 1, 2, 9, 0, 0),
            },
            "task-wrong-status": {
                "task_id": "task-wrong-status",
                "type": "daily_analysis",
                "status": "running",
                "group_id": "155",
                "created_at": datetime(2026, 1, 3, 9, 0, 0),
            },
            "task-wrong-group": {
                "task_id": "task-wrong-group",
                "type": "daily_analysis",
                "status": "completed",
                "group_id": "166",
                "created_at": datetime(2026, 1, 4, 9, 0, 0),
            },
            "task-global": {
                "task_id": "task-global",
                "type": "daily_analysis",
                "status": "completed",
                "group_id": None,
                "created_at": datetime(2026, 1, 3, 9, 0, 0),
            },
            "task-stopped": {
                "task_id": "task-stopped",
                "type": "daily_analysis",
                "status": "stopped",
                "group_id": "155",
                "created_at": datetime(2026, 1, 5, 9, 0, 0),
            },
            "task-other-type": {
                "task_id": "task-other-type",
                "type": "file_analysis",
                "status": "completed",
                "group_id": "155",
                "created_at": datetime(2026, 1, 6, 9, 0, 0),
            },
        }

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            latest_completed = get_latest_task_by_type("daily_analysis", status="completed", group_id="155")
            latest_cancelled = get_latest_task_by_type("daily_analysis", status="cancelled", group_id=155)
            latest_any_completed = get_latest_task_by_type("daily_analysis", status="completed")
            latest_global_completed = get_latest_task_by_type("daily_analysis", status="completed", group_id=None)

        self.assertEqual("task-new", latest_completed["task_id"])
        self.assertEqual("task-stopped", latest_cancelled["task_id"])
        self.assertEqual("cancelled", latest_cancelled["status"])
        self.assertEqual("task-wrong-group", latest_any_completed["task_id"])
        self.assertEqual("task-global", latest_global_completed["task_id"])

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
                task_runtime.register_task_file_downloader("task-1", downloader)

                stopped = task_runtime.stop_task("task-1")
            finally:
                task_runtime.unregister_task_crawler("task-1")
                task_runtime.unregister_task_file_downloader("task-1")
                task_runtime.task_stop_flags.pop("task-1", None)

        self.assertTrue(stopped)
        self.assertTrue(crawler.stopped)
        self.assertTrue(downloader.stopped)
        self.assertTrue(store.stop_flags["task-1"])
        self.assertEqual("cancelled", store.tasks["task-1"]["status"])
        self.assertEqual([("task-1", "cancelled")], store.released_locks)

    def test_is_task_cancellable_uses_workflow_spec(self):
        from backend.services import task_runtime

        self.assertFalse(task_runtime.is_task_cancellable({"type": "a_share_analysis"}))
        self.assertTrue(task_runtime.is_task_cancellable({"type": "download_selected_files"}))
        self.assertTrue(task_runtime.is_task_cancellable({"type": "legacy_task"}))

    def test_stop_task_refuses_non_cancellable_workflow(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {
            "task_id": "task-1",
            "type": "a_share_analysis",
            "status": "running",
            "message": "running",
        }
        crawler = Stoppable()
        downloader = Stoppable()

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            try:
                task_runtime.register_task_crawler("task-1", crawler)
                task_runtime.register_task_file_downloader("task-1", downloader)

                stopped = task_runtime.stop_task("task-1")
            finally:
                task_runtime.unregister_task_crawler("task-1")
                task_runtime.unregister_task_file_downloader("task-1")
                task_runtime.task_stop_flags.pop("task-1", None)

        self.assertFalse(stopped)
        self.assertFalse(crawler.stopped)
        self.assertFalse(downloader.stopped)
        self.assertNotIn("task-1", store.stop_flags)
        self.assertEqual("running", store.tasks["task-1"]["status"])
        self.assertEqual([], store.released_locks)
        self.assertEqual([("task-1", "⚠️ 该任务类型不支持停止请求")], store.logs)

    def test_unregister_task_crawler_removes_registered_crawler_and_is_idempotent(self):
        from backend.services import task_runtime

        crawler = Stoppable()

        try:
            task_runtime.register_task_crawler("task-1", crawler)
            self.assertIs(crawler, task_runtime.crawler_instances["task-1"])

            task_runtime.unregister_task_crawler("task-1")
            task_runtime.unregister_task_crawler("task-1")
        finally:
            task_runtime.crawler_instances.pop("task-1", None)

        self.assertNotIn("task-1", task_runtime.crawler_instances)

    def test_unregister_task_file_downloader_removes_registered_downloader_and_is_idempotent(self):
        from backend.services import task_runtime

        downloader = Stoppable()

        try:
            task_runtime.register_task_file_downloader("task-1", downloader)
            self.assertIs(downloader, task_runtime.file_downloader_instances["task-1"])

            task_runtime.unregister_task_file_downloader("task-1")
            task_runtime.unregister_task_file_downloader("task-1")
        finally:
            task_runtime.file_downloader_instances.pop("task-1", None)

        self.assertNotIn("task-1", task_runtime.file_downloader_instances)

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

    def test_update_task_updates_memory_task_when_present(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            task_runtime.current_tasks["task-1"] = dict(store.tasks["task-1"])
            try:
                task_runtime.update_task("task-1", "running", "working", result={"ok": True})
                memory_task = dict(task_runtime.current_tasks["task-1"])
            finally:
                task_runtime.current_tasks.pop("task-1", None)
                task_runtime.task_logs.pop("task-1", None)

        self.assertEqual("running", memory_task["status"])
        self.assertEqual("working", memory_task["message"])
        self.assertEqual({"ok": True}, memory_task["result"])
        self.assertEqual("running", store.tasks["task-1"]["status"])
        self.assertEqual([("task-1", "状态更新: working")], store.logs)

    def test_update_task_returns_when_task_is_unknown(self):
        from backend.services import task_runtime

        store = FakeTaskStore()

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch.object(store, "update_task", side_effect=AssertionError("store should not be updated")),
            patch("backend.services.task_runtime.add_task_log", side_effect=AssertionError("log should not be added")),
        ):
            task_runtime.update_task("missing-task", "running", "working")

    def test_run_workflow_updates_running_and_completed_with_result(self):
        from backend.services.task_runtime import run_workflow

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message="done now",
                failure_label="每日股票概念提取",
                work=lambda: {"ok": True},
            )

        self.assertEqual("completed", store.tasks["task-1"]["status"])
        self.assertEqual("done now", store.tasks["task-1"]["message"])
        self.assertEqual({"ok": True}, store.tasks["task-1"]["result"])
        self.assertIn(("task-1", "状态更新: running now"), store.logs)
        self.assertIn(("task-1", "状态更新: done now"), store.logs)
        self.assertEqual([("task-1", "completed")], store.released_locks)

    def test_run_workflow_resolves_dynamic_messages_in_order(self):
        from backend.services.task_runtime import run_workflow

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}
        events = []

        def running_message():
            events.append("running_message")
            return "running dynamic"

        def work():
            events.append("work")
            return {"ok": True}

        def completed_message(result):
            events.append(("completed_message", result))
            return "done dynamic"

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message=running_message,
                completed_message=completed_message,
                failure_label="每日股票概念提取",
                work=work,
            )

        self.assertEqual(["running_message", "work", ("completed_message", {"ok": True})], events)
        self.assertEqual("completed", store.tasks["task-1"]["status"])
        self.assertEqual("done dynamic", store.tasks["task-1"]["message"])
        self.assertEqual({"ok": True}, store.tasks["task-1"]["result"])
        self.assertIn(("task-1", "状态更新: running dynamic"), store.logs)
        self.assertIn(("task-1", "状态更新: done dynamic"), store.logs)

    def test_run_workflow_applies_explicit_terminal_decision(self):
        from backend.services.task_runtime import finish_workflow, run_workflow

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}
        result = {"analysis": {"failed": 1}}

        def completed_message(_result):
            self.fail("explicit terminal messages should bypass completed_message")

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message=completed_message,
                failure_label="文件分析任务",
                work=lambda: finish_workflow("failed", "文件分析全部失败", result),
            )

        self.assertEqual("failed", store.tasks["task-1"]["status"])
        self.assertEqual("文件分析全部失败", store.tasks["task-1"]["message"])
        self.assertEqual(result, store.tasks["task-1"]["result"])
        self.assertIn(("task-1", "状态更新: running now"), store.logs)
        self.assertIn(("task-1", "状态更新: 文件分析全部失败"), store.logs)
        self.assertEqual([("task-1", "failed")], store.released_locks)

    def test_run_workflow_calls_completion_hook_after_terminal_update(self):
        from backend.services.task_runtime import run_workflow

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}
        events = []

        def on_completed(result):
            events.append(("hook", store.tasks["task-1"]["status"], result))

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message="done now",
                failure_label="每日股票概念提取",
                work=lambda: {"ok": True},
                on_completed=on_completed,
            )

        self.assertEqual([("hook", "completed", {"ok": True})], events)
        self.assertEqual("completed", store.tasks["task-1"]["status"])
        self.assertEqual("done now", store.tasks["task-1"]["message"])
        self.assertIn(("task-1", "状态更新: done now"), store.logs)

    def test_run_workflow_skips_completion_hook_when_work_skips_completion(self):
        from backend.services.task_runtime import run_workflow, skip_workflow_completion

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}
        events = []

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message="done now",
                failure_label="每日股票概念提取",
                work=skip_workflow_completion,
                on_completed=lambda result: events.append(result),
            )

        self.assertEqual([], events)
        self.assertEqual("running", store.tasks["task-1"]["status"])

    def test_run_workflow_skips_completion_hook_when_stopped_after_work(self):
        from backend.services.task_runtime import run_workflow

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}
        events = []

        def stop_after_work():
            store.stop_flags["task-1"] = True
            return {"ok": True}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message="done now",
                failure_label="每日股票概念提取",
                work=stop_after_work,
                on_completed=lambda result: events.append(result),
            )

        self.assertEqual([], events)
        self.assertEqual("running", store.tasks["task-1"]["status"])

    def test_run_workflow_can_swallow_failure_reporting_errors(self):
        from backend.services.task_runtime import run_workflow

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}

        def fail():
            raise RuntimeError("boom")

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch(
                "backend.services.task_workflow_lifecycle.fail_task_unless_stopped",
                side_effect=RuntimeError("report down"),
            ) as fail_task,
        ):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message="done now",
                failure_label="每日股票概念提取",
                work=fail,
                swallow_failure_reporting_errors=True,
            )

        fail_task.assert_called_once()

    def test_run_workflow_logs_and_fails_unstopped_exception(self):
        from backend.services.task_runtime import run_workflow

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}

        def fail():
            raise RuntimeError("boom")

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message="done now",
                failure_label="每日股票概念提取",
                work=fail,
            )

        self.assertEqual("failed", store.tasks["task-1"]["status"])
        self.assertEqual("每日股票概念提取失败: boom", store.tasks["task-1"]["message"])
        self.assertIn(("task-1", "❌ 每日股票概念提取失败: boom"), store.logs)
        self.assertIn(("task-1", "状态更新: 每日股票概念提取失败: boom"), store.logs)
        self.assertEqual([("task-1", "failed")], store.released_locks)

    def test_run_workflow_skips_completion_when_stopped_after_work(self):
        from backend.services.task_runtime import run_workflow

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}

        def stop_after_work():
            store.stop_flags["task-1"] = True
            return {"ok": True}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message="done now",
                failure_label="每日股票概念提取",
                work=stop_after_work,
            )

        self.assertEqual("running", store.tasks["task-1"]["status"])
        self.assertEqual("running now", store.tasks["task-1"]["message"])
        self.assertIsNone(store.tasks["task-1"]["result"])
        self.assertEqual([], store.released_locks)

    def test_run_workflow_allows_work_to_skip_completion(self):
        from backend.services.task_runtime import run_workflow, skip_workflow_completion

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message="done now",
                failure_label="每日股票概念提取",
                work=skip_workflow_completion,
            )

        self.assertEqual("running", store.tasks["task-1"]["status"])
        self.assertEqual("running now", store.tasks["task-1"]["message"])
        self.assertIsNone(store.tasks["task-1"]["result"])
        self.assertEqual([("task-1", "状态更新: running now")], store.logs)
        self.assertEqual([], store.released_locks)

    def test_run_workflow_skips_work_when_already_stopped(self):
        from backend.services.task_runtime import run_workflow

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}
        store.stop_flags["task-1"] = True
        work_calls = []

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            run_workflow(
                "task-1",
                running_message="running now",
                completed_message="done now",
                failure_label="每日股票概念提取",
                work=lambda: work_calls.append("called"),
            )

        self.assertEqual([], work_calls)
        self.assertEqual("pending", store.tasks["task-1"]["status"])
        self.assertEqual("queued", store.tasks["task-1"]["message"])
        self.assertEqual([], store.logs)
        self.assertEqual([], store.released_locks)

    def test_complete_task_unless_stopped_updates_completed_with_result(self):
        from backend.services.task_runtime import complete_task_unless_stopped

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            complete_task_unless_stopped("task-1", "done now", {"ok": True})

        self.assertEqual("completed", store.tasks["task-1"]["status"])
        self.assertEqual("done now", store.tasks["task-1"]["message"])
        self.assertEqual({"ok": True}, store.tasks["task-1"]["result"])
        self.assertIn(("task-1", "状态更新: done now"), store.logs)
        self.assertEqual([("task-1", "completed")], store.released_locks)

    def test_complete_task_unless_stopped_skips_stopped_task(self):
        from backend.services.task_runtime import complete_task_unless_stopped

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}
        store.stop_flags["task-1"] = True

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            complete_task_unless_stopped("task-1", "done now", {"ok": True})

        self.assertEqual("pending", store.tasks["task-1"]["status"])
        self.assertEqual("queued", store.tasks["task-1"]["message"])
        self.assertEqual([], store.logs)
        self.assertEqual([], store.released_locks)

    def test_fail_task_unless_stopped_logs_and_fails_unstopped_exception(self):
        from backend.services.task_runtime import fail_task_unless_stopped

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            fail_task_unless_stopped("task-1", "每日抓取与 AI 分析", RuntimeError("boom"))

        self.assertEqual("failed", store.tasks["task-1"]["status"])
        self.assertEqual("每日抓取与 AI 分析失败: boom", store.tasks["task-1"]["message"])
        self.assertIn(("task-1", "❌ 每日抓取与 AI 分析失败: boom"), store.logs)
        self.assertIn(("task-1", "状态更新: 每日抓取与 AI 分析失败: boom"), store.logs)
        self.assertEqual([("task-1", "failed")], store.released_locks)

    def test_fail_task_unless_stopped_skips_stopped_task(self):
        from backend.services.task_runtime import fail_task_unless_stopped

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}
        store.stop_flags["task-1"] = True

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            fail_task_unless_stopped("task-1", "每日抓取与 AI 分析", RuntimeError("boom"))

        self.assertEqual("pending", store.tasks["task-1"]["status"])
        self.assertEqual("queued", store.tasks["task-1"]["message"])
        self.assertEqual([], store.logs)
        self.assertEqual([], store.released_locks)

    def test_fail_task_with_message_unless_stopped_logs_and_fails_unstopped_task(self):
        from backend.services.task_runtime import fail_task_with_message_unless_stopped

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            fail_task_with_message_unless_stopped(
                "task-1",
                "会员已过期",
                {"expired": True},
                log_message="❌ 会员已过期: expired",
            )

        self.assertEqual("failed", store.tasks["task-1"]["status"])
        self.assertEqual("会员已过期", store.tasks["task-1"]["message"])
        self.assertEqual({"expired": True}, store.tasks["task-1"]["result"])
        self.assertIn(("task-1", "❌ 会员已过期: expired"), store.logs)
        self.assertIn(("task-1", "状态更新: 会员已过期"), store.logs)
        self.assertEqual([("task-1", "failed")], store.released_locks)

    def test_fail_task_with_message_unless_stopped_skips_stopped_task(self):
        from backend.services.task_runtime import fail_task_with_message_unless_stopped

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "pending", "message": "queued"}
        store.stop_flags["task-1"] = True

        with patch("backend.services.task_runtime.get_task_store", return_value=store):
            fail_task_with_message_unless_stopped(
                "task-1",
                "会员已过期",
                {"expired": True},
                log_message="❌ 会员已过期: expired",
            )

        self.assertEqual("pending", store.tasks["task-1"]["status"])
        self.assertEqual("queued", store.tasks["task-1"]["message"])
        self.assertNotIn("result", store.tasks["task-1"])
        self.assertEqual([], store.logs)
        self.assertEqual([], store.released_locks)

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

    def test_build_task_log_callback_writes_task_log(self):
        from backend.services import task_runtime

        with patch("backend.services.task_runtime.add_task_log") as add_task_log:
            log_callback = task_runtime.build_task_log_callback("task-1")
            log_callback("hello")

        add_task_log.assert_called_once_with("task-1", "hello")

    def test_build_task_log_callback_uses_custom_log_writer(self):
        from backend.services.task_runtime import build_task_log_callback

        writes = []
        log_callback = build_task_log_callback(
            "task-1",
            lambda task_id, message: writes.append((task_id, message)),
        )

        log_callback("hello")

        self.assertEqual([("task-1", "hello")], writes)

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

    def test_task_log_unsubscribe_ignores_unknown_subscriber(self):
        from backend.services import task_runtime

        subscriber = task_runtime.subscribe_task_logs("task-1")
        unknown_subscriber = queue.Queue()
        try:
            task_runtime.unsubscribe_task_logs("task-1", unknown_subscriber)
            task_runtime.broadcast_log("task-1", "first")

            self.assertEqual("first", subscriber.get_nowait())
            self.assertIn(subscriber, task_runtime.sse_connections["task-1"])
        finally:
            task_runtime.sse_connections.pop("task-1", None)

    def test_task_log_unsubscribe_is_noop_for_unknown_task(self):
        from backend.services import task_runtime

        task_runtime.unsubscribe_task_logs("missing-task", queue.Queue())

        self.assertNotIn("missing-task", task_runtime.sse_connections)

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
                task_runtime.register_task_file_downloader("task-1", downloader)
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

    def test_start_task_lock_heartbeat_skips_non_ingestion_tasks(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {"task_id": "task-1", "status": "running", "message": "running"}

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch(
                "backend.services.task_runtime.threading.Thread",
                side_effect=AssertionError("heartbeat thread should not start"),
            ),
        ):
            task_runtime._start_task_lock_heartbeat("task-1")

        self.assertNotIn("task-1", task_runtime.runtime_task_heartbeats)

    def test_start_task_lock_heartbeat_registers_and_stop_clears_ingestion_heartbeat(self):
        from backend.services import task_runtime

        store = FakeTaskStore()
        store.tasks["task-1"] = {
            "task_id": "task-1",
            "status": "running",
            "message": "running",
            "ingestion_lock_key": "ingestion",
        }
        created_threads = []

        class FakeThread:
            def __init__(self, target, name, daemon):
                self.target = target
                self.name = name
                self.daemon = daemon
                self.started = False
                created_threads.append(self)

            def start(self):
                self.started = True

        with (
            patch("backend.services.task_runtime.get_task_store", return_value=store),
            patch("backend.services.task_runtime.threading.Thread", FakeThread),
        ):
            try:
                task_runtime._start_task_lock_heartbeat("task-1")
                heartbeat = task_runtime.runtime_task_heartbeats["task-1"]

                task_runtime._stop_task_lock_heartbeat("task-1")
            finally:
                task_runtime.runtime_task_heartbeats.clear()

        self.assertEqual(1, len(created_threads))
        self.assertEqual("zsxq-lock-heartbeat-task-1", created_threads[0].name)
        self.assertTrue(created_threads[0].daemon)
        self.assertTrue(created_threads[0].started)
        self.assertTrue(heartbeat.is_set())
        self.assertNotIn("task-1", task_runtime.runtime_task_heartbeats)

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
            self.assertEqual("zsxq-task-task-thread", thread.name)
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
