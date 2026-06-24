import unittest


class TopicRecommendationRefreshHelperTests(unittest.TestCase):
    def test_historical_failed_item_counts_filters_by_group_and_builds_missing_keys(self):
        from scripts import run_zsxq_topic_recommendation_refresh as refresh

        records = [
            {
                "tasks": [
                    {
                        "label": "a-share",
                        "result": {
                            "failed_items": [
                                {
                                    "group_id": "511",
                                    "item_key": "topics:1001:2026-06-21",
                                    "topic_id": "1001",
                                    "day": "2026-06-21",
                                },
                                {
                                    "group_id": "288",
                                    "item_key": "topics:2001:2026-06-21",
                                    "topic_id": "2001",
                                    "day": "2026-06-21",
                                },
                            ]
                        },
                    }
                ]
            },
            {
                "tasks": [
                    {
                        "label": "a-share",
                        "result": {
                            "failed_items": [
                                {
                                    "group_id": "511",
                                    "topic_id": "1001",
                                    "day": "2026-06-21",
                                }
                            ]
                        },
                    }
                ]
            },
        ]

        counts = refresh._historical_failed_item_counts(records, "511")

        self.assertEqual(["topics:1001:2026-06-21"], sorted(counts))
        self.assertEqual(2, counts["topics:1001:2026-06-21"]["count"])

    def test_item_keys_exceeding_failure_limit_requires_more_than_threshold(self):
        from scripts import run_zsxq_topic_recommendation_refresh as refresh

        counts = {
            "topics:1001:2026-06-21": {"count": 3},
            "topics:1002:2026-06-22": {"count": 4},
        }

        item_keys = refresh._item_keys_exceeding_failure_limit(counts, complete_failed_after=3)

        self.assertEqual({"topics:1002:2026-06-22"}, item_keys)


if __name__ == "__main__":
    unittest.main()
