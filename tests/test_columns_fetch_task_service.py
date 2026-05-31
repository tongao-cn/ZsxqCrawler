import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.services.columns_fetch_summary import ColumnFetchStats


class FakeColumnsDb:
    def __init__(self):
        self.closed = False
        self.crawl_logs = []
        self.updated_logs = []

    def close(self):
        self.closed = True

    def start_crawl_log(self, group_id, crawl_type):
        self.crawl_logs.append((group_id, crawl_type))
        return 9

    def update_crawl_log(self, log_id, **fields):
        self.updated_logs.append((log_id, fields))


class FakeColumnsReadDb:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def get_columns(self, group_id):
        return [{"column_id": 1, "group_id": group_id}]

    def get_stats(self, group_id):
        return {"group_id": group_id, "columns": 1}

    def get_column_topics(self, column_id, group_id):
        return [{"topic_id": 10, "column_id": column_id, "group_id": group_id}]

    def get_column(self, column_id, group_id):
        return {"column_id": column_id, "group_id": group_id}

    def get_topic_detail(self, topic_id, group_id):
        return {
            "topic_id": topic_id,
            "group_id": group_id,
            "full_text": "",
            "raw_json": json.dumps({"type": "talk", "talk": {"text": "正文"}}),
        }

    def clear_all_data(self, group_id):
        return {"columns": 1, "group_id": group_id}


class ColumnsFetchTaskServiceTests(unittest.TestCase):
    def test_columns_db_closes_database(self):
        from backend.services import columns_fetch_task_service as service

        fake_db = FakeColumnsDb()

        with patch.object(service, "get_columns_db", return_value=fake_db):
            with service.columns_db("123") as db:
                self.assertIs(fake_db, db)
                self.assertFalse(fake_db.closed)

        self.assertTrue(fake_db.closed)

    def test_read_responses_use_database_and_enrich_topic_detail(self):
        from backend.services import columns_fetch_task_service as service

        fake_db = FakeColumnsReadDb()

        with patch.object(service, "get_columns_db", return_value=fake_db):
            self.assertEqual(
                {"columns": [{"column_id": 1, "group_id": 123}], "stats": {"group_id": 123, "columns": 1}},
                service.get_group_columns_response("123"),
            )
            self.assertEqual(
                {
                    "column": {"column_id": 1, "group_id": "123"},
                    "topics": [{"topic_id": 10, "column_id": 1, "group_id": "123"}],
                },
                service.get_column_topics_response("123", 1),
            )
            detail = service.get_column_topic_detail_response("123", 10)
            self.assertEqual("正文", detail["full_text"])
            self.assertEqual({"success": True, "message": "已清空专栏数据", "deleted": {"columns": 1, "group_id": 123}}, service.delete_all_columns_response("123"))

        self.assertTrue(fake_db.closed)

    def test_complete_empty_columns_task_logs_and_updates_task(self):
        from backend.services import columns_fetch_task_service as service

        with (
            patch.object(service, "add_task_log") as add_log,
            patch.object(service, "update_task") as update,
        ):
            service.complete_empty_columns_task("task-1")

        add_log.assert_called_once_with("task-1", "ℹ️ 该群组没有专栏内容")
        update.assert_called_once_with("task-1", "completed", "该群组没有专栏内容")

    def test_run_columns_fetch_task_completes_empty_catalog(self):
        from backend.services import columns_fetch_task_service as service

        fake_db = FakeColumnsDb()
        settings = SimpleNamespace(
            crawlIntervalMin=2.0,
            crawlIntervalMax=5.0,
            longSleepIntervalMin=30.0,
            longSleepIntervalMax=60.0,
            itemsPerBatch=10,
            downloadFiles=True,
            downloadVideos=True,
            cacheImages=True,
            incrementalMode=False,
        )

        with (
            patch.object(service, "get_cookie_for_group", return_value="cookie"),
            patch.object(service, "build_stealth_headers", return_value={"Cookie": "cookie"}),
            patch.object(service, "get_columns_db", return_value=fake_db),
            patch.object(service, "fetch_columns_catalog", new=AsyncMock(return_value=([], 1))),
            patch.object(service, "add_task_log"),
            patch.object(service, "update_task") as update_task,
        ):
            import asyncio

            asyncio.run(service.run_columns_fetch_task("task-1", "123", settings))

        self.assertEqual([(123, "full_fetch")], fake_db.crawl_logs)
        update_task.assert_called_with("task-1", "completed", "该群组没有专栏内容")
        self.assertTrue(fake_db.closed)

    def test_run_columns_fetch_task_updates_completed_result(self):
        from backend.services import columns_fetch_task_service as service

        fake_db = FakeColumnsDb()
        settings = SimpleNamespace(
            crawlIntervalMin=2.0,
            crawlIntervalMax=5.0,
            longSleepIntervalMin=30.0,
            longSleepIntervalMax=60.0,
            itemsPerBatch=10,
            downloadFiles=True,
            downloadVideos=True,
            cacheImages=True,
            incrementalMode=False,
        )
        column_stats = ColumnFetchStats(columns_count=1, topics_count=2, details_count=2, files_count=1)

        with (
            patch.object(service, "get_cookie_for_group", return_value="cookie"),
            patch.object(service, "build_stealth_headers", return_value={"Cookie": "cookie"}),
            patch.object(service, "get_columns_db", return_value=fake_db),
            patch.object(service, "fetch_columns_catalog", new=AsyncMock(return_value=([{"column_id": 1}], 1))),
            patch.object(service, "process_column", new=AsyncMock(return_value=column_stats)),
            patch.object(service, "is_task_stopped", return_value=False),
            patch.object(service, "add_task_log"),
            patch.object(service, "update_task") as update_task,
        ):
            import asyncio

            asyncio.run(service.run_columns_fetch_task("task-1", "123", settings))

        self.assertEqual(
            (
                9,
                {
                    "columns_count": 1,
                    "topics_count": 2,
                    "details_count": 2,
                    "files_count": 1,
                    "status": "completed",
                },
            ),
            fake_db.updated_logs[-1],
        )
        update_task.assert_called_with(
            "task-1",
            "completed",
            "采集完成: 1 个专栏, 2 篇新文章, 1 个文件, 0 个视频",
            {
                "columns_count": 1,
                "topics_count": 2,
                "details_count": 2,
                "files_count": 1,
                "images_count": 0,
                "videos_count": 0,
                "skipped_count": 0,
                "files_skipped": 0,
                "videos_skipped": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
