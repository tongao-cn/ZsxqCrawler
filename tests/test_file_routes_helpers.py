import unittest
from contextlib import ExitStack
from unittest.mock import patch

from backend.services.file_workflow_service import (
    _build_check_local_file_status_response,
    _build_download_file_info,
    _build_download_task_stats,
    _build_file_status_response,
    _build_sync_files_response,
    _close_crawler_file_databases,
    _complete_download_records_task,
    _complete_successful_single_file_download,
    _download_result_stat_key,
    _enqueue_file_task,
    _fail_file_task,
    _get_download_file_status,
    _load_download_file_records,
    _load_filtered_download_file_records,
    _query_group_id,
    _resolve_download_record_status,
    _run_download_records,
    _unique_int_file_ids,
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


class FakeFileDownloadTaskCursor:
    def __init__(self, existing_count):
        self.existing_count = existing_count
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return (self.existing_count,)


class FakeFileDownloadTaskDownloader:
    def __init__(self, existing_count):
        self.file_db = type("FakeFileDb", (), {"cursor": FakeFileDownloadTaskCursor(existing_count)})()
        self.collect_calls = []
        self.download_calls = []

    def collect_files_for_date_range(self, **kwargs):
        self.collect_calls.append(("date_range", kwargs))
        return "range-result"

    def collect_incremental_files(self):
        self.collect_calls.append(("incremental", {}))
        return "incremental-result"

    def download_files_from_database(self, **kwargs):
        self.download_calls.append(kwargs)
        return "download-result"


class FakeSingleFileDownloadTaskCursor:
    def __init__(self, row):
        self.row = row
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.row


class FakeSingleFileDownloadTaskFileDb:
    def __init__(self, row):
        self.cursor = FakeSingleFileDownloadTaskCursor(row)
        self.status_updates = []

    def update_file_download_status(self, file_id, status, local_path):
        self.status_updates.append((file_id, status, local_path))


class FakeSingleFileDownloadTaskDownloader:
    def __init__(self, row, download_result):
        self.file_db = FakeSingleFileDownloadTaskFileDb(row)
        self.download_dir = r"C:\downloads"
        self.download_result = download_result
        self.download_calls = []

    def download_file(self, file_info):
        self.download_calls.append(file_info)
        return self.download_result


class FakeSyncFilesTopicsDb:
    def __init__(self):
        self.backfill_calls = 0
        self.closed = False

    def backfill_topic_files_to_file_database(self):
        self.backfill_calls += 1
        return {"files": 2, "topics": 3}

    def close(self):
        self.closed = True


class FakeImageCacheManager:
    def __init__(self, result):
        self.result = result
        self.clear_calls = 0

    def clear_cache(self):
        self.clear_calls += 1
        return self.result


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

    def test_file_route_error_preserves_status_and_detail_format(self):
        from backend.routes import file_routes

        error = file_routes._file_route_error("创建文件收集任务失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("创建文件收集任务失败: boom", error.detail)

    def test_file_task_routes_preserve_wrapped_unexpected_errors(self):
        from backend.routes import file_routes
        from backend.schemas.files import (
            FileAIAnalysisBatchRequest,
            FileAIAnalysisRequest,
            FileCollectRequest,
            FileDownloadRequest,
            FileFilteredDownloadRequest,
            FileIdListRequest,
        )

        background_tasks = FakeBackgroundTasks()
        cases = [
            (
                file_routes.collect_files,
                ("group-1", FileCollectRequest(), background_tasks),
                {},
                "创建文件收集任务失败: boom",
                False,
            ),
            (
                file_routes.download_files,
                ("group-1", FileDownloadRequest(), background_tasks),
                {},
                "创建文件下载任务失败: boom",
                False,
            ),
            (
                file_routes.download_single_file,
                ("group-1", 123, background_tasks),
                {"file_name": "file.pdf", "file_size": 456},
                "创建单个文件下载任务失败: boom",
                False,
            ),
            (
                file_routes.download_selected_files,
                ("group-1", FileIdListRequest(file_ids=[123, 456]), background_tasks),
                {},
                "创建选中文件下载任务失败: boom",
                False,
            ),
            (
                file_routes.download_filtered_files,
                ("group-1", FileFilteredDownloadRequest(status="failed", search="pdf"), background_tasks),
                {},
                "创建筛选结果下载任务失败: boom",
                False,
            ),
            (
                file_routes.create_file_analysis_task,
                ("group-1", 123, FileAIAnalysisRequest(force=True), background_tasks),
                {},
                "创建文件 AI 分析任务失败: boom",
                True,
            ),
            (
                file_routes.create_selected_file_analysis_task,
                ("group-1", FileAIAnalysisBatchRequest(file_ids=[123, 456]), background_tasks),
                {},
                "创建批量文件 AI 分析任务失败: boom",
                True,
            ),
            (
                file_routes.sync_files_from_topics,
                ("group-1", background_tasks),
                {},
                "创建同步文件记录任务失败: boom",
                False,
            ),
        ]

        for route, route_args, route_kwargs, expected_detail, needs_api_key in cases:
            with self.subTest(route=route.__name__):
                with ExitStack() as stack:
                    stack.enter_context(
                        patch("backend.routes.file_routes._enqueue_file_task", side_effect=RuntimeError("boom"))
                    )
                    if needs_api_key:
                        stack.enter_context(patch("backend.routes.file_routes.has_openai_api_key", return_value=True))

                    with self.assertRaises(file_routes.HTTPException) as raised:
                        self._run_async(route(*route_args, **route_kwargs))

                self.assertEqual(500, raised.exception.status_code)
                self.assertEqual(expected_detail, raised.exception.detail)

        self.assertEqual([], background_tasks.calls)

    def test_file_task_routes_preserve_http_exception_passthrough(self):
        from backend.routes import file_routes
        from backend.schemas.files import (
            FileAIAnalysisBatchRequest,
            FileAIAnalysisRequest,
            FileCollectRequest,
            FileDownloadRequest,
            FileFilteredDownloadRequest,
            FileIdListRequest,
        )

        background_tasks = FakeBackgroundTasks()
        cases = [
            (file_routes.collect_files, ("group-1", FileCollectRequest(), background_tasks), {}, False),
            (file_routes.download_files, ("group-1", FileDownloadRequest(), background_tasks), {}, False),
            (
                file_routes.download_single_file,
                ("group-1", 123, background_tasks),
                {"file_name": "file.pdf", "file_size": 456},
                False,
            ),
            (
                file_routes.download_selected_files,
                ("group-1", FileIdListRequest(file_ids=[123, 456]), background_tasks),
                {},
                False,
            ),
            (
                file_routes.download_filtered_files,
                ("group-1", FileFilteredDownloadRequest(status="failed", search="pdf"), background_tasks),
                {},
                False,
            ),
            (
                file_routes.create_file_analysis_task,
                ("group-1", 123, FileAIAnalysisRequest(force=True), background_tasks),
                {},
                True,
            ),
            (
                file_routes.create_selected_file_analysis_task,
                ("group-1", FileAIAnalysisBatchRequest(file_ids=[123, 456]), background_tasks),
                {},
                True,
            ),
            (file_routes.sync_files_from_topics, ("group-1", background_tasks), {}, False),
        ]

        for route, route_args, route_kwargs, needs_api_key in cases:
            original_error = file_routes.HTTPException(status_code=409, detail="conflict")
            with self.subTest(route=route.__name__):
                with ExitStack() as stack:
                    stack.enter_context(patch("backend.routes.file_routes._enqueue_file_task", side_effect=original_error))
                    if needs_api_key:
                        stack.enter_context(patch("backend.routes.file_routes.has_openai_api_key", return_value=True))

                    with self.assertRaises(file_routes.HTTPException) as raised:
                        self._run_async(route(*route_args, **route_kwargs))

                self.assertIs(original_error, raised.exception)
                self.assertEqual(409, raised.exception.status_code)
                self.assertEqual("conflict", raised.exception.detail)

        self.assertEqual([], background_tasks.calls)

    def test_file_analysis_routes_preserve_success_payloads(self):
        from backend.routes import file_routes
        from backend.schemas.files import FileAIAnalysisRequest

        calls = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append((func, args, kwargs))
            return {"called": func.__name__, "args": args, "kwargs": kwargs}

        with (
            patch("backend.routes.file_routes.asyncio.to_thread", side_effect=fake_to_thread),
            patch("backend.routes.file_routes.has_openai_api_key", return_value=True),
        ):
            cached = self._run_async(file_routes.get_file_analysis("group-1", 123))
            created = self._run_async(
                file_routes.create_file_analysis("group-1", 456, FileAIAnalysisRequest(force=True))
            )

        self.assertEqual(
            [
                (file_routes.get_group_file_analysis, ("group-1", 123), {}),
                (
                    file_routes.analyze_group_file,
                    ("group-1", 456),
                    {
                        "force": True,
                        "model": file_routes.A_SHARE_DEFAULT_MODEL,
                        "api_base": file_routes.A_SHARE_DEFAULT_API_BASE,
                        "wire_api": file_routes.A_SHARE_DEFAULT_WIRE_API,
                        "reasoning_effort": file_routes.DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
                    },
                ),
            ],
            calls,
        )
        self.assertEqual(
            {"analysis": {"called": "get_group_file_analysis", "args": ("group-1", 123), "kwargs": {}}},
            cached,
        )
        self.assertEqual(
            {
                "analysis": {
                    "called": "analyze_group_file",
                    "args": ("group-1", 456),
                    "kwargs": {
                        "force": True,
                        "model": file_routes.A_SHARE_DEFAULT_MODEL,
                        "api_base": file_routes.A_SHARE_DEFAULT_API_BASE,
                        "wire_api": file_routes.A_SHARE_DEFAULT_WIRE_API,
                        "reasoning_effort": file_routes.DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
                    },
                }
            },
            created,
        )

    def test_file_analysis_helpers_preserve_service_call_shapes(self):
        from backend.routes import file_routes

        calls = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append((func, args, kwargs))
            return {"called": func.__name__, "args": args, "kwargs": kwargs}

        with patch("backend.routes.file_routes.asyncio.to_thread", side_effect=fake_to_thread):
            cached = self._run_async(file_routes._file_analysis("group-1", 123))
            created = self._run_async(file_routes._created_file_analysis("group-1", 456, True))

        self.assertEqual(
            [
                (file_routes.get_group_file_analysis, ("group-1", 123), {}),
                (
                    file_routes.analyze_group_file,
                    ("group-1", 456),
                    {
                        "force": True,
                        "model": file_routes.A_SHARE_DEFAULT_MODEL,
                        "api_base": file_routes.A_SHARE_DEFAULT_API_BASE,
                        "wire_api": file_routes.A_SHARE_DEFAULT_WIRE_API,
                        "reasoning_effort": file_routes.DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
                    },
                ),
            ],
            calls,
        )
        self.assertEqual(
            {"analysis": {"called": "get_group_file_analysis", "args": ("group-1", 123), "kwargs": {}}},
            cached,
        )
        self.assertEqual(
            {
                "analysis": {
                    "called": "analyze_group_file",
                    "args": ("group-1", 456),
                    "kwargs": {
                        "force": True,
                        "model": file_routes.A_SHARE_DEFAULT_MODEL,
                        "api_base": file_routes.A_SHARE_DEFAULT_API_BASE,
                        "wire_api": file_routes.A_SHARE_DEFAULT_WIRE_API,
                        "reasoning_effort": file_routes.DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
                    },
                }
            },
            created,
        )

    def test_create_file_analysis_preserves_missing_api_key_wrapped_error(self):
        from backend.routes import file_routes
        from backend.schemas.files import FileAIAnalysisRequest
        from fastapi import HTTPException

        with (
            patch("backend.routes.file_routes.has_openai_api_key", return_value=False),
            patch("backend.routes.file_routes.asyncio.to_thread") as to_thread,
        ):
            with self.assertRaises(HTTPException) as raised:
                self._run_async(file_routes.create_file_analysis("group-1", 456, FileAIAnalysisRequest(force=True)))

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual(
            "文件 AI 分析失败: 400: 未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key",
            raised.exception.detail,
        )
        to_thread.assert_not_called()

    def test_create_file_analysis_preserves_service_error_mapping(self):
        from backend.routes import file_routes
        from backend.schemas.files import FileAIAnalysisRequest
        from fastapi import HTTPException

        async def raise_value_error(*_args, **_kwargs):
            raise ValueError("bad value")

        async def raise_runtime_error(*_args, **_kwargs):
            raise RuntimeError("bad runtime")

        cases = [
            (raise_value_error, "bad value"),
            (raise_runtime_error, "bad runtime"),
        ]

        for side_effect, detail in cases:
            with self.subTest(detail=detail):
                with (
                    patch("backend.routes.file_routes.has_openai_api_key", return_value=True),
                    patch("backend.routes.file_routes.asyncio.to_thread", side_effect=side_effect),
                ):
                    with self.assertRaises(HTTPException) as raised:
                        self._run_async(
                            file_routes.create_file_analysis(
                                "group-1",
                                456,
                                FileAIAnalysisRequest(force=True),
                            )
                        )

                self.assertEqual(400, raised.exception.status_code)
                self.assertEqual(detail, raised.exception.detail)

    def test_create_file_analysis_preserves_wrapped_unexpected_error(self):
        from backend.routes import file_routes
        from backend.schemas.files import FileAIAnalysisRequest

        with (
            patch("backend.routes.file_routes.has_openai_api_key", return_value=True),
            patch("backend.routes.file_routes._created_file_analysis", side_effect=Exception("boom")),
        ):
            with self.assertRaises(file_routes.HTTPException) as raised:
                self._run_async(
                    file_routes.create_file_analysis(
                        "group-1",
                        456,
                        FileAIAnalysisRequest(force=True),
                    )
                )

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("文件 AI 分析失败: boom", raised.exception.detail)

    def test_create_file_analysis_preserves_internal_http_exception_wrapping(self):
        from backend.routes import file_routes
        from backend.schemas.files import FileAIAnalysisRequest

        original_error = file_routes.HTTPException(status_code=409, detail="conflict")

        with (
            patch("backend.routes.file_routes.has_openai_api_key", return_value=True),
            patch("backend.routes.file_routes._created_file_analysis", side_effect=original_error),
        ):
            with self.assertRaises(file_routes.HTTPException) as raised:
                self._run_async(
                    file_routes.create_file_analysis(
                        "group-1",
                        456,
                        FileAIAnalysisRequest(force=True),
                    )
                )

        self.assertIsNot(original_error, raised.exception)
        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("文件 AI 分析失败: 409: conflict", raised.exception.detail)

    def test_run_file_analysis_task_dedupes_ids_and_preserves_mixed_stats(self):
        from backend.services import file_workflow_service

        def analyze_side_effect(group_id, file_id, **_kwargs):
            if file_id == 3:
                raise RuntimeError("boom")
            return {"cached": file_id == 2}

        with (
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service.analyze_group_file", side_effect=analyze_side_effect) as analyze,
        ):
            file_workflow_service.run_file_analysis_task("task-1", "group-1", [1, 2, 1, 3], force=True)

        self.assertEqual(
            [("group-1", 1), ("group-1", 2), ("group-1", 3)],
            [call.args[:2] for call in analyze.call_args_list],
        )
        self.assertTrue(all(call.kwargs["force"] is True for call in analyze.call_args_list))
        update_task.assert_any_call(
            "task-1",
            "completed",
            "文件分析完成",
            {"analysis": {"total_files": 3, "completed": 1, "cached": 1, "failed": 1}},
        )
        self.assertIn(
            ("task-1", "❌ 文件分析失败: 3, boom"),
            [call.args for call in add_task_log.call_args_list],
        )

    def test_run_file_analysis_task_preserves_pre_cast_deduplication_for_mixed_id_types(self):
        from backend.services import file_workflow_service

        with (
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log"),
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service.analyze_group_file", return_value={"cached": False}) as analyze,
        ):
            file_workflow_service.run_file_analysis_task("task-1", "group-1", [1, "1"], force=False)

        self.assertEqual(
            [("group-1", 1), ("group-1", 1)],
            [call.args[:2] for call in analyze.call_args_list],
        )
        update_task.assert_any_call(
            "task-1",
            "completed",
            "文件分析完成",
            {"analysis": {"total_files": 2, "completed": 2, "cached": 0, "failed": 0}},
        )

    def test_run_file_analysis_task_stops_between_files_without_final_update(self):
        from backend.services import file_workflow_service

        with (
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_workflow_service.analyze_group_file", return_value={"cached": False}) as analyze,
        ):
            file_workflow_service.run_file_analysis_task("task-1", "group-1", [1, 2], force=False)

        self.assertEqual([("group-1", 1)], [call.args[:2] for call in analyze.call_args_list])
        self.assertEqual(
            [
                ("task-1", "running", "开始分析 2 个文件..."),
            ],
            [call.args for call in update_task.call_args_list],
        )
        self.assertIn(
            ("task-1", "🛑 文件分析任务被停止"),
            [call.args for call in add_task_log.call_args_list],
        )

    def test_run_file_analysis_task_marks_task_failed_when_all_files_fail(self):
        from backend.services import file_workflow_service

        with (
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log"),
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service.analyze_group_file", side_effect=RuntimeError("boom")),
        ):
            file_workflow_service.run_file_analysis_task("task-1", "group-1", [1], force=False)

        update_task.assert_any_call(
            "task-1",
            "failed",
            "文件分析全部失败",
            {"analysis": {"total_files": 1, "completed": 0, "cached": 0, "failed": 1}},
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

    def test_fail_file_task_logs_and_updates_failure(self):
        with (
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.update_task") as update_task,
        ):
            _fail_file_task("task-1", "下载失败: boom", "下载失败: boom", {"failed": 1})

        add_task_log.assert_called_once_with("task-1", "❌ 下载失败: boom")
        update_task.assert_called_once_with("task-1", "failed", "下载失败: boom", {"failed": 1})

    def test_fail_file_task_skips_stopped_tasks(self):
        with (
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=True),
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.update_task") as update_task,
        ):
            _fail_file_task("task-1", "下载失败: boom", "下载失败: boom")

        add_task_log.assert_not_called()
        update_task.assert_not_called()

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

    def test_build_download_task_stats_keeps_result_shape(self):
        stats = _build_download_task_stats(total_files=3, found=2, missing=1)

        self.assertEqual(
            {
                "total_files": 3,
                "found": 2,
                "missing": 1,
                "downloaded": 0,
                "skipped": 0,
                "failed": 0,
            },
            stats,
        )

    def test_build_download_file_info_keeps_downloader_payload_shape(self):
        payload = _build_download_file_info(123, "file.pdf", 456, 7)

        self.assertEqual(
            {
                "file": {
                    "id": 123,
                    "name": "file.pdf",
                    "size": 456,
                    "download_count": 7,
                }
            },
            payload,
        )

    def test_download_result_stat_key_preserves_existing_counts(self):
        self.assertEqual("skipped", _download_result_stat_key("skipped"))
        self.assertEqual("downloaded", _download_result_stat_key(True))
        self.assertEqual("downloaded", _download_result_stat_key("local/path.pdf"))
        self.assertEqual("failed", _download_result_stat_key(False))
        self.assertEqual("failed", _download_result_stat_key(None))

    def test_get_file_stats_response_keeps_download_stats_shape_and_query(self):
        from backend.services import file_workflow_service

        class FakeCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchone(self):
                return (9, 4, 3, 2)

        class FakeFileDb:
            def __init__(self):
                self.cursor = FakeCursor()

            def get_database_stats(self):
                return {"files": 9, "topics": 5}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeFileDb()
        with patch("backend.services.file_workflow_service._file_db", return_value=fake_db):
            response = file_workflow_service._get_file_stats_response("123")

        query, params = fake_db.cursor.executed[0]
        self.assertIn("COUNT(CASE WHEN download_status IN ('completed', 'downloaded', 'skipped') THEN 1 END)", query)
        self.assertEqual((123,), params)
        self.assertEqual(
            {
                "database_stats": {"files": 9, "topics": 5},
                "download_stats": {
                    "total_files": 9,
                    "downloaded": 4,
                    "pending": 3,
                    "failed": 2,
                },
            },
            response,
        )

    def test_get_file_stats_response_defaults_missing_download_stats_to_zero(self):
        from backend.services import file_workflow_service

        class FakeCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchone(self):
                return None

        class FakeFileDb:
            def __init__(self):
                self.cursor = FakeCursor()

            def get_database_stats(self):
                return {"files": 0}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeFileDb()
        with patch("backend.services.file_workflow_service._file_db", return_value=fake_db):
            response = file_workflow_service._get_file_stats_response("group-1")

        self.assertEqual(("group-1",), fake_db.cursor.executed[0][1])
        self.assertEqual(
            {
                "database_stats": {"files": 0},
                "download_stats": {
                    "total_files": 0,
                    "downloaded": 0,
                    "pending": 0,
                    "failed": 0,
                },
            },
            response,
        )

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

    def test_file_read_routes_preserve_wrapped_unexpected_errors(self):
        from backend.routes import file_routes

        cases = [
            (file_routes.get_file_status, ("group-1", 123), {}, "_file_status", "获取文件状态失败: boom", None),
            (
                file_routes.check_local_file_status,
                ("group-1", "file.pdf", 456),
                {},
                "_local_file_status",
                "检查本地文件失败: boom",
                None,
            ),
            (file_routes.get_file_analysis, ("group-1", 123), {}, "_file_analysis", "获取文件 AI 分析失败: boom", None),
            (file_routes.get_file_stats, ("group-1",), {}, "_file_stats", "获取文件统计失败: boom", None),
            (
                file_routes.clear_file_database,
                ("group-1",),
                {},
                "_clear_file_database",
                "删除文件数据库失败: boom",
                ("ERROR", "删除文件数据库失败: boom"),
            ),
            (
                file_routes.get_files,
                ("group-1",),
                {"page": 2, "per_page": 5, "status": "completed", "search": "pdf", "analysis_status": "pending"},
                "_files_page",
                "获取文件列表失败: boom",
                None,
            ),
        ]

        for route, route_args, route_kwargs, helper_name, expected_detail, expected_log in cases:
            with (
                self.subTest(helper=helper_name),
                patch.object(file_routes, helper_name, side_effect=RuntimeError("boom")),
                patch.object(file_routes, "_log_file_route_event") as log_file_route_event,
            ):
                with self.assertRaises(file_routes.HTTPException) as raised:
                    self._run_async(route(*route_args, **route_kwargs))

                self.assertEqual(500, raised.exception.status_code)
                self.assertEqual(expected_detail, raised.exception.detail)
                if expected_log:
                    log_file_route_event.assert_called_once_with(*expected_log)
                else:
                    log_file_route_event.assert_not_called()

    def test_clear_file_database_preserves_http_exception_passthrough(self):
        from backend.routes import file_routes

        original_error = file_routes.HTTPException(status_code=409, detail="conflict")

        with (
            patch.object(file_routes, "_clear_file_database", side_effect=original_error),
            patch.object(file_routes, "_log_file_route_event") as log_file_route_event,
        ):
            with self.assertRaises(file_routes.HTTPException) as raised:
                self._run_async(file_routes.clear_file_database("group-1"))

        self.assertIs(original_error, raised.exception)
        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual("conflict", raised.exception.detail)
        log_file_route_event.assert_not_called()

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

    def test_get_files_offloads_sync_work_to_thread(self):
        from backend.routes import file_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"files": [], "pagination": {"page": args[1], "per_page": args[2], "total": 0, "pages": 0}}

        with patch("backend.routes.file_routes.asyncio.to_thread", side_effect=fake_to_thread):
            response = self._run_async(
                file_routes.get_files(
                    "group-1",
                    page=2,
                    per_page=5,
                    status="completed",
                    search="pdf",
                    analysis_status="pending",
                )
            )

        self.assertEqual([(file_routes._get_files_response, ("group-1", 2, 5, "completed", "pdf", "pending"))], calls)
        self.assertEqual({"files": [], "pagination": {"page": 2, "per_page": 5, "total": 0, "pages": 0}}, response)

    def test_file_read_helpers_preserve_service_call_shapes(self):
        from backend.routes import file_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"called": func.__name__, "args": args}

        with patch("backend.routes.file_routes.asyncio.to_thread", side_effect=fake_to_thread):
            file_status = self._run_async(file_routes._file_status("group-1", 123))
            local_status = self._run_async(file_routes._local_file_status("group-1", "file.pdf", 456))
            stats = self._run_async(file_routes._file_stats("group-1"))
            clear_response = self._run_async(file_routes._clear_file_database("group-1"))
            files = self._run_async(
                file_routes._files_page(
                    "group-1",
                    2,
                    5,
                    "completed",
                    "pdf",
                    "pending",
                )
            )

        self.assertEqual(
            [
                (file_routes._get_file_status_response, ("group-1", 123)),
                (file_routes._check_local_file_status_response, ("group-1", "file.pdf", 456)),
                (file_routes._get_file_stats_response, ("group-1",)),
                (file_routes._clear_file_database_response, ("group-1",)),
                (file_routes._get_files_response, ("group-1", 2, 5, "completed", "pdf", "pending")),
            ],
            calls,
        )
        self.assertEqual({"called": "_get_file_status_response", "args": ("group-1", 123)}, file_status)
        self.assertEqual({"called": "_check_local_file_status_response", "args": ("group-1", "file.pdf", 456)}, local_status)
        self.assertEqual({"called": "_get_file_stats_response", "args": ("group-1",)}, stats)
        self.assertEqual({"called": "_clear_file_database_response", "args": ("group-1",)}, clear_response)
        self.assertEqual({"called": "_get_files_response", "args": ("group-1", 2, 5, "completed", "pdf", "pending")}, files)

    def test_get_files_response_filters_analysis_status_in_database_query(self):
        from backend.services import file_workflow_service

        class FakeCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchall(self):
                return []

            def fetchone(self):
                return (0,)

        class FakeFileDb:
            def __init__(self):
                self.cursor = FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeFileDb()
        with patch("backend.services.file_workflow_service._file_db", return_value=fake_db):
            response = file_workflow_service._get_files_response("group-1", analysis_status="analyzed")

        self.assertEqual([], response["files"])
        self.assertTrue(any("faa.updated_at IS NOT NULL" in sql for sql, _params in fake_db.cursor.executed))
        self.assertEqual(2, len(fake_db.cursor.executed))
        self.assertTrue(
            all(
                "LEFT JOIN file_ai_analyses faa ON faa.file_id = f.file_id" in sql
                for sql, _params in fake_db.cursor.executed
            )
        )

        fake_db = FakeFileDb()
        with patch("backend.services.file_workflow_service._file_db", return_value=fake_db):
            file_workflow_service._get_files_response("group-1", analysis_status="pending")

        self.assertTrue(any("faa.updated_at IS NULL" in sql for sql, _params in fake_db.cursor.executed))
        self.assertEqual(2, len(fake_db.cursor.executed))
        self.assertTrue(
            all(
                "LEFT JOIN file_ai_analyses faa ON faa.file_id = f.file_id" in sql
                for sql, _params in fake_db.cursor.executed
            )
        )

    def test_get_files_response_without_status_keeps_download_status_unfiltered(self):
        from backend.services import file_workflow_service

        class FakeCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchall(self):
                return []

            def fetchone(self):
                return (0,)

        class FakeFileDb:
            def __init__(self):
                self.cursor = FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeFileDb()
        with patch("backend.services.file_workflow_service._file_db", return_value=fake_db):
            response = file_workflow_service._get_files_response("123")

        query, params = fake_db.cursor.executed[0]
        count_query, count_params = fake_db.cursor.executed[1]
        self.assertEqual([], response["files"])
        self.assertNotIn("f.download_status IN", query)
        self.assertNotIn("f.download_status =", query)
        self.assertNotIn("f.download_status IN", count_query)
        self.assertNotIn("f.download_status =", count_query)
        self.assertEqual((123, 20, 0), params)
        self.assertEqual((123,), count_params)

    def test_get_files_response_keeps_completed_search_and_pagination_shape(self):
        from backend.services import file_workflow_service

        class FakeCursor:
            def __init__(self):
                self.executed = []
                self._fetchall_calls = 0

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchall(self):
                self._fetchall_calls += 1
                return [
                    (
                        101,
                        "Report.PDF",
                        123,
                        7,
                        "2026-06-10T10:00:00+08:00",
                        "downloaded",
                        r"C:\old\Report.PDF",
                        "E1",
                        "boom",
                        "2026-06-11T09:00:00+08:00",
                        "2026-06-11T10:00:00+08:00",
                    )
                ]

            def fetchone(self):
                return (21,)

        class FakeFileDb:
            def __init__(self):
                self.cursor = FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeFileDb()
        with (
            patch("backend.services.file_workflow_service._file_db", return_value=fake_db),
            patch(
                "backend.services.file_workflow_service.resolve_local_file_path",
                return_value=r"C:\resolved\Report.PDF",
            ),
        ):
            response = file_workflow_service._get_files_response(
                "123",
                page=2,
                per_page=5,
                status="completed",
                search=" Foo ",
                analysis_status="analyzed",
            )

        query, params = fake_db.cursor.executed[0]
        count_query, count_params = fake_db.cursor.executed[1]
        self.assertIn("f.download_status IN (?, ?, ?)", query)
        self.assertIn("faa.updated_at IS NOT NULL", query)
        self.assertIn("LOWER(COALESCE(f.name, '')) LIKE ?", query)
        self.assertEqual((123, "completed", "downloaded", "skipped", *["%foo%"] * 8, 5, 5), params)
        self.assertEqual((123, "completed", "downloaded", "skipped", *["%foo%"] * 8), count_params)
        self.assertTrue(count_query.strip().startswith("SELECT COUNT(*)"))
        self.assertEqual(
            {
                "page": 2,
                "per_page": 5,
                "total": 21,
                "pages": 5,
            },
            response["pagination"],
        )
        self.assertEqual(
            {
                "file_id": 101,
                "name": "Report.PDF",
                "size": 123,
                "download_count": 7,
                "create_time": "2026-06-10T10:00:00+08:00",
                "download_status": "completed",
                "local_exists": True,
                "local_path": r"C:\resolved\Report.PDF",
                "download_error_code": "E1",
                "download_error_message": "boom",
                "last_download_attempt_at": "2026-06-11T09:00:00+08:00",
                "has_ai_analysis": True,
                "analysis_updated_at": "2026-06-11T10:00:00+08:00",
            },
            response["files"][0],
        )

    def test_run_collect_files_task_date_range_logs_and_completes(self):
        from backend.schemas.files import FileCollectRequest
        from backend.services.file_workflow_service import run_collect_files_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=0)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_collect_files_task(
                "task-1",
                "123",
                FileCollectRequest(start_time="2026-06-01", end_time="2026-06-02"),
            )

        self.assertEqual(
            [
                (
                    "date_range",
                    {"start_date": "2026-06-01", "end_date": "2026-06-02", "last_days": None},
                )
            ],
            downloader.collect_calls,
        )
        log_calls = [call.args for call in add_task_log.call_args_list]
        self.assertIn(("task-1", "📡 连接到知识星球API..."), log_calls)
        self.assertIn(("task-1", "📍 阶段一：收集文件列表"), log_calls)
        self.assertIn(
            ("task-1", "📅 收集范围: 2026-06-01 ~ 2026-06-02"),
            log_calls,
        )
        update_task.assert_any_call("task-1", "completed", "文件列表收集完成", "range-result")
        safe_remove.assert_called_once_with("task-1")

    def test_run_collect_files_task_default_uses_incremental_collect(self):
        from backend.schemas.files import FileCollectRequest
        from backend.services.file_workflow_service import run_collect_files_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=0)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_collect_files_task("task-1", "123", FileCollectRequest())

        self.assertEqual([("incremental", {})], downloader.collect_calls)
        log_calls = [call.args for call in add_task_log.call_args_list]
        self.assertNotIn(
            ("task-1", "📅 收集最近天数: None天"),
            log_calls,
        )
        update_task.assert_any_call("task-1", "completed", "文件列表收集完成", "incremental-result")
        safe_remove.assert_called_once_with("task-1")

    def test_run_collect_files_task_stops_after_downloader_creation(self):
        from backend.schemas.files import FileCollectRequest
        from backend.services.file_workflow_service import run_collect_files_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=0)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=True),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_collect_files_task("task-1", "123", FileCollectRequest())

        create_downloader.assert_called_once_with("task-1", "123")
        self.assertEqual([], downloader.collect_calls)
        self.assertEqual(
            [("task-1", "running", "开始收集文件列表...")],
            [call.args for call in update_task.call_args_list],
        )
        add_task_log.assert_called_once_with("task-1", "🛑 任务在初始化过程中被停止")
        safe_remove.assert_called_once_with("task-1")

    def test_run_collect_files_task_logs_success_and_completed_payload(self):
        from backend.schemas.files import FileCollectRequest
        from backend.services.file_workflow_service import run_collect_files_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=0)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_collect_files_task("task-1", "123", FileCollectRequest(last_days=7))

        log_calls = [call.args for call in add_task_log.call_args_list]
        self.assertIn(("task-1", "✅ 文件列表收集完成！"), log_calls)
        update_task.assert_any_call("task-1", "completed", "文件列表收集完成", "range-result")
        safe_remove.assert_called_once_with("task-1")

    def test_run_file_download_task_existing_files_uses_download_count_without_collect(self):
        from backend.services.file_workflow_service import run_file_download_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=2)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_file_download_task(
                "task-1",
                "123",
                max_files=5,
                sort_by="download_count",
                download_interval=2.0,
                long_sleep_interval=30.0,
                files_per_batch=4,
            )

        create_downloader.assert_called_once_with(
            "task-1",
            "123",
            download_interval=2.0,
            long_sleep_interval=30.0,
            files_per_batch=4,
            download_interval_min=None,
            download_interval_max=None,
            long_sleep_interval_min=None,
            long_sleep_interval_max=None,
        )
        self.assertEqual(
            [("SELECT COUNT(*) FROM files WHERE group_id = ?", (123,))],
            downloader.file_db.cursor.executed,
        )
        self.assertEqual([], downloader.collect_calls)
        self.assertEqual(
            [{"max_files": 5, "status_filter": "pending", "sort_by": "download_count"}],
            downloader.download_calls,
        )
        self.assertIn(
            ("task-1", "📚 文件库已有 2 条记录，跳过收集阶段，直接下载"),
            [call.args for call in add_task_log.call_args_list],
        )
        update_task.assert_any_call("task-1", "completed", "文件下载完成", {"downloaded_files": "download-result"})
        safe_remove.assert_called_once_with("task-1")

    def test_run_file_download_task_empty_create_time_collects_and_downloads_date_range(self):
        from backend.services.file_workflow_service import run_file_download_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=0)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_file_download_task(
                "task-1",
                "123",
                max_files=5,
                sort_by="create_time",
                start_time="2026-06-01",
                end_time="2026-06-02",
            )

        self.assertEqual(
            [
                (
                    "date_range",
                    {"start_date": "2026-06-01", "end_date": "2026-06-02", "last_days": None},
                )
            ],
            downloader.collect_calls,
        )
        self.assertEqual(
            [
                {
                    "max_files": 5,
                    "status_filter": "pending",
                    "sort_by": "create_time",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-02",
                    "last_days": None,
                }
            ],
            downloader.download_calls,
        )
        self.assertIn(
            ("task-1", "   📅 下载区间: 2026-06-01 ~ 2026-06-02"),
            [call.args for call in add_task_log.call_args_list],
        )
        self.assertIn(
            ("task-1", "📊 文件收集完成: range-result"),
            [call.args for call in add_task_log.call_args_list],
        )
        update_task.assert_any_call("task-1", "completed", "文件下载完成", {"downloaded_files": "download-result"})
        safe_remove.assert_called_once_with("task-1")

    def test_run_file_download_task_logs_download_config_before_work(self):
        from backend.services.file_workflow_service import run_file_download_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=1)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service.update_task"),
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader"),
        ):
            run_file_download_task(
                "task-1",
                "123",
                max_files=2,
                sort_by="create_time",
                last_days=3,
                download_interval=2.5,
                long_sleep_interval=40.0,
                files_per_batch=6,
            )

        self.assertEqual(
            [
                ("task-1", "⚙️ 下载配置:"),
                ("task-1", "   ⏱️ 单次下载间隔: 2.5秒"),
                ("task-1", "   😴 长休眠间隔: 40.0秒"),
                ("task-1", "   📦 批次大小: 6个文件"),
                ("task-1", "   📅 下载最近天数: 3天"),
            ],
            [call.args for call in add_task_log.call_args_list[:5]],
        )

    def test_run_file_download_task_stops_after_collect_before_download_phase(self):
        from backend.services.file_workflow_service import run_file_download_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=0)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_file_download_task(
                "task-1",
                "123",
                max_files=5,
                sort_by="create_time",
                start_time="2026-06-01",
                end_time="2026-06-02",
            )

        self.assertEqual(
            [
                (
                    "date_range",
                    {"start_date": "2026-06-01", "end_date": "2026-06-02", "last_days": None},
                )
            ],
            downloader.collect_calls,
        )
        self.assertEqual([], downloader.download_calls)
        log_calls = [call.args for call in add_task_log.call_args_list]
        self.assertIn(("task-1", "📍 阶段一：收集文件列表"), log_calls)
        self.assertNotIn(("task-1", "📊 文件收集完成: range-result"), log_calls)
        self.assertNotIn(("task-1", "📍 阶段二：下载文件本体"), log_calls)
        self.assertEqual(
            [("task-1", "running", "开始文件下载...")],
            [call.args for call in update_task.call_args_list],
        )
        safe_remove.assert_called_once_with("task-1")

    def test_run_file_download_task_stops_after_download_before_completion(self):
        from backend.services.file_workflow_service import run_file_download_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=2)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", side_effect=[False, False, True]),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_file_download_task(
                "task-1",
                "123",
                max_files=5,
                sort_by="download_count",
            )

        self.assertEqual([], downloader.collect_calls)
        self.assertEqual(
            [{"max_files": 5, "status_filter": "pending", "sort_by": "download_count"}],
            downloader.download_calls,
        )
        log_calls = [call.args for call in add_task_log.call_args_list]
        self.assertIn(("task-1", "📍 阶段二：下载文件本体"), log_calls)
        self.assertIn(("task-1", "🚀 开始下载文件..."), log_calls)
        self.assertNotIn(("task-1", "✅ 文件下载完成！"), log_calls)
        self.assertEqual(
            [("task-1", "running", "开始文件下载...")],
            [call.args for call in update_task.call_args_list],
        )
        safe_remove.assert_called_once_with("task-1")

    def test_run_file_download_task_logs_success_and_completed_payload(self):
        from backend.services.file_workflow_service import run_file_download_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=1)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_file_download_task(
                "task-1",
                "123",
                max_files=5,
                sort_by="download_count",
            )

        self.assertIn(
            ("task-1", "✅ 文件下载完成！"),
            [call.args for call in add_task_log.call_args_list],
        )
        update_task.assert_any_call("task-1", "completed", "文件下载完成", {"downloaded_files": "download-result"})
        safe_remove.assert_called_once_with("task-1")

    def test_run_file_download_task_stops_after_initialization(self):
        from backend.services.file_workflow_service import run_file_download_task

        downloader = FakeFileDownloadTaskDownloader(existing_count=1)

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=True),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_file_download_task(
                "task-1",
                "123",
                max_files=5,
                sort_by="download_count",
                download_interval=2.0,
                long_sleep_interval=30.0,
                files_per_batch=4,
            )

        create_downloader.assert_called_once_with(
            "task-1",
            "123",
            download_interval=2.0,
            long_sleep_interval=30.0,
            files_per_batch=4,
            download_interval_min=None,
            download_interval_max=None,
            long_sleep_interval_min=None,
            long_sleep_interval_max=None,
        )
        self.assertEqual([], downloader.collect_calls)
        self.assertEqual([], downloader.download_calls)
        self.assertEqual(
            [("task-1", "running", "开始文件下载...")],
            [call.args for call in update_task.call_args_list],
        )
        self.assertEqual(
            [
                ("task-1", "⚙️ 下载配置:"),
                ("task-1", "   ⏱️ 单次下载间隔: 2.0秒"),
                ("task-1", "   😴 长休眠间隔: 30.0秒"),
                ("task-1", "   📦 批次大小: 4个文件"),
                ("task-1", "🛑 任务在初始化过程中被停止"),
            ],
            [call.args for call in add_task_log.call_args_list],
        )
        safe_remove.assert_called_once_with("task-1")

    def test_run_selected_file_download_task_stops_after_downloader_creation(self):
        from backend.services.file_workflow_service import run_selected_file_download_task

        downloader = object()

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_workflow_service._load_download_file_records") as load_records,
            patch("backend.services.file_workflow_service._run_download_records") as run_download_records,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=True),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_selected_file_download_task("task-1", "123", [101, 102])

        create_downloader.assert_called_once_with("task-1", "123")
        load_records.assert_not_called()
        run_download_records.assert_not_called()
        self.assertEqual(
            [("task-1", "running", "开始下载选中的 2 个文件...")],
            [call.args for call in update_task.call_args_list],
        )
        add_task_log.assert_called_once_with("task-1", "🛑 任务在初始化过程中被停止")
        safe_remove.assert_called_once_with("task-1")

    def test_run_filtered_file_download_task_stops_after_downloader_creation(self):
        from backend.services.file_workflow_service import run_filtered_file_download_task

        downloader = object()

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_workflow_service._load_filtered_download_file_records") as load_records,
            patch("backend.services.file_workflow_service._run_download_records") as run_download_records,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=True),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_filtered_file_download_task("task-1", "123", status="pending", search="pdf", max_files=1)

        create_downloader.assert_called_once_with("task-1", "123")
        load_records.assert_not_called()
        run_download_records.assert_not_called()
        self.assertEqual(
            [("task-1", "running", "开始下载当前筛选结果...")],
            [call.args for call in update_task.call_args_list],
        )
        add_task_log.assert_called_once_with("task-1", "🛑 任务在初始化过程中被停止")
        safe_remove.assert_called_once_with("task-1")

    def test_run_selected_file_download_task_skips_completion_when_stopped_after_records(self):
        from backend.services.file_workflow_service import run_selected_file_download_task

        downloader = object()
        records = [(101, "Report.pdf", 123, 7)]

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service._load_download_file_records", return_value=(records, [])),
            patch("backend.services.file_workflow_service._run_download_records") as run_download_records,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log"),
            patch("backend.services.file_workflow_service.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_selected_file_download_task("task-1", "123", [101])

        run_download_records.assert_called_once()
        self.assertEqual(
            [
                ("task-1", "running", "开始下载选中的 1 个文件..."),
            ],
            [call.args for call in update_task.call_args_list],
        )
        safe_remove.assert_called_once_with("task-1")

    def test_run_filtered_file_download_task_skips_completion_when_stopped_after_records(self):
        from backend.services.file_workflow_service import run_filtered_file_download_task

        downloader = object()
        records = [(101, "Report.pdf", 123, 7)]

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service._load_filtered_download_file_records", return_value=records),
            patch("backend.services.file_workflow_service._run_download_records") as run_download_records,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log"),
            patch("backend.services.file_workflow_service.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_filtered_file_download_task("task-1", "123", status="pending", search="pdf", max_files=1)

        run_download_records.assert_called_once()
        self.assertEqual(
            [
                ("task-1", "running", "开始下载当前筛选结果..."),
            ],
            [call.args for call in update_task.call_args_list],
        )
        safe_remove.assert_called_once_with("task-1")

    def test_run_selected_file_download_task_completes_empty_records_with_missing_stats(self):
        from backend.services.file_workflow_service import run_selected_file_download_task

        downloader = object()

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service._load_download_file_records", return_value=([], [101, 102])),
            patch("backend.services.file_workflow_service._run_download_records") as run_download_records,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_selected_file_download_task("task-1", "123", [101, 102, 101])

        run_download_records.assert_not_called()
        self.assertEqual(
            [
                ("task-1", "running", "开始下载选中的 3 个文件..."),
                (
                    "task-1",
                    "completed",
                    "没有可下载的文件记录",
                    {
                        "downloaded_files": {
                            "total_files": 2,
                            "found": 0,
                            "missing": 2,
                            "downloaded": 0,
                            "skipped": 0,
                            "failed": 0,
                        }
                    },
                ),
            ],
            [call.args for call in update_task.call_args_list],
        )
        add_task_log.assert_called_once_with("task-1", "⚠️ 2 个文件未在文件库中找到，已跳过")
        safe_remove.assert_called_once_with("task-1")

    def test_run_filtered_file_download_task_completes_empty_records_with_stats_payload(self):
        from backend.services.file_workflow_service import run_filtered_file_download_task

        downloader = object()

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader),
            patch("backend.services.file_workflow_service._load_filtered_download_file_records", return_value=[]),
            patch("backend.services.file_workflow_service._run_download_records") as run_download_records,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_filtered_file_download_task("task-1", "123", status="pending", search="pdf", max_files=1)

        run_download_records.assert_not_called()
        self.assertEqual(
            [
                ("task-1", "running", "开始下载当前筛选结果..."),
                (
                    "task-1",
                    "completed",
                    "当前筛选下没有可下载文件",
                    {
                        "downloaded_files": {
                            "total_files": 0,
                            "found": 0,
                            "missing": 0,
                            "downloaded": 0,
                            "skipped": 0,
                            "failed": 0,
                        }
                    },
                ),
            ],
            [call.args for call in update_task.call_args_list],
        )
        add_task_log.assert_not_called()
        safe_remove.assert_called_once_with("task-1")

    def test_complete_download_records_task_updates_completion_when_running(self):
        downloader = object()
        records = [(101, "Report.pdf", 123, 7)]
        stats = _build_download_task_stats(total_files=1, found=1)

        with (
            patch("backend.services.file_workflow_service._run_download_records") as run_download_records,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service.update_task") as update_task,
        ):
            _complete_download_records_task("task-1", downloader, records, stats, "下载完成")

        run_download_records.assert_called_once_with("task-1", downloader, records, stats)
        update_task.assert_called_once_with("task-1", "completed", "下载完成", {"downloaded_files": stats})

    def test_complete_download_records_task_skips_completion_when_stopped_after_records(self):
        downloader = object()
        records = [(101, "Report.pdf", 123, 7)]
        stats = _build_download_task_stats(total_files=1, found=1)

        with (
            patch("backend.services.file_workflow_service._run_download_records") as run_download_records,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=True),
            patch("backend.services.file_workflow_service.update_task") as update_task,
        ):
            _complete_download_records_task("task-1", downloader, records, stats, "下载完成")

        run_download_records.assert_called_once_with("task-1", downloader, records, stats)
        update_task.assert_not_called()

    def test_run_download_records_updates_stats_logs_and_payloads(self):
        class FakeDownloader:
            def __init__(self):
                self.results = [True, "skipped", False]
                self.download_calls = []

            def download_file(self, file_info):
                self.download_calls.append(file_info)
                return self.results.pop(0)

        downloader = FakeDownloader()
        records = [
            (101, "First.pdf", 123, 7),
            (102, "Second.pdf", 456, 0),
            (103, "Third.pdf", 789, 2),
        ]
        stats = _build_download_task_stats(total_files=3, found=3)

        with (
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
        ):
            result = _run_download_records("task-1", downloader, records, stats)

        self.assertIs(result, stats)
        self.assertEqual(
            [
                {"file": {"id": 101, "name": "First.pdf", "size": 123, "download_count": 7}},
                {"file": {"id": 102, "name": "Second.pdf", "size": 456, "download_count": 0}},
                {"file": {"id": 103, "name": "Third.pdf", "size": 789, "download_count": 2}},
            ],
            downloader.download_calls,
        )
        self.assertEqual(
            {
                "total_files": 3,
                "found": 3,
                "missing": 0,
                "downloaded": 1,
                "skipped": 1,
                "failed": 1,
            },
            stats,
        )
        self.assertEqual(
            [
                ("task-1", "【1/3】First.pdf"),
                ("task-1", "【2/3】Second.pdf"),
                ("task-1", "【3/3】Third.pdf"),
            ],
            [call.args for call in add_task_log.call_args_list],
        )

    def test_run_download_records_stops_before_next_record(self):
        class FakeDownloader:
            def __init__(self):
                self.download_calls = []

            def download_file(self, file_info):
                self.download_calls.append(file_info)
                return True

        downloader = FakeDownloader()
        records = [
            (101, "First.pdf", 123, 7),
            (102, "Second.pdf", 456, 0),
        ]
        stats = _build_download_task_stats(total_files=2, found=2)

        with (
            patch("backend.services.file_workflow_service.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
        ):
            result = _run_download_records("task-1", downloader, records, stats)

        self.assertIs(result, stats)
        self.assertEqual(
            [{"file": {"id": 101, "name": "First.pdf", "size": 123, "download_count": 7}}],
            downloader.download_calls,
        )
        self.assertEqual(
            {
                "total_files": 2,
                "found": 2,
                "missing": 0,
                "downloaded": 1,
                "skipped": 0,
                "failed": 0,
            },
            stats,
        )
        self.assertEqual(
            [
                ("task-1", "【1/2】First.pdf"),
                ("task-1", "🛑 下载任务被停止"),
            ],
            [call.args for call in add_task_log.call_args_list],
        )

    def test_run_sync_files_from_topics_task_completes_with_backfill_stats(self):
        from backend.services.file_workflow_service import run_sync_files_from_topics_task

        topics_db = FakeSyncFilesTopicsDb()

        with (
            patch("backend.services.file_workflow_service.ZSXQDatabase", return_value=topics_db) as create_db,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log"),
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
        ):
            run_sync_files_from_topics_task("task-1", "123")

        create_db.assert_called_once_with("123")
        self.assertEqual(1, topics_db.backfill_calls)
        self.assertTrue(topics_db.closed)
        self.assertEqual(
            [
                ("task-1", "running", "开始从话题同步文件记录..."),
                ("task-1", "completed", "从话题同步文件记录完成", {"files": 2, "topics": 3}),
            ],
            [call.args for call in update_task.call_args_list],
        )

    def test_run_sync_files_from_topics_task_stops_before_database_open(self):
        from backend.services.file_workflow_service import run_sync_files_from_topics_task

        with (
            patch("backend.services.file_workflow_service.ZSXQDatabase") as create_db,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=True),
        ):
            run_sync_files_from_topics_task("task-1", "123")

        create_db.assert_not_called()
        self.assertEqual(
            [("task-1", "running", "开始从话题同步文件记录...")],
            [call.args for call in update_task.call_args_list],
        )
        add_task_log.assert_called_once_with("task-1", "🛑 任务在初始化过程中被停止")

    def test_run_sync_files_from_topics_task_stops_after_backfill_without_completion(self):
        from backend.services.file_workflow_service import run_sync_files_from_topics_task

        topics_db = FakeSyncFilesTopicsDb()

        with (
            patch("backend.services.file_workflow_service.ZSXQDatabase", return_value=topics_db),
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log"),
            patch("backend.services.file_workflow_service.is_task_stopped", side_effect=[False, True]),
        ):
            run_sync_files_from_topics_task("task-1", "123")

        self.assertEqual(1, topics_db.backfill_calls)
        self.assertTrue(topics_db.closed)
        self.assertEqual(
            [("task-1", "running", "开始从话题同步文件记录...")],
            [call.args for call in update_task.call_args_list],
        )

    def test_run_single_file_download_task_uses_database_file_info_and_marks_completed(self):
        downloader = FakeSingleFileDownloadTaskDownloader(
            row=(123, "Db File.pdf", 456, 7),
            download_result=True,
        )

        _create_downloader, update_task, add_task_log, safe_remove = self._run_single_file_download_case(downloader)

        self.assertEqual(
            [("SELECT file_id, name, size, download_count FROM files WHERE file_id = ? AND group_id = ?", (123, 123))],
            [(" ".join(sql.split()), params) for sql, params in downloader.file_db.cursor.executed],
        )
        self.assertEqual(
            [{"file": {"id": 123, "name": "Db File.pdf", "size": 456, "download_count": 7}}],
            downloader.download_calls,
        )
        self.assertEqual([(123, "completed", r"C:\downloads\DbFile.pdf")], downloader.file_db.status_updates)
        self.assertIn(
            ("task-1", "📄 从数据库获取文件信息: Db File.pdf (456 bytes)"),
            [call.args for call in add_task_log.call_args_list],
        )
        update_task.assert_any_call("task-1", "completed", "下载成功")
        safe_remove.assert_called_once_with("task-1")

    def test_complete_successful_single_file_download_updates_status_with_safe_local_path(self):
        downloader = FakeSingleFileDownloadTaskDownloader(row=None, download_result=True)
        file_info = {
            "file": {
                "id": 123,
                "name": "Report / 2026.pdf",
                "size": 456,
                "download_count": 7,
            }
        }

        with (
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.update_task") as update_task,
        ):
            _complete_successful_single_file_download("task-1", downloader, 123, file_info)

        add_task_log.assert_called_once_with("task-1", "✅ 文件下载成功")
        self.assertEqual([(123, "completed", r"C:\downloads\Report2026.pdf")], downloader.file_db.status_updates)
        update_task.assert_called_once_with("task-1", "completed", "下载成功")

    def test_run_single_file_download_task_uses_request_info_fallback_for_skipped_file(self):
        downloader = FakeSingleFileDownloadTaskDownloader(row=None, download_result="skipped")

        _create_downloader, update_task, add_task_log, safe_remove = self._run_single_file_download_case(
            downloader,
            file_name="Request File.pdf",
            file_size=456,
        )

        self.assertEqual(
            [{"file": {"id": 123, "name": "Request File.pdf", "size": 456, "download_count": 0}}],
            downloader.download_calls,
        )
        self.assertEqual([], downloader.file_db.status_updates)
        self.assertIn(
            ("task-1", "📄 文件库未命中，使用请求中的文件信息: Request File.pdf (456 bytes)"),
            [call.args for call in add_task_log.call_args_list],
        )
        update_task.assert_any_call("task-1", "completed", "文件已存在")
        safe_remove.assert_called_once_with("task-1")

    def test_run_single_file_download_task_uses_file_id_fallback_for_failed_file(self):
        downloader = FakeSingleFileDownloadTaskDownloader(row=None, download_result=False)

        _create_downloader, update_task, add_task_log, safe_remove = self._run_single_file_download_case(downloader)

        self.assertEqual(
            [{"file": {"id": 123, "name": "file_123", "size": 0, "download_count": 0}}],
            downloader.download_calls,
        )
        self.assertEqual([], downloader.file_db.status_updates)
        self.assertIn(
            ("task-1", "📄 直接下载文件 ID: 123"),
            [call.args for call in add_task_log.call_args_list],
        )
        update_task.assert_any_call("task-1", "failed", "下载失败")
        safe_remove.assert_called_once_with("task-1")

    def test_run_single_file_download_task_stops_after_downloader_creation(self):
        from backend.services.file_workflow_service import run_single_file_download_task_with_info

        downloader = FakeSingleFileDownloadTaskDownloader(
            row=(123, "Db File.pdf", 456, 7),
            download_result=True,
        )

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=True),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_single_file_download_task_with_info("task-1", "123", 123)

        create_downloader.assert_called_once_with("task-1", "123")
        self.assertEqual([], downloader.file_db.cursor.executed)
        self.assertEqual([], downloader.download_calls)
        self.assertEqual([], downloader.file_db.status_updates)
        self.assertEqual(
            [("task-1", "running", "开始下载文件 (ID: 123)...")],
            [call.args for call in update_task.call_args_list],
        )
        add_task_log.assert_called_once_with("task-1", "🛑 任务在初始化过程中被停止")
        safe_remove.assert_called_once_with("task-1")

    def test_load_filtered_download_file_records_keeps_default_search_and_limit_shape(self):
        class FakeCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchall(self):
                return [
                    (101, "Report.PDF", 123, 7),
                    (102, None, None, None),
                ]

        class FakeDownloader:
            def __init__(self):
                self.file_db = type("FakeFileDb", (), {"cursor": FakeCursor()})()

        downloader = FakeDownloader()

        records = _load_filtered_download_file_records(
            downloader,
            "123",
            search=" Foo ",
            max_files=3,
        )

        query, params = downloader.file_db.cursor.executed[0]
        self.assertIn("(f.download_status IS NULL OR f.download_status NOT IN (?, ?, ?))", query)
        self.assertIn("LOWER(COALESCE(f.name, '')) LIKE ?", query)
        self.assertIn("ORDER BY f.create_time DESC, f.download_count DESC", query)
        self.assertIn("LIMIT ?", query)
        self.assertEqual((123, "completed", "downloaded", "skipped", *["%foo%"] * 8, 3), params)
        self.assertEqual(
            [
                (101, "Report.PDF", 123, 7),
                (102, "file_102", 0, 0),
            ],
            records,
        )

    def test_load_filtered_download_file_records_keeps_completed_status_shape(self):
        class FakeCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchall(self):
                return [(101, "Report.PDF", 123, 7)]

        class FakeDownloader:
            def __init__(self):
                self.file_db = type("FakeFileDb", (), {"cursor": FakeCursor()})()

        downloader = FakeDownloader()

        records = _load_filtered_download_file_records(downloader, "123", status="completed")

        query, params = downloader.file_db.cursor.executed[0]
        self.assertIn("f.download_status IN (?, ?, ?)", query)
        self.assertNotIn("f.download_status NOT IN", query)
        self.assertNotIn("LIMIT ?", query)
        self.assertEqual((123, "completed", "downloaded", "skipped"), params)
        self.assertEqual([(101, "Report.PDF", 123, 7)], records)

    def test_load_download_file_records_dedupes_preserves_order_and_reports_missing(self):
        class FakeCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchall(self):
                return [
                    (102, None, None, None),
                    (101, "Report.PDF", 123, 7),
                ]

        class FakeDownloader:
            def __init__(self):
                self.file_db = type("FakeFileDb", (), {"cursor": FakeCursor()})()

        downloader = FakeDownloader()

        records, missing = _load_download_file_records(downloader, "123", [101, 102, 101, 999])

        query, params = downloader.file_db.cursor.executed[0]
        self.assertIn("WHERE group_id = ? AND file_id IN (?, ?, ?)", " ".join(query.split()))
        self.assertEqual((123, 101, 102, 999), params)
        self.assertEqual(
            [
                (101, "Report.PDF", 123, 7),
                (102, "file_102", 0, 0),
            ],
            records,
        )
        self.assertEqual([999], missing)

    def test_unique_int_file_ids_preserves_existing_selected_download_semantics(self):
        self.assertEqual([101, 102, 999], _unique_int_file_ids(["101", 102, "101", 999]))

    def test_close_crawler_file_databases_closes_file_and_topic_dbs(self):
        crawler = FakeCrawler()

        _close_crawler_file_databases(crawler)

        self.assertTrue(crawler.downloader.file_db.closed)
        self.assertTrue(crawler.db.closed)

    def test_clear_file_database_does_not_construct_legacy_crawler(self):
        from backend.services.file_workflow_service import _clear_file_database_response

        with (
            patch("backend.services.file_workflow_service._clear_group_file_data", return_value={"files": 0}) as clear_data,
            patch("backend.core.crawler_runtime.get_crawler_for_group", side_effect=AssertionError("legacy crawler used")),
        ):
            response = _clear_file_database_response("group-1")

        clear_data.assert_called_once_with("group-1")
        self.assertEqual({"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 0}}, response)

    def test_clear_file_database_clears_image_cache_and_logs_success(self):
        from backend.services.file_workflow_service import _clear_file_database_response

        cache_manager = FakeImageCacheManager((True, "已删除 2 个缓存文件"))

        with (
            patch("backend.services.file_workflow_service._clear_group_file_data", return_value={"files": 1}),
            patch("backend.core.image_cache_manager.get_image_cache_manager", return_value=cache_manager) as get_cache,
            patch("backend.core.image_cache_manager.clear_group_cache_manager") as clear_group_cache,
            patch("backend.services.file_workflow_service._log_file_route_event") as log_file_route_event,
        ):
            response = _clear_file_database_response("group-1")

        get_cache.assert_called_once_with("group-1")
        self.assertEqual(1, cache_manager.clear_calls)
        clear_group_cache.assert_called_once_with("group-1")
        log_file_route_event.assert_called_once_with("INFO", "图片缓存已清空: 已删除 2 个缓存文件")
        self.assertEqual({"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 1}}, response)

    def test_clear_file_database_logs_image_cache_clear_failure_but_keeps_response(self):
        from backend.services.file_workflow_service import _clear_file_database_response

        cache_manager = FakeImageCacheManager((False, "permission denied"))

        with (
            patch("backend.services.file_workflow_service._clear_group_file_data", return_value={"files": 1}),
            patch("backend.core.image_cache_manager.get_image_cache_manager", return_value=cache_manager),
            patch("backend.core.image_cache_manager.clear_group_cache_manager") as clear_group_cache,
            patch("backend.services.file_workflow_service._log_file_route_event") as log_file_route_event,
        ):
            response = _clear_file_database_response("group-1")

        self.assertEqual(1, cache_manager.clear_calls)
        clear_group_cache.assert_called_once_with("group-1")
        log_file_route_event.assert_called_once_with("WARN", "清空图片缓存失败: permission denied")
        self.assertEqual({"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 1}}, response)

    def test_clear_file_database_logs_image_cache_exception_but_keeps_response(self):
        from backend.services.file_workflow_service import _clear_file_database_response

        with (
            patch("backend.services.file_workflow_service._clear_group_file_data", return_value={"files": 1}),
            patch("backend.core.image_cache_manager.get_image_cache_manager", side_effect=RuntimeError("cache boom")),
            patch("backend.core.image_cache_manager.clear_group_cache_manager") as clear_group_cache,
            patch("backend.services.file_workflow_service._log_file_route_event") as log_file_route_event,
        ):
            response = _clear_file_database_response("group-1")

        clear_group_cache.assert_not_called()
        log_file_route_event.assert_called_once_with("WARN", "清空图片缓存时出错: cache boom")
        self.assertEqual({"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 1}}, response)

    def test_query_group_id_casts_numeric_ids_for_sql_filters(self):
        self.assertEqual(123, _query_group_id("123"))
        self.assertEqual("abc", _query_group_id("abc"))

    def _run_async(self, coro):
        import asyncio

        return asyncio.run(coro)

    def _run_single_file_download_case(self, downloader, file_name=None, file_size=None):
        from backend.services.file_workflow_service import run_single_file_download_task_with_info

        with (
            patch("backend.services.file_workflow_service._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_workflow_service.update_task") as update_task,
            patch("backend.services.file_workflow_service.add_task_log") as add_task_log,
            patch("backend.services.file_workflow_service.is_task_stopped", return_value=False),
            patch("backend.services.file_workflow_service._safe_remove_file_downloader") as safe_remove,
        ):
            run_single_file_download_task_with_info(
                "task-1",
                "123",
                123,
                file_name=file_name,
                file_size=file_size,
            )

        return create_downloader, update_task, add_task_log, safe_remove


if __name__ == "__main__":
    unittest.main()
