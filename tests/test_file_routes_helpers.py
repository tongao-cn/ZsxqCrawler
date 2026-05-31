import unittest
from unittest.mock import patch

from backend.routes.file_routes import (
    _build_check_local_file_status_response,
    _build_file_status_response,
    _build_sync_files_response,
    _enqueue_file_task,
    _get_download_file_status,
    _query_group_id,
    _resolve_download_record_status,
)
from backend.services.file_workflow_service import _close_crawler_file_databases


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

    def test_enqueue_file_task_can_attach_group_metadata(self):
        background_tasks = FakeBackgroundTasks()

        with (
            patch("backend.services.file_workflow_service.create_task", return_value="task-1") as create_task,
            patch("backend.services.file_workflow_service.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _enqueue_file_task(
                background_tasks,
                "analyze_files",
                "分析文件",
                fake_task,
                "group-1",
                [123],
                task_group_id="group-1",
            )

        create_task.assert_called_once_with("analyze_files", "分析文件", metadata={"group_id": "group-1"})
        self.assertEqual({"task_id": "task-1", "message": "任务已创建，正在后台执行"}, response)
        enqueue_runtime_task.assert_called_once_with(fake_task, "task-1", "group-1", [123])
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

    def test_download_selected_files_uses_one_group_ingestion_task(self):
        from backend.routes.file_routes import download_selected_files, run_selected_file_download_task
        from backend.schemas.files import FileIdListRequest

        background_tasks = FakeBackgroundTasks()

        with patch("backend.routes.file_routes._enqueue_file_task", return_value={"task_id": "task-1", "message": "ok"}) as enqueue:
            response = self._run_async(
                download_selected_files(
                    "group-1",
                    FileIdListRequest(file_ids=[123, 456]),
                    background_tasks,
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        enqueue.assert_called_once_with(
            background_tasks,
            "download_selected_files",
            "下载选中文件 (2 个)",
            run_selected_file_download_task,
            "group-1",
            [123, 456],
            message="选中文件下载任务已创建",
            ingestion_group_id="group-1",
        )

    def test_download_filtered_files_uses_one_group_ingestion_task(self):
        from backend.routes.file_routes import download_filtered_files, run_filtered_file_download_task
        from backend.schemas.files import FileFilteredDownloadRequest

        background_tasks = FakeBackgroundTasks()

        with patch("backend.routes.file_routes._enqueue_file_task", return_value={"task_id": "task-1", "message": "ok"}) as enqueue:
            response = self._run_async(
                download_filtered_files(
                    "group-1",
                    FileFilteredDownloadRequest(status="failed", search="pdf", max_files=10),
                    background_tasks,
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        enqueue.assert_called_once_with(
            background_tasks,
            "download_filtered_files",
            "下载筛选结果",
            run_filtered_file_download_task,
            "group-1",
            "failed",
            "pdf",
            10,
            message="筛选结果下载任务已创建",
            ingestion_group_id="group-1",
        )

    def test_sync_files_from_topics_is_enqueued(self):
        from backend.routes.file_routes import sync_files_from_topics, run_sync_files_from_topics_task

        background_tasks = FakeBackgroundTasks()

        with patch("backend.routes.file_routes._enqueue_file_task", return_value={"task_id": "task-1", "message": "ok"}) as enqueue:
            response = self._run_async(sync_files_from_topics("group-1", background_tasks))

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        enqueue.assert_called_once_with(
            background_tasks,
            "sync_files_from_topics",
            "从话题同步文件记录 (群组: group-1)",
            run_sync_files_from_topics_task,
            "group-1",
            message="从话题同步文件记录任务已创建",
            ingestion_group_id="group-1",
        )

    def test_file_analysis_task_attaches_group_metadata(self):
        from backend.routes.file_routes import create_file_analysis_task, run_file_analysis_task
        from backend.schemas.files import FileAIAnalysisRequest

        background_tasks = FakeBackgroundTasks()

        with (
            patch("backend.routes.file_routes.has_openai_api_key", return_value=True),
            patch("backend.routes.file_routes._enqueue_file_task", return_value={"task_id": "task-1", "message": "ok"}) as enqueue,
        ):
            response = self._run_async(
                create_file_analysis_task(
                    "group-1",
                    123,
                    FileAIAnalysisRequest(force=True),
                    background_tasks,
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        enqueue.assert_called_once_with(
            background_tasks,
            "analyze_file",
            "分析文件 (ID: 123)",
            run_file_analysis_task,
            "group-1",
            [123],
            True,
            message="文件 AI 分析任务已创建",
            task_group_id="group-1",
        )

    def test_selected_file_analysis_task_attaches_group_metadata(self):
        from backend.routes.file_routes import create_selected_file_analysis_task, run_file_analysis_task
        from backend.schemas.files import FileAIAnalysisBatchRequest

        background_tasks = FakeBackgroundTasks()

        with (
            patch("backend.routes.file_routes.has_openai_api_key", return_value=True),
            patch("backend.routes.file_routes._enqueue_file_task", return_value={"task_id": "task-1", "message": "ok"}) as enqueue,
        ):
            response = self._run_async(
                create_selected_file_analysis_task(
                    "group-1",
                    FileAIAnalysisBatchRequest(file_ids=[123, 456], force=False),
                    background_tasks,
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        enqueue.assert_called_once_with(
            background_tasks,
            "analyze_files",
            "批量分析文件 (2 个)",
            run_file_analysis_task,
            "group-1",
            [123, 456],
            False,
            message="批量文件 AI 分析任务已创建",
            task_group_id="group-1",
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

    def test_file_status_routes_offload_sync_work_to_thread(self):
        from backend.routes import file_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"called": func.__name__, "args": args}

        with patch("backend.routes.file_routes.asyncio.to_thread", side_effect=fake_to_thread):
            file_status = self._run_async(file_routes.get_file_status("group-1", 123))
            local_status = self._run_async(file_routes.check_local_file_status("group-1", "file.pdf", 456))
            stats = self._run_async(file_routes.get_file_stats("group-1"))

        self.assertEqual(
            [
                (file_routes._get_file_status_response, ("group-1", 123)),
                (file_routes._check_local_file_status_response, ("group-1", "file.pdf", 456)),
                (file_routes._get_file_stats_response, ("group-1",)),
            ],
            calls,
        )
        self.assertEqual({"called": "_get_file_status_response", "args": ("group-1", 123)}, file_status)
        self.assertEqual({"called": "_check_local_file_status_response", "args": ("group-1", "file.pdf", 456)}, local_status)
        self.assertEqual({"called": "_get_file_stats_response", "args": ("group-1",)}, stats)

    def test_clear_file_database_offloads_sync_work_to_thread(self):
        from backend.routes import file_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"message": "ok", "deleted": {"files": 1}}

        with patch("backend.routes.file_routes.asyncio.to_thread", side_effect=fake_to_thread):
            response = self._run_async(file_routes.clear_file_database("group-1"))

        self.assertEqual([(file_routes._clear_file_database_response, ("group-1",))], calls)
        self.assertEqual({"message": "ok", "deleted": {"files": 1}}, response)

    def test_close_crawler_file_databases_closes_file_and_topic_dbs(self):
        crawler = FakeCrawler()

        _close_crawler_file_databases(crawler)

        self.assertTrue(crawler.downloader.file_db.closed)
        self.assertTrue(crawler.db.closed)

    def test_clear_file_database_does_not_construct_legacy_crawler(self):
        from backend.routes.file_routes import _clear_file_database_response

        with (
            patch("backend.routes.file_routes._clear_group_file_data", return_value={"files": 0}) as clear_data,
            patch("backend.core.crawler_runtime.get_crawler_for_group", side_effect=AssertionError("legacy crawler used")),
        ):
            response = _clear_file_database_response("group-1")

        clear_data.assert_called_once_with("group-1")
        self.assertEqual({"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 0}}, response)

    def test_query_group_id_casts_numeric_ids_for_sql_filters(self):
        self.assertEqual(123, _query_group_id("123"))
        self.assertEqual("abc", _query_group_id("abc"))

    def _run_async(self, coro):
        import asyncio

        return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
