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


class TimeRangeCrawler:
    def __init__(self, pages):
        self.pages = list(pages)
        self.fetch_calls = []
        self.store_calls = []
        self.delay_calls = 0
        self.interval_kwargs = None
        self.stop_check_func = None
        self.timestamp_offset_ms = 1

    def fetch_topics_safe(self, **kwargs):
        self.fetch_calls.append(kwargs)
        return self.pages.pop(0)

    def store_batch_data(self, data):
        self.store_calls.append(data)
        return {"new_topics": 2, "updated_topics": 1, "errors": 0}

    def check_page_long_delay(self):
        self.delay_calls += 1

    def set_custom_intervals(self, **kwargs):
        self.interval_kwargs = kwargs


class LatestCrawler:
    def __init__(self):
        self.interval_kwargs = None
        self.stop_check_func = None
        self.latest_calls = 0

    def set_custom_intervals(self, **kwargs):
        self.interval_kwargs = kwargs

    def crawl_latest_until_complete(self):
        self.latest_calls += 1
        return {"new_topics": 1, "updated_topics": 2}


class FailingLatestCrawler(LatestCrawler):
    def crawl_latest_until_complete(self):
        self.latest_calls += 1
        raise RuntimeError("boom")


class LegacyLifecycleCrawler:
    def __init__(self, incremental_result=None, all_result=None):
        self.db = self
        self.incremental_calls = []
        self.all_calls = []
        self.incremental_result = incremental_result or {"new_topics": 3, "updated_topics": 4}
        self.all_result = all_result or {"new_topics": 5, "updated_topics": 6, "pages": 7}

    def crawl_incremental(self, pages, per_page):
        self.incremental_calls.append((pages, per_page))
        return self.incremental_result

    def crawl_all_historical(self, **kwargs):
        self.all_calls.append(kwargs)
        return self.all_result

    def get_database_stats(self):
        return {"topics": 10, "users": 2}


class FailingLegacyLifecycleCrawler(LegacyLifecycleCrawler):
    def crawl_incremental(self, pages, per_page):
        self.incremental_calls.append((pages, per_page))
        raise RuntimeError("boom")

    def crawl_all_historical(self, **kwargs):
        self.all_calls.append(kwargs)
        raise RuntimeError("boom")


