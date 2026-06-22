import unittest
from types import SimpleNamespace

from backend.services.legacy_topic_crawl_runner import (
    LEGACY_CRAWL_ALL,
    LEGACY_CRAWL_HISTORICAL,
    LEGACY_CRAWL_INCREMENTAL,
    LEGACY_CRAWL_LATEST,
    LegacyTopicCrawlRuntime,
    LegacyTopicCrawlTarget,
    run_legacy_topic_crawl,
)


class RecordingCrawler:
    def __init__(self, incremental_result=None, all_result=None, latest_result=None):
        self.db = self
        self.incremental_calls = []
        self.all_calls = []
        self.latest_calls = 0
        self.incremental_result = incremental_result or {"new_topics": 3, "updated_topics": 4}
        self.all_result = all_result or {"new_topics": 5, "updated_topics": 6, "pages": 7}
        self.latest_result = latest_result or {"new_topics": 1, "updated_topics": 2}

    def crawl_incremental(self, pages, per_page):
        self.incremental_calls.append((pages, per_page))
        return self.incremental_result

    def crawl_all_historical(self, **kwargs):
        self.all_calls.append(kwargs)
        return self.all_result

    def crawl_latest_until_complete(self):
        self.latest_calls += 1
        return self.latest_result

    def get_database_stats(self):
        return {"topics": 10, "users": 2}


class FailingLatestCrawler(RecordingCrawler):
    def crawl_latest_until_complete(self):
        self.latest_calls += 1
        raise RuntimeError("boom")


class LegacyTopicCrawlRunnerTests(unittest.TestCase):
    def _runtime(self, crawler, *, stopped=False):
        calls = SimpleNamespace(
            update=[],
            logs=[],
            completed=[],
            failed=[],
            factory=[],
        )

        def crawler_factory(task_id, group_id, crawl_settings):
            calls.factory.append((task_id, group_id, crawl_settings))
            return crawler

        runtime = LegacyTopicCrawlRuntime(
            update_task=lambda *args: calls.update.append(args),
            add_task_log=lambda *args: calls.logs.append(args),
            task_stopped=lambda _task_id: stopped,
            complete_task=lambda *args: calls.completed.append(args),
            fail_task=lambda *args, **kwargs: calls.failed.append((args, kwargs)),
            crawler_factory=crawler_factory,
        )
        return runtime, calls

    def test_run_legacy_topic_crawl_completes_non_range_modes(self):
        cases = [
            (
                LEGACY_CRAWL_HISTORICAL,
                LegacyTopicCrawlTarget("task-1", "group-1", LEGACY_CRAWL_HISTORICAL, None, 3, 25),
                "开始爬取历史数据 3 页...",
                "历史数据爬取完成",
                {"new_topics": 3, "updated_topics": 4},
                lambda crawler: self.assertEqual([(3, 25)], crawler.incremental_calls),
            ),
            (
                LEGACY_CRAWL_ALL,
                LegacyTopicCrawlTarget("task-1", "group-1", LEGACY_CRAWL_ALL),
                "开始全量爬取...",
                "全量爬取完成",
                {"new_topics": 5, "updated_topics": 6, "pages": 7},
                lambda crawler: self.assertEqual(
                    [{"per_page": 20, "auto_confirm": True}],
                    crawler.all_calls,
                ),
            ),
            (
                LEGACY_CRAWL_INCREMENTAL,
                LegacyTopicCrawlTarget("task-1", "group-1", LEGACY_CRAWL_INCREMENTAL, None, 4, 26),
                "开始增量爬取...",
                "增量爬取完成",
                {"new_topics": 3, "updated_topics": 4},
                lambda crawler: self.assertEqual([(4, 26)], crawler.incremental_calls),
            ),
            (
                LEGACY_CRAWL_LATEST,
                LegacyTopicCrawlTarget("task-1", "group-1", LEGACY_CRAWL_LATEST),
                "开始获取最新记录...",
                "获取最新记录完成",
                {"new_topics": 1, "updated_topics": 2},
                lambda crawler: self.assertEqual(1, crawler.latest_calls),
            ),
        ]

        for case_name, target, running_message, completed_message, result, assert_crawler in cases:
            with self.subTest(case_name=case_name):
                crawler = RecordingCrawler()
                runtime, calls = self._runtime(crawler)

                run_legacy_topic_crawl(runtime, target)

            self.assertEqual([("task-1", "running", running_message)], calls.update)
            self.assertEqual([("task-1", completed_message, result)], calls.completed)
            self.assertEqual([], calls.failed)
            self.assertEqual([("task-1", "group-1", target.crawl_settings)], calls.factory)
            assert_crawler(crawler)

    def test_run_legacy_topic_crawl_fails_expired_result_instead_of_completing(self):
        expired_payload = {"expired": True, "code": 1059, "message": "expired"}
        crawler = RecordingCrawler(incremental_result=expired_payload)
        runtime, calls = self._runtime(crawler)

        run_legacy_topic_crawl(
            runtime,
            LegacyTopicCrawlTarget("task-1", "group-1", LEGACY_CRAWL_INCREMENTAL, None, 4, 26),
        )

        self.assertEqual([], calls.completed)
        self.assertEqual(
            [
                (
                    ("task-1", "会员已过期", {"expired": True, "code": 1059, "message": "expired"}),
                    {"log_message": "❌ 会员已过期: expired"},
                )
            ],
            calls.failed,
        )

    def test_run_legacy_topic_crawl_wraps_mode_specific_failures(self):
        crawler = FailingLatestCrawler()
        runtime, calls = self._runtime(crawler)

        run_legacy_topic_crawl(
            runtime,
            LegacyTopicCrawlTarget("task-1", "group-1", LEGACY_CRAWL_LATEST),
        )

        self.assertEqual([], calls.completed)
        self.assertEqual(
            [(("task-1", "获取最新记录失败: boom"), {"log_message": "❌ 获取最新记录失败: boom"})],
            calls.failed,
        )

    def test_run_legacy_topic_crawl_historical_stops_before_update(self):
        crawler = RecordingCrawler()
        runtime, calls = self._runtime(crawler, stopped=True)

        run_legacy_topic_crawl(
            runtime,
            LegacyTopicCrawlTarget("task-1", "group-1", LEGACY_CRAWL_HISTORICAL, None, 3, 25),
        )

        self.assertEqual([], calls.update)
        self.assertEqual([], calls.factory)
        self.assertEqual([], calls.completed)
        self.assertEqual([], calls.failed)


if __name__ == "__main__":
    unittest.main()
