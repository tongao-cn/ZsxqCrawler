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

    def set_custom_intervals(self, **kwargs):
        self.interval_kwargs = kwargs

    def crawl_latest_until_complete(self):
        return {"new_topics": 1, "updated_topics": 2}


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
            patch("backend.services.crawl_service.update_task") as update_task,
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
        update_task.assert_any_call("task-1", "failed", "官方增量采集失败: 数据库为空")

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
        update_task.assert_any_call(
            "task-1",
            "completed",
            "时间区间爬取完成",
            {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0},
        )

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
        update_task.assert_any_call(
            "task-1",
            "completed",
            "时间区间爬取完成",
            {"new_topics": 2, "updated_topics": 1, "errors": 0, "pages": 1},
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
        update_task.assert_any_call(
            "task-1",
            "completed",
            "时间区间爬取完成",
            {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 1},
        )

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
        update_task.assert_any_call(
            "task-1",
            "completed",
            "获取最新记录完成",
            {"new_topics": 1, "updated_topics": 2},
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
    def test_official_import_topic_preserves_existence_query_group_id_and_result_mapping(self):
        from backend.services.crawl_service import _official_import_topic

        class FakeCursor:
            def __init__(self):
                self.execute_calls = []
                self.rows = [("10",), None, None]

            def execute(self, query, params):
                self.execute_calls.append((query, params))

            def fetchone(self):
                return self.rows.pop(0)

        class FakeDb:
            def __init__(self):
                self.cursor = FakeCursor()
                self.imported = []
                self.import_results = [True, True, False]

            def import_topic_data(self, topic_data):
                self.imported.append(topic_data)
                return self.import_results.pop(0)

        db = FakeDb()
        existing_topic = {"topic_id": "10"}
        missing_id_topic = {"title": "missing"}
        failed_topic = {"topic_id": 12}

        self.assertEqual("updated", _official_import_topic(db, "511", existing_topic))
        self.assertEqual("new", _official_import_topic(db, "group-1", missing_id_topic))
        self.assertEqual("error", _official_import_topic(db, "group-2", failed_topic))

        self.assertEqual(
            [
                ("SELECT topic_id FROM topics WHERE topic_id = ? AND group_id = ?", ("10", 511)),
                ("SELECT topic_id FROM topics WHERE topic_id = ? AND group_id = ?", (None, "group-1")),
                ("SELECT topic_id FROM topics WHERE topic_id = ? AND group_id = ?", (12, "group-2")),
            ],
            db.cursor.execute_calls,
        )
        self.assertEqual([existing_topic, missing_id_topic, failed_topic], db.imported)

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
    def test_official_next_page_cursor_requires_has_more_and_moving_cursor(self):
        from backend.services.crawl_service import _official_next_page_cursor

        self.assertIsNone(_official_next_page_cursor({"has_more": False, "next_end_time": "next"}, "same"))
        self.assertIsNone(_official_next_page_cursor({"has_more": True}, "same"))
        self.assertIsNone(_official_next_page_cursor({"has_more": True, "next_end_time": "same"}, "same"))
        self.assertEqual("next", _official_next_page_cursor({"has_more": True, "next_end_time": "next"}, "same"))

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
    def test_filter_official_topics_by_time_range_preserves_bounds_and_oldest_time(self):
        from backend.services.crawl_service import _filter_official_topics_by_time_range

        start_dt = datetime(2026, 5, 1, tzinfo=timezone(timedelta(hours=8)))
        end_dt = datetime(2026, 5, 7, 23, 59, 59, tzinfo=timezone(timedelta(hours=8)))
        start_topic = {"topic_id": 1, "create_time": "2026-05-01T00:00:00.000+0800"}
        middle_topic = {"topic_id": 2, "create_time": "2026-05-03T12:00:00.000+0800"}
        end_topic = {"topic_id": 3, "create_time": "2026-05-07T23:59:59.000+0800"}

        filtered, oldest_dt = _filter_official_topics_by_time_range(
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


if __name__ == "__main__":
    unittest.main()
