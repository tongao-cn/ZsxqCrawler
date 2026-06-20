import unittest

from backend.crawlers.topic_ingestion import TopicIngestionMixin
from backend.crawlers.topic_pagination import (
    TOPIC_PAGINATION_MAX_RETRIES_PER_PAGE,
    TopicPaginationMixin,
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


def _topic(topic_id, create_time="2026-02-01T10:00:00.000+0800"):
    return {"topic_id": topic_id, "create_time": create_time}


def _topic_page(topics):
    return {"succeeded": True, "resp_data": {"topics": list(topics)}}


class FakeTopicPaginationDb:
    def __init__(self, existing_topic_ids=()):
        self.conn = FakeTopicIngestionConnection()
        self.existing_topic_ids = set(existing_topic_ids)
        self.topic_exists_calls = []
        self.imported_topics = []
        self.timestamp_info = {
            "has_data": True,
            "oldest_timestamp": "2026-02-01T10:00:00.000+0800",
            "newest_timestamp": "2026-02-03T10:00:00.000+0800",
            "total_topics": len(self.existing_topic_ids),
        }

    def get_timestamp_range_info(self):
        return dict(self.timestamp_info)

    def topic_exists(self, topic_id):
        self.topic_exists_calls.append(topic_id)
        return topic_id in self.existing_topic_ids

    def import_topic_data(self, topic_data):
        self.imported_topics.append(topic_data)
        if topic_data.get("import_ok", True):
            self.existing_topic_ids.add(topic_data.get("topic_id"))
            return True
        return False


class FakeTopicPaginationCrawler(TopicPaginationMixin):
    def __init__(self, db, pages, store_results=()):
        self.db = db
        self.group_id = "303"
        self.fetch_pages = list(pages)
        self.fetch_calls = []
        self.store_results = list(store_results)
        self.stored_batches = []
        self.logs = []
        self.debug_mode = False
        self.timestamp_offset_ms = 1
        self.delay_calls = 0

    def is_stopped(self):
        return False

    def log(self, message):
        self.logs.append(message)

    def fetch_topics_safe(self, **kwargs):
        self.fetch_calls.append(kwargs)
        return self.fetch_pages.pop(0)

    def store_batch_data(self, data):
        self.stored_batches.append(data)
        if self.store_results:
            return self.store_results.pop(0)
        return {"new_topics": 0, "updated_topics": 0, "errors": 0}

    def check_page_long_delay(self):
        self.delay_calls += 1


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

    def test_crawl_incremental_stops_on_short_all_existing_page_without_storing(self):
        db = FakeTopicPaginationDb(existing_topic_ids={101, 102})
        crawler = FakeTopicPaginationCrawler(
            db,
            [_topic_page([_topic(101), _topic(102)])],
        )

        stats = crawler.crawl_incremental(pages=5, per_page=3)

        self.assertEqual({"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0}, stats)
        self.assertEqual([101, 102], db.topic_exists_calls)
        self.assertEqual([], crawler.stored_batches)

    def test_crawl_all_historical_stores_short_existing_page_before_bottom_stop(self):
        db = FakeTopicPaginationDb(existing_topic_ids={101, 102})
        crawler = FakeTopicPaginationCrawler(
            db,
            [_topic_page([_topic(101), _topic(102)])],
            [{"new_topics": 0, "updated_topics": 2, "errors": 0}],
        )

        stats = crawler.crawl_all_historical(per_page=3, auto_confirm=True)

        self.assertEqual({"new_topics": 0, "updated_topics": 2, "errors": 0, "pages": 1}, stats)
        self.assertEqual([101, 102], db.topic_exists_calls)
        self.assertEqual(1, len(crawler.stored_batches))

    def test_crawl_latest_until_complete_returns_without_storing_when_page_all_existing(self):
        db = FakeTopicPaginationDb(existing_topic_ids={101, 102})
        crawler = FakeTopicPaginationCrawler(
            db,
            [_topic_page([_topic(101), _topic(102)])],
        )

        stats = crawler.crawl_latest_until_complete(per_page=2)

        self.assertEqual({"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0}, stats)
        self.assertEqual([101, 102], db.topic_exists_calls)
        self.assertEqual([], crawler.stored_batches)
        self.assertEqual([], db.imported_topics)

    def test_crawl_latest_until_complete_imports_only_new_topics_for_mixed_page(self):
        existing_topic = _topic(101)
        new_topic = _topic(102)
        db = FakeTopicPaginationDb(existing_topic_ids={101})
        crawler = FakeTopicPaginationCrawler(
            db,
            [_topic_page([existing_topic, new_topic]), _topic_page([])],
        )

        stats = crawler.crawl_latest_until_complete(per_page=2)

        self.assertEqual({"new_topics": 1, "updated_topics": 0, "errors": 0, "pages": 1}, stats)
        self.assertEqual([101, 102, 102], db.topic_exists_calls)
        self.assertEqual([new_topic], db.imported_topics)
        self.assertEqual([], crawler.stored_batches)
        self.assertEqual(1, db.conn.commits)

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
