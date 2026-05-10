import unittest
from datetime import datetime, timedelta, timezone
from importlib.util import find_spec
from unittest.mock import call, patch


HAS_CRAWL_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class FakeCrawler:
    def __init__(self):
        self.interval_kwargs = None

    def set_custom_intervals(self, **kwargs):
        self.interval_kwargs = kwargs


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args):
        self.tasks.append((func, args))


class EmptyPageCrawler:
    def __init__(self, cookie, group_id, log_callback):
        self.cookie = cookie
        self.group_id = group_id
        self.log_callback = log_callback
        self.stop_check_func = None
        self.timestamp_offset_ms = 1
        self.fetch_calls = []

    def fetch_topics_safe(self, **kwargs):
        self.fetch_calls.append(kwargs)
        return {"succeeded": True, "resp_data": {"topics": []}}

    def set_custom_intervals(self, **kwargs):
        self.interval_kwargs = kwargs


def fake_task_func(*args):
    return args


class CrawlRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_crawl_interval_kwargs_maps_request_fields(self):
        from backend.routes.crawl_routes import CrawlSettingsRequest
        from backend.services.crawl_service import _crawl_interval_kwargs

        request = CrawlSettingsRequest(
            crawlIntervalMin=2.0,
            crawlIntervalMax=3.0,
            longSleepIntervalMin=120.0,
            longSleepIntervalMax=180.0,
            pagesPerBatch=10,
        )

        self.assertEqual(
            {
                "crawl_interval_min": 2.0,
                "crawl_interval_max": 3.0,
                "long_sleep_interval_min": 120.0,
                "long_sleep_interval_max": 180.0,
                "pages_per_batch": 10,
            },
            _crawl_interval_kwargs(request),
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_apply_crawl_settings_skips_when_overrides_required_and_empty(self):
        from backend.routes.crawl_routes import CrawlSettingsRequest
        from backend.services.crawl_service import _apply_crawl_settings

        crawler = FakeCrawler()

        applied = _apply_crawl_settings(crawler, CrawlSettingsRequest(), require_overrides=True)

        self.assertFalse(applied)
        self.assertIsNone(crawler.interval_kwargs)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_apply_crawl_settings_sets_intervals_when_present(self):
        from backend.routes.crawl_routes import CrawlSettingsRequest
        from backend.services.crawl_service import _apply_crawl_settings

        crawler = FakeCrawler()

        applied = _apply_crawl_settings(crawler, CrawlSettingsRequest(crawlIntervalMin=2.0), require_overrides=True)

        self.assertTrue(applied)
        self.assertEqual(2.0, crawler.interval_kwargs["crawl_interval_min"])
        self.assertIsNone(crawler.interval_kwargs["crawl_interval_max"])

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_parse_user_time_accepts_date_and_iso_variants(self):
        from backend.services.crawl_service import _parse_user_time

        self.assertEqual(
            datetime(2026, 5, 7, tzinfo=timezone(timedelta(hours=8))),
            _parse_user_time("2026-05-07"),
        )
        self.assertEqual(
            datetime(2026, 5, 7, 23, 59, 59, 999999, tzinfo=timezone(timedelta(hours=8))),
            _parse_user_time("2026-05-07", date_end=True),
        )
        self.assertEqual(
            datetime(2026, 5, 7, 12, 30, tzinfo=timezone.utc),
            _parse_user_time("2026-05-07T12:30Z"),
        )
        self.assertEqual(
            datetime(2026, 5, 7, 12, 30, tzinfo=timezone(timedelta(hours=8))),
            _parse_user_time("2026-05-07T12:30"),
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_resolve_time_range_uses_last_days_and_swaps_reversed_bounds(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import _resolve_time_range

        now_bj = datetime(2026, 5, 7, 12, tzinfo=timezone(timedelta(hours=8)))

        start_dt, end_dt = _resolve_time_range(CrawlTimeRangeRequest(lastDays=7), now_bj)
        self.assertEqual(now_bj - timedelta(days=7), start_dt)
        self.assertEqual(now_bj, end_dt)

        start_dt, end_dt = _resolve_time_range(
            CrawlTimeRangeRequest(startTime="2026-05-07", endTime="2026-05-01"),
            now_bj,
        )
        self.assertLessEqual(start_dt, end_dt)
        self.assertEqual(datetime(2026, 5, 1, tzinfo=timezone(timedelta(hours=8))), start_dt)
        self.assertEqual(datetime(2026, 5, 7, 23, 59, 59, 999999, tzinfo=timezone(timedelta(hours=8))), end_dt)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_format_zsxq_time_uses_bj_timezone_without_colon(self):
        from backend.services.crawl_service import _format_zsxq_time

        self.assertEqual(
            "2026-02-01T08:00:00.000+0800",
            _format_zsxq_time(datetime(2026, 2, 1, 0, tzinfo=timezone.utc)),
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_time_range_crawl_stops_after_empty_page(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = EmptyPageCrawler("cookie", "group-1", lambda message: None)

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.update_task") as update_task,
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(startTime="2026-02-01", endTime="2026-02-01", perPage=20),
            )

        self.assertEqual(1, len(crawler.fetch_calls))
        self.assertEqual(
            {
                "scope": "all",
                "count": 20,
                "begin_time": "2026-02-01T00:00:00.000+0800",
                "end_time": "2026-02-01T23:59:59.999+0800",
                "is_historical": True,
            },
            crawler.fetch_calls[0],
        )
        add_task_log.assert_any_call("task-1", "📭 无更多数据，任务结束")
        update_task.assert_any_call(
            "task-1",
            "completed",
            "时间区间爬取完成",
            {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0},
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_create_crawl_task_response_creates_and_enqueues_task(self):
        from backend.routes.crawl_routes import _create_crawl_task_response

        background_tasks = FakeBackgroundTasks()

        with (
            patch("backend.routes.ingestion_helpers.create_ingestion_task", return_value=("task-1", None)) as create_task,
            patch("backend.routes.ingestion_helpers.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _create_crawl_task_response(
                background_tasks,
                "crawl_latest",
                "latest description",
                fake_task_func,
                "group-1",
                "request",
            )

        create_task.assert_called_once_with("crawl_latest", "latest description", "group-1")
        self.assertEqual({"task_id": "task-1", "message": "任务已创建，正在后台执行"}, response)
        enqueue_runtime_task.assert_called_once_with(fake_task_func, "task-1", "group-1", "request")
        self.assertEqual([], background_tasks.tasks)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_create_crawl_task_response_rejects_same_group_ingestion_conflict(self):
        from fastapi import HTTPException
        from backend.routes.crawl_routes import _create_crawl_task_response

        background_tasks = FakeBackgroundTasks()
        existing = {"task_id": "task-old", "type": "crawl_latest", "status": "running"}

        with patch("backend.routes.ingestion_helpers.create_ingestion_task", return_value=(None, existing)):
            with self.assertRaises(HTTPException) as raised:
                _create_crawl_task_response(
                    background_tasks,
                    "crawl_latest",
                    "latest description",
                    fake_task_func,
                    "group-1",
                    "request",
                )

        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual([], background_tasks.tasks)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_build_task_callbacks_logs_and_checks_stop(self):
        from backend.services.crawl_service import _build_task_callbacks

        log_callback, stop_check = _build_task_callbacks("task-1")

        with (
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.is_task_stopped", return_value=True) as is_task_stopped,
        ):
            log_callback("hello")
            stopped = stop_check()

        add_task_log.assert_called_once_with("task-1", "hello")
        is_task_stopped.assert_called_once_with("task-1")
        self.assertTrue(stopped)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_log_crawler_startup_logs_connection_and_database_status(self):
        from backend.services.crawl_service import _log_crawler_startup

        with patch("backend.services.crawl_service.add_task_log") as add_task_log:
            _log_crawler_startup("task-1")

        self.assertEqual(
            [
                call("task-1", "📡 连接到知识星球API..."),
                call("task-1", "🔍 检查数据库状态..."),
            ],
            add_task_log.call_args_list,
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_log_init_stopped_logs_existing_message(self):
        from backend.services.crawl_service import _log_init_stopped

        with patch("backend.services.crawl_service.add_task_log") as add_task_log:
            _log_init_stopped("task-1")

        add_task_log.assert_called_once_with("task-1", "🛑 任务在初始化过程中被停止")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_mark_expired_task_logs_and_updates_failure(self):
        from backend.services.crawl_service import _mark_expired_task

        result = {"expired": True, "code": 1059, "message": "expired"}

        with (
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.update_task") as update_task,
        ):
            _mark_expired_task("task-1", result)

        add_task_log.assert_called_once_with("task-1", "❌ 会员已过期: expired")
        update_task.assert_called_once_with(
            "task-1",
            "failed",
            "会员已过期",
            {"expired": True, "code": 1059, "message": "expired"},
        )


if __name__ == "__main__":
    unittest.main()
