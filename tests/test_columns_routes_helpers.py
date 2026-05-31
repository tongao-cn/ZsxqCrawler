import asyncio
import unittest
from importlib.util import find_spec
from unittest.mock import AsyncMock, patch

HAS_COLUMNS_ROUTE_DEPS = (
    find_spec("fastapi") is not None
    and find_spec("loguru") is not None
    and find_spec("requests") is not None
)


class FakeColumnsDb:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


class FakeImageCacheManager:
    def __init__(self, result):
        self.result = result

    def download_and_cache(self, url):
        return self.result


class FakeColumnsDbWithImages:
    def __init__(self):
        self.updated_images = []
        self.updated_video_covers = []

    def update_image_local_path(self, image_id, local_path):
        self.updated_images.append((image_id, local_path))

    def update_video_cover_path(self, video_id, local_path):
        self.updated_video_covers.append((video_id, local_path))


class FakeColumnsDbWithDetails:
    def __init__(self):
        self.inserted_details = []

    def insert_topic_detail(self, group_id, topic_data, raw_json):
        self.inserted_details.append((group_id, topic_data, raw_json))


class FakeColumnsDbForTopicPrep:
    def __init__(self, exists=False):
        self.exists = exists
        self.inserted_topics = []

    def insert_column_topic(self, column_id, group_id, topic):
        self.inserted_topics.append((column_id, group_id, topic))

    def topic_detail_exists(self, topic_id):
        return self.exists


class FakeColumnsDbForColumn:
    def __init__(self):
        self.inserted_columns = []

    def insert_column(self, group_id, column):
        self.inserted_columns.append((group_id, column))


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args):
        self.tasks.append((func, args))


class ColumnsRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_resolve_columns_fetch_config_applies_defaults_and_overrides(self):
        from backend.routes.columns_routes import ColumnsSettingsRequest, _resolve_columns_fetch_config

        default_config = _resolve_columns_fetch_config(ColumnsSettingsRequest())
        self.assertEqual(2.0, default_config["crawl_interval_min"])
        self.assertTrue(default_config["download_files"])
        self.assertFalse(default_config["incremental_mode"])

        override_config = _resolve_columns_fetch_config(
            ColumnsSettingsRequest(
                crawlIntervalMin=3.0,
                downloadFiles=False,
                downloadVideos=False,
                cacheImages=False,
                incrementalMode=True,
            )
        )

        self.assertEqual(3.0, override_config["crawl_interval_min"])
        self.assertFalse(override_config["download_files"])
        self.assertFalse(override_config["download_videos"])
        self.assertFalse(override_config["cache_images"])
        self.assertTrue(override_config["incremental_mode"])

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_build_columns_fetch_result_includes_skip_summary(self):
        from backend.routes.columns_routes import _build_columns_fetch_result

        message, payload = _build_columns_fetch_result(2, 5, 4, 3, 6, 1, 7, 8, 9)

        self.assertEqual("采集完成: 2 个专栏, 4 篇新文章, 3 个文件, 1 个视频, 跳过 7 篇已存在文章", message)
        self.assertEqual(
            {
                "columns_count": 2,
                "topics_count": 5,
                "details_count": 4,
                "files_count": 3,
                "images_count": 6,
                "videos_count": 1,
                "skipped_count": 7,
                "files_skipped": 8,
                "videos_skipped": 9,
            },
            payload,
        )

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_create_columns_fetch_task_response_creates_ingestion_task(self):
        from backend.routes.columns_routes import ColumnsSettingsRequest, _create_columns_fetch_task_response, _fetch_columns_task

        background_tasks = FakeBackgroundTasks()
        request = ColumnsSettingsRequest()

        with (
            patch("backend.routes.columns_routes.create_ingestion_task_or_raise", return_value="task-1") as create_task,
            patch("backend.routes.columns_routes.update_task") as update_task,
            patch("backend.routes.columns_routes.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _create_columns_fetch_task_response(background_tasks, "123", request)

        create_task.assert_called_once_with("columns_fetch", "采集专栏内容 (群组: 123)", "123")
        update_task.assert_called_once_with("task-1", "running", "正在采集专栏内容...")
        self.assertEqual(
            {"success": True, "task_id": "task-1", "message": "专栏采集任务已启动"},
            response,
        )
        enqueue_runtime_task.assert_called_once_with(_fetch_columns_task, "task-1", "123", request)
        self.assertEqual([], background_tasks.tasks)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_create_columns_fetch_task_response_rejects_ingestion_conflict(self):
        from fastapi import HTTPException
        from backend.routes.columns_routes import ColumnsSettingsRequest, _create_columns_fetch_task_response

        background_tasks = FakeBackgroundTasks()
        conflict = HTTPException(
            status_code=409,
            detail={
                "message": "该群组已有采集或同步任务正在运行",
                "task_id": "task-old",
                "type": "crawl_latest_until_complete",
                "status": "running",
            },
        )

        with (
            patch("backend.routes.columns_routes.create_ingestion_task_or_raise", side_effect=conflict),
            patch("backend.routes.columns_routes.update_task") as update_task,
        ):
            with self.assertRaises(HTTPException) as raised:
                _create_columns_fetch_task_response(background_tasks, "123", ColumnsSettingsRequest())

        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual(
            {
                "message": "该群组已有采集或同步任务正在运行",
                "task_id": "task-old",
                "type": "crawl_latest_until_complete",
                "status": "running",
            },
            raised.exception.detail,
        )
        self.assertEqual([], background_tasks.tasks)
        update_task.assert_not_called()

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_complete_empty_columns_task_logs_and_updates_task(self):
        from backend.routes.columns_routes import _complete_empty_columns_task

        with (
            patch("backend.routes.columns_routes.add_task_log") as add_log,
            patch("backend.routes.columns_routes.update_task") as update,
        ):
            _complete_empty_columns_task("task-1")

        add_log.assert_called_once_with("task-1", "ℹ️ 该群组没有专栏内容")
        update.assert_called_once_with("task-1", "completed", "该群组没有专栏内容")

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_get_column_topic_full_comments_runs_service_in_thread(self):
        from backend.routes import columns_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"success": True, "comments": [], "total": 0}

        with patch("backend.routes.columns_routes.asyncio.to_thread", side_effect=fake_to_thread):
            result = asyncio.run(columns_routes.get_column_topic_full_comments("123", 456))

        self.assertEqual({"success": True, "comments": [], "total": 0}, result)
        self.assertEqual([(columns_routes._service_fetch_column_topic_full_comments, ("123", 456))], calls)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_save_topic_detail_inserts_topic_with_unescaped_json(self):
        from backend.routes.columns_routes import _save_topic_detail

        db = FakeColumnsDbWithDetails()
        topic_detail = {"succeeded": True, "resp_data": {"topic": {"topic_id": 10, "title": "中文标题"}}}

        saved = _save_topic_detail(db, "123", topic_detail)

        self.assertTrue(saved)
        self.assertEqual(1, len(db.inserted_details))
        group_id, topic_data, raw_json = db.inserted_details[0]
        self.assertEqual(123, group_id)
        self.assertEqual(topic_detail["resp_data"]["topic"], topic_data)
        self.assertIn("中文标题", raw_json)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_save_topic_detail_returns_false_without_topic_data(self):
        from backend.routes.columns_routes import _save_topic_detail

        db = FakeColumnsDbWithDetails()

        self.assertFalse(_save_topic_detail(db, "123", {"succeeded": True, "resp_data": {}}))
        self.assertEqual([], db.inserted_details)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_build_columns_progress_message(self):
        from backend.routes.columns_routes import _build_columns_progress_message

        self.assertEqual(
            "进度: 4 篇文章, 3 个文件, 2 个视频, 1 张图片",
            _build_columns_progress_message(4, 3, 2, 1),
        )

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_prepare_column_topic_inserts_and_marks_existing_topic_skipped(self):
        from backend.routes.columns_routes import _prepare_column_topic

        db = FakeColumnsDbForTopicPrep(exists=True)
        topic = {"topic_id": 10, "title": "一篇很长的文章标题"}

        with patch("backend.routes.columns_routes.add_task_log") as add_log:
            topic_id, topic_title, skipped = _prepare_column_topic("task-1", db, 3, "123", topic, 1, 2, True)

        self.assertEqual(10, topic_id)
        self.assertEqual("一篇很长的文章标题", topic_title)
        self.assertTrue(skipped)
        self.assertEqual([(3, 123, topic)], db.inserted_topics)
        add_log.assert_called_once_with("task-1", "   📄 [1/2] 一篇很长的文章标题... ⏭️ 跳过（已存在）")

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_process_topic_resources_aggregates_helper_counts(self):
        from backend.routes.columns_routes import ColumnsSettingsRequest, _process_topic_resources, _resolve_columns_fetch_config

        config = _resolve_columns_fetch_config(ColumnsSettingsRequest())
        video = {"video_id": 7, "size": 1024, "duration": 30, "cover": {"url": "cover"}}

        with (
            patch("backend.routes.columns_routes._download_topic_files", return_value=(1, 2, 3)),
            patch("backend.routes.columns_routes._cache_topic_images", return_value=4),
            patch("backend.routes.columns_routes._get_topic_video", return_value=video),
            patch("backend.routes.columns_routes._cache_video_cover"),
            patch("backend.routes.columns_routes._download_topic_video", return_value=(5, 6, 7)),
            patch("backend.routes.columns_routes.add_task_log"),
        ):
            stats = asyncio.run(_process_topic_resources("task-1", "123", 10, {}, object(), {}, 0, config))

        self.assertEqual(1, stats.files_count)
        self.assertEqual(2, stats.files_skipped)
        self.assertEqual(4, stats.images_count)
        self.assertEqual(5, stats.videos_count)
        self.assertEqual(6, stats.videos_skipped)
        self.assertEqual(10, stats.request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_process_column_topic_returns_skip_counts_for_existing_topic(self):
        from backend.routes.columns_routes import ColumnsSettingsRequest, _process_column_topic, _resolve_columns_fetch_config

        config = _resolve_columns_fetch_config(ColumnsSettingsRequest(incrementalMode=True))

        with patch("backend.routes.columns_routes._prepare_column_topic", return_value=(10, "title", True)):
            stats = asyncio.run(_process_column_topic("task-1", "123", 3, {}, 1, 2, object(), {}, 0, config))

        self.assertEqual(1, stats.topics_count)
        self.assertEqual(1, stats.skipped_count)
        self.assertEqual(0, stats.request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_process_column_topic_aggregates_detail_and_resource_counts(self):
        from backend.routes.columns_routes import ColumnFetchStats, ColumnsSettingsRequest, _process_column_topic, _resolve_columns_fetch_config

        config = _resolve_columns_fetch_config(ColumnsSettingsRequest())
        topic_detail = {"succeeded": True, "resp_data": {"topic": {"topic_id": 10}}}

        with (
            patch("backend.routes.columns_routes._prepare_column_topic", return_value=(10, "title", False)),
            patch("backend.routes.columns_routes._fetch_topic_detail", return_value=(topic_detail, 1)),
            patch("backend.routes.columns_routes._save_topic_detail", return_value=True),
            patch("backend.routes.columns_routes._process_topic_resources", return_value=ColumnFetchStats(files_count=2, files_skipped=3, images_count=4, videos_count=5, videos_skipped=6, request_count=7)),
        ):
            stats = asyncio.run(_process_column_topic("task-1", "123", 3, {}, 1, 2, object(), {}, 0, config))

        self.assertEqual(1, stats.topics_count)
        self.assertEqual(1, stats.details_count)
        self.assertEqual(2, stats.files_count)
        self.assertEqual(4, stats.images_count)
        self.assertEqual(5, stats.videos_count)
        self.assertEqual(3, stats.files_skipped)
        self.assertEqual(6, stats.videos_skipped)
        self.assertEqual(8, stats.request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_process_column_aggregates_topics_and_requests(self):
        from backend.routes.columns_routes import ColumnFetchStats, ColumnsSettingsRequest, _process_column, _resolve_columns_fetch_config

        config = _resolve_columns_fetch_config(ColumnsSettingsRequest())
        column = {"column_id": 3, "name": "专栏", "statistics": {"topics_count": 2}}
        topics = [{"topic_id": 10}, {"topic_id": 11}]
        db = FakeColumnsDbForColumn()

        with (
            patch("backend.routes.columns_routes.random.uniform", return_value=0),
            patch("backend.routes.columns_routes.asyncio.sleep", new_callable=AsyncMock),
            patch("backend.routes.columns_routes.add_task_log"),
            patch("backend.routes.columns_routes._fetch_column_topics", return_value=(topics, 1)),
            patch("backend.routes.columns_routes.is_task_stopped", return_value=False),
            patch("backend.routes.columns_routes._process_column_topic", side_effect=[
                ColumnFetchStats(topics_count=1, details_count=1, files_count=2, images_count=3, videos_count=4, files_skipped=5, videos_skipped=6, request_count=7),
                ColumnFetchStats(topics_count=1, skipped_count=1, request_count=2),
            ]),
            patch("backend.routes.columns_routes.update_task") as update_task,
        ):
            stats = asyncio.run(
                _process_column(
                    "task-1",
                    "123",
                    column,
                    1,
                    1,
                    db,
                    {},
                    0,
                    config,
                    base_stats=ColumnFetchStats(details_count=10, files_count=20, images_count=30, videos_count=40),
                )
            )

        self.assertEqual([(123, column)], db.inserted_columns)
        self.assertEqual(1, stats.columns_count)
        self.assertEqual(2, stats.topics_count)
        self.assertEqual(1, stats.details_count)
        self.assertEqual(2, stats.files_count)
        self.assertEqual(3, stats.images_count)
        self.assertEqual(4, stats.videos_count)
        self.assertEqual(1, stats.skipped_count)
        self.assertEqual(5, stats.files_skipped)
        self.assertEqual(6, stats.videos_skipped)
        self.assertEqual(10, stats.request_count)
        update_task.assert_called_once_with(
            "task-1",
            "running",
            "进度: 11 篇文章, 22 个文件, 44 个视频, 33 张图片",
        )

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_columns_db_closes_database(self):
        from backend.routes.columns_routes import _columns_db

        fake_db = FakeColumnsDb()

        with patch("backend.routes.columns_routes.get_columns_db", return_value=fake_db):
            with _columns_db("123") as db:
                self.assertIs(fake_db, db)
                self.assertFalse(fake_db.closed)

        self.assertTrue(fake_db.closed)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_fetch_columns_catalog_returns_columns_and_request_count(self):
        from backend.routes.columns_routes import _fetch_columns_catalog

        payload = {
            "succeeded": True,
            "resp_data": {"columns": [{"column_id": 1, "name": "专栏"}]},
        }

        with (
            patch("backend.routes.columns_routes.requests.get", return_value=FakeResponse(payload)),
            patch("backend.routes.columns_routes.is_task_stopped", return_value=False),
            patch("backend.routes.columns_routes.add_task_log"),
        ):
            columns, request_count = asyncio.run(_fetch_columns_catalog("task-1", "123", {"Cookie": "c"}))

        self.assertEqual(payload["resp_data"]["columns"], columns)
        self.assertEqual(1, request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_fetch_columns_catalog_retries_anti_crawl_response(self):
        from backend.routes.columns_routes import _fetch_columns_catalog

        anti_crawl = FakeResponse({"succeeded": False, "code": 1059, "error_message": "retry"})
        success = FakeResponse({"succeeded": True, "resp_data": {"columns": []}})

        with (
            patch("backend.routes.columns_routes.requests.get", side_effect=[anti_crawl, success]),
            patch("backend.routes.columns_routes.is_task_stopped", return_value=False),
            patch("backend.routes.columns_routes.add_task_log"),
            patch("backend.routes.columns_routes.asyncio.sleep", new_callable=AsyncMock),
        ):
            columns, request_count = asyncio.run(_fetch_columns_catalog("task-1", "123", {"Cookie": "c"}))

        self.assertEqual([], columns)
        self.assertEqual(2, request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_fetch_column_topics_returns_topics_and_request_count(self):
        from backend.routes.columns_routes import _fetch_column_topics

        payload = {
            "succeeded": True,
            "resp_data": {"topics": [{"topic_id": 10, "title": "文章"}]},
        }

        with (
            patch("backend.routes.columns_routes.requests.get", return_value=FakeResponse(payload)),
            patch("backend.routes.columns_routes.add_task_log"),
        ):
            topics, request_count = _fetch_column_topics("task-1", 1, "https://example.test/topics", {})

        self.assertEqual(payload["resp_data"]["topics"], topics)
        self.assertEqual(1, request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_fetch_column_topics_returns_none_on_http_error(self):
        from backend.routes.columns_routes import _fetch_column_topics

        with (
            patch("backend.routes.columns_routes.requests.get", return_value=FakeResponse({}, status_code=500, text="bad")),
            patch("backend.routes.columns_routes.add_task_log"),
            patch("backend.routes.columns_routes.log_error"),
        ):
            topics, request_count = _fetch_column_topics("task-1", 1, "https://example.test/topics", {})

        self.assertIsNone(topics)
        self.assertEqual(1, request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_fetch_topic_detail_returns_detail_and_request_count(self):
        from backend.routes.columns_routes import _fetch_topic_detail

        payload = {"succeeded": True, "resp_data": {"topic": {"topic_id": 10}}}

        with (
            patch("backend.routes.columns_routes.requests.get", return_value=FakeResponse(payload)),
            patch("backend.routes.columns_routes.is_task_stopped", return_value=False),
            patch("backend.routes.columns_routes.random.uniform", return_value=0),
            patch("backend.routes.columns_routes.asyncio.sleep", new_callable=AsyncMock),
        ):
            detail, request_count = asyncio.run(
                _fetch_topic_detail("task-1", 10, {}, 0, 10, 30.0, 60.0, 2.0, 5.0)
            )

        self.assertEqual(payload, detail)
        self.assertEqual(1, request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_fetch_topic_detail_retries_http_error(self):
        from backend.routes.columns_routes import _fetch_topic_detail

        success_payload = {"succeeded": True, "resp_data": {"topic": {"topic_id": 10}}}

        with (
            patch(
                "backend.routes.columns_routes.requests.get",
                side_effect=[FakeResponse({}, status_code=500, text="bad"), FakeResponse(success_payload)],
            ),
            patch("backend.routes.columns_routes.is_task_stopped", return_value=False),
            patch("backend.routes.columns_routes.add_task_log"),
            patch("backend.routes.columns_routes.log_error"),
            patch("backend.routes.columns_routes.random.uniform", return_value=0),
            patch("backend.routes.columns_routes.asyncio.sleep", new_callable=AsyncMock),
        ):
            detail, request_count = asyncio.run(
                _fetch_topic_detail("task-1", 10, {}, 0, 10, 30.0, 60.0, 2.0, 5.0)
            )

        self.assertEqual(success_payload, detail)
        self.assertEqual(2, request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_collect_topic_files_includes_content_voice(self):
        from backend.routes.columns_routes import _collect_topic_files

        file_info = {"file_id": 1, "name": "file.pdf"}
        voice_info = {"file_id": 2, "name": "voice.m4a"}

        files = _collect_topic_files({"talk": {"files": [file_info]}, "content_voice": voice_info})

        self.assertEqual([file_info, voice_info], files)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_download_topic_files_counts_downloaded_and_skipped_files(self):
        from backend.routes.columns_routes import _download_topic_files

        topic_detail = {
            "talk": {
                "files": [
                    {"file_id": 1, "name": "downloaded.pdf", "size": 10},
                    {"file_id": 2, "name": "skipped.pdf", "size": 20},
                ]
            }
        }

        with (
            patch("backend.routes.columns_routes._download_column_file", side_effect=["downloaded", "skipped"]),
            patch("backend.routes.columns_routes.is_task_stopped", return_value=False),
            patch("backend.routes.columns_routes.add_task_log"),
            patch("backend.routes.columns_routes.random.uniform", return_value=0),
            patch("backend.routes.columns_routes.asyncio.sleep", new_callable=AsyncMock),
        ):
            downloaded, skipped, request_count = asyncio.run(
                _download_topic_files("task-1", "123", 10, topic_detail, object(), {}, 0, 10, 30.0, 60.0, 2.0, 5.0)
            )

        self.assertEqual(1, downloaded)
        self.assertEqual(1, skipped)
        self.assertEqual(1, request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_cache_topic_images_updates_local_paths(self):
        from backend.routes.columns_routes import _cache_topic_images

        db = FakeColumnsDbWithImages()
        topic_detail = {
            "talk": {
                "images": [
                    {"image_id": 1, "original": {"url": "https://example.test/image.jpg"}},
                    {"image_id": 2, "original": {}},
                ]
            }
        }

        with (
            patch("backend.routes.columns_routes.get_image_cache_manager", return_value=FakeImageCacheManager((True, "local.jpg", None))),
            patch("backend.routes.columns_routes.is_task_stopped", return_value=False),
        ):
            cached_count = _cache_topic_images("task-1", "123", topic_detail, db)

        self.assertEqual(1, cached_count)
        self.assertEqual([(1, "local.jpg")], db.updated_images)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_get_topic_video_returns_video_with_id(self):
        from backend.routes.columns_routes import _get_topic_video

        video = {"video_id": 7, "size": 1024}

        self.assertEqual(video, _get_topic_video({"talk": {"video": video}}))
        self.assertIsNone(_get_topic_video({"talk": {"video": {"size": 1024}}}))
        self.assertIsNone(_get_topic_video({}))

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_cache_video_cover_updates_local_path(self):
        from backend.routes.columns_routes import _cache_video_cover

        db = FakeColumnsDbWithImages()

        with (
            patch("backend.routes.columns_routes.get_image_cache_manager", return_value=FakeImageCacheManager((True, "cover.jpg", None))),
            patch("backend.routes.columns_routes.add_task_log"),
        ):
            cached = _cache_video_cover("task-1", "123", 7, "https://example.test/cover.jpg", db)

        self.assertTrue(cached)
        self.assertEqual([(7, "cover.jpg")], db.updated_video_covers)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_download_topic_video_counts_downloaded_result(self):
        from backend.routes.columns_routes import _download_topic_video

        video = {"video_id": 7, "size": 1024, "duration": 30}

        with (
            patch("backend.routes.columns_routes._download_column_video", return_value="downloaded"),
            patch("backend.routes.columns_routes.add_task_log"),
            patch("backend.routes.columns_routes.random.uniform", return_value=0),
            patch("backend.routes.columns_routes.asyncio.sleep", new_callable=AsyncMock),
        ):
            downloaded, skipped, request_count = asyncio.run(
                _download_topic_video("task-1", "123", 10, video, object(), {}, 0, 10, 30.0, 60.0, 2.0, 5.0)
            )

        self.assertEqual(1, downloaded)
        self.assertEqual(0, skipped)
        self.assertEqual(1, request_count)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_download_topic_video_counts_skipped_result(self):
        from backend.routes.columns_routes import _download_topic_video

        video = {"video_id": 7, "size": 1024, "duration": 30}

        with (
            patch("backend.routes.columns_routes._download_column_video", return_value="skipped"),
            patch("backend.routes.columns_routes.random.uniform", return_value=0),
            patch("backend.routes.columns_routes.asyncio.sleep", new_callable=AsyncMock),
        ):
            downloaded, skipped, request_count = asyncio.run(
                _download_topic_video("task-1", "123", 10, video, object(), {}, 0, 10, 30.0, 60.0, 2.0, 5.0)
            )

        self.assertEqual(0, downloaded)
        self.assertEqual(1, skipped)
        self.assertEqual(0, request_count)


if __name__ == "__main__":
    unittest.main()
