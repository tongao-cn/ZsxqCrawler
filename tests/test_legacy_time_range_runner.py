import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


class LegacyTimeRangeRunnerTests(unittest.TestCase):
    def test_run_legacy_time_range_pages_filters_stores_and_advances_cursor(self):
        from backend.services.legacy_time_range_runner import run_legacy_time_range_pages

        class Crawler:
            timestamp_offset_ms = 1

            def __init__(self):
                self.responses = [
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
                self.fetch_calls = []
                self.store_calls = []
                self.delay_calls = 0

            def fetch_topics_safe(self, **kwargs):
                self.fetch_calls.append(kwargs)
                return self.responses.pop(0)

            def store_batch_data(self, data):
                self.store_calls.append(data)
                return {"new_topics": 2, "updated_topics": 1, "errors": 0}

            def check_page_long_delay(self):
                self.delay_calls += 1

        crawler = Crawler()
        logs = []
        failures = []
        start_dt = datetime(2026, 2, 1, tzinfo=timezone(timedelta(hours=8)))
        end_dt = datetime(2026, 2, 2, 23, 59, 59, 999000, tzinfo=timezone(timedelta(hours=8)))

        result = run_legacy_time_range_pages(
            "task-1",
            crawler,
            SimpleNamespace(perPage=20),
            start_dt,
            end_dt,
            add_task_log=lambda task_id, message: logs.append((task_id, message)),
            task_stopped=lambda _task_id: False,
            fail_task_with_message_unless_stopped=lambda *args, **kwargs: failures.append((args, kwargs)),
        )

        self.assertFalse(result.expired)
        self.assertEqual({"new_topics": 2, "updated_topics": 1, "errors": 0, "pages": 1}, result.stats)
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
        self.assertIn(("task-1", "📄 本页获取 3 个话题，区间内 2 个"), logs)
        self.assertIn(("task-1", "📭 无更多数据，任务结束"), logs)
        self.assertEqual([], failures)

    def test_run_legacy_time_range_pages_returns_expired_after_failure_adapter(self):
        from backend.services.legacy_time_range_runner import run_legacy_time_range_pages

        class Crawler:
            timestamp_offset_ms = 1

            def __init__(self):
                self.fetch_calls = []
                self.store_calls = []

            def fetch_topics_safe(self, **kwargs):
                self.fetch_calls.append(kwargs)
                return {"expired": True, "code": 1059, "message": "expired"}

            def store_batch_data(self, data):
                self.store_calls.append(data)
                return {}

            def check_page_long_delay(self):
                raise AssertionError("delay should not run after expired response")

        failures = []
        start_dt = datetime(2026, 2, 1, tzinfo=timezone(timedelta(hours=8)))
        end_dt = datetime(2026, 2, 2, tzinfo=timezone(timedelta(hours=8)))

        result = run_legacy_time_range_pages(
            "task-1",
            Crawler(),
            SimpleNamespace(perPage=20),
            start_dt,
            end_dt,
            add_task_log=lambda _task_id, _message: None,
            task_stopped=lambda _task_id: False,
            fail_task_with_message_unless_stopped=lambda *args, **kwargs: failures.append((args, kwargs)),
        )

        self.assertTrue(result.expired)
        self.assertEqual({"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0}, result.stats)
        self.assertEqual(
            [
                (
                    ("task-1", "会员已过期", {"expired": True, "code": 1059, "message": "expired"}),
                    {"log_message": "❌ 会员已过期: expired"},
                )
            ],
            failures,
        )


if __name__ == "__main__":
    unittest.main()
