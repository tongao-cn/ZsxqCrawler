import asyncio
import unittest

from backend.services.columns_column_service import process_column, process_column_topic
from backend.services.columns_fetch_summary import ColumnFetchStats


async def no_sleep(_seconds):
    return None


class FakeColumnsDbForColumn:
    def __init__(self):
        self.inserted_columns = []

    def insert_column(self, group_id, column):
        self.inserted_columns.append((group_id, column))


class ColumnsColumnServiceTests(unittest.TestCase):
    def test_process_column_topic_returns_skip_counts_for_existing_topic(self):
        config = {
            "incremental_mode": True,
            "items_per_batch": 10,
            "long_sleep_min": 0,
            "long_sleep_max": 0,
            "crawl_interval_min": 0,
            "crawl_interval_max": 0,
        }

        stats = asyncio.run(
            process_column_topic(
                column_id=3,
                config=config,
                current_request_count=0,
                db=object(),
                fetch_topic_detail=lambda *args: self.fail("fetch_topic_detail should not be called"),
                group_id="123",
                headers={},
                prepare_column_topic=lambda *args: (10, "title", True),
                process_topic_resources=lambda *args: self.fail("process_topic_resources should not be called"),
                save_topic_detail=lambda *args: self.fail("save_topic_detail should not be called"),
                task_id="task-1",
                topic={},
                topic_idx=1,
                total_topics=2,
            )
        )

        self.assertEqual(1, stats.topics_count)
        self.assertEqual(1, stats.skipped_count)
        self.assertEqual(0, stats.request_count)

    def test_process_column_topic_aggregates_detail_and_resource_counts(self):
        config = {
            "incremental_mode": False,
            "items_per_batch": 10,
            "long_sleep_min": 0,
            "long_sleep_max": 0,
            "crawl_interval_min": 0,
            "crawl_interval_max": 0,
        }
        topic_detail = {"succeeded": True, "resp_data": {"topic": {"topic_id": 10}}}

        async def fake_fetch_topic_detail(*args):
            return topic_detail, 1

        async def fake_process_topic_resources(*args):
            return ColumnFetchStats(files_count=2, files_skipped=3, images_count=4, videos_count=5, videos_skipped=6, request_count=7)

        stats = asyncio.run(
            process_column_topic(
                column_id=3,
                config=config,
                current_request_count=0,
                db=object(),
                fetch_topic_detail=fake_fetch_topic_detail,
                group_id="123",
                headers={},
                prepare_column_topic=lambda *args: (10, "title", False),
                process_topic_resources=fake_process_topic_resources,
                save_topic_detail=lambda *args: True,
                task_id="task-1",
                topic={},
                topic_idx=1,
                total_topics=2,
            )
        )

        self.assertEqual(1, stats.topics_count)
        self.assertEqual(1, stats.details_count)
        self.assertEqual(2, stats.files_count)
        self.assertEqual(4, stats.images_count)
        self.assertEqual(5, stats.videos_count)
        self.assertEqual(3, stats.files_skipped)
        self.assertEqual(6, stats.videos_skipped)
        self.assertEqual(8, stats.request_count)

    def test_process_column_aggregates_topics_and_updates_progress(self):
        config = {
            "items_per_batch": 10,
            "long_sleep_min": 0,
            "long_sleep_max": 0,
            "crawl_interval_min": 0,
            "crawl_interval_max": 0,
        }
        column = {"column_id": 3, "name": "专栏", "statistics": {"topics_count": 2}}
        topics = [{"topic_id": 10}, {"topic_id": 11}]
        db = FakeColumnsDbForColumn()
        updates = []

        async def fake_process_column_topic(*args):
            if len(updates) == 0:
                return ColumnFetchStats(
                    topics_count=1,
                    details_count=1,
                    files_count=2,
                    images_count=3,
                    videos_count=4,
                    files_skipped=5,
                    videos_skipped=6,
                    request_count=7,
                )
            return ColumnFetchStats(topics_count=1, skipped_count=1, request_count=2)

        stats = asyncio.run(
            process_column(
                add_task_log=lambda _task_id, _message: None,
                base_stats=ColumnFetchStats(details_count=10, files_count=20, images_count=30, videos_count=40),
                column=column,
                col_idx=1,
                config=config,
                current_request_count=0,
                db=db,
                fetch_column_topics=lambda *_args: (topics, 1),
                group_id="123",
                headers={},
                is_task_stopped=lambda _task_id: False,
                process_column_topic=fake_process_column_topic,
                random_uniform=lambda _min, _max: 0,
                sleep=no_sleep,
                task_id="task-1",
                total_columns=1,
                update_task=lambda *args: updates.append(args),
            )
        )

        self.assertEqual([(123, column)], db.inserted_columns)
        self.assertEqual(1, stats.columns_count)
        self.assertEqual(2, stats.topics_count)
        self.assertEqual(1, stats.details_count)
        self.assertEqual(2, stats.files_count)
        self.assertEqual(3, stats.images_count)
        self.assertEqual(4, stats.videos_count)
        self.assertEqual(1, stats.skipped_count)
        self.assertEqual(5, stats.files_skipped)
        self.assertEqual(6, stats.videos_skipped)
        self.assertEqual(10, stats.request_count)
        self.assertEqual(
            [("task-1", "running", "进度: 11 篇文章, 22 个文件, 44 个视频, 33 张图片")],
            updates,
        )


if __name__ == "__main__":
    unittest.main()
