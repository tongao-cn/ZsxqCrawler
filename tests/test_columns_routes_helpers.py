import asyncio
import unittest
from importlib.util import find_spec
from unittest.mock import patch

HAS_COLUMNS_ROUTE_DEPS = (
    find_spec("fastapi") is not None
    and find_spec("loguru") is not None
    and find_spec("requests") is not None
)


class ColumnsRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_columns_route_error_preserves_status_and_detail_format(self):
        from backend.routes.columns_routes import _columns_route_error

        error = _columns_route_error("获取专栏目录失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("获取专栏目录失败: boom", error.detail)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_resolve_columns_fetch_config_applies_defaults_and_overrides(self):
        from backend.routes.columns_routes import ColumnsSettingsRequest
        from backend.services.columns_fetch_summary import resolve_columns_fetch_config

        default_config = resolve_columns_fetch_config(ColumnsSettingsRequest())
        self.assertEqual(2.0, default_config["crawl_interval_min"])
        self.assertTrue(default_config["download_files"])
        self.assertFalse(default_config["incremental_mode"])

        override_config = resolve_columns_fetch_config(
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
    def test_create_columns_fetch_task_response_creates_ingestion_task(self):
        from backend.routes.columns_routes import ColumnsSettingsRequest, _create_columns_fetch_task_response

        request = ColumnsSettingsRequest()

        with patch(
            "backend.routes.columns_routes.create_columns_fetch_task",
            return_value={"success": True, "task_id": "task-1", "message": "专栏采集任务已启动"},
        ) as create_task:
            response = _create_columns_fetch_task_response("123", request)

        create_task.assert_called_once_with("123", request)
        self.assertEqual(
            {"success": True, "task_id": "task-1", "message": "专栏采集任务已启动"},
            response,
        )

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_create_columns_fetch_task_response_rejects_ingestion_conflict(self):
        from backend.services.task_launch import TaskLaunchConflict
        from backend.routes.columns_routes import ColumnsSettingsRequest, _create_columns_fetch_task_response

        existing = {
            "task_id": "task-old",
            "type": "crawl_latest_until_complete",
            "status": "running",
        }

        with patch(
            "backend.routes.columns_routes.create_columns_fetch_task",
            side_effect=TaskLaunchConflict(existing),
        ) as create_task:
            with self.assertRaises(TaskLaunchConflict) as raised:
                _create_columns_fetch_task_response("123", ColumnsSettingsRequest())

        create_task.assert_called_once()
        self.assertEqual(existing, raised.exception.existing)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_columns_route_error_maps_task_launch_conflict(self):
        from backend.routes.columns_routes import _columns_route_error
        from backend.services.task_launch import TaskLaunchConflict

        error = _columns_route_error(
            "启动专栏采集失败",
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

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_columns_read_routes_preserve_success_payloads(self):
        from backend.routes import columns_routes

        cases = [
            (
                "group_columns",
                columns_routes.get_group_columns,
                ("123",),
                columns_routes.get_group_columns_response,
                ("123",),
                {"columns": []},
            ),
            (
                "column_topics",
                columns_routes.get_column_topics,
                ("123", 456),
                columns_routes.get_column_topics_response,
                ("123", 456),
                {"topics": []},
            ),
            (
                "columns_stats",
                columns_routes.get_columns_stats,
                ("123",),
                columns_routes.get_columns_stats_response,
                ("123",),
                {"stats": {}},
            ),
            (
                "delete_all_columns",
                columns_routes.delete_all_columns,
                ("123",),
                columns_routes.delete_all_columns_response,
                ("123",),
                {"success": True},
            ),
        ]

        for case_name, route, route_args, service_func, service_args, payload in cases:
            with self.subTest(case_name=case_name):
                calls = []

                async def fake_to_thread(func, *args):
                    calls.append((func, args))
                    return payload

                with patch(
                    "backend.routes.columns_routes.asyncio.to_thread",
                    side_effect=fake_to_thread,
                ):
                    result = asyncio.run(route(*route_args))

                self.assertEqual(payload, result)
                self.assertEqual([(service_func, service_args)], calls)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_columns_read_routes_preserve_wrapped_unexpected_errors(self):
        from fastapi import HTTPException
        from backend.routes import columns_routes

        cases = [
            (
                "group_columns",
                columns_routes.get_group_columns,
                ("123",),
                "_group_columns",
                "获取专栏目录失败: boom",
            ),
            (
                "column_topics",
                columns_routes.get_column_topics,
                ("123", 456),
                "_column_topics",
                "获取专栏文章列表失败: boom",
            ),
            (
                "columns_stats",
                columns_routes.get_columns_stats,
                ("123",),
                "_columns_stats",
                "获取专栏统计失败: boom",
            ),
            (
                "delete_all_columns",
                columns_routes.delete_all_columns,
                ("123",),
                "_delete_all_columns",
                "删除专栏数据失败: boom",
            ),
        ]

        for case_name, route, route_args, helper_name, expected_detail in cases:
            with self.subTest(case_name=case_name):
                error = RuntimeError("boom")

                with patch.object(columns_routes, helper_name, side_effect=error):
                    with self.assertRaises(HTTPException) as raised:
                        asyncio.run(route(*route_args))

                self.assertEqual(500, raised.exception.status_code)
                self.assertEqual(expected_detail, raised.exception.detail)
                self.assertIs(error, raised.exception.__cause__)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_columns_read_helpers_preserve_service_call_shapes(self):
        from backend.routes import columns_routes

        cases = [
            (
                "group_columns",
                columns_routes._group_columns,
                ("123",),
                columns_routes.get_group_columns_response,
                ("123",),
                {"columns": []},
            ),
            (
                "column_topics",
                columns_routes._column_topics,
                ("123", 456),
                columns_routes.get_column_topics_response,
                ("123", 456),
                {"topics": []},
            ),
            (
                "columns_stats",
                columns_routes._columns_stats,
                ("123",),
                columns_routes.get_columns_stats_response,
                ("123",),
                {"stats": {}},
            ),
            (
                "delete_all_columns",
                columns_routes._delete_all_columns,
                ("123",),
                columns_routes.delete_all_columns_response,
                ("123",),
                {"success": True},
            ),
        ]

        for case_name, helper, helper_args, service_func, service_args, payload in cases:
            with self.subTest(case_name=case_name):
                calls = []

                async def fake_to_thread(func, *args):
                    calls.append((func, args))
                    return payload

                with patch(
                    "backend.routes.columns_routes.asyncio.to_thread",
                    side_effect=fake_to_thread,
                ):
                    result = asyncio.run(helper(*helper_args))

                self.assertEqual(payload, result)
                self.assertEqual([(service_func, service_args)], calls)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_get_column_topic_detail_preserves_success_payload(self):
        from backend.routes import columns_routes

        detail = {"topic_id": 456, "title": "memo"}
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return detail

        with patch(
            "backend.routes.columns_routes.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            result = asyncio.run(columns_routes.get_column_topic_detail("123", 456))

        self.assertEqual(detail, result)
        self.assertEqual(
            [(columns_routes.get_column_topic_detail_response, ("123", 456))],
            calls,
        )

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_get_column_topic_detail_returns_404_for_missing_detail(self):
        from fastapi import HTTPException
        from backend.routes import columns_routes

        async def fake_to_thread(func, *args):
            return None

        with patch("backend.routes.columns_routes.asyncio.to_thread", side_effect=fake_to_thread):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(columns_routes.get_column_topic_detail("123", 456))

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("文章详情不存在", raised.exception.detail)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_get_column_topic_detail_preserves_wrapped_unexpected_error(self):
        from fastapi import HTTPException
        from backend.routes import columns_routes

        error = RuntimeError("boom")

        with patch.object(columns_routes, "_column_topic_detail_or_404", side_effect=error):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(columns_routes.get_column_topic_detail("123", 456))

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("获取文章详情失败: boom", raised.exception.detail)
        self.assertIs(error, raised.exception.__cause__)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_column_topic_detail_or_404_preserves_success_and_missing_detail(self):
        from fastapi import HTTPException
        from backend.routes import columns_routes

        detail = {"topic_id": 456, "title": "memo"}

        async def fake_success_to_thread(func, *args):
            self.assertEqual(columns_routes.get_column_topic_detail_response, func)
            self.assertEqual(("123", 456), args)
            return detail

        with patch(
            "backend.routes.columns_routes.asyncio.to_thread",
            side_effect=fake_success_to_thread,
        ):
            result = asyncio.run(columns_routes._column_topic_detail_or_404("123", 456))

        self.assertEqual(detail, result)

        async def fake_missing_to_thread(func, *args):
            self.assertEqual(columns_routes.get_column_topic_detail_response, func)
            self.assertEqual(("123", 456), args)
            return None

        with patch(
            "backend.routes.columns_routes.asyncio.to_thread",
            side_effect=fake_missing_to_thread,
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(columns_routes._column_topic_detail_or_404("123", 456))

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("文章详情不存在", raised.exception.detail)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_fetch_group_columns_preserves_wrapped_unexpected_error(self):
        from fastapi import HTTPException
        from backend.routes import columns_routes

        error = RuntimeError("boom")

        with patch.object(columns_routes, "_create_columns_fetch_task_response", side_effect=error):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    columns_routes.fetch_group_columns(
                        "123",
                        columns_routes.ColumnsSettingsRequest(),
                    )
                )

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("启动专栏采集失败: boom", raised.exception.detail)
        self.assertIs(error, raised.exception.__cause__)

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
        self.assertEqual([(columns_routes.fetch_column_topic_full_comments, ("123", 456))], calls)

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_column_topic_full_comments_preserves_service_call_shape(self):
        from backend.routes import columns_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"success": True, "comments": [], "total": 0}

        with patch(
            "backend.routes.columns_routes.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            result = asyncio.run(columns_routes._column_topic_full_comments("123", 456))

        self.assertEqual({"success": True, "comments": [], "total": 0}, result)
        self.assertEqual(
            [(columns_routes.fetch_column_topic_full_comments, ("123", 456))],
            calls,
        )

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_get_column_topic_full_comments_preserves_http_exception_passthrough(self):
        from fastapi import HTTPException
        from backend.routes import columns_routes

        http_error = HTTPException(status_code=429, detail="rate limited")

        async def fake_to_thread(func, *args):
            raise http_error

        with (
            patch(
                "backend.routes.columns_routes.asyncio.to_thread",
                side_effect=fake_to_thread,
            ),
            patch("backend.routes.columns_routes.log_exception") as log_exception,
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(columns_routes.get_column_topic_full_comments("123", 456))

        self.assertIs(http_error, raised.exception)
        log_exception.assert_not_called()

    @unittest.skipUnless(HAS_COLUMNS_ROUTE_DEPS, "columns route dependencies are not installed")
    def test_get_column_topic_full_comments_logs_unexpected_error(self):
        from fastapi import HTTPException
        from backend.routes import columns_routes

        async def fake_to_thread(func, *args):
            raise RuntimeError("boom")

        with (
            patch(
                "backend.routes.columns_routes.asyncio.to_thread",
                side_effect=fake_to_thread,
            ),
            patch("backend.routes.columns_routes.log_exception") as log_exception,
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(columns_routes.get_column_topic_full_comments("123", 456))

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("获取完整评论失败: boom", raised.exception.detail)
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        log_exception.assert_called_once_with("获取专栏完整评论失败: topic_id=456")


if __name__ == "__main__":
    unittest.main()
