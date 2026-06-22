import unittest


class OfficialTopicPageFetcherTests(unittest.TestCase):
    def test_fetch_official_topic_page_preserves_call_shape_and_payload_topics(self):
        from backend.services.official_topic_page_fetcher import fetch_official_topic_page

        payload = {"topics_brief": [{"topic_id": "1"}], "next_end_time": "next"}

        class Client:
            def __init__(self):
                self.calls = []

            def get_group_topics(self, group_id, **kwargs):
                self.calls.append((group_id, kwargs))
                return payload

        client = Client()
        page = fetch_official_topic_page(client, "group-1", 30, "cursor-1")

        self.assertIs(payload, page.payload)
        self.assertEqual([{"topic_id": "1"}], page.topics)
        self.assertEqual(
            [
                (
                    "group-1",
                    {"limit": 30, "scope": "all", "end_time": "cursor-1"},
                )
            ],
            client.calls,
        )

    def test_fetch_unique_official_topic_page_preserves_empty_and_dedupe_semantics(self):
        from backend.services.official_topic_page_fetcher import fetch_unique_official_topic_page
        from backend.services.official_topic_page_state import empty_official_crawl_stats

        first_topic = {"topic_id": "1"}
        duplicate_topic = {"topic_id": 1}
        last_topic = {"topic_id": 2}
        payload = {
            "topics_brief": [first_topic, duplicate_topic, last_topic],
            "next_end_time": "next",
        }
        logs = []

        class Client:
            def __init__(self):
                self.calls = []
                self.payload = payload

            def get_group_topics(self, group_id, **kwargs):
                self.calls.append((group_id, kwargs))
                return self.payload

        client = Client()
        total_stats = empty_official_crawl_stats()
        seen_topic_ids: set[int] = set()

        page = fetch_unique_official_topic_page(
            "task-1",
            client,
            "group-1",
            30,
            "cursor-1",
            seen_topic_ids,
            total_stats,
            lambda task_id, message: logs.append((task_id, message)),
        )

        self.assertIs(payload, page.payload)
        self.assertEqual([first_topic, duplicate_topic, last_topic], page.topics)
        self.assertEqual([first_topic, last_topic], page.unique_topics)
        self.assertEqual({1, 2}, seen_topic_ids)
        self.assertEqual(1, total_stats["duplicates"])
        self.assertEqual([], logs)
        self.assertEqual(
            [
                (
                    "group-1",
                    {"limit": 30, "scope": "all", "end_time": "cursor-1"},
                )
            ],
            client.calls,
        )

        client.payload = {"topics_brief": []}
        empty_page = fetch_unique_official_topic_page(
            "task-1",
            client,
            "group-1",
            30,
            None,
            seen_topic_ids,
            total_stats,
            lambda task_id, message: logs.append((task_id, message)),
        )

        self.assertIsNone(empty_page)
        self.assertEqual(1, total_stats["duplicates"])
        self.assertEqual([("task-1", "📭 无更多数据，任务结束")], logs)


if __name__ == "__main__":
    unittest.main()
