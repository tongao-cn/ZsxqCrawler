import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch


class OfficialTopicCrawlRunnerTests(unittest.TestCase):
    def test_run_official_crawl_pages_completes_empty_page_with_stats(self):
        from backend.services.official_topic_crawl_runner import (
            OfficialCrawlPagesTarget,
            OfficialTopicCrawlRuntime,
            run_official_crawl_pages,
        )

        completed = []
        logs = []

        runtime = OfficialTopicCrawlRuntime(
            lambda task_id, message: logs.append((task_id, message)),
            lambda _task_id: False,
            lambda task_id, message, stats: completed.append((task_id, message, stats)),
            lambda _task_id: object(),
            lambda _group_id: object(),
        )

        with patch("backend.services.official_topic_crawl_runner.fetch_unique_official_topic_page", return_value=None):
            run_official_crawl_pages(
                runtime,
                OfficialCrawlPagesTarget("task-1", "group-1", 1, 20, "latest"),
            )

        self.assertEqual([], logs)
        self.assertEqual(
            [
                (
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
            ],
            completed,
        )

    def test_run_official_crawl_time_range_logs_cap_and_completes_empty_page(self):
        from backend.services.official_topic_crawl_runner import (
            OfficialCrawlTimeRangeTarget,
            OfficialTopicCrawlRuntime,
            run_official_crawl_time_range,
        )

        completed = []
        logs = []
        start_dt = datetime(2026, 5, 1, tzinfo=timezone(timedelta(hours=8)))
        end_dt = datetime(2026, 5, 1, 23, 59, 59, tzinfo=timezone(timedelta(hours=8)))

        runtime = OfficialTopicCrawlRuntime(
            lambda task_id, message: logs.append((task_id, message)),
            lambda _task_id: False,
            lambda task_id, message, stats: completed.append((task_id, message, stats)),
            lambda _task_id: object(),
            lambda _group_id: object(),
        )

        with patch("backend.services.official_topic_crawl_runner.fetch_unique_official_topic_page", return_value=None):
            run_official_crawl_time_range(
                runtime,
                OfficialCrawlTimeRangeTarget(
                    "task-1",
                    "group-1",
                    SimpleNamespace(perPage=31),
                    start_dt,
                    end_dt,
                ),
            )

        self.assertEqual(
            [
                ("task-1", "🔁 使用官方话题采集流程（MCP HTTP）"),
                ("task-1", "ℹ️ 官方接口单页上限按 30 处理"),
            ],
            logs,
        )
        self.assertEqual(
            [
                (
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
            ],
            completed,
        )


if __name__ == "__main__":
    unittest.main()
