import unittest
from datetime import date
from unittest.mock import Mock, patch


class TopicMaterialTests(unittest.TestCase):
    def test_parse_topic_material_date_accepts_iso_date(self):
        from backend.services.topic_material import parse_topic_material_date

        self.assertEqual(date(2026, 5, 7), parse_topic_material_date("2026-05-07"))
        self.assertEqual(date(2026, 5, 7), parse_topic_material_date(date(2026, 5, 7)))

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

    def test_load_daily_topic_material_returns_snapshot_and_closes_connection(self):
        from backend.services import topic_material

        conn = Mock()
        topics = [{"topic_id": "1", "talk_text": "hello"}]

        with (
            patch("backend.services.topic_material.connect_topic_material_db", return_value=conn) as connect_db,
            patch("backend.services.topic_material.fetch_daily_topic_material", return_value=topics) as fetch,
        ):
            material = topic_material.load_daily_topic_material(
                "303",
                report_date="2026-05-07",
                comments_per_topic=5,
                max_prompt_chars=1000,
            )

        connect_db.assert_called_once_with("303")
        fetch.assert_called_once_with(
            conn,
            group_id="303",
            report_date=date(2026, 5, 7),
            comments_per_topic=5,
            max_topic_chars=topic_material.MAX_TOPIC_CHARS,
            max_images_per_topic=topic_material.MAX_IMAGES_PER_TOPIC,
        )
        conn.close.assert_called_once_with()
        self.assertEqual("303", material.group_id)
        self.assertEqual(date(2026, 5, 7), material.report_date)
        self.assertEqual("2026-05-07", material.report_date_text)
        self.assertEqual(1, material.topic_count)
        self.assertIn('"topic_count": 1', material.prompt_payload)
        self.assertIn('"topic_id": "1"', material.prompt_payload_unclipped)

    def test_fetch_daily_topic_material_scopes_child_queries_by_group(self):
        from backend.services.topic_material import fetch_daily_topic_material

        class FakeResult:
            def __init__(self, rows):
                self.rows = rows

            def fetchall(self):
                return self.rows

        class FakeConn:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                normalized = " ".join(sql.split())
                self.calls.append((normalized, tuple(params)))
                if "FROM topics t" in normalized:
                    return FakeResult(
                        [
                            {
                                "topic_id": 101,
                                "group_id": "303",
                                "type": "talk",
                                "title": "topic",
                                "create_time": "2026-05-07T10:00:00.000+0800",
                                "likes_count": 1,
                                "comments_count": 2,
                                "reading_count": 3,
                                "readers_count": 4,
                                "digested": 0,
                                "sticky": 0,
                                "talk_text": "body",
                                "talk_owner_name": "owner",
                                "question_text": None,
                                "question_owner_name": None,
                                "answer_text": None,
                                "answer_owner_name": None,
                            }
                        ]
                    )
                return FakeResult([])

        conn = FakeConn()
        topics = fetch_daily_topic_material(conn, group_id="303", report_date=date(2026, 5, 7), comments_per_topic=5)

        self.assertEqual(1, len(topics))
        child_sql = "\n".join(sql for sql, _params in conn.calls[1:])
        self.assertIn("c.group_id = ?", child_sql)
        self.assertIn("tt.topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", child_sql)
        self.assertIn("topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", child_sql)
        self.assertIn((101, "303", 5), [params for _sql, params in conn.calls])


if __name__ == "__main__":
    unittest.main()
