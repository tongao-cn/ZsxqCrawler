import unittest

from backend.crawlers.topic_pagination import _offset_zsxq_end_time
from backend.crawlers.topic_crawler import ZSXQTopicCrawler


class TopicCrawlerPaginationTests(unittest.TestCase):
    def test_offset_zsxq_end_time_formats_without_timezone_colon(self):
        self.assertEqual(
            "2026-02-01T09:59:59.999+0800",
            _offset_zsxq_end_time("2026-02-01T10:00:00.000+0800", 1),
        )

    def test_topic_next_end_time_returns_none_when_last_topic_has_no_create_time(self):
        crawler = object.__new__(ZSXQTopicCrawler)
        crawler.timestamp_offset_ms = 1
        crawler.logs = []
        crawler.log = crawler.logs.append

        next_end_time = ZSXQTopicCrawler._topic_next_end_time(
            crawler,
            [{"create_time": "2026-02-01T10:00:00.000+0800"}, {}],
        )

        self.assertIsNone(next_end_time)
        self.assertIn("缺少 create_time", crawler.logs[-1])

    def test_topic_next_end_time_moves_before_last_topic_time(self):
        crawler = object.__new__(ZSXQTopicCrawler)
        crawler.timestamp_offset_ms = 1
        crawler.log = lambda message: None

        next_end_time = ZSXQTopicCrawler._topic_next_end_time(
            crawler,
            [{"create_time": "2026-02-01T10:00:00.000+0800"}],
        )

        self.assertEqual("2026-02-01T09:59:59.999+0800", next_end_time)

    def test_topic_next_end_time_returns_original_when_timestamp_adjustment_fails(self):
        crawler = object.__new__(ZSXQTopicCrawler)
        crawler.timestamp_offset_ms = 1
        crawler.logs = []
        crawler.log = crawler.logs.append

        next_end_time = ZSXQTopicCrawler._topic_next_end_time(
            crawler,
            [{"create_time": "not-a-time"}],
        )

        self.assertEqual("not-a-time", next_end_time)
        self.assertIn("时间戳调整失败", crawler.logs[-1])


if __name__ == "__main__":
    unittest.main()
