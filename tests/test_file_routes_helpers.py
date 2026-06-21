import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.services.file_analysis_workflow import (
    _build_file_analysis_stats,
    _fail_file_analysis_task,
    _run_file_analysis_items,
)
from backend.services.file_download_records_workflow import (
    _build_download_file_info,
    _build_download_task_stats,
    _complete_download_records_task,
    _download_result_stat_key,
    _load_download_file_records,
    _load_filtered_download_file_records,
    _run_download_records,
)
from backend.services.file_single_download_workflow import _complete_successful_single_file_download
from backend.services.file_status_service import (
    _build_check_local_file_status_response,
    _build_file_status_response,
    _build_sync_files_response,
    _get_download_file_status,
    _get_file_status_response,
    _resolve_download_record_status,
)
from backend.services.file_workflow_service import (
    _close_crawler_file_databases,
    create_filtered_file_download_task,
    create_file_ai_analysis_task,
    create_file_collect_task,
    create_file_download_task,
    create_selected_file_download_task,
    create_selected_file_ai_analysis_task,
    create_single_file_download_task,
    create_sync_files_from_topics_task,
    run_collect_files_task,
    run_filtered_file_download_task,
    run_file_analysis_task,
    run_file_download_task,
    run_selected_file_download_task,
    run_single_file_download_task_with_info,
    run_sync_files_from_topics_task,
)
from backend.storage.zsxq_file_database import (
    DownloadFileRecord,
    DownloadFileSelection,
    FileAnalysisSourceRecord,
    FileListPage,
    FileListRecord,
    ZSXQFileDatabase,
    _add_file_search_condition,
    _query_group_id,
    _unique_int_file_ids,
)


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


class FakeFileDownloadTaskFileDb:
    def __init__(self, existing_count):
        self.cursor = FakeFileDownloadTaskCursor(existing_count)
        self.count_calls = []

    def count_files(self, group_id=None):
        self.count_calls.append(group_id)
        return self.cursor.existing_count


class FakeFileDownloadTaskDownloader:
    def __init__(self, existing_count):
        self.file_db = FakeFileDownloadTaskFileDb(existing_count)
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
        self.record_calls = []

    def get_download_file_record(self, file_id, group_id=None):
        self.record_calls.append((file_id, group_id))
        row = self.cursor.fetchone()
        return DownloadFileRecord.from_row(row) if row else None

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


class FakeFileListDb:
    def __init__(self, records=None, total=0):
        self.page_calls = []
        self.page = FileListPage(list(records or []), total)

    def load_file_list_page(self, **kwargs):
        self.page_calls.append(kwargs)
        return self.page

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def fake_zsxq_file_db(cursor, group_id="123"):
    file_db = object.__new__(ZSXQFileDatabase)
    file_db.group_id = group_id
    file_db.cursor = cursor
    return file_db


class FakeImageCacheManager:
    def __init__(self, result):
        self.result = result
        self.clear_calls = 0

    def clear_cache(self):
        self.clear_calls += 1
        return self.result


