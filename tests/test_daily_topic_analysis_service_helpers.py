import unittest
from importlib.util import find_spec


HAS_DAILY_SERVICE_DEPS = find_spec("openai") is not None


class DailyTopicAnalysisServiceHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_build_empty_report_summary_preserves_expected_content(self):
        from backend.services.daily_topic_analysis_service import _build_empty_report_summary

        summary = _build_empty_report_summary("2026-05-07")

        self.assertIn("# 每日话题分析报告", summary)
        self.assertIn("日期：2026-05-07", summary)
        self.assertIn("当天没有采集到话题", summary)

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_build_report_metadata_collects_topic_ids_and_limited_image_refs(self):
        from backend.services.daily_topic_analysis_service import MAX_IMAGES_PER_REPORT, _build_report_metadata

        topics = [
            {
                "topic_id": "topic-1",
                "images": [{"image_ref": f"topic-image-{index}", "url": f"https://example.com/{index}.jpg"}],
                "comments": [],
            }
            for index in range(MAX_IMAGES_PER_REPORT + 2)
        ]

        metadata = _build_report_metadata(
            group_id="group-1",
            report_date="2026-05-07",
            topics=topics,
            report_path="C:/tmp/report.md",
        )

        self.assertEqual("group-1", metadata["group_id"])
        self.assertEqual("2026-05-07", metadata["report_date"])
        self.assertEqual(MAX_IMAGES_PER_REPORT + 2, metadata["topic_count"])
        self.assertEqual(["topic-1"] * (MAX_IMAGES_PER_REPORT + 2), metadata["topic_ids"])
        self.assertEqual(MAX_IMAGES_PER_REPORT, len(metadata["image_refs"]))
        self.assertEqual("topic-image-0", metadata["image_refs"][0])
        self.assertEqual("C:/tmp/report.md", metadata["report_path"])

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_parse_report_raw_json_returns_dict_or_empty_dict(self):
        from backend.services.daily_topic_analysis_service import _parse_report_raw_json

        self.assertEqual({"ok": True}, _parse_report_raw_json('{"ok": true}'))
        self.assertEqual({}, _parse_report_raw_json(""))
        self.assertEqual({}, _parse_report_raw_json("{bad json"))
        self.assertEqual({}, _parse_report_raw_json("[1, 2]"))

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_fetch_topics_for_date_scopes_child_queries_by_group(self):
        from datetime import date

        from backend.services.daily_topic_analysis_service import _fetch_topics_for_date

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
        topics = _fetch_topics_for_date(conn, group_id="303", report_date=date(2026, 5, 7), comments_per_topic=5)

        self.assertEqual(1, len(topics))
        child_sql = "\n".join(sql for sql, _params in conn.calls[1:])
        self.assertIn("c.group_id = ?", child_sql)
        self.assertIn("tt.topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", child_sql)
        self.assertIn("topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", child_sql)
        self.assertIn((101, "303", 5), [params for _sql, params in conn.calls])


if __name__ == "__main__":
    unittest.main()
