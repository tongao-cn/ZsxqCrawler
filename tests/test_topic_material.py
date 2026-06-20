import unittest
from datetime import date
from unittest.mock import Mock, patch


class TopicMaterialTests(unittest.TestCase):
    def test_parse_topic_material_date_accepts_iso_date(self):
        from backend.services.topic_material import parse_topic_material_date

        self.assertEqual(date(2026, 5, 7), parse_topic_material_date("2026-05-07"))

        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            parse_topic_material_date("2026/05/07")

    def test_fetch_daily_topic_material_uses_standard_limits(self):
        from backend.services import topic_material

        conn = Mock()
        with patch(
            "backend.services.topic_material.fetch_topics_for_date",
            return_value=[{"topic_id": "1"}],
        ) as fetch:
            topics = topic_material.fetch_daily_topic_material(
                conn,
                group_id="303",
                report_date=date(2026, 5, 7),
                comments_per_topic=5,
            )

        self.assertEqual([{"topic_id": "1"}], topics)
        fetch.assert_called_once_with(
            conn,
            group_id="303",
            report_date=date(2026, 5, 7),
            comments_per_topic=5,
            max_topic_chars=topic_material.MAX_TOPIC_CHARS,
            max_images_per_topic=topic_material.MAX_IMAGES_PER_TOPIC,
        )

    def test_build_daily_topic_material_payload_delegates_to_prompt_builder(self):
        from backend.services.topic_material import build_daily_topic_material_payload

        payload = build_daily_topic_material_payload(
            "303",
            "2026-05-07",
            [{"topic_id": "1", "talk_text": "hello"}],
            max_prompt_chars=1000,
        )

        self.assertIn('"group_id": "303"', payload)
        self.assertIn('"report_date": "2026-05-07"', payload)
        self.assertIn('"topic_count": 1', payload)


if __name__ == "__main__":
    unittest.main()
