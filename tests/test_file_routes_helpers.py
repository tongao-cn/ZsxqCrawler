import unittest
from unittest.mock import patch

from backend.routes.file_routes import (
    _build_check_local_file_status_response,
    _build_file_status_response,
    _build_sync_files_response,
    _close_crawler_file_databases,
    _enqueue_file_task,
    _get_download_file_status,
    _query_group_id,
    _resolve_download_record_status,
)


class FakeBackgroundTasks:
    def __init__(self):
        self.calls = []

    def add_task(self, func, *args):
        self.calls.append((func, args))


def fake_task(*args):
    return args


class FakeClosable:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeDownloader:
    def __init__(self):
        self.file_db = FakeClosable()


class FakeCrawler:
    def __init__(self):
        self.downloader = FakeDownloader()
        self.db = FakeClosable()

    def get_file_downloader(self):
        return self.downloader


class FileRoutesHelperTests(unittest.TestCase):
    def test_enqueue_file_task_creates_task_and_schedules_callback(self):
        background_tasks = FakeBackgroundTasks()

        with (
            patch("backend.services.file_workflow_service.create_task", return_value="task-1") as create_task,
            patch("backend.services.file_workflow_service.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _enqueue_file_task(
                background_tasks,
                "unit_file_task",
                "测试文件任务",
                fake_task,
                "group-1",
                123,
                message="已创建",
            )

        create_task.assert_called_once_with("unit_file_task", "测试文件任务")
        self.assertEqual({"task_id": "task-1", "message": "已创建"}, response)
        enqueue_runtime_task.assert_called_once_with(fake_task, "task-1", "group-1", 123)
        self.assertEqual([], background_tasks.calls)

    def test_enqueue_file_task_uses_ingestion_lock_when_requested(self):
        background_tasks = FakeBackgroundTasks()

        with (
            patch("backend.routes.ingestion_helpers.create_ingestion_task", return_value=("task-1", None)) as create_task,
            patch("backend.services.file_workflow_service.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _enqueue_file_task(
                background_tasks,
                "collect_files",
                "收集文件列表",
                fake_task,
                "group-1",
                "request",
                ingestion_group_id="group-1",
            )

        create_task.assert_called_once_with("collect_files", "收集文件列表", "group-1")
        self.assertEqual({"task_id": "task-1", "message": "任务已创建，正在后台执行"}, response)
        enqueue_runtime_task.assert_called_once_with(fake_task, "task-1", "group-1", "request")
        self.assertEqual([], background_tasks.calls)

    def test_download_single_file_uses_group_ingestion_lock(self):
        from backend.routes.file_routes import download_single_file, run_single_file_download_task_with_info

        background_tasks = FakeBackgroundTasks()

        with patch("backend.routes.file_routes._enqueue_file_task", return_value={"task_id": "task-1", "message": "ok"}) as enqueue:
            response = self._run_async(
                download_single_file(
                    "group-1",
                    123,
                    background_tasks,
                    file_name="file.pdf",
                    file_size=456,
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        enqueue.assert_called_once_with(
            background_tasks,
            "download_single_file",
            "下载单个文件 (ID: 123)",
            run_single_file_download_task_with_info,
            "group-1",
            123,
            "file.pdf",
            456,
            message="单个文件下载任务已创建",
            ingestion_group_id="group-1",
        )

    def test_enqueue_file_task_rejects_ingestion_conflict(self):
        from fastapi import HTTPException

        existing = {"task_id": "task-old", "type": "crawl_latest", "status": "running"}
        background_tasks = FakeBackgroundTasks()

        with patch("backend.routes.ingestion_helpers.create_ingestion_task", return_value=(None, existing)):
            with self.assertRaises(HTTPException) as raised:
                _enqueue_file_task(
                    background_tasks,
                    "collect_files",
                    "收集文件列表",
                    fake_task,
                    "group-1",
                    ingestion_group_id="group-1",
                )

        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual([], background_tasks.calls)

    def test_get_download_file_status_handles_missing_file(self):
        with patch("backend.services.file_workflow_service.get_db_path_manager") as mocked_manager:
            mocked_manager.return_value.get_group_dir.return_value = r"C:\tmp\group-1"

            status = _get_download_file_status("group-1", "missing.pdf", 123, "fallback.pdf")

        self.assertEqual("missing.pdf", status["safe_filename"])
        self.assertFalse(status["local_exists"])
        self.assertEqual(0, status["local_size"])
        self.assertIsNone(status["local_path"])
        self.assertFalse(status["is_complete"])

    def test_resolve_download_record_status_marks_existing_file_completed(self):
        with patch("backend.services.file_workflow_service.resolve_local_file_path") as mocked_resolve:
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

    def test_build_file_status_response_handles_missing_file(self):
        response = _build_file_status_response(123, None)

        self.assertEqual(
            {
                "file_id": 123,
                "name": "file_123",
                "size": 0,
                "download_status": "not_collected",
                "local_exists": False,
                "local_size": 0,
                "local_path": None,
                "is_complete": False,
                "message": "文件信息未收集，请先运行文件收集任务",
            },
            response,
        )

    def test_build_file_status_response_defaults_pending_status(self):
        local_status = {
            "local_exists": True,
            "local_size": 456,
            "local_path": r"C:\tmp\group-1\downloads\file.pdf",
            "is_complete": True,
        }

        response = _build_file_status_response(123, ("file.pdf", 456, None), local_status)

        self.assertEqual(
            {
                "file_id": 123,
                "name": "file.pdf",
                "size": 456,
                "download_status": "pending",
                "local_exists": True,
                "local_size": 456,
                "local_path": r"C:\tmp\group-1\downloads\file.pdf",
                "is_complete": True,
            },
            response,
        )

    def test_build_check_local_file_status_response_keeps_shape(self):
        local_status = {
            "safe_filename": "file.pdf",
            "local_exists": False,
            "local_size": 0,
            "local_path": None,
            "is_complete": False,
            "download_dir": r"C:\tmp\group-1\downloads",
        }

        response = _build_check_local_file_status_response("file.pdf", 456, local_status)

        self.assertEqual(
            {
                "file_name": "file.pdf",
                "safe_filename": "file.pdf",
                "expected_size": 456,
                "local_exists": False,
                "local_size": 0,
                "local_path": None,
                "is_complete": False,
                "download_dir": r"C:\tmp\group-1\downloads",
            },
            response,
        )

    def test_build_sync_files_response_keeps_shape(self):
        stats = {"inserted": 2, "updated": 1}

        response = _build_sync_files_response("group-1", stats)

        self.assertEqual({"success": True, "group_id": "group-1", "stats": stats}, response)

    def test_close_crawler_file_databases_closes_file_and_topic_dbs(self):
        crawler = FakeCrawler()

        _close_crawler_file_databases(crawler)

        self.assertTrue(crawler.downloader.file_db.closed)
        self.assertTrue(crawler.db.closed)

    def test_query_group_id_casts_numeric_ids_for_sql_filters(self):
        self.assertEqual(123, _query_group_id("123"))
        self.assertEqual("abc", _query_group_id("abc"))

    def _run_async(self, coro):
        import asyncio

        return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