class FailingTimeRangeCrawler(TimeRangeCrawler):
    def __init__(self):
        super().__init__([])

    def fetch_topics_safe(self, **kwargs):
        self.fetch_calls.append(kwargs)
        raise RuntimeError("boom")


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
        from backend.services.crawl_time_range import parse_user_time

        self.assertEqual(
            datetime(2026, 5, 7, tzinfo=timezone(timedelta(hours=8))),
            parse_user_time("2026-05-07"),
        )
        self.assertEqual(
            datetime(2026, 5, 7, 23, 59, 59, 999999, tzinfo=timezone(timedelta(hours=8))),
            parse_user_time("2026-05-07", date_end=True),
        )
        self.assertEqual(
            datetime(2026, 5, 7, 12, 30, tzinfo=timezone.utc),
            parse_user_time("2026-05-07T12:30Z"),
        )
        self.assertEqual(
            datetime(2026, 5, 7, 12, 30, tzinfo=timezone(timedelta(hours=8))),
            parse_user_time("2026-05-07T12:30"),
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_resolve_time_range_uses_last_days_and_swaps_reversed_bounds(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_time_range import resolve_time_range

        now_bj = datetime(2026, 5, 7, 12, tzinfo=timezone(timedelta(hours=8)))

        start_dt, end_dt = resolve_time_range(CrawlTimeRangeRequest(lastDays=7), now_bj)
        self.assertEqual(now_bj - timedelta(days=7), start_dt)
        self.assertEqual(now_bj, end_dt)

        start_dt, end_dt = resolve_time_range(
            CrawlTimeRangeRequest(startTime="2026-05-07", endTime="2026-05-01"),
            now_bj,
        )
        self.assertLessEqual(start_dt, end_dt)
        self.assertEqual(datetime(2026, 5, 1, tzinfo=timezone(timedelta(hours=8))), start_dt)
        self.assertEqual(datetime(2026, 5, 7, 23, 59, 59, 999999, tzinfo=timezone(timedelta(hours=8))), end_dt)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_format_zsxq_time_uses_bj_timezone_without_colon(self):
        from backend.services.crawl_time_range import format_zsxq_time

        self.assertEqual(
            "2026-02-01T08:00:00.000+0800",
            format_zsxq_time(datetime(2026, 2, 1, 0, tzinfo=timezone.utc)),
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_resolve_topic_source_prefers_request_then_env_then_official(self):
        from backend.routes.crawl_routes import CrawlSettingsRequest, CrawlTimeRangeRequest
        from backend.services.crawl_service import _normalize_topic_source, _resolve_topic_source, _uses_official_topic_source

        self.assertEqual("official", _normalize_topic_source("mcp"))
        self.assertEqual("official", _normalize_topic_source("cli"))
        self.assertEqual("legacy", _normalize_topic_source("crawler"))
        self.assertEqual("legacy", _normalize_topic_source("cookie"))
        self.assertIsNone(_normalize_topic_source("unknown"))

        with patch.dict("os.environ", {"ZSXQ_TOPIC_SOURCE": ""}):
            self.assertEqual("official", _resolve_topic_source(CrawlTimeRangeRequest()))
            self.assertTrue(_uses_official_topic_source(CrawlTimeRangeRequest()))

        with patch.dict("os.environ", {"ZSXQ_TOPIC_SOURCE": "legacy"}):
            self.assertEqual("legacy", _resolve_topic_source(CrawlTimeRangeRequest()))
            self.assertEqual("official", _resolve_topic_source(CrawlTimeRangeRequest(topicSource="official")))
            self.assertFalse(_uses_official_topic_source(CrawlTimeRangeRequest()))
            self.assertTrue(_uses_official_topic_source(CrawlTimeRangeRequest(topicSource="official")))

        with patch.dict("os.environ", {"ZSXQ_TOPIC_SOURCE": "official"}):
            self.assertEqual("legacy", _resolve_topic_source(CrawlTimeRangeRequest(topicSource="legacy")))
            self.assertFalse(_uses_official_topic_source(CrawlTimeRangeRequest(topicSource="legacy")))

        self.assertEqual("official", _resolve_topic_source(CrawlTimeRangeRequest(topicSource="official")))
        self.assertEqual("official", _resolve_topic_source(CrawlSettingsRequest(topicSource="official")))

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_latest_branch_skips_legacy_crawler(self):
        from backend.routes.crawl_routes import CrawlSettingsRequest
        from backend.services.crawl_service import run_crawl_latest_task

        with (
            patch("backend.services.crawl_service._run_official_crawl_pages_task") as official_runner,
            patch("backend.services.crawl_service.ZSXQTopicCrawler") as legacy_crawler,
            patch("backend.services.crawl_service.update_task"),
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_latest_task("task-1", "group-1", CrawlSettingsRequest(topicSource="official"))

        official_runner.assert_called_once_with("task-1", "group-1", None, 20, "latest")
        legacy_crawler.assert_not_called()

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_all_branch_uses_oldest_cursor_and_skips_legacy_crawler(self):
        from backend.routes.crawl_routes import CrawlSettingsRequest
        from backend.services.crawl_service import run_crawl_all_task

        with (
            patch("backend.services.crawl_service._official_start_cursor_from_oldest", return_value="cursor-all") as start_cursor,
            patch("backend.services.crawl_service._run_official_crawl_pages_task") as official_runner,
            patch("backend.services.crawl_service.ZSXQDatabase") as database,
            patch("backend.services.crawl_service.ZSXQTopicCrawler") as legacy_crawler,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_all_task("task-1", "group-1", CrawlSettingsRequest(topicSource="official"))

        update_task.assert_any_call("task-1", "running", "开始全量爬取...")
        add_task_log.assert_any_call("task-1", "🚀 开始全量爬取...")
        add_task_log.assert_any_call("task-1", "⚠️ 警告：此模式将持续爬取直到没有数据，可能需要很长时间")
        add_task_log.assert_any_call("task-1", "🔁 使用官方全量采集流程（MCP HTTP）")
        database.assert_called_once_with("group-1")
        start_cursor.assert_called_once_with(database.return_value, "task-1", allow_empty=True)
        official_runner.assert_called_once_with("task-1", "group-1", None, 20, "all", start_cursor="cursor-all")
        legacy_crawler.assert_not_called()

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_historical_branch_uses_oldest_cursor_and_skips_legacy_crawler(self):
        from backend.routes.crawl_routes import CrawlHistoricalRequest
        from backend.services.crawl_service import run_crawl_historical_task

        with (
            patch("backend.services.crawl_service._official_start_cursor_from_oldest", return_value="cursor-1") as start_cursor,
            patch("backend.services.crawl_service._run_official_crawl_pages_task") as official_runner,
            patch("backend.services.crawl_service.ZSXQDatabase") as database,
            patch("backend.services.crawl_service.ZSXQTopicCrawler") as legacy_crawler,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_historical_task(
                "task-1",
                "group-1",
                3,
                25,
                CrawlHistoricalRequest(topicSource="official"),
            )

        update_task.assert_any_call("task-1", "running", "开始爬取历史数据 3 页...")
        add_task_log.assert_any_call("task-1", "🚀 开始获取历史数据，3 页，每页 25 条")
        add_task_log.assert_any_call("task-1", "🔁 使用官方历史增量采集流程（MCP HTTP）")
        database.assert_called_once_with("group-1")
        start_cursor.assert_called_once_with(database.return_value, "task-1", allow_empty=False)
        official_runner.assert_called_once_with("task-1", "group-1", 3, 25, "incremental", start_cursor="cursor-1")
        legacy_crawler.assert_not_called()

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_incremental_branch_uses_oldest_cursor_and_skips_legacy_crawler(self):
        from backend.routes.crawl_routes import CrawlHistoricalRequest
        from backend.services.crawl_service import run_crawl_incremental_task

        with (
            patch("backend.services.crawl_service._official_start_cursor_from_oldest", return_value="cursor-2") as start_cursor,
            patch("backend.services.crawl_service._run_official_crawl_pages_task") as official_runner,
            patch("backend.services.crawl_service.ZSXQDatabase") as database,
            patch("backend.services.crawl_service.ZSXQTopicCrawler") as legacy_crawler,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_incremental_task(
                "task-2",
                "group-2",
                4,
                26,
                CrawlHistoricalRequest(topicSource="official"),
            )

        update_task.assert_any_call("task-2", "running", "开始增量爬取...")
        add_task_log.assert_any_call("task-2", "🔁 使用官方增量采集流程（MCP HTTP）")
        database.assert_called_once_with("group-2")
        start_cursor.assert_called_once_with(database.return_value, "task-2", allow_empty=False)
        official_runner.assert_called_once_with("task-2", "group-2", 4, 26, "incremental", start_cursor="cursor-2")
        legacy_crawler.assert_not_called()

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_incremental_empty_database_fails_without_legacy_crawler(self):
        from backend.routes.crawl_routes import CrawlHistoricalRequest
        from backend.services.crawl_service import run_crawl_incremental_task

        with (
            patch("backend.services.crawl_service._official_start_cursor_from_oldest", return_value=""),
            patch("backend.services.crawl_service._run_official_crawl_pages_task") as official_runner,
            patch("backend.services.crawl_service.ZSXQDatabase"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler") as legacy_crawler,
            patch("backend.services.crawl_service.update_task"),
            patch("backend.services.crawl_service.fail_task_with_message_unless_stopped") as fail_task,
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_incremental_task(
                "task-1",
                "group-1",
                10,
                20,
                CrawlHistoricalRequest(topicSource="official"),
            )

        official_runner.assert_not_called()
        legacy_crawler.assert_not_called()
        fail_task.assert_called_once_with("task-1", "官方增量采集失败: 数据库为空")

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
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-01",
                    perPage=20,
                    topicSource="legacy",
                ),
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
        complete_task.assert_called_once_with(
            "task-1",
            "时间区间爬取完成",
            {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0},
        )
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_uses_default_per_page_when_missing(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = EmptyPageCrawler("cookie", "group-1", lambda message: None)

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.update_task"),
            patch("backend.services.crawl_service.complete_task_unless_stopped"),
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-01",
                    topicSource="legacy",
                ),
            )

        self.assertEqual(20, crawler.fetch_calls[0]["count"])

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_outer_stop_completes_without_fetching(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = TimeRangeCrawler([])

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=True),
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.unregister_task_crawler") as unregister_task_crawler,
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-01",
                    perPage=20,
                    topicSource="legacy",
                ),
            )

        self.assertEqual([], crawler.fetch_calls)
        add_task_log.assert_any_call("task-1", "🛑 任务已停止")
        complete_task.assert_called_once_with(
            "task-1",
            "时间区间爬取完成",
            {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0},
        )
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )
        unregister_task_crawler.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_filters_topics_and_advances_end_time(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = TimeRangeCrawler(
            [
                {
                    "succeeded": True,
                    "resp_data": {
                        "topics": [
                            {"topic_id": 1, "create_time": "2026-02-02T10:00:00.000+0800"},
                            {"topic_id": 2, "create_time": "not-a-time"},
                            {"topic_id": 3, "create_time": "2026-02-01T09:00:00.000+0800"},
                        ]
                    },
                },
                {"succeeded": True, "resp_data": {"topics": []}},
            ]
        )

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-02",
                    perPage=20,
                    topicSource="legacy",
                ),
            )

        self.assertEqual(
            [
                {
                    "scope": "all",
                    "count": 20,
                    "begin_time": "2026-02-01T00:00:00.000+0800",
                    "end_time": "2026-02-02T23:59:59.999+0800",
                    "is_historical": True,
                },
                {
                    "scope": "all",
                    "count": 20,
                    "begin_time": "2026-02-01T00:00:00.000+0800",
                    "end_time": "2026-02-01T08:59:59.999+0800",
                    "is_historical": True,
                },
            ],
            crawler.fetch_calls,
        )
        self.assertEqual(
            [
                {
                    "succeeded": True,
                    "resp_data": {
                        "topics": [
                            {"topic_id": 1, "create_time": "2026-02-02T10:00:00.000+0800"},
                            {"topic_id": 3, "create_time": "2026-02-01T09:00:00.000+0800"},
                        ]
                    },
                }
            ],
            crawler.store_calls,
        )
        self.assertEqual(1, crawler.delay_calls)
        add_task_log.assert_any_call("task-1", "📄 本页获取 3 个话题，区间内 2 个")
        add_task_log.assert_any_call("task-1", "📭 无更多数据，任务结束")
        complete_task.assert_called_once_with(
            "task-1",
            "时间区间爬取完成",
            {"new_topics": 2, "updated_topics": 1, "errors": 0, "pages": 1},
        )
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_keeps_invalid_oldest_time_as_next_end_time(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = TimeRangeCrawler(
            [
                {
                    "succeeded": True,
                    "resp_data": {
                        "topics": [
                            {"topic_id": 1, "create_time": "2026-02-02T10:00:00.000+0800"},
                            {"topic_id": 2, "create_time": "not-a-time"},
                        ]
                    },
                },
                {"succeeded": True, "resp_data": {"topics": []}},
            ]
        )

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.update_task"),
            patch("backend.services.crawl_service.complete_task_unless_stopped"),
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-02",
                    perPage=20,
                    topicSource="legacy",
                ),
            )

        self.assertEqual("not-a-time", crawler.fetch_calls[1]["end_time"])

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_counts_unstored_out_of_range_page(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = TimeRangeCrawler(
            [
                {
                    "succeeded": True,
                    "resp_data": {
                        "topics": [
                            {"topic_id": 1, "create_time": "2026-02-03T10:00:00.000+0800"},
                        ]
                    },
                },
                {"succeeded": True, "resp_data": {"topics": []}},
            ]
        )

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-02",
                    perPage=20,
                    topicSource="legacy",
                ),
            )

        self.assertEqual([], crawler.store_calls)
        self.assertEqual(1, crawler.delay_calls)
        add_task_log.assert_any_call("task-1", "📄 本页获取 1 个话题，区间内 0 个")
        complete_task.assert_called_once_with(
            "task-1",
            "时间区间爬取完成",
            {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 1},
        )
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_stops_when_page_is_before_start_time(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = TimeRangeCrawler(
            [
                {
                    "succeeded": True,
                    "resp_data": {
                        "topics": [
                            {"topic_id": 1, "create_time": "2026-01-31T23:59:59.999+0800"},
                        ]
                    },
                },
            ]
        )

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-02",
                    perPage=20,
                    topicSource="legacy",
                ),
            )

        self.assertEqual(1, len(crawler.fetch_calls))
        self.assertEqual([], crawler.store_calls)
        self.assertEqual(0, crawler.delay_calls)
        add_task_log.assert_any_call("task-1", "✅ 已到达起始时间之前，任务结束")
        complete_task.assert_called_once_with(
            "task-1",
            "时间区间爬取完成",
            {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 1},
        )
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_retries_failed_page_fetch(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = TimeRangeCrawler(
            [
                None,
                {"succeeded": True, "resp_data": {"topics": []}},
            ]
        )

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-02",
                    perPage=20,
                    topicSource="legacy",
                ),
            )

        self.assertEqual(2, len(crawler.fetch_calls))
        add_task_log.assert_any_call("task-1", "❌ 页面获取失败 (重试1/10)")
        add_task_log.assert_any_call("task-1", "📭 无更多数据，任务结束")
        complete_task.assert_called_once_with(
            "task-1",
            "时间区间爬取完成",
            {"new_topics": 0, "updated_topics": 0, "errors": 1, "pages": 0},
        )
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_stops_after_max_failed_page_fetches(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = TimeRangeCrawler([None] * 10)

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.unregister_task_crawler"),
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-02",
                    perPage=20,
                    topicSource="legacy",
                ),
            )

        self.assertEqual(10, len(crawler.fetch_calls))
        add_task_log.assert_any_call("task-1", "❌ 页面获取失败 (重试10/10)")
        add_task_log.assert_any_call("task-1", "🚫 当前页面达到最大重试次数，终止任务")
        complete_task.assert_called_once_with(
            "task-1",
            "时间区间爬取完成",
            {"new_topics": 0, "updated_topics": 0, "errors": 10, "pages": 0},
        )
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_expired_response_fails_with_original_payload(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        expired_payload = {"expired": True, "code": 1059, "message": "expired"}
        crawler = TimeRangeCrawler([expired_payload])

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie"),
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.fail_task_with_message_unless_stopped") as fail_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.unregister_task_crawler") as unregister_task_crawler,
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-02",
                    perPage=20,
                    topicSource="legacy",
                ),
            )

        self.assertEqual(1, len(crawler.fetch_calls))
        self.assertEqual([], crawler.store_calls)
        fail_task.assert_called_once_with(
            "task-1",
            "会员已过期",
            expired_payload,
            log_message="❌ 会员已过期: expired",
        )
        complete_task.assert_not_called()
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )
        unregister_task_crawler.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_non_range_crawl_success_completes_through_task_runtime_guard(self):
        from backend.routes.crawl_routes import CrawlHistoricalRequest, CrawlSettingsRequest
        from backend.services.crawl_service import (
            run_crawl_all_task,
            run_crawl_historical_task,
            run_crawl_incremental_task,
        )

        cases = [
            (
                "historical",
                run_crawl_historical_task,
                ("task-1", "group-1", 3, 25, CrawlHistoricalRequest(topicSource="legacy")),
                "开始爬取历史数据 3 页...",
                "历史数据爬取完成",
                {"new_topics": 3, "updated_topics": 4},
                lambda crawler: self.assertEqual([(3, 25)], crawler.incremental_calls),
            ),
            (
                "all",
                run_crawl_all_task,
                ("task-1", "group-1", CrawlSettingsRequest(topicSource="legacy")),
                "开始全量爬取...",
                "全量爬取完成",
                {"new_topics": 5, "updated_topics": 6, "pages": 7},
                lambda crawler: self.assertEqual(
                    [{"per_page": 20, "auto_confirm": True}],
                    crawler.all_calls,
                ),
            ),
            (
                "incremental",
                run_crawl_incremental_task,
                ("task-1", "group-1", 4, 26, CrawlHistoricalRequest(topicSource="legacy")),
                "开始增量爬取...",
                "增量爬取完成",
                {"new_topics": 3, "updated_topics": 4},
                lambda crawler: self.assertEqual([(4, 26)], crawler.incremental_calls),
            ),
        ]

        for case_name, runner, args, running_message, completed_message, result, assert_crawler in cases:
            crawler = LegacyLifecycleCrawler()
            with (
                self.subTest(case_name=case_name),
                patch("backend.services.crawl_service._prepare_legacy_crawler", return_value=crawler),
                patch("backend.services.crawl_service.is_task_stopped", return_value=False),
                patch("backend.services.crawl_service.add_task_log"),
                patch("backend.services.crawl_service.update_task") as update_task,
                patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
                patch("backend.services.crawl_service.unregister_task_crawler") as unregister_task_crawler,
            ):
                runner(*args)

            assert_crawler(crawler)
            update_task.assert_any_call("task-1", "running", running_message)
            complete_task.assert_called_once_with("task-1", completed_message, result)
            self.assertFalse(
                any(
                    len(call_args.args) > 1 and call_args.args[1] == "completed"
                    for call_args in update_task.call_args_list
                )
            )
            unregister_task_crawler.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_non_range_crawl_failures_use_task_runtime_guard(self):
        from backend.routes.crawl_routes import CrawlHistoricalRequest, CrawlSettingsRequest
        from backend.services.crawl_service import (
            run_crawl_all_task,
            run_crawl_historical_task,
            run_crawl_incremental_task,
        )

        cases = [
            (
                "historical",
                run_crawl_historical_task,
                ("task-1", "group-1", 3, 25, CrawlHistoricalRequest(topicSource="legacy")),
                "开始爬取历史数据 3 页...",
                "爬取失败: boom",
                "❌ 获取失败: boom",
                lambda crawler: self.assertEqual([(3, 25)], crawler.incremental_calls),
            ),
            (
                "all",
                run_crawl_all_task,
                ("task-1", "group-1", CrawlSettingsRequest(topicSource="legacy")),
                "开始全量爬取...",
                "全量爬取失败: boom",
                "❌ 全量爬取失败: boom",
                lambda crawler: self.assertEqual(
                    [{"per_page": 20, "auto_confirm": True}],
                    crawler.all_calls,
                ),
            ),
            (
                "incremental",
                run_crawl_incremental_task,
                ("task-1", "group-1", 4, 26, CrawlHistoricalRequest(topicSource="legacy")),
                "开始增量爬取...",
                "增量爬取失败: boom",
                "❌ 增量爬取失败: boom",
                lambda crawler: self.assertEqual([(4, 26)], crawler.incremental_calls),
            ),
        ]

        for case_name, runner, args, running_message, failed_message, log_message, assert_crawler in cases:
            crawler = FailingLegacyLifecycleCrawler()
            with (
                self.subTest(case_name=case_name),
                patch("backend.services.crawl_service._prepare_legacy_crawler", return_value=crawler),
                patch("backend.services.crawl_service.update_task") as update_task,
                patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
                patch("backend.services.crawl_service.fail_task_with_message_unless_stopped") as fail_task,
                patch("backend.services.crawl_service.add_task_log"),
                patch("backend.services.crawl_service.unregister_task_crawler") as unregister_task_crawler,
            ):
                runner(*args)

            assert_crawler(crawler)
            update_task.assert_any_call("task-1", "running", running_message)
            fail_task.assert_called_once_with("task-1", failed_message, log_message=log_message)
            complete_task.assert_not_called()
            self.assertFalse(
                any(
                    len(call_args.args) > 1 and call_args.args[1] == "failed"
                    for call_args in update_task.call_args_list
                )
            )
            unregister_task_crawler.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_latest_failure_uses_task_runtime_guard(self):
        from backend.routes.crawl_routes import CrawlSettingsRequest
        from backend.services.crawl_service import run_crawl_latest_task

        crawler = FailingLatestCrawler()

        with (
            patch("backend.services.crawl_service._prepare_legacy_crawler", return_value=crawler),
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.fail_task_with_message_unless_stopped") as fail_task,
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.unregister_task_crawler") as unregister_task_crawler,
        ):
            run_crawl_latest_task("task-1", "group-1", CrawlSettingsRequest(topicSource="legacy"))

        self.assertEqual(1, crawler.latest_calls)
        update_task.assert_any_call("task-1", "running", "开始获取最新记录...")
        fail_task.assert_called_once_with(
            "task-1",
            "获取最新记录失败: boom",
            log_message="❌ 获取最新记录失败: boom",
        )
        complete_task.assert_not_called()
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "failed"
                for call_args in update_task.call_args_list
            )
        )
        unregister_task_crawler.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_time_range_failure_uses_task_runtime_guard(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import run_crawl_time_range_task

        crawler = FailingTimeRangeCrawler()

        with (
            patch("backend.services.crawl_service._prepare_legacy_crawler", return_value=crawler),
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.fail_task_with_message_unless_stopped") as fail_task,
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.unregister_task_crawler") as unregister_task_crawler,
        ):
            run_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(
                    startTime="2026-02-01",
                    endTime="2026-02-02",
                    perPage=20,
                    topicSource="legacy",
                ),
            )

        self.assertEqual(1, len(crawler.fetch_calls))
        update_task.assert_any_call("task-1", "running", "开始按时间区间爬取...")
        fail_task.assert_called_once_with(
            "task-1",
            "时间区间爬取失败: boom",
            log_message="❌ 时间区间爬取失败: boom",
        )
        complete_task.assert_not_called()
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "failed"
                for call_args in update_task.call_args_list
            )
        )
        unregister_task_crawler.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_incremental_expired_result_fails_instead_of_completing(self):
        from backend.routes.crawl_routes import CrawlHistoricalRequest
        from backend.services.crawl_service import run_crawl_incremental_task

        expired_payload = {"expired": True, "code": 1059, "message": "expired"}
        crawler = LegacyLifecycleCrawler(incremental_result=expired_payload)

        with (
            patch("backend.services.crawl_service._prepare_legacy_crawler", return_value=crawler),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.fail_task_with_message_unless_stopped") as fail_task,
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.unregister_task_crawler") as unregister_task_crawler,
        ):
            run_crawl_incremental_task(
                "task-1",
                "group-1",
                4,
                26,
                CrawlHistoricalRequest(topicSource="legacy"),
            )

        self.assertEqual([(4, 26)], crawler.incremental_calls)
        fail_task.assert_called_once_with(
            "task-1",
            "会员已过期",
            {"expired": True, "code": 1059, "message": "expired"},
            log_message="❌ 会员已过期: expired",
        )
        complete_task.assert_not_called()
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )
        unregister_task_crawler.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_legacy_latest_branch_creates_registered_crawler_and_applies_settings(self):
        from backend.routes.crawl_routes import CrawlSettingsRequest
        from backend.services.crawl_service import run_crawl_latest_task

        crawler = LatestCrawler()

        with (
            patch("backend.services.crawl_service.get_cookie_for_group", return_value="cookie") as get_cookie,
            patch("backend.services.crawl_service.ZSXQTopicCrawler", return_value=crawler) as crawler_cls,
            patch("backend.services.crawl_service.register_task_crawler") as register_task_crawler,
            patch("backend.services.crawl_service.unregister_task_crawler") as unregister_task_crawler,
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
            patch("backend.services.crawl_service.update_task") as update_task,
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
        ):
            run_crawl_latest_task(
                "task-1",
                "group-1",
                CrawlSettingsRequest(topicSource="legacy", crawlIntervalMin=2.0),
            )

        get_cookie.assert_called_once_with("group-1")
        crawler_cls.assert_called_once()
        register_task_crawler.assert_called_once_with("task-1", crawler)
        unregister_task_crawler.assert_called_once_with("task-1")
        self.assertIsNotNone(crawler.stop_check_func)
        self.assertEqual(2.0, crawler.interval_kwargs["crawl_interval_min"])
        add_task_log.assert_any_call("task-1", "📡 连接到知识星球API...")
        add_task_log.assert_any_call("task-1", "🔍 检查数据库状态...")
        add_task_log.assert_any_call("task-1", "✅ 获取最新记录完成！新增话题: 1, 更新话题: 2")
        update_task.assert_any_call("task-1", "running", "开始获取最新记录...")
        complete_task.assert_called_once_with(
            "task-1",
            "获取最新记录完成",
            {"new_topics": 1, "updated_topics": 2},
        )
        self.assertFalse(
            any(
                len(call_args.args) > 1 and call_args.args[1] == "completed"
                for call_args in update_task.call_args_list
            )
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_crawl_route_task_responses_delegate_to_crawl_workflow(self):
        import asyncio

        from backend.routes import crawl_routes

        response_payload = {"task_id": "task-1", "message": "任务已创建，正在后台执行"}
        historical_request = crawl_routes.CrawlHistoricalRequest(pages=3, per_page=25)
        incremental_request = crawl_routes.CrawlHistoricalRequest(pages=4, per_page=30)
        all_request = crawl_routes.CrawlSettingsRequest(topicSource="official")
        latest_request = crawl_routes.CrawlSettingsRequest(topicSource="legacy")
        range_request = crawl_routes.CrawlTimeRangeRequest(lastDays=7, perPage=40)

        cases = [
            (
                "historical",
                crawl_routes.crawl_historical,
                historical_request,
                "create_historical_crawl_task",
            ),
            (
                "all",
                crawl_routes.crawl_all,
                all_request,
                "create_all_crawl_task",
            ),
            (
                "incremental",
                crawl_routes.crawl_incremental,
                incremental_request,
                "create_incremental_crawl_task",
            ),
            (
                "latest",
                crawl_routes.crawl_latest_until_complete,
                latest_request,
                "launch_latest_crawl_task",
            ),
            (
                "range",
                crawl_routes.crawl_by_time_range,
                range_request,
                "create_time_range_crawl_task",
            ),
        ]

        for case_name, route, request, launcher_name in cases:
            with self.subTest(case_name=case_name):
                with patch(
                    f"backend.routes.crawl_routes.{launcher_name}",
                    return_value=response_payload,
                ) as create_task:
                    response = asyncio.run(route("group-1", request))

                self.assertEqual(response_payload, response)
                create_task.assert_called_once_with("group-1", request)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_crawl_route_error_preserves_status_and_detail_format(self):
        from backend.routes import crawl_routes

        error = crawl_routes._crawl_route_error("创建爬取任务失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("创建爬取任务失败: boom", error.detail)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_crawl_routes_preserve_wrapped_unexpected_errors(self):
        import asyncio

        from backend.routes import crawl_routes

        historical_request = crawl_routes.CrawlHistoricalRequest()
        settings_request = crawl_routes.CrawlSettingsRequest()
        range_request = crawl_routes.CrawlTimeRangeRequest()

        cases = [
            (
                "historical",
                crawl_routes.crawl_historical,
                historical_request,
                "create_historical_crawl_task",
                "创建爬取任务失败: boom",
            ),
            (
                "all",
                crawl_routes.crawl_all,
                settings_request,
                "create_all_crawl_task",
                "创建全量爬取任务失败: boom",
            ),
            (
                "incremental",
                crawl_routes.crawl_incremental,
                historical_request,
                "create_incremental_crawl_task",
                "创建增量爬取任务失败: boom",
            ),
            (
                "latest",
                crawl_routes.crawl_latest_until_complete,
                settings_request,
                "launch_latest_crawl_task",
                "创建获取最新记录任务失败: boom",
            ),
            (
                "range",
                crawl_routes.crawl_by_time_range,
                range_request,
                "create_time_range_crawl_task",
                "创建时间区间爬取任务失败: boom",
            ),
        ]

        for case_name, route, request, launcher_name, expected_detail in cases:
            with self.subTest(case_name=case_name), patch(
                f"backend.routes.crawl_routes.{launcher_name}",
                side_effect=RuntimeError("boom"),
            ):
                with self.assertRaises(crawl_routes.HTTPException) as raised:
                    asyncio.run(route("group-1", request))

                self.assertEqual(500, raised.exception.status_code)
                self.assertEqual(expected_detail, raised.exception.detail)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_crawl_routes_preserve_http_exception_passthrough(self):
        import asyncio

        from backend.routes import crawl_routes

        historical_request = crawl_routes.CrawlHistoricalRequest()
        settings_request = crawl_routes.CrawlSettingsRequest()
        range_request = crawl_routes.CrawlTimeRangeRequest()
        original_error = crawl_routes.HTTPException(status_code=409, detail="conflict")

        cases = [
            (crawl_routes.crawl_historical, historical_request, "create_historical_crawl_task"),
            (crawl_routes.crawl_all, settings_request, "create_all_crawl_task"),
            (crawl_routes.crawl_incremental, historical_request, "create_incremental_crawl_task"),
            (crawl_routes.crawl_latest_until_complete, settings_request, "launch_latest_crawl_task"),
            (crawl_routes.crawl_by_time_range, range_request, "create_time_range_crawl_task"),
        ]

        for route, request, launcher_name in cases:
            with self.subTest(launcher=launcher_name), patch(
                f"backend.routes.crawl_routes.{launcher_name}",
                side_effect=original_error,
            ):
                with self.assertRaises(crawl_routes.HTTPException) as raised:
                    asyncio.run(route("group-1", request))

                self.assertIs(original_error, raised.exception)
                self.assertEqual(409, raised.exception.status_code)
                self.assertEqual("conflict", raised.exception.detail)

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
    def test_task_stopped_with_log_preserves_stop_log_semantics(self):
        from backend.services.crawl_service import _task_stopped_with_log

        with (
            patch("backend.services.crawl_service.is_task_stopped", return_value=False) as is_task_stopped,
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
        ):
            self.assertFalse(_task_stopped_with_log("task-1"))

        is_task_stopped.assert_called_once_with("task-1")
        add_task_log.assert_not_called()

        with (
            patch("backend.services.crawl_service.is_task_stopped", return_value=True) as is_task_stopped,
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
        ):
            self.assertTrue(_task_stopped_with_log("task-1"))

        is_task_stopped.assert_called_once_with("task-1")
        add_task_log.assert_called_once_with("task-1", "🛑 任务已停止")

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

        with patch("backend.services.crawl_service.fail_task_with_message_unless_stopped") as fail_task:
            _mark_expired_task("task-1", result)

        fail_task.assert_called_once_with(
            "task-1",
            "会员已过期",
            {"expired": True, "code": 1059, "message": "expired"},
            log_message="❌ 会员已过期: expired",
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_empty_official_crawl_stats_preserves_shape_and_independent_instances(self):
        from backend.services.crawl_service import _empty_official_crawl_stats

        first = _empty_official_crawl_stats()
        second = _empty_official_crawl_stats()

        self.assertEqual(
            {
                "new_topics": 0,
                "updated_topics": 0,
                "errors": 0,
                "pages": 0,
                "duplicates": 0,
                "source": "official",
            },
            first,
        )
        first["pages"] = 1
        self.assertEqual(0, second["pages"])

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_add_official_page_stats_preserves_accumulation_semantics(self):
        from backend.services.crawl_service import _add_official_page_stats, _empty_official_crawl_stats

        total_stats = _empty_official_crawl_stats()
        total_stats["duplicates"] = 2
        page_stats = {"new_topics": 3, "updated_topics": 4, "errors": 1}

        _add_official_page_stats(total_stats, page_stats)
        _add_official_page_stats(total_stats, {"new_topics": 1, "updated_topics": 0, "errors": 2})

        self.assertEqual(
            {
                "new_topics": 4,
                "updated_topics": 4,
                "errors": 3,
                "pages": 2,
                "duplicates": 2,
                "source": "official",
            },
            total_stats,
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_dedupe_official_page_topics_preserves_seen_and_missing_id_semantics(self):
        from backend.services.crawl_service import _dedupe_official_page_topics, _empty_official_crawl_stats

        total_stats = _empty_official_crawl_stats()
        seen_topic_ids: set[int] = set()
        first_topic = {"topic_id": "10", "title": "first"}
        missing_id_topic = {"title": "missing id"}
        last_topic = {"topic_id": 11, "title": "last"}

        unique_topics = _dedupe_official_page_topics(
            [
                first_topic,
                {"topic_id": 10, "title": "duplicate first"},
                missing_id_topic,
                {"topic_id": 0, "title": "duplicate missing id"},
                last_topic,
            ],
            seen_topic_ids,
            total_stats,
        )

        self.assertEqual([first_topic, missing_id_topic, last_topic], unique_topics)
        self.assertEqual({0, 10, 11}, seen_topic_ids)
        self.assertEqual(2, total_stats["duplicates"])

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_topic_id_preserves_integer_coercion_and_invalid_error(self):
        from backend.services.crawl_service import _official_topic_id

        self.assertEqual(0, _official_topic_id({}))
        self.assertEqual(0, _official_topic_id({"topic_id": None}))
        self.assertEqual(10, _official_topic_id({"topic_id": "10"}))
        self.assertEqual(11, _official_topic_id({"topic_id": 11}))
        with self.assertRaises(ValueError):
            _official_topic_id({"topic_id": "not-a-number"})

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_topic_comments_count_preserves_integer_coercion_and_invalid_error(self):
        from backend.services.crawl_service import _official_topic_comments_count

        self.assertEqual(0, _official_topic_comments_count({}))
        self.assertEqual(0, _official_topic_comments_count({"counts": None}))
        self.assertEqual(0, _official_topic_comments_count({"counts": {"comments": None}}))
        self.assertEqual(2, _official_topic_comments_count({"counts": {"comments": "2"}}))
        self.assertEqual(3, _official_topic_comments_count({"counts": {"comments": 3}}))
        with self.assertRaises(ValueError):
            _official_topic_comments_count({"counts": {"comments": "not-a-number"}})

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_add_official_import_result_preserves_status_mapping(self):
        from backend.services.crawl_service import _add_official_import_result

        stats = {"new_topics": 0, "updated_topics": 0, "errors": 0}

        _add_official_import_result(stats, "new")
        _add_official_import_result(stats, "updated")
        _add_official_import_result(stats, "error")
        _add_official_import_result(stats, "unexpected")

        self.assertEqual({"new_topics": 1, "updated_topics": 1, "errors": 2}, stats)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_import_topic_uses_storage_import_result_mapping(self):
        from backend.services.crawl_service import _official_import_topic
        from backend.storage.zsxq_database import TopicImportResult

        class FakeDb:
            def __init__(self):
                self.imported = []
                self.import_results = [
                    TopicImportResult("existing", topic_id="10"),
                    TopicImportResult("created", topic_id=None),
                    TopicImportResult("error", topic_id=12, error_message="boom"),
                ]

            def import_topic_data_with_result(self, topic_data):
                self.imported.append(topic_data)
                return self.import_results.pop(0)

        db = FakeDb()
        existing_topic = {"topic_id": "10"}
        missing_id_topic = {"title": "missing"}
        failed_topic = {"topic_id": 12}

        self.assertEqual("updated", _official_import_topic(db, "511", existing_topic))
        self.assertEqual("new", _official_import_topic(db, "group-1", missing_id_topic))
        self.assertEqual("error", _official_import_topic(db, "group-2", failed_topic))

        self.assertEqual([existing_topic, missing_id_topic, failed_topic], db.imported)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_topic_exists_delegates_to_storage_topic_exists(self):
        from backend.services.crawl_service import _official_topic_exists

        class FakeDb:
            def __init__(self):
                self.topic_exists_calls = []

            def topic_exists(self, topic_id):
                self.topic_exists_calls.append(topic_id)
                return topic_id == 10

        db = FakeDb()

        self.assertTrue(_official_topic_exists(db, "group-1", 10))
        self.assertFalse(_official_topic_exists(db, "group-2", 11))
        self.assertEqual([10, 11], db.topic_exists_calls)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_import_topics_preserves_comment_count_stats_and_commit(self):
        from backend.services.crawl_service import _official_import_topics

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        class FakeDb:
            def __init__(self):
                self.conn = FakeConnection()

        class FakeOfficialClient:
            def __init__(self):
                self.comment_topic_ids = []

            def get_topic_comments(self, topic_id):
                self.comment_topic_ids.append(topic_id)
                return [{"comment_id": f"comment-{topic_id}"}]

        db = FakeDb()
        client = FakeOfficialClient()
        normalized_topics = []

        def normalize_topic(topic, group_id, comments=None):
            normalized = {"topic_id": topic["topic_id"], "group_id": group_id, "comments": comments}
            normalized_topics.append(normalized)
            return normalized

        topics = [
            {"topic_id": "10", "counts": {"comments": "2"}},
            {"topic_id": 11, "counts": {"comments": 0}},
            {"topic_id": 12},
        ]

        with (
            patch("backend.services.crawl_service.normalize_official_topic", side_effect=normalize_topic),
            patch("backend.services.crawl_service._official_import_topic", side_effect=["new", "updated", "error"]) as import_topic,
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
        ):
            stats = _official_import_topics(db, client, "group-1", topics, "task-1")

        self.assertEqual({"new_topics": 1, "updated_topics": 1, "errors": 1}, stats)
        self.assertEqual(1, db.conn.commits)
        self.assertEqual([10], client.comment_topic_ids)
        self.assertEqual(
            [
                {"topic_id": "10", "group_id": "group-1", "comments": [{"comment_id": "comment-10"}]},
                {"topic_id": 11, "group_id": "group-1", "comments": None},
                {"topic_id": 12, "group_id": "group-1", "comments": None},
            ],
            normalized_topics,
        )
        self.assertEqual(
            [
                call(db, "group-1", normalized_topics[0]),
                call(db, "group-1", normalized_topics[1]),
                call(db, "group-1", normalized_topics[2]),
            ],
            import_topic.call_args_list,
        )
        add_task_log.assert_called_once_with("task-1", "📝 话题 10 官方评论拉取 1/2 条")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_import_page_topics_preserves_import_then_accumulate_order(self):
        from backend.services.crawl_service import _official_import_page_topics

        total_stats = {"pages": 0, "new_topics": 0, "updated_topics": 0, "errors": 0}
        db = object()
        client = object()
        topics = [{"topic_id": 1}]
        page_stats = {"new_topics": 1, "updated_topics": 2, "errors": 0}
        calls = []

        def import_topics(*args):
            calls.append(("import", args))
            return page_stats

        def add_page_stats(*args):
            calls.append(("add", args))

        with (
            patch("backend.services.crawl_service._official_import_topics", side_effect=import_topics),
            patch("backend.services.crawl_service._add_official_page_stats", side_effect=add_page_stats),
        ):
            result = _official_import_page_topics(total_stats, db, client, "group-1", topics, "task-1")

        self.assertIs(page_stats, result)
        self.assertEqual(
            [
                ("import", (db, client, "group-1", topics, "task-1")),
                ("add", (total_stats, page_stats)),
            ],
            calls,
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_next_page_cursor_requires_has_more_and_moving_cursor(self):
        from backend.services.crawl_service import _official_next_page_cursor

        self.assertIsNone(_official_next_page_cursor({"has_more": False, "next_end_time": "next"}, "same"))
        self.assertIsNone(_official_next_page_cursor({"has_more": True}, "same"))
        self.assertIsNone(_official_next_page_cursor({"has_more": True, "next_end_time": "same"}, "same"))
        self.assertEqual("next", _official_next_page_cursor({"has_more": True, "next_end_time": "next"}, "same"))

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_next_cursor_or_log_end_preserves_cursor_and_end_log(self):
        from backend.services.crawl_service import _official_next_cursor_or_log_end

        with patch("backend.services.crawl_service.add_task_log") as add_task_log:
            self.assertEqual(
                "next",
                _official_next_cursor_or_log_end(
                    "task-1",
                    {"has_more": True, "next_end_time": "next"},
                    "cursor",
                ),
            )
            add_task_log.assert_not_called()

            self.assertIsNone(
                _official_next_cursor_or_log_end(
                    "task-1",
                    {"has_more": False, "next_end_time": "next"},
                    "cursor",
                )
            )

        add_task_log.assert_called_once_with("task-1", "✅ 官方分页已无更多数据")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_pages_remaining_preserves_unbounded_and_limit_semantics(self):
        from backend.services.crawl_service import _official_pages_remaining

        self.assertTrue(_official_pages_remaining(None, {}))
        self.assertFalse(_official_pages_remaining(0, {"pages": 0}))
        self.assertTrue(_official_pages_remaining(2, {"pages": 1}))
        self.assertFalse(_official_pages_remaining(2, {"pages": 2}))

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_reached_before_start_preserves_none_equal_and_older_semantics(self):
        from backend.services.crawl_service import _official_reached_before_start

        start_dt = datetime(2026, 5, 1, tzinfo=timezone(timedelta(hours=8)))

        self.assertFalse(_official_reached_before_start(None, start_dt))
        self.assertFalse(_official_reached_before_start(start_dt, start_dt))
        self.assertFalse(_official_reached_before_start(start_dt + timedelta(seconds=1), start_dt))
        self.assertTrue(_official_reached_before_start(start_dt - timedelta(milliseconds=1), start_dt))

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_per_page_limit_preserves_default_and_cap(self):
        from backend.services.crawl_service import _official_per_page_limit

        self.assertEqual(20, _official_per_page_limit(None))
        self.assertEqual(20, _official_per_page_limit(0))
        self.assertEqual(1, _official_per_page_limit(1))
        self.assertEqual(30, _official_per_page_limit(30))
        self.assertEqual(30, _official_per_page_limit(31))

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_crawl_completion_message_preserves_mode_mapping(self):
        from backend.services.crawl_service import _official_crawl_completion_message

        self.assertEqual("官方最新采集完成", _official_crawl_completion_message("latest"))
        self.assertEqual("官方增量采集完成", _official_crawl_completion_message("incremental"))
        self.assertEqual("官方全量采集完成", _official_crawl_completion_message("all"))
        self.assertEqual("官方采集完成", _official_crawl_completion_message("unexpected"))

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_cursor_before_timestamp_preserves_offset_and_fallback(self):
        from backend.services.crawl_service import _official_cursor_before_timestamp

        self.assertEqual(
            "2026-05-06T23:59:59.999+0800",
            _official_cursor_before_timestamp("2026-05-07T00:00:00.000+0800"),
        )
        self.assertEqual(
            "2026-05-06T23:59:59.999+0800",
            _official_cursor_before_timestamp("2026-05-07T00:00:00.000+08:00"),
        )
        self.assertEqual("not-a-time", _official_cursor_before_timestamp("not-a-time"))

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_start_cursor_for_group_oldest_preserves_db_construction_and_allow_empty(self):
        from backend.services.crawl_service import _official_start_cursor_for_group_oldest

        db = object()

        with (
            patch("backend.services.crawl_service.ZSXQDatabase", return_value=db) as database_cls,
            patch("backend.services.crawl_service._official_start_cursor_from_oldest", return_value="cursor-1") as start_cursor,
        ):
            result = _official_start_cursor_for_group_oldest("group-1", "task-1", allow_empty=True)

        self.assertEqual("cursor-1", result)
        database_cls.assert_called_once_with("group-1")
        start_cursor.assert_called_once_with(db, "task-1", allow_empty=True)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_filter_official_topics_by_time_range_preserves_bounds_and_oldest_time(self):
        from backend.services.crawl_time_range import filter_official_topics_by_time_range

        start_dt = datetime(2026, 5, 1, tzinfo=timezone(timedelta(hours=8)))
        end_dt = datetime(2026, 5, 7, 23, 59, 59, tzinfo=timezone(timedelta(hours=8)))
        start_topic = {"topic_id": 1, "create_time": "2026-05-01T00:00:00.000+0800"}
        middle_topic = {"topic_id": 2, "create_time": "2026-05-03T12:00:00.000+0800"}
        end_topic = {"topic_id": 3, "create_time": "2026-05-07T23:59:59.000+0800"}

        filtered, oldest_dt = filter_official_topics_by_time_range(
            [
                {"topic_id": 0, "create_time": "not-a-time"},
                start_topic,
                middle_topic,
                end_topic,
                {"topic_id": 4, "create_time": "2026-04-30T23:59:59.000+0800"},
            ],
            start_dt,
            end_dt,
        )

        self.assertEqual([start_topic, middle_topic, end_topic], filtered)
        self.assertEqual(datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone(timedelta(hours=8))), oldest_dt)

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_new_official_topics_preserves_existing_check_order_and_missing_id_semantics(self):
        from backend.services.crawl_service import _new_official_topics

        existing_topic = {"topic_id": "10", "title": "existing"}
        missing_id_topic = {"title": "missing id"}
        new_topic = {"topic_id": 11, "title": "new"}
        db = object()

        with patch(
            "backend.services.crawl_service._official_topic_exists",
            side_effect=lambda _db, _group_id, topic_id: topic_id == 10,
        ) as topic_exists:
            new_topics = _new_official_topics(
                db,
                "group-1",
                [existing_topic, missing_id_topic, new_topic],
            )

        self.assertEqual([missing_id_topic, new_topic], new_topics)
        self.assertEqual(
            [
                call(db, "group-1", 10),
                call(db, "group-1", 0),
                call(db, "group-1", 11),
            ],
            topic_exists.call_args_list,
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_topics_to_import_for_mode_preserves_latest_and_page_logs(self):
        from backend.services.crawl_service import _official_topics_to_import_for_mode

        db = object()
        topics = [{"topic_id": 1}, {"topic_id": 2}]
        new_topics = [topics[1]]

        with (
            patch("backend.services.crawl_service._new_official_topics", return_value=new_topics) as new_official_topics,
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
        ):
            topics_to_import, should_stop = _official_topics_to_import_for_mode(
                "task-1",
                db,
                "group-1",
                "latest",
                topics,
            )

        self.assertEqual(new_topics, topics_to_import)
        self.assertFalse(should_stop)
        new_official_topics.assert_called_once_with(db, "group-1", topics)
        add_task_log.assert_called_once_with("task-1", "📊 官方页面分析: 2 个话题，1 个新话题")

        with (
            patch("backend.services.crawl_service._new_official_topics") as new_official_topics,
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
        ):
            topics_to_import, should_stop = _official_topics_to_import_for_mode(
                "task-1",
                db,
                "group-1",
                "incremental",
                topics,
            )

        self.assertIs(topics, topics_to_import)
        self.assertFalse(should_stop)
        new_official_topics.assert_not_called()
        add_task_log.assert_called_once_with("task-1", "📄 官方本页获取 2 个话题")

        with (
            patch("backend.services.crawl_service._new_official_topics", return_value=[]),
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
        ):
            topics_to_import, should_stop = _official_topics_to_import_for_mode(
                "task-1",
                db,
                "group-1",
                "latest",
                topics,
            )

        self.assertEqual([], topics_to_import)
        self.assertTrue(should_stop)
        self.assertEqual(
            [
                call("task-1", "📊 官方页面分析: 2 个话题，0 个新话题"),
                call("task-1", "✅ 本页话题均已存在，最新采集完成"),
            ],
            add_task_log.call_args_list,
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_run_official_crawl_pages_task_completes_through_task_runtime_guard(self):
        from backend.services.crawl_service import _run_official_crawl_pages_task

        with (
            patch("backend.services.crawl_service._official_topic_client", return_value=object()),
            patch("backend.services.crawl_service.ZSXQDatabase"),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service._fetch_unique_official_topic_page", return_value=None),
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.update_task") as update_task,
        ):
            _run_official_crawl_pages_task("task-1", "group-1", 1, 20, "latest")

        complete_task.assert_called_once_with(
            "task-1",
            "官方最新采集完成",
            {
                "new_topics": 0,
                "updated_topics": 0,
                "errors": 0,
                "pages": 0,
                "duplicates": 0,
                "source": "official",
            },
        )
        update_task.assert_not_called()

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_run_official_time_range_task_completes_through_task_runtime_guard(self):
        from backend.routes.crawl_routes import CrawlTimeRangeRequest
        from backend.services.crawl_service import _run_official_crawl_time_range_task

        start_dt = datetime(2026, 5, 1, tzinfo=timezone(timedelta(hours=8)))
        end_dt = datetime(2026, 5, 1, 23, 59, 59, tzinfo=timezone(timedelta(hours=8)))

        with (
            patch("backend.services.crawl_service._official_topic_client", return_value=object()),
            patch("backend.services.crawl_service.ZSXQDatabase"),
            patch("backend.services.crawl_service.is_task_stopped", return_value=False),
            patch("backend.services.crawl_service._fetch_unique_official_topic_page", return_value=None),
            patch("backend.services.crawl_service.add_task_log"),
            patch("backend.services.crawl_service.complete_task_unless_stopped") as complete_task,
            patch("backend.services.crawl_service.update_task") as update_task,
        ):
            _run_official_crawl_time_range_task(
                "task-1",
                "group-1",
                CrawlTimeRangeRequest(perPage=20, topicSource="official"),
                start_dt,
                end_dt,
            )

        complete_task.assert_called_once_with(
            "task-1",
            "官方时间区间采集完成",
            {
                "new_topics": 0,
                "updated_topics": 0,
                "errors": 0,
                "pages": 0,
                "duplicates": 0,
                "source": "official",
            },
        )
        update_task.assert_not_called()

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_topic_client_preserves_log_callback_binding(self):
        from backend.services.crawl_service import _official_topic_client

        with (
            patch("backend.services.crawl_service.OfficialTopicClient") as client_cls,
            patch("backend.services.crawl_service.add_task_log") as add_task_log,
        ):
            client = _official_topic_client("task-1")
            callback = client_cls.call_args.kwargs["log_callback"]
            callback("client log")

        self.assertIs(client, client_cls.return_value)
        client_cls.assert_called_once()
        add_task_log.assert_called_once_with("task-1", "client log")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_fetch_official_topic_page_preserves_call_shape_and_payload_topics(self):
        from backend.services.crawl_service import _fetch_official_topic_page

        payload = {"topics_brief": [{"topic_id": "1"}], "next_end_time": "next"}

        class Client:
            def __init__(self):
                self.calls = []

            def get_group_topics(self, group_id, **kwargs):
                self.calls.append((group_id, kwargs))
                return payload

        client = Client()
        page = _fetch_official_topic_page(client, "group-1", 30, "cursor-1")

        self.assertIs(payload, page.payload)
        self.assertEqual([{"topic_id": "1"}], page.topics)
        self.assertEqual(
            [
                (
                    "group-1",
                    {"limit": 30, "scope": "all", "end_time": "cursor-1"},
                )
            ],
            client.calls,
        )

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_fetch_unique_official_topic_page_preserves_empty_and_dedupe_semantics(self):
        from backend.services.crawl_service import (
            _empty_official_crawl_stats,
            _fetch_unique_official_topic_page,
        )

        first_topic = {"topic_id": "1"}
        duplicate_topic = {"topic_id": 1}
        last_topic = {"topic_id": 2}
        payload = {
            "topics_brief": [first_topic, duplicate_topic, last_topic],
            "next_end_time": "next",
        }

        class Client:
            def __init__(self):
                self.calls = []
                self.payload = payload

            def get_group_topics(self, group_id, **kwargs):
                self.calls.append((group_id, kwargs))
                return self.payload

        client = Client()
        total_stats = _empty_official_crawl_stats()
        seen_topic_ids: set[int] = set()

        with patch("backend.services.crawl_service.add_task_log") as add_task_log:
            page = _fetch_unique_official_topic_page(
                "task-1",
                client,
                "group-1",
                30,
                "cursor-1",
                seen_topic_ids,
                total_stats,
            )

        self.assertIs(payload, page.payload)
        self.assertEqual([first_topic, duplicate_topic, last_topic], page.topics)
        self.assertEqual([first_topic, last_topic], page.unique_topics)
        self.assertEqual({1, 2}, seen_topic_ids)
        self.assertEqual(1, total_stats["duplicates"])
        add_task_log.assert_not_called()
        self.assertEqual(
            [
                (
                    "group-1",
                    {"limit": 30, "scope": "all", "end_time": "cursor-1"},
                )
            ],
            client.calls,
        )

        client.payload = {"topics_brief": []}
        with patch("backend.services.crawl_service.add_task_log") as add_task_log:
            empty_page = _fetch_unique_official_topic_page(
                "task-1",
                client,
                "group-1",
                30,
                None,
                seen_topic_ids,
                total_stats,
            )

        self.assertIsNone(empty_page)
        self.assertEqual(1, total_stats["duplicates"])
        add_task_log.assert_called_once_with("task-1", "📭 无更多数据，任务结束")

    @unittest.skipUnless(HAS_CRAWL_ROUTE_DEPS, "crawl route dependencies are not installed")
    def test_official_topic_page_empty_preserves_log_and_truthiness(self):
        from backend.services.crawl_service import _official_topic_page_empty

        with patch("backend.services.crawl_service.add_task_log") as add_task_log:
            self.assertFalse(_official_topic_page_empty("task-1", [{"topic_id": 1}]))
            add_task_log.assert_not_called()

            self.assertTrue(_official_topic_page_empty("task-1", []))

        add_task_log.assert_called_once_with("task-1", "📭 无更多数据，任务结束")


if __name__ == "__main__":
    unittest.main()
