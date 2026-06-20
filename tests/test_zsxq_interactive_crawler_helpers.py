import unittest

from backend.crawlers.topic_ingestion import TopicIngestionMixin
from backend.crawlers.topic_pagination import (
    TOPIC_PAGINATION_MAX_RETRIES_PER_PAGE,
    _empty_topic_pagination_stats,
    _offset_zsxq_end_time,
    _offset_zsxq_end_time_by_hours,
)
from backend.crawlers.topic_crawler import ZSXQTopicCrawler
from backend.storage.zsxq_database import TopicImportResult


class FakeTopicIngestionConnection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakeTopicIngestionDb:
    def __init__(self, results):
        self.conn = FakeTopicIngestionConnection()
        self.results = list(results)
        self.imported_topics = []
        self.imported_comments = []

    def import_topic_data_with_result(self, topic_data):
        self.imported_topics.append(topic_data)
        return self.results.pop(0)

    def import_additional_comments(self, topic_id, comments):
        self.imported_comments.append((topic_id, comments))


class FakeTopicIngestionCrawler(TopicIngestionMixin):
    def __init__(self, db):
        self.db = db
        self.group_id = "123"
        self.logs = []
        self.comment_fetches = []

    def is_stopped(self):
        return False

    def log(self, message):
        self.logs.append(message)

    def fetch_all_comments(self, topic_id, comments_count):
        self.comment_fetches.append((topic_id, comments_count))
        return [{"comment_id": f"comment-{topic_id}"}]


class TopicCrawlerPaginationTests(unittest.TestCase):
    def test_store_batch_data_uses_topic_import_result_for_stats(self):
        db = FakeTopicIngestionDb(
            [
                TopicImportResult("created", topic_id=101),
                TopicImportResult("existing", topic_id=102),
                TopicImportResult("error", topic_id=103, error_message="boom"),
            ]
        )
        crawler = FakeTopicIngestionCrawler(db)

        stats = crawler.store_batch_data(
            {
                "succeeded": True,
                "resp_data": {
                    "topics": [
                        {"topic_id": 101, "comments_count": 9},
                        {"topic_id": 102, "comments_count": 0},
                        {"topic_id": 103, "comments_count": 12},
                    ]
                },
            }
        )

        self.assertEqual({"new_topics": 1, "updated_topics": 1, "errors": 1}, stats)
        self.assertEqual(1, db.conn.commits)
        self.assertEqual(
            [
                {"topic_id": 101, "comments_count": 9},
                {"topic_id": 102, "comments_count": 0},
                {"topic_id": 103, "comments_count": 12},
            ],
            db.imported_topics,
        )
        self.assertEqual([(101, 9)], crawler.comment_fetches)
        self.assertEqual([(101, [{"comment_id": "comment-101"}])], db.imported_comments)
        self.assertIn("⚠️ 话题 103 导入失败，已回滚该话题写入", crawler.logs)

    def test_topic_pagination_max_retries_per_page_preserves_current_value(self):
        self.assertEqual(10, TOPIC_PAGINATION_MAX_RETRIES_PER_PAGE)

    def test_empty_topic_pagination_stats_preserves_shape_and_independent_instances(self):
        first = _empty_topic_pagination_stats()
        second = _empty_topic_pagination_stats()

        self.assertEqual(
            {'new_topics': 0, 'updated_topics': 0, 'errors': 0, 'pages': 0},
            first,
        )
        first['pages'] = 1
        self.assertEqual(0, second['pages'])

    def test_offset_zsxq_end_time_formats_without_timezone_colon(self):
        self.assertEqual(
            "2026-02-01T09:59:59.999+0800",
            _offset_zsxq_end_time("2026-02-01T10:00:00.000+0800", 1),
        )

    def test_offset_zsxq_end_time_by_hours_formats_without_timezone_colon(self):
        self.assertEqual(
            "2026-02-01T09:00:00.000+0800",
            _offset_zsxq_end_time_by_hours("2026-02-01T10:00:00.000+0800", 1),
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
