import asyncio
import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_DAILY_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class DailyAnalysisRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_daily_analysis_route_error_preserves_status_and_detail_format(self):
        from backend.routes.daily_analysis_routes import _daily_analysis_route_error

        error = _daily_analysis_route_error("获取每日报告失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("获取每日报告失败: boom", error.detail)

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_create_daily_report_task_response_delegates_to_workflow_launch(self):
        from backend.routes import daily_analysis_routes
        from backend.routes.daily_analysis_routes import DailyAnalysisRequest

        request = DailyAnalysisRequest(date="2026-06-13", commentsPerTopic=2)
        expected = {"task_id": "task-daily", "message": "任务已创建，正在后台执行"}
        with patch.object(
            daily_analysis_routes,
            "create_daily_topic_analysis_task",
            return_value=expected,
        ) as create_task:
            result = daily_analysis_routes._create_daily_report_task_response(
                "51111112855254",
                request,
            )

        self.assertEqual(expected, result)
        create_task.assert_called_once_with(
            "51111112855254",
            date="2026-06-13",
            comments_per_topic=2,
        )

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_create_daily_report_preserves_wrapped_unexpected_error(self):
        from fastapi import HTTPException

        from backend.routes import daily_analysis_routes
        from backend.routes.daily_analysis_routes import DailyAnalysisRequest

        request = DailyAnalysisRequest(date="2026-06-13")

        with patch.object(
            daily_analysis_routes,
            "_create_daily_report_task_response",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    daily_analysis_routes.create_daily_report(
                        "group-1",
                        request,
                    )
                )

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("创建每日分析任务失败: boom", raised.exception.detail)

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_create_daily_today_task_response_delegates_to_workflow_launch(self):
        from backend.schemas.crawl import CrawlSettingsRequest
        from backend.routes import daily_analysis_routes
        from backend.routes.daily_analysis_routes import DailyRunTodayRequest

        crawl_settings = CrawlSettingsRequest(pagesPerBatch=15)
        request = DailyRunTodayRequest(
            date="2026-06-13",
            commentsPerTopic=2,
            crawlLatestFirst=False,
            crawlSettings=crawl_settings,
        )
        expected = {"task_id": "task-today", "message": "任务已创建，正在后台执行"}
        with patch.object(
            daily_analysis_routes,
            "create_daily_topic_crawl_and_analysis_task",
            return_value=expected,
        ) as create_task:
            result = daily_analysis_routes._create_daily_today_task_response(
                "51111112855254",
                request,
            )

        self.assertEqual(expected, result)
        create_task.assert_called_once_with(
            "51111112855254",
            date="2026-06-13",
            comments_per_topic=2,
            crawl_latest_first=False,
            crawl_settings=crawl_settings,
        )

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_run_today_report_preserves_wrapped_unexpected_error(self):
        from fastapi import HTTPException

        from backend.routes import daily_analysis_routes
        from backend.routes.daily_analysis_routes import DailyRunTodayRequest

        request = DailyRunTodayRequest(date="2026-06-13", crawlLatestFirst=False)

        with patch.object(
            daily_analysis_routes,
            "_create_daily_today_task_response",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    daily_analysis_routes.run_today_report(
                        "group-1",
                        request,
                    )
                )

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("创建每日抓取分析任务失败: boom", raised.exception.detail)

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_read_daily_report_preserves_report_passthrough(self):
        from backend.routes import daily_analysis_routes

        report = {"date": "2026-06-13", "summary": "ok"}
        with patch.object(daily_analysis_routes, "get_daily_report", return_value=report) as get_report:
            result = asyncio.run(daily_analysis_routes.read_daily_report("group-1", "2026-06-13"))

        self.assertEqual(report, result)
        get_report.assert_called_once_with("group-1", "2026-06-13")

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_read_daily_report_preserves_missing_report_404(self):
        from fastapi import HTTPException

        from backend.routes import daily_analysis_routes

        with patch.object(daily_analysis_routes, "get_daily_report", return_value=None) as get_report:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(daily_analysis_routes.read_daily_report("group-1", None))

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("日报不存在，请先生成", raised.exception.detail)
        get_report.assert_called_once_with("group-1", None)

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_read_daily_report_preserves_wrapped_unexpected_error(self):
        from fastapi import HTTPException

        from backend.routes import daily_analysis_routes

        with patch.object(daily_analysis_routes, "_daily_report_or_404", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(daily_analysis_routes.read_daily_report("group-1", None))

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("获取每日报告失败: boom", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