class FileRoutesHelperTests(unittest.TestCase):
    def test_create_file_collect_task_uses_ingestion_launch_recipe(self):
        with patch(
            "backend.services.file_workflow_service.launch_task_recipe",
            return_value={"task_id": "task-1", "message": "任务已创建，正在后台执行"},
        ) as launch:
            response = create_file_collect_task("group-1", "request")

        launch.assert_called_once()
        recipe = launch.call_args.args[0]
        self.assertEqual("collect_files", recipe.task_type)
        self.assertEqual("收集文件列表", recipe.description)
        self.assertEqual(run_collect_files_task, recipe.task_func)
        self.assertEqual("group-1", recipe.ingestion_group_id)
        self.assertEqual(("group-1", "request"), recipe.args)
        self.assertFalse(recipe.prepend_group_id_to_args)
        self.assertEqual({"task_id": "task-1", "message": "任务已创建，正在后台执行"}, response)

    def test_create_file_download_task_uses_ingestion_launch_recipe(self):
        from backend.schemas.files import FileDownloadRequest

        request = FileDownloadRequest(
            max_files=12,
            sort_by="time",
            start_time="2026-06-01",
            end_time="2026-06-02",
            last_days=7,
            download_interval=2.5,
            long_sleep_interval=30.0,
            files_per_batch=5,
            download_interval_min=1.0,
            download_interval_max=3.0,
            long_sleep_interval_min=10.0,
            long_sleep_interval_max=60.0,
        )

        with patch(
            "backend.services.file_workflow_service.launch_task_recipe",
            return_value={"task_id": "task-1", "message": "任务已创建，正在后台执行"},
        ) as launch:
            response = create_file_download_task("group-1", request)

        launch.assert_called_once()
        recipe = launch.call_args.args[0]
        self.assertEqual("download_files", recipe.task_type)
        self.assertEqual("下载文件 (排序: time)", recipe.description)
        self.assertEqual(run_file_download_task, recipe.task_func)
        self.assertEqual("group-1", recipe.ingestion_group_id)
        self.assertEqual(
            (
                "group-1",
                12,
                "time",
                "2026-06-01",
                "2026-06-02",
                7,
                2.5,
                30.0,
                5,
                1.0,
                3.0,
                10.0,
                60.0,
            ),
            recipe.args,
        )
        self.assertFalse(recipe.prepend_group_id_to_args)
        self.assertEqual({"task_id": "task-1", "message": "任务已创建，正在后台执行"}, response)

    def test_create_single_file_download_task_uses_ingestion_launch_recipe(self):
        with patch(
            "backend.services.file_workflow_service.launch_task_recipe",
            return_value={"task_id": "task-1", "message": "单个文件下载任务已创建"},
        ) as launch:
            response = create_single_file_download_task("group-1", 123, "file.pdf", 456)

        launch.assert_called_once()
        recipe = launch.call_args.args[0]
        self.assertEqual("download_single_file", recipe.task_type)
        self.assertEqual("下载单个文件 (ID: 123)", recipe.description)
        self.assertEqual(run_single_file_download_task_with_info, recipe.task_func)
        self.assertEqual("group-1", recipe.ingestion_group_id)
        self.assertEqual(("group-1", 123, "file.pdf", 456), recipe.args)
        self.assertEqual("单个文件下载任务已创建", recipe.message)
        self.assertFalse(recipe.prepend_group_id_to_args)
        self.assertEqual({"task_id": "task-1", "message": "单个文件下载任务已创建"}, response)

    def test_create_selected_file_download_task_uses_ingestion_launch_recipe(self):
        from backend.schemas.files import FileIdListRequest

        request = FileIdListRequest(file_ids=[123, 456])

        with patch(
            "backend.services.file_workflow_service.launch_task_recipe",
            return_value={"task_id": "task-1", "message": "选中文件下载任务已创建"},
        ) as launch:
            response = create_selected_file_download_task("group-1", request)

        launch.assert_called_once()
        recipe = launch.call_args.args[0]
        self.assertEqual("download_selected_files", recipe.task_type)
        self.assertEqual("下载选中文件 (2 个)", recipe.description)
        self.assertEqual(run_selected_file_download_task, recipe.task_func)
        self.assertEqual("group-1", recipe.ingestion_group_id)
        self.assertEqual(("group-1", [123, 456]), recipe.args)
        self.assertEqual("选中文件下载任务已创建", recipe.message)
        self.assertFalse(recipe.prepend_group_id_to_args)
        self.assertEqual({"task_id": "task-1", "message": "选中文件下载任务已创建"}, response)

    def test_create_filtered_file_download_task_uses_ingestion_launch_recipe(self):
        from backend.schemas.files import FileFilteredDownloadRequest

        request = FileFilteredDownloadRequest(status="failed", search="pdf", max_files=20)

        with patch(
            "backend.services.file_workflow_service.launch_task_recipe",
            return_value={"task_id": "task-1", "message": "筛选结果下载任务已创建"},
        ) as launch:
            response = create_filtered_file_download_task("group-1", request)

        launch.assert_called_once()
        recipe = launch.call_args.args[0]
        self.assertEqual("download_filtered_files", recipe.task_type)
        self.assertEqual("下载筛选结果", recipe.description)
        self.assertEqual(run_filtered_file_download_task, recipe.task_func)
        self.assertEqual("group-1", recipe.ingestion_group_id)
        self.assertEqual(("group-1", "failed", "pdf", 20), recipe.args)
        self.assertEqual("筛选结果下载任务已创建", recipe.message)
        self.assertFalse(recipe.prepend_group_id_to_args)
        self.assertEqual({"task_id": "task-1", "message": "筛选结果下载任务已创建"}, response)

    def test_create_file_ai_analysis_task_uses_group_metadata_launch_recipe(self):
        with patch(
            "backend.services.file_workflow_service.launch_task_recipe",
            return_value={"task_id": "task-1", "message": "文件 AI 分析任务已创建"},
        ) as launch:
            response = create_file_ai_analysis_task("group-1", 123, True)

        launch.assert_called_once()
        recipe = launch.call_args.args[0]
        self.assertEqual("analyze_file", recipe.task_type)
        self.assertEqual("分析文件 (ID: 123)", recipe.description)
        self.assertEqual(run_file_analysis_task, recipe.task_func)
        self.assertEqual(("group-1", [123], True), recipe.args)
        self.assertEqual("group-1", recipe.group_id)
        self.assertEqual("文件 AI 分析任务已创建", recipe.message)
        self.assertEqual({"task_id": "task-1", "message": "文件 AI 分析任务已创建"}, response)

    def test_create_selected_file_ai_analysis_task_uses_group_metadata_launch_recipe(self):
        from backend.schemas.files import FileAIAnalysisBatchRequest

        request = FileAIAnalysisBatchRequest(file_ids=[123, 456], force=False)

        with patch(
            "backend.services.file_workflow_service.launch_task_recipe",
            return_value={"task_id": "task-1", "message": "批量文件 AI 分析任务已创建"},
        ) as launch:
            response = create_selected_file_ai_analysis_task("group-1", request)

        launch.assert_called_once()
        recipe = launch.call_args.args[0]
        self.assertEqual("analyze_files", recipe.task_type)
        self.assertEqual("批量分析文件 (2 个)", recipe.description)
        self.assertEqual(run_file_analysis_task, recipe.task_func)
        self.assertEqual(("group-1", [123, 456], False), recipe.args)
        self.assertEqual("group-1", recipe.group_id)
        self.assertEqual("批量文件 AI 分析任务已创建", recipe.message)
        self.assertEqual({"task_id": "task-1", "message": "批量文件 AI 分析任务已创建"}, response)

    def test_create_sync_files_from_topics_task_uses_ingestion_launch_recipe(self):
        with patch(
            "backend.services.file_workflow_service.launch_task_recipe",
            return_value={"task_id": "task-1", "message": "从话题同步文件记录任务已创建"},
        ) as launch:
            response = create_sync_files_from_topics_task("group-1")

        launch.assert_called_once()
        recipe = launch.call_args.args[0]
        self.assertEqual("sync_files_from_topics", recipe.task_type)
        self.assertEqual("从话题同步文件记录 (群组: group-1)", recipe.description)
        self.assertEqual(run_sync_files_from_topics_task, recipe.task_func)
        self.assertEqual("group-1", recipe.ingestion_group_id)
        self.assertEqual(("group-1",), recipe.args)
        self.assertEqual("从话题同步文件记录任务已创建", recipe.message)
        self.assertFalse(recipe.prepend_group_id_to_args)
        self.assertEqual({"task_id": "task-1", "message": "从话题同步文件记录任务已创建"}, response)

    def test_collect_files_delegates_to_collect_launch_recipe(self):
        from backend.routes.file_routes import collect_files
        from backend.schemas.files import FileCollectRequest

        request = FileCollectRequest()

        with patch(
            "backend.routes.file_routes.create_file_collect_task",
            return_value={"task_id": "task-1", "message": "ok"},
        ) as create_task:
            response = self._run_async(collect_files("group-1", request))

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        create_task.assert_called_once_with("group-1", request)

    def test_download_files_delegates_to_download_launch_recipe(self):
        from backend.routes.file_routes import download_files
        from backend.schemas.files import FileDownloadRequest

        request = FileDownloadRequest()

        with patch(
            "backend.routes.file_routes.create_file_download_task",
            return_value={"task_id": "task-1", "message": "ok"},
        ) as create_task:
            response = self._run_async(download_files("group-1", request))

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        create_task.assert_called_once_with("group-1", request)

    def test_download_single_file_delegates_to_single_download_launch_recipe(self):
        from backend.routes.file_routes import download_single_file

        with patch(
            "backend.routes.file_routes.create_single_file_download_task",
            return_value={"task_id": "task-1", "message": "ok"},
        ) as create_task:
            response = self._run_async(
                download_single_file(
                    "group-1",
                    123,
                    file_name="file.pdf",
                    file_size=456,
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        create_task.assert_called_once_with("group-1", 123, "file.pdf", 456)

    def test_download_selected_files_delegates_to_selected_download_launch_recipe(self):
        from backend.routes.file_routes import download_selected_files
        from backend.schemas.files import FileIdListRequest

        request = FileIdListRequest(file_ids=[123, 456])

        with patch(
            "backend.routes.file_routes.create_selected_file_download_task",
            return_value={"task_id": "task-1", "message": "ok"},
        ) as create_task:
            response = self._run_async(
                download_selected_files(
                    "group-1",
                    request,
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        create_task.assert_called_once_with("group-1", request)

    def test_download_filtered_files_delegates_to_filtered_download_launch_recipe(self):
        from backend.routes.file_routes import download_filtered_files
        from backend.schemas.files import FileFilteredDownloadRequest

        request = FileFilteredDownloadRequest(status="failed", search="pdf", max_files=10)

        with patch(
            "backend.routes.file_routes.create_filtered_file_download_task",
            return_value={"task_id": "task-1", "message": "ok"},
        ) as create_task:
            response = self._run_async(
                download_filtered_files(
                    "group-1",
                    request,
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        create_task.assert_called_once_with("group-1", request)

    def test_sync_files_from_topics_is_enqueued(self):
        from backend.routes.file_routes import sync_files_from_topics

        with patch(
            "backend.routes.file_routes.create_sync_files_from_topics_task",
            return_value={"task_id": "task-1", "message": "ok"},
        ) as create_task:
            response = self._run_async(sync_files_from_topics("group-1"))

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        create_task.assert_called_once_with("group-1")

    def test_file_analysis_task_attaches_group_metadata(self):
        from backend.routes.file_routes import create_file_analysis_task
        from backend.schemas.files import FileAIAnalysisRequest

        with (
            patch(
                "backend.routes.file_routes.create_file_analysis_task_response",
                return_value={"task_id": "task-1", "message": "ok"},
            ) as create_task,
        ):
            response = self._run_async(
                create_file_analysis_task(
                    "group-1",
                    123,
                    FileAIAnalysisRequest(force=True),
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        create_task.assert_called_once_with("group-1", 123, True)

    def test_selected_file_analysis_task_attaches_group_metadata(self):
        from backend.routes.file_routes import create_selected_file_analysis_task
        from backend.schemas.files import FileAIAnalysisBatchRequest

        request = FileAIAnalysisBatchRequest(file_ids=[123, 456], force=False)

        with (
            patch(
                "backend.routes.file_routes.create_selected_file_analysis_task_response",
                return_value={"task_id": "task-1", "message": "ok"},
            ) as create_task,
        ):
            response = self._run_async(
                create_selected_file_analysis_task(
                    "group-1",
                    request,
                )
            )

        self.assertEqual({"task_id": "task-1", "message": "ok"}, response)
        create_task.assert_called_once_with("group-1", request)

    def test_file_route_error_preserves_status_and_detail_format(self):
        from backend.routes import file_routes

        error = file_routes._file_route_error("创建文件收集任务失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("创建文件收集任务失败: boom", error.detail)

    def test_file_route_error_maps_task_launch_conflict(self):
        from backend.routes import file_routes
        from backend.services.task_launch import TaskLaunchConflict

        error = file_routes._file_route_error(
            "创建文件收集任务失败",
            TaskLaunchConflict({"task_id": "task-old", "type": "crawl_all", "status": "running"}),
        )

        self.assertEqual(409, error.status_code)
        self.assertEqual(
            {
                "message": "该群组已有采集或同步任务正在运行",
                "task_id": "task-old",
                "type": "crawl_all",
                "status": "running",
            },
            error.detail,
        )

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

        cases = [
            (
                file_routes.collect_files,
                ("group-1", FileCollectRequest()),
                {},
                "创建文件收集任务失败: boom",
            ),
            (
                file_routes.download_files,
                ("group-1", FileDownloadRequest()),
                {},
                "创建文件下载任务失败: boom",
            ),
            (
                file_routes.download_single_file,
                ("group-1", 123),
                {"file_name": "file.pdf", "file_size": 456},
                "创建单个文件下载任务失败: boom",
            ),
            (
                file_routes.download_selected_files,
                ("group-1", FileIdListRequest(file_ids=[123, 456])),
                {},
                "创建选中文件下载任务失败: boom",
            ),
            (
                file_routes.download_filtered_files,
                ("group-1", FileFilteredDownloadRequest(status="failed", search="pdf")),
                {},
                "创建筛选结果下载任务失败: boom",
            ),
            (
                file_routes.create_file_analysis_task,
                ("group-1", 123, FileAIAnalysisRequest(force=True)),
                {},
                "创建文件 AI 分析任务失败: boom",
            ),
            (
                file_routes.create_selected_file_analysis_task,
                ("group-1", FileAIAnalysisBatchRequest(file_ids=[123, 456])),
                {},
                "创建批量文件 AI 分析任务失败: boom",
            ),
            (
                file_routes.sync_files_from_topics,
                ("group-1",),
                {},
                "创建同步文件记录任务失败: boom",
            ),
        ]

        for route, route_args, route_kwargs, expected_detail in cases:
            with self.subTest(route=route.__name__):
                with ExitStack() as stack:
                    launch_patch_targets = {
                        file_routes.collect_files: "backend.routes.file_routes.create_file_collect_task",
                        file_routes.download_files: "backend.routes.file_routes.create_file_download_task",
                        file_routes.download_single_file: "backend.routes.file_routes.create_single_file_download_task",
                        file_routes.download_selected_files: "backend.routes.file_routes.create_selected_file_download_task",
                        file_routes.download_filtered_files: "backend.routes.file_routes.create_filtered_file_download_task",
                        file_routes.create_file_analysis_task: "backend.routes.file_routes.create_file_analysis_task_response",
                        file_routes.create_selected_file_analysis_task: (
                            "backend.routes.file_routes.create_selected_file_analysis_task_response"
                        ),
                        file_routes.sync_files_from_topics: "backend.routes.file_routes.create_sync_files_from_topics_task",
                    }
                    patch_target = launch_patch_targets[route]
                    stack.enter_context(
                        patch(patch_target, side_effect=RuntimeError("boom"))
                    )
                    with self.assertRaises(file_routes.HTTPException) as raised:
                        self._run_async(route(*route_args, **route_kwargs))

                self.assertEqual(500, raised.exception.status_code)
                self.assertEqual(expected_detail, raised.exception.detail)
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

        cases = [
            (file_routes.collect_files, ("group-1", FileCollectRequest()), {}),
            (file_routes.download_files, ("group-1", FileDownloadRequest()), {}),
            (
                file_routes.download_single_file,
                ("group-1", 123),
                {"file_name": "file.pdf", "file_size": 456},
            ),
            (
                file_routes.download_selected_files,
                ("group-1", FileIdListRequest(file_ids=[123, 456])),
                {},
            ),
            (
                file_routes.download_filtered_files,
                ("group-1", FileFilteredDownloadRequest(status="failed", search="pdf")),
                {},
            ),
            (
                file_routes.create_file_analysis_task,
                ("group-1", 123, FileAIAnalysisRequest(force=True)),
                {},
            ),
            (
                file_routes.create_selected_file_analysis_task,
                ("group-1", FileAIAnalysisBatchRequest(file_ids=[123, 456])),
                {},
            ),
            (file_routes.sync_files_from_topics, ("group-1",), {}),
        ]

        for route, route_args, route_kwargs in cases:
            original_error = file_routes.HTTPException(status_code=409, detail="conflict")
            with self.subTest(route=route.__name__):
                with ExitStack() as stack:
                    launch_patch_targets = {
                        file_routes.collect_files: "backend.routes.file_routes.create_file_collect_task",
                        file_routes.download_files: "backend.routes.file_routes.create_file_download_task",
                        file_routes.download_single_file: "backend.routes.file_routes.create_single_file_download_task",
                        file_routes.download_selected_files: "backend.routes.file_routes.create_selected_file_download_task",
                        file_routes.download_filtered_files: "backend.routes.file_routes.create_filtered_file_download_task",
                        file_routes.create_file_analysis_task: "backend.routes.file_routes.create_file_analysis_task_response",
                        file_routes.create_selected_file_analysis_task: (
                            "backend.routes.file_routes.create_selected_file_analysis_task_response"
                        ),
                        file_routes.sync_files_from_topics: "backend.routes.file_routes.create_sync_files_from_topics_task",
                    }
                    patch_target = launch_patch_targets[route]
                    stack.enter_context(patch(patch_target, side_effect=original_error))
                    with self.assertRaises(file_routes.HTTPException) as raised:
                        self._run_async(route(*route_args, **route_kwargs))

                self.assertIs(original_error, raised.exception)
                self.assertEqual(409, raised.exception.status_code)
                self.assertEqual("conflict", raised.exception.detail)
    def test_file_analysis_routes_preserve_success_payloads(self):
        from backend.routes import file_routes
        from backend.schemas.files import FileAIAnalysisRequest

        calls = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append((func, args, kwargs))
            return {"called": func.__name__, "args": args, "kwargs": kwargs}

        with (
            patch("backend.routes.file_routes.asyncio.to_thread", side_effect=fake_to_thread),
        ):
            cached = self._run_async(file_routes.get_file_analysis("group-1", 123))
            created = self._run_async(
                file_routes.create_file_analysis("group-1", 456, FileAIAnalysisRequest(force=True))
            )

        self.assertEqual(
            [
                (file_routes.get_file_analysis_response, ("group-1", 123), {}),
                (file_routes.create_file_analysis_response, ("group-1", 456, True), {}),
            ],
            calls,
        )
        self.assertEqual(
            {"called": "get_file_analysis_response", "args": ("group-1", 123), "kwargs": {}},
            cached,
        )
        self.assertEqual(
            {"called": "create_file_analysis_response", "args": ("group-1", 456, True), "kwargs": {}},
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
                (file_routes.get_file_analysis_response, ("group-1", 123), {}),
                (file_routes.create_file_analysis_response, ("group-1", 456, True), {}),
            ],
            calls,
        )
        self.assertEqual(
            {"called": "get_file_analysis_response", "args": ("group-1", 123), "kwargs": {}},
            cached,
        )
        self.assertEqual(
            {"called": "create_file_analysis_response", "args": ("group-1", 456, True), "kwargs": {}},
            created,
        )

    def test_create_file_analysis_preserves_missing_api_key_wrapped_error(self):
        from backend.routes import file_routes
        from backend.schemas.files import FileAIAnalysisRequest
        from fastapi import HTTPException

        with patch(
            "backend.routes.file_routes._created_file_analysis",
            side_effect=file_routes.FileAIAnalysisEntryError(
                400,
                "未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key",
            ),
        ) as create_analysis:
            with self.assertRaises(HTTPException) as raised:
                self._run_async(file_routes.create_file_analysis("group-1", 456, FileAIAnalysisRequest(force=True)))

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual(
            "文件 AI 分析失败: 400: 未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key",
            raised.exception.detail,
        )
        create_analysis.assert_called_once_with("group-1", 456, True)

    def test_create_file_analysis_preserves_service_error_mapping(self):
        from backend.routes import file_routes
        from backend.schemas.files import FileAIAnalysisRequest
        from fastapi import HTTPException

        cases = [
            (ValueError("bad value"), "bad value"),
            (RuntimeError("bad runtime"), "bad runtime"),
        ]

        for error, detail in cases:
            with self.subTest(detail=detail):
                with patch("backend.routes.file_routes._created_file_analysis", side_effect=error):
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

        with patch("backend.routes.file_routes._created_file_analysis", side_effect=Exception("boom")):
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

        with patch("backend.routes.file_routes._created_file_analysis", side_effect=original_error):
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

    def test_analyze_group_file_uses_storage_source_record(self):
        from backend.services import file_ai_analysis_service

        class NoCursor:
            def execute(self, *_args, **_kwargs):
                raise AssertionError("analyze_group_file should not execute SQL directly")

        class FakeFileDb:
            def __init__(self):
                self.cursor = NoCursor()
                self.analysis_reads = 0
                self.source_calls = []
                self.upserts = []
                self.closed = False

            def get_file_ai_analysis(self, file_id):
                self.analysis_reads += 1
                if self.analysis_reads == 1:
                    return None
                return {"file_id": file_id, "status": "completed", "summary": "summary"}

            def get_file_analysis_source_record(self, file_id):
                self.source_calls.append(file_id)
                return FileAnalysisSourceRecord(file_id, "note.txt", 12, "completed", None)

            def upsert_file_ai_analysis(self, file_id, **kwargs):
                self.upserts.append((file_id, kwargs))

            def close(self):
                self.closed = True

        fake_db = FakeFileDb()
        with TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "note.txt"
            source_path.write_text("content", encoding="utf-8")

            with (
                patch("backend.services.file_ai_analysis_service._get_file_db", return_value=fake_db),
                patch("backend.services.file_ai_analysis_service.resolve_local_file_path", return_value=source_path) as resolve,
                patch(
                    "backend.services.file_ai_analysis_service._extract_file_content_for_analysis",
                    return_value=("正文", "text/plain"),
                ),
                patch("backend.services.file_ai_analysis_service._summarize_text_with_ai", return_value="summary"),
            ):
                result = file_ai_analysis_service.analyze_group_file("group-1", 456, force=True)

        self.assertEqual({"file_id": 456, "status": "completed", "summary": "summary", "cached": False}, result)
        self.assertEqual([456], fake_db.source_calls)
        resolve.assert_called_once_with("group-1", 456, "note.txt", None)
        self.assertEqual(1, len(fake_db.upserts))
        self.assertEqual(456, fake_db.upserts[0][0])
        self.assertEqual(str(source_path), fake_db.upserts[0][1]["source_path"])
        self.assertEqual("summary", fake_db.upserts[0][1]["summary"])
        self.assertTrue(fake_db.closed)

    def test_run_file_analysis_task_dedupes_ids_and_preserves_mixed_stats(self):
        from backend.services import file_analysis_workflow

        def analyze_side_effect(group_id, file_id, **_kwargs):
            if file_id == 3:
                raise RuntimeError("boom")
            return {"cached": file_id == 2}

        with (
            patch("backend.services.file_analysis_workflow.update_task") as update_task,
            patch("backend.services.file_analysis_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_analysis_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_analysis_workflow.analyze_group_file", side_effect=analyze_side_effect) as analyze,
        ):
            file_analysis_workflow.run_file_analysis_task("task-1", "group-1", [1, 2, 1, 3], force=True)

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
        from backend.services import file_analysis_workflow

        with (
            patch("backend.services.file_analysis_workflow.update_task") as update_task,
            patch("backend.services.file_analysis_workflow.add_task_log"),
            patch("backend.services.file_analysis_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_analysis_workflow.analyze_group_file", return_value={"cached": False}) as analyze,
        ):
            file_analysis_workflow.run_file_analysis_task("task-1", "group-1", [1, "1"], force=False)

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
        from backend.services import file_analysis_workflow

        with (
            patch("backend.services.file_analysis_workflow.update_task") as update_task,
            patch("backend.services.file_analysis_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_analysis_workflow.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_analysis_workflow.analyze_group_file", return_value={"cached": False}) as analyze,
        ):
            file_analysis_workflow.run_file_analysis_task("task-1", "group-1", [1, 2], force=False)

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
        from backend.services import file_analysis_workflow

        with (
            patch("backend.services.file_analysis_workflow.update_task") as update_task,
            patch("backend.services.file_analysis_workflow.add_task_log"),
            patch("backend.services.file_analysis_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_analysis_workflow.analyze_group_file", side_effect=RuntimeError("boom")),
        ):
            file_analysis_workflow.run_file_analysis_task("task-1", "group-1", [1], force=False)

        update_task.assert_any_call(
            "task-1",
            "failed",
            "文件分析全部失败",
            {"analysis": {"total_files": 1, "completed": 0, "cached": 0, "failed": 1}},
        )

    def test_fail_file_analysis_task_uses_file_lifecycle_failure_payload(self):
        stats = {"total_files": 1, "completed": 0, "cached": 0, "failed": 1}

        with (
            patch("backend.services.file_analysis_workflow.update_task") as update_task,
            patch("backend.services.file_analysis_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_analysis_workflow.is_task_stopped", return_value=False),
        ):
            _fail_file_analysis_task("task-1", "文件分析任务失败: boom", stats)

        add_task_log.assert_called_once_with("task-1", "❌ 文件分析任务失败: boom")
        update_task.assert_called_once_with(
            "task-1",
            "failed",
            "文件分析任务失败: boom",
            {"analysis": stats},
        )

    def test_run_file_analysis_items_updates_stats_logs_and_continues_after_failure(self):
        def analyze_side_effect(group_id, file_id, force):
            if file_id == 3:
                raise RuntimeError("boom")
            return {"cached": file_id == 2}

        stats = _build_file_analysis_stats(total_files=3)

        with (
            patch("backend.services.file_analysis_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_analysis_workflow.add_task_log") as add_task_log,
            patch(
                "backend.services.file_analysis_workflow._analyze_group_file_with_defaults",
                side_effect=analyze_side_effect,
            ) as analyze,
        ):
            result = _run_file_analysis_items("task-1", "group-1", [1, 2, 3], stats, force=True)

        self.assertTrue(result)
        self.assertEqual(
            [("group-1", 1, True), ("group-1", 2, True), ("group-1", 3, True)],
            [call.args for call in analyze.call_args_list],
        )
        self.assertEqual({"total_files": 3, "completed": 1, "cached": 1, "failed": 1}, stats)
        self.assertEqual(
            [
                ("task-1", "【1/3】分析文件 ID: 1"),
                ("task-1", "✅ 文件分析完成: 1"),
                ("task-1", "【2/3】分析文件 ID: 2"),
                ("task-1", "✅ 文件分析完成: 2"),
                ("task-1", "【3/3】分析文件 ID: 3"),
                ("task-1", "❌ 文件分析失败: 3, boom"),
            ],
            [call.args for call in add_task_log.call_args_list],
        )

    def test_run_file_analysis_items_stops_before_next_file_without_completion_log(self):
        stats = _build_file_analysis_stats(total_files=2)

        with (
            patch("backend.services.file_analysis_workflow.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_analysis_workflow.add_task_log") as add_task_log,
            patch(
                "backend.services.file_analysis_workflow._analyze_group_file_with_defaults",
                return_value={"cached": False},
            ) as analyze,
        ):
            result = _run_file_analysis_items("task-1", "group-1", [1, 2], stats, force=False)

        self.assertFalse(result)
        self.assertEqual([("group-1", 1, False)], [call.args for call in analyze.call_args_list])
        self.assertEqual({"total_files": 2, "completed": 1, "cached": 0, "failed": 0}, stats)
        self.assertEqual(
            [
                ("task-1", "【1/2】分析文件 ID: 1"),
                ("task-1", "✅ 文件分析完成: 1"),
                ("task-1", "🛑 文件分析任务被停止"),
            ],
            [call.args for call in add_task_log.call_args_list],
        )

    def test_get_download_file_status_handles_missing_file(self):
        with patch("backend.services.file_status_service.group_download_dir", return_value=r"C:\tmp\group-1\downloads"):
            status = _get_download_file_status("group-1", "missing.pdf", 123, "fallback.pdf")

        self.assertEqual("missing.pdf", status["safe_filename"])
        self.assertFalse(status["local_exists"])
        self.assertEqual(0, status["local_size"])
        self.assertIsNone(status["local_path"])
        self.assertFalse(status["is_complete"])

    def test_resolve_download_record_status_marks_existing_file_completed(self):
        with patch("backend.services.file_status_service.resolve_local_file_path") as mocked_resolve:
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

    def test_get_file_status_response_queries_database_and_local_status(self):
        class FakeFileDb:
            def __init__(self):
                self.status_calls = []

            def get_file_status_record(self, file_id):
                self.status_calls.append(file_id)
                return ("file.pdf", 456, "downloaded")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        local_status = {
            "local_exists": True,
            "local_size": 456,
            "local_path": r"C:\tmp\group-1\downloads\file.pdf",
            "is_complete": True,
        }
        fake_db = FakeFileDb()

        with (
            patch("backend.services.file_status_service._file_db", return_value=fake_db),
            patch(
                "backend.services.file_status_service._get_download_file_status",
                return_value=local_status,
            ) as get_download_file_status,
        ):
            response = _get_file_status_response("123", 456)

        self.assertEqual([456], fake_db.status_calls)
        get_download_file_status.assert_called_once_with("123", "file.pdf", 456, "file_456")
        self.assertEqual(
            {
                "file_id": 456,
                "name": "file.pdf",
                "size": 456,
                "download_status": "downloaded",
                "local_exists": True,
                "local_size": 456,
                "local_path": r"C:\tmp\group-1\downloads\file.pdf",
                "is_complete": True,
            },
            response,
        )

    def test_get_file_status_response_skips_local_status_for_missing_row(self):
        class FakeFileDb:
            def __init__(self):
                self.status_calls = []

            def get_file_status_record(self, file_id):
                self.status_calls.append(file_id)
                return None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeFileDb()
        with (
            patch("backend.services.file_status_service._file_db", return_value=fake_db),
            patch("backend.services.file_status_service._get_download_file_status") as get_download_file_status,
        ):
            response = _get_file_status_response("group-1", 123)

        self.assertEqual([123], fake_db.status_calls)
        get_download_file_status.assert_not_called()
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

    def test_create_file_downloader_registers_with_task_runtime(self):
        from backend.services.file_downloader_runtime import _create_file_downloader

        class FakeDownloader:
            pass

        downloader = FakeDownloader()

        with (
            patch("backend.services.file_downloader_runtime.get_cookie_for_group", return_value="cookie") as get_cookie,
            patch("backend.services.file_downloader_runtime.ZSXQFileDownloader", return_value=downloader) as downloader_cls,
            patch("backend.services.file_downloader_runtime.register_task_file_downloader") as register_downloader,
        ):
            created = _create_file_downloader("task-1", "123", files_per_batch=5)

        self.assertIs(downloader, created)
        self.assertTrue(callable(downloader.log_callback))
        self.assertTrue(callable(downloader.stop_check_func))
        get_cookie.assert_called_once_with("123")
        downloader_cls.assert_called_once_with(cookie="cookie", group_id="123", files_per_batch=5)
        register_downloader.assert_called_once_with("task-1", downloader)

    def test_remove_file_downloader_unregisters_with_task_runtime(self):
        from backend.services.file_downloader_runtime import _remove_file_downloader

        with patch("backend.services.file_downloader_runtime.unregister_task_file_downloader") as unregister_downloader:
            _remove_file_downloader("task-1")

        unregister_downloader.assert_called_once_with("task-1")

    def test_download_file_record_builds_downloader_payload(self):
        record = DownloadFileRecord.from_row((123, "", None, None))

        self.assertEqual(123, record.file_id)
        self.assertEqual("file_123", record.name)
        self.assertEqual(0, record.size)
        self.assertEqual(0, record.download_count)
        self.assertEqual(
            _build_download_file_info(123, "file_123", 0, 0),
            record.to_downloader_payload(),
        )

    def test_download_result_stat_key_preserves_existing_counts(self):
        self.assertEqual("skipped", _download_result_stat_key("skipped"))
        self.assertEqual("downloaded", _download_result_stat_key(True))
        self.assertEqual("downloaded", _download_result_stat_key("local/path.pdf"))
        self.assertEqual("failed", _download_result_stat_key(False))
        self.assertEqual("failed", _download_result_stat_key(None))

    def test_get_file_stats_response_uses_storage_download_stats(self):
        from backend.services import file_read_model

        class FakeFileDb:
            def __init__(self):
                self.download_stats_calls = 0

            def get_database_stats(self):
                return {"files": 9, "topics": 5}

            def get_file_download_stats(self):
                self.download_stats_calls += 1
                return (9, 4, 3, 2)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeFileDb()
        with patch("backend.services.file_status_service._file_db", return_value=fake_db):
            response = file_read_model.get_file_stats_response("123")

        self.assertEqual(1, fake_db.download_stats_calls)
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
        from backend.services import file_read_model

        class FakeFileDb:
            def __init__(self):
                self.download_stats_calls = 0

            def get_database_stats(self):
                return {"files": 0}

            def get_file_download_stats(self):
                self.download_stats_calls += 1
                return None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeFileDb()
        with patch("backend.services.file_status_service._file_db", return_value=fake_db):
            response = file_read_model.get_file_stats_response("group-1")

        self.assertEqual(1, fake_db.download_stats_calls)
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

    def test_get_file_stats_response_reads_database_stats_before_download_stats(self):
        from backend.services import file_read_model

        events = []

        class FakeFileDb:
            def get_database_stats(self):
                events.append("database_stats")
                return {"files": 1}

            def get_file_download_stats(self):
                events.append("download_stats")
                return (1, 1, 0, 0)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeFileDb()
        with patch("backend.services.file_status_service._file_db", return_value=fake_db):
            response = file_read_model.get_file_stats_response("123")

        self.assertEqual(
            ["database_stats", "download_stats"],
            events,
        )
        self.assertEqual(1, response["download_stats"]["downloaded"])

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
                (file_routes.get_file_status_response, ("group-1", 123)),
                (file_routes.check_local_file_status_response, ("group-1", "file.pdf", 456)),
                (file_routes.get_file_stats_response, ("group-1",)),
            ],
            calls,
        )
        self.assertEqual({"called": "get_file_status_response", "args": ("group-1", 123)}, file_status)
        self.assertEqual({"called": "check_local_file_status_response", "args": ("group-1", "file.pdf", 456)}, local_status)
        self.assertEqual({"called": "get_file_stats_response", "args": ("group-1",)}, stats)

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

        self.assertEqual([(file_routes.clear_file_database_response, ("group-1",))], calls)
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

        self.assertEqual([(file_routes.get_files_response, ("group-1", 2, 5, "completed", "pdf", "pending"))], calls)
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
                (file_routes.get_file_status_response, ("group-1", 123)),
                (file_routes.check_local_file_status_response, ("group-1", "file.pdf", 456)),
                (file_routes.get_file_stats_response, ("group-1",)),
                (file_routes.clear_file_database_response, ("group-1",)),
                (file_routes.get_files_response, ("group-1", 2, 5, "completed", "pdf", "pending")),
            ],
            calls,
        )
        self.assertEqual({"called": "get_file_status_response", "args": ("group-1", 123)}, file_status)
        self.assertEqual({"called": "check_local_file_status_response", "args": ("group-1", "file.pdf", 456)}, local_status)
        self.assertEqual({"called": "get_file_stats_response", "args": ("group-1",)}, stats)
        self.assertEqual({"called": "clear_file_database_response", "args": ("group-1",)}, clear_response)
        self.assertEqual({"called": "get_files_response", "args": ("group-1", 2, 5, "completed", "pdf", "pending")}, files)

    def test_get_files_response_passes_analysis_status_to_storage(self):
        from backend.services import file_read_model

        fake_db = FakeFileListDb()
        with patch("backend.services.file_read_model._file_db", return_value=fake_db):
            response = file_read_model.get_files_response("group-1", analysis_status="analyzed")

        self.assertEqual([], response["files"])
        self.assertEqual(
            [{"page": 1, "per_page": 20, "status": None, "search": None, "analysis_status": "analyzed"}],
            fake_db.page_calls,
        )

        fake_db = FakeFileListDb()
        with patch("backend.services.file_read_model._file_db", return_value=fake_db):
            file_read_model.get_files_response("group-1", analysis_status="pending")

        self.assertEqual(
            [{"page": 1, "per_page": 20, "status": None, "search": None, "analysis_status": "pending"}],
            fake_db.page_calls,
        )

    def test_get_files_response_passes_empty_status_to_storage(self):
        from backend.services import file_read_model

        fake_db = FakeFileListDb()
        with patch("backend.services.file_read_model._file_db", return_value=fake_db):
            response = file_read_model.get_files_response("123")

        self.assertEqual([], response["files"])
        self.assertEqual(
            [{"page": 1, "per_page": 20, "status": None, "search": None, "analysis_status": None}],
            fake_db.page_calls,
        )

    def test_get_files_response_keeps_completed_search_and_pagination_shape(self):
        from backend.services import file_read_model

        fake_db = FakeFileListDb(
            records=[
                FileListRecord(
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
            ],
            total=21,
        )
        with (
            patch("backend.services.file_read_model._file_db", return_value=fake_db),
            patch(
                "backend.services.file_status_service.resolve_local_file_path",
                return_value=r"C:\resolved\Report.PDF",
            ),
        ):
            response = file_read_model.get_files_response(
                "123",
                page=2,
                per_page=5,
                status="completed",
                search=" Foo ",
                analysis_status="analyzed",
            )

        self.assertEqual(
            [{"page": 2, "per_page": 5, "status": "completed", "search": " Foo ", "analysis_status": "analyzed"}],
            fake_db.page_calls,
        )
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
            patch("backend.services.file_collect_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_collect_workflow.update_task") as update_task,
            patch("backend.services.file_collect_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_collect_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_collect_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_collect_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_collect_workflow.update_task") as update_task,
            patch("backend.services.file_collect_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_collect_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_collect_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_collect_workflow._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_collect_workflow.update_task") as update_task,
            patch("backend.services.file_collect_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_collect_workflow.is_task_stopped", return_value=True),
            patch("backend.services.file_collect_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_collect_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_collect_workflow.update_task") as update_task,
            patch("backend.services.file_collect_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_collect_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_collect_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_download_workflow._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_download_workflow.update_task") as update_task,
            patch("backend.services.file_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_download_workflow._safe_remove_file_downloader") as safe_remove,
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
        self.assertEqual(["123"], downloader.file_db.count_calls)
        self.assertEqual([], downloader.file_db.cursor.executed)
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
            patch("backend.services.file_download_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_download_workflow.update_task") as update_task,
            patch("backend.services.file_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_download_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_download_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_download_workflow.update_task"),
            patch("backend.services.file_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_download_workflow._safe_remove_file_downloader"),
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
            patch("backend.services.file_download_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_download_workflow.update_task") as update_task,
            patch("backend.services.file_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_workflow.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_download_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_download_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_download_workflow.update_task") as update_task,
            patch("backend.services.file_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_workflow.is_task_stopped", side_effect=[False, False, True]),
            patch("backend.services.file_download_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_download_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_download_workflow.update_task") as update_task,
            patch("backend.services.file_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_download_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_download_workflow._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_download_workflow.update_task") as update_task,
            patch("backend.services.file_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_workflow.is_task_stopped", return_value=True),
            patch("backend.services.file_download_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_download_records_workflow._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_download_records_workflow._load_download_file_records") as load_records,
            patch("backend.services.file_download_records_workflow._run_download_records") as run_download_records,
            patch("backend.services.file_download_records_workflow.update_task") as update_task,
            patch("backend.services.file_download_records_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_records_workflow.is_task_stopped", return_value=True),
            patch("backend.services.file_download_records_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_download_records_workflow._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_download_records_workflow._load_filtered_download_file_records") as load_records,
            patch("backend.services.file_download_records_workflow._run_download_records") as run_download_records,
            patch("backend.services.file_download_records_workflow.update_task") as update_task,
            patch("backend.services.file_download_records_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_records_workflow.is_task_stopped", return_value=True),
            patch("backend.services.file_download_records_workflow._safe_remove_file_downloader") as safe_remove,
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
        records = [DownloadFileRecord(101, "Report.pdf", 123, 7)]

        with (
            patch("backend.services.file_download_records_workflow._create_file_downloader", return_value=downloader),
            patch(
                "backend.services.file_download_records_workflow._load_download_file_records",
                return_value=DownloadFileSelection(records, [], len(records)),
            ),
            patch("backend.services.file_download_records_workflow._run_download_records") as run_download_records,
            patch("backend.services.file_download_records_workflow.update_task") as update_task,
            patch("backend.services.file_download_records_workflow.add_task_log"),
            patch("backend.services.file_download_records_workflow.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_download_records_workflow._safe_remove_file_downloader") as safe_remove,
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
        records = [DownloadFileRecord(101, "Report.pdf", 123, 7)]

        with (
            patch("backend.services.file_download_records_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_download_records_workflow._load_filtered_download_file_records", return_value=records),
            patch("backend.services.file_download_records_workflow._run_download_records") as run_download_records,
            patch("backend.services.file_download_records_workflow.update_task") as update_task,
            patch("backend.services.file_download_records_workflow.add_task_log"),
            patch("backend.services.file_download_records_workflow.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_download_records_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_download_records_workflow._create_file_downloader", return_value=downloader),
            patch(
                "backend.services.file_download_records_workflow._load_download_file_records",
                return_value=DownloadFileSelection([], [101, 102], 2),
            ),
            patch("backend.services.file_download_records_workflow._run_download_records") as run_download_records,
            patch("backend.services.file_download_records_workflow.update_task") as update_task,
            patch("backend.services.file_download_records_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_records_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_download_records_workflow._safe_remove_file_downloader") as safe_remove,
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
            patch("backend.services.file_download_records_workflow._create_file_downloader", return_value=downloader),
            patch("backend.services.file_download_records_workflow._load_filtered_download_file_records", return_value=[]),
            patch("backend.services.file_download_records_workflow._run_download_records") as run_download_records,
            patch("backend.services.file_download_records_workflow.update_task") as update_task,
            patch("backend.services.file_download_records_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_download_records_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_download_records_workflow._safe_remove_file_downloader") as safe_remove,
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
        records = [DownloadFileRecord(101, "Report.pdf", 123, 7)]
        stats = _build_download_task_stats(total_files=1, found=1)

        with (
            patch("backend.services.file_download_records_workflow._run_download_records") as run_download_records,
            patch("backend.services.file_download_records_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_download_records_workflow.update_task") as update_task,
        ):
            _complete_download_records_task("task-1", downloader, records, stats, "下载完成")

        run_download_records.assert_called_once_with("task-1", downloader, records, stats)
        update_task.assert_called_once_with("task-1", "completed", "下载完成", {"downloaded_files": stats})

    def test_complete_download_records_task_skips_completion_when_stopped_after_records(self):
        downloader = object()
        records = [DownloadFileRecord(101, "Report.pdf", 123, 7)]
        stats = _build_download_task_stats(total_files=1, found=1)

        with (
            patch("backend.services.file_download_records_workflow._run_download_records") as run_download_records,
            patch("backend.services.file_download_records_workflow.is_task_stopped", return_value=True),
            patch("backend.services.file_download_records_workflow.update_task") as update_task,
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
            DownloadFileRecord(101, "First.pdf", 123, 7),
            DownloadFileRecord(102, "Second.pdf", 456, 0),
            DownloadFileRecord(103, "Third.pdf", 789, 2),
        ]
        stats = _build_download_task_stats(total_files=3, found=3)

        with (
            patch("backend.services.file_download_records_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_download_records_workflow.add_task_log") as add_task_log,
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
            DownloadFileRecord(101, "First.pdf", 123, 7),
            DownloadFileRecord(102, "Second.pdf", 456, 0),
        ]
        stats = _build_download_task_stats(total_files=2, found=2)

        with (
            patch("backend.services.file_download_records_workflow.is_task_stopped", side_effect=[False, True]),
            patch("backend.services.file_download_records_workflow.add_task_log") as add_task_log,
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
            patch("backend.services.file_topic_sync_workflow.ZSXQDatabase", return_value=topics_db) as create_db,
            patch("backend.services.file_topic_sync_workflow.update_task") as update_task,
            patch("backend.services.file_topic_sync_workflow.add_task_log"),
            patch("backend.services.file_topic_sync_workflow.is_task_stopped", return_value=False),
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
            patch("backend.services.file_topic_sync_workflow.ZSXQDatabase") as create_db,
            patch("backend.services.file_topic_sync_workflow.update_task") as update_task,
            patch("backend.services.file_topic_sync_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_topic_sync_workflow.is_task_stopped", return_value=True),
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
            patch("backend.services.file_topic_sync_workflow.ZSXQDatabase", return_value=topics_db),
            patch("backend.services.file_topic_sync_workflow.update_task") as update_task,
            patch("backend.services.file_topic_sync_workflow.add_task_log"),
            patch("backend.services.file_topic_sync_workflow.is_task_stopped", side_effect=[False, True]),
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

        self.assertEqual([(123, "123")], downloader.file_db.record_calls)
        self.assertEqual([], downloader.file_db.cursor.executed)
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
            patch("backend.services.file_single_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_single_download_workflow.update_task") as update_task,
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
            patch("backend.services.file_single_download_workflow._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_single_download_workflow.update_task") as update_task,
            patch("backend.services.file_single_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_single_download_workflow.is_task_stopped", return_value=True),
            patch("backend.services.file_single_download_workflow._safe_remove_file_downloader") as safe_remove,
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
                self.file_db = fake_zsxq_file_db(FakeCursor())

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
                self.file_db = fake_zsxq_file_db(FakeCursor())

        downloader = FakeDownloader()

        records = _load_filtered_download_file_records(downloader, "123", status="completed")

        query, params = downloader.file_db.cursor.executed[0]
        self.assertIn("f.download_status IN (?, ?, ?)", query)
        self.assertNotIn("f.download_status NOT IN", query)
        self.assertNotIn("LIMIT ?", query)
        self.assertEqual((123, "completed", "downloaded", "skipped"), params)
        self.assertEqual([(101, "Report.PDF", 123, 7)], records)

    def test_load_filtered_download_file_records_keeps_all_status_and_zero_limit_shape(self):
        class FakeCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchall(self):
                return []

        class FakeDownloader:
            def __init__(self):
                self.file_db = fake_zsxq_file_db(FakeCursor())

        downloader = FakeDownloader()

        records = _load_filtered_download_file_records(
            downloader,
            "123",
            status=" all ",
            max_files=0,
        )

        query, params = downloader.file_db.cursor.executed[0]
        self.assertIn("(f.download_status IS NULL OR f.download_status NOT IN (?, ?, ?))", query)
        self.assertNotIn("f.download_status IN (?, ?, ?)", query)
        self.assertNotIn("LIMIT ?", query)
        self.assertEqual((123, "completed", "downloaded", "skipped"), params)
        self.assertEqual([], records)

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
                self.file_db = fake_zsxq_file_db(FakeCursor())

        downloader = FakeDownloader()

        selection = _load_download_file_records(downloader, "123", [101, 102, 101, 999])

        query, params = downloader.file_db.cursor.executed[0]
        self.assertIn("WHERE group_id = ? AND file_id IN (?, ?, ?)", " ".join(query.split()))
        self.assertEqual((123, 101, 102, 999), params)
        self.assertEqual(
            [
                (101, "Report.PDF", 123, 7),
                (102, "file_102", 0, 0),
            ],
            selection.records,
        )
        self.assertEqual([999], selection.missing)
        self.assertEqual(3, selection.requested_count)

    def test_load_download_file_records_keeps_empty_selection_query_shape(self):
        class FakeCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql, params=()):
                self.executed.append((sql, params))

            def fetchall(self):
                return []

        class FakeDownloader:
            def __init__(self):
                self.file_db = fake_zsxq_file_db(FakeCursor())

        downloader = FakeDownloader()

        selection = _load_download_file_records(downloader, "123", [])

        query, params = downloader.file_db.cursor.executed[0]
        self.assertIn(
            "WHERE group_id = ? AND file_id IN ()",
            " ".join(query.split()),
        )
        self.assertEqual((123,), params)
        self.assertEqual([], selection.records)
        self.assertEqual([], selection.missing)
        self.assertEqual(0, selection.requested_count)

    def test_unique_int_file_ids_preserves_existing_selected_download_semantics(self):
        self.assertEqual([101, 102, 999], _unique_int_file_ids(["101", 102, "101", 999]))

    def test_close_crawler_file_databases_closes_file_and_topic_dbs(self):
        crawler = FakeCrawler()

        _close_crawler_file_databases(crawler)

        self.assertTrue(crawler.downloader.file_db.closed)
        self.assertTrue(crawler.db.closed)

    def test_clear_group_file_data_uses_storage_interface(self):
        from backend.services import file_clear_workflow

        class FakeFileDb:
            last_instance = None

            def __init__(self, group_id):
                self.group_id = group_id
                self.clear_calls = 0
                self.closed = False
                FakeFileDb.last_instance = self

            def clear_group_file_records(self):
                self.clear_calls += 1
                return {"files": 2}

            def close(self):
                self.closed = True

        with patch("backend.services.file_clear_workflow.ZSXQFileDatabase", FakeFileDb):
            result = file_clear_workflow._clear_group_file_data("group-1")

        self.assertEqual({"files": 2}, result)
        self.assertEqual("group-1", FakeFileDb.last_instance.group_id)
        self.assertEqual(1, FakeFileDb.last_instance.clear_calls)
        self.assertTrue(FakeFileDb.last_instance.closed)

    def test_clear_file_database_does_not_construct_legacy_crawler(self):
        from backend.services.file_read_model import clear_file_database_response

        with (
            patch("backend.services.file_clear_workflow._clear_group_file_data", return_value={"files": 0}) as clear_data,
            patch("backend.core.crawler_runtime.get_crawler_for_group", side_effect=AssertionError("legacy crawler used")),
        ):
            response = clear_file_database_response("group-1")

        clear_data.assert_called_once_with("group-1")
        self.assertEqual({"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 0}}, response)

    def test_clear_file_database_clears_image_cache_and_logs_success(self):
        from backend.services.file_read_model import clear_file_database_response

        cache_manager = FakeImageCacheManager((True, "已删除 2 个缓存文件"))

        with (
            patch("backend.services.file_clear_workflow._clear_group_file_data", return_value={"files": 1}),
            patch("backend.core.image_cache_manager.get_image_cache_manager", return_value=cache_manager) as get_cache,
            patch("backend.core.image_cache_manager.clear_group_cache_manager") as clear_group_cache,
            patch("backend.services.file_clear_workflow._log_file_route_event") as log_file_route_event,
        ):
            response = clear_file_database_response("group-1")

        get_cache.assert_called_once_with("group-1")
        self.assertEqual(1, cache_manager.clear_calls)
        clear_group_cache.assert_called_once_with("group-1")
        log_file_route_event.assert_called_once_with("INFO", "图片缓存已清空: 已删除 2 个缓存文件")
        self.assertEqual({"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 1}}, response)

    def test_clear_file_database_logs_image_cache_clear_failure_but_keeps_response(self):
        from backend.services.file_read_model import clear_file_database_response

        cache_manager = FakeImageCacheManager((False, "permission denied"))

        with (
            patch("backend.services.file_clear_workflow._clear_group_file_data", return_value={"files": 1}),
            patch("backend.core.image_cache_manager.get_image_cache_manager", return_value=cache_manager),
            patch("backend.core.image_cache_manager.clear_group_cache_manager") as clear_group_cache,
            patch("backend.services.file_clear_workflow._log_file_route_event") as log_file_route_event,
        ):
            response = clear_file_database_response("group-1")

        self.assertEqual(1, cache_manager.clear_calls)
        clear_group_cache.assert_called_once_with("group-1")
        log_file_route_event.assert_called_once_with("WARN", "清空图片缓存失败: permission denied")
        self.assertEqual({"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 1}}, response)

    def test_clear_file_database_logs_image_cache_exception_but_keeps_response(self):
        from backend.services.file_read_model import clear_file_database_response

        with (
            patch("backend.services.file_clear_workflow._clear_group_file_data", return_value={"files": 1}),
            patch("backend.core.image_cache_manager.get_image_cache_manager", side_effect=RuntimeError("cache boom")),
            patch("backend.core.image_cache_manager.clear_group_cache_manager") as clear_group_cache,
            patch("backend.services.file_clear_workflow._log_file_route_event") as log_file_route_event,
        ):
            response = clear_file_database_response("group-1")

        clear_group_cache.assert_not_called()
        log_file_route_event.assert_called_once_with("WARN", "清空图片缓存时出错: cache boom")
        self.assertEqual({"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 1}}, response)

    def test_query_group_id_casts_numeric_ids_for_sql_filters(self):
        self.assertEqual(123, _query_group_id("123"))
        self.assertEqual("abc", _query_group_id("abc"))

    def test_add_file_search_condition_skips_blank_search_without_mutation(self):
        conditions = ["f.group_id = ?"]
        params = [123]

        _add_file_search_condition(conditions, params, "   ")

        self.assertEqual(["f.group_id = ?"], conditions)
        self.assertEqual([123], params)

    def test_add_file_search_condition_trims_lowercases_and_adds_eight_params(self):
        conditions = ["f.group_id = ?"]
        params = [123]

        _add_file_search_condition(conditions, params, " Foo ")

        self.assertEqual(2, len(conditions))
        self.assertIn("LOWER(COALESCE(f.name, '')) LIKE ?", conditions[1])
        self.assertIn("FROM file_topic_relations fr", conditions[1])
        self.assertIn("FROM topic_files tf", conditions[1])
        self.assertEqual([123, *["%foo%"] * 8], params)

    def _run_async(self, coro):
        import asyncio

        return asyncio.run(coro)

    def _run_single_file_download_case(self, downloader, file_name=None, file_size=None):
        from backend.services.file_workflow_service import run_single_file_download_task_with_info

        with (
            patch("backend.services.file_single_download_workflow._create_file_downloader", return_value=downloader) as create_downloader,
            patch("backend.services.file_single_download_workflow.update_task") as update_task,
            patch("backend.services.file_single_download_workflow.add_task_log") as add_task_log,
            patch("backend.services.file_single_download_workflow.is_task_stopped", return_value=False),
            patch("backend.services.file_single_download_workflow._safe_remove_file_downloader") as safe_remove,
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
