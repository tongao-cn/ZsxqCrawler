import unittest
from datetime import datetime, timedelta, timezone


class OfficialTopicPageStateTests(unittest.TestCase):
    def test_stats_dedupe_and_page_accumulation_share_one_state_shape(self):
        from backend.services.official_topic_page_state import (
            add_official_page_stats,
            dedupe_official_page_topics,
            empty_official_crawl_stats,
        )

        total_stats = empty_official_crawl_stats()
        seen_topic_ids: set[int] = set()
        first_topic = {"topic_id": "10", "title": "first"}
        missing_id_topic = {"title": "missing id"}
        last_topic = {"topic_id": 11, "title": "last"}

        unique_topics = dedupe_official_page_topics(
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
        add_official_page_stats(
            total_stats,
            {"new_topics": 1, "updated_topics": 2, "errors": 3},
        )

        self.assertEqual([first_topic, missing_id_topic, last_topic], unique_topics)
        self.assertEqual({0, 10, 11}, seen_topic_ids)
        self.assertEqual(
            {
                "new_topics": 1,
                "updated_topics": 2,
                "errors": 3,
                "pages": 1,
                "duplicates": 2,
                "source": "official",
            },
            total_stats,
        )

    def test_cursor_limit_completion_and_time_window_helpers_preserve_semantics(self):
        from backend.services.official_topic_page_state import (
            official_crawl_completion_message,
            official_cursor_before_timestamp,
            official_next_cursor_or_log_end,
            official_next_page_cursor,
            official_pages_remaining,
            official_per_page_limit,
            official_reached_before_start,
        )

        logs = []

        self.assertEqual(
            "next",
            official_next_page_cursor(
                {"has_more": True, "next_end_time": "next"},
                "same",
            ),
        )
        self.assertIsNone(
            official_next_page_cursor(
                {"has_more": False, "next_end_time": "next"},
                "same",
            )
        )
        self.assertEqual(
            "next",
            official_next_cursor_or_log_end(
                "task-1",
                {"has_more": True, "next_end_time": "next"},
                "same",
                lambda task_id, message: logs.append((task_id, message)),
            ),
        )
        self.assertEqual([], logs)
        self.assertIsNone(
            official_next_cursor_or_log_end(
                "task-1",
                {"has_more": False, "next_end_time": "next"},
                "same",
                lambda task_id, message: logs.append((task_id, message)),
            )
        )
        self.assertEqual([("task-1", "✅ 官方分页已无更多数据")], logs)

        self.assertTrue(official_pages_remaining(None, {}))
        self.assertFalse(official_pages_remaining(2, {"pages": 2}))
        self.assertEqual(20, official_per_page_limit(None))
        self.assertEqual(30, official_per_page_limit(31))
        self.assertEqual(
            "官方最新采集完成",
            official_crawl_completion_message("latest"),
        )
        self.assertEqual(
            "官方采集完成",
            official_crawl_completion_message("unexpected"),
        )

        start_dt = datetime(2026, 5, 1, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(official_reached_before_start(None, start_dt))
        self.assertFalse(official_reached_before_start(start_dt, start_dt))
        self.assertTrue(
            official_reached_before_start(
                start_dt - timedelta(milliseconds=1),
                start_dt,
            )
        )

        def format_zsxq_time(dt):
            return (
                dt.astimezone(timezone(timedelta(hours=8)))
                .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
                + "+0800"
            )

        self.assertEqual(
            "2026-05-06T23:59:59.999+0800",
            official_cursor_before_timestamp(
                "2026-05-07T00:00:00.000+0800",
                format_zsxq_time,
            ),
        )
        self.assertEqual(
            "not-a-time",
            official_cursor_before_timestamp("not-a-time", lambda _dt: "unused"),
        )

    def test_official_start_cursor_from_oldest_returns_cursor_and_empty_results(self):
        from backend.services.official_topic_page_state import (
            OfficialStartCursorResult,
            official_start_cursor_from_oldest,
        )

        logs = []

        result = official_start_cursor_from_oldest(
            {"has_data": True, "oldest_timestamp": "2026-05-07T00:00:00.000+0800"},
            "task-1",
            allow_empty=False,
            add_task_log=lambda task_id, message: logs.append((task_id, message)),
            cursor_before_timestamp=lambda timestamp: f"cursor-before-{timestamp}",
        )

        self.assertEqual(
            OfficialStartCursorResult("cursor-before-2026-05-07T00:00:00.000+0800", False),
            result,
        )
        self.assertEqual(
            [("task-1", "📊 当前最老时间戳: 2026-05-07T00:00:00.000+0800")],
            logs,
        )

        logs.clear()

        result = official_start_cursor_from_oldest(
            {"has_data": False},
            "task-2",
            allow_empty=True,
            add_task_log=lambda task_id, message: logs.append((task_id, message)),
            cursor_before_timestamp=lambda _timestamp: "unused",
        )

        self.assertEqual(OfficialStartCursorResult(None, False), result)
        self.assertEqual([("task-2", "📊 数据库为空，将从最新数据开始")], logs)

        logs.clear()

        result = official_start_cursor_from_oldest(
            {"has_data": False},
            "task-3",
            allow_empty=False,
            add_task_log=lambda task_id, message: logs.append((task_id, message)),
            cursor_before_timestamp=lambda _timestamp: "unused",
        )

        self.assertEqual(OfficialStartCursorResult(None, True), result)
        self.assertEqual([("task-3", "❌ 数据库中没有话题数据，请先采集最新或全量")], logs)


if __name__ == "__main__":
    unittest.main()
