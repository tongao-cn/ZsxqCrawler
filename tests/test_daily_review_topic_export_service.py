import json
import tempfile
import unittest
from datetime import date
from pathlib import Path


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Rows(self.rows)


def _row(**overrides):
    data = {
        "group_id": 15552822451452,
        "group_name": "调研鹅纪要",
        "topic_id": 1,
        "type": "talk",
        "title": "",
        "create_time": "2026-05-22T08:19:00.000+0800",
        "likes_count": 1,
        "comments_count": 2,
        "reading_count": 3,
        "readers_count": 4,
        "author": "鹅鹅",
        "talk_text": "",
        "question_text": "",
        "answer_text": "",
        "detail_text": "",
    }
    data.update(overrides)
    return data


class DailyReviewTopicExportServiceTests(unittest.TestCase):
    def test_normalize_review_slot_accepts_chinese_aliases(self):
        from backend.services.daily_review_topic_export_service import normalize_review_slot

        self.assertEqual("morning", normalize_review_slot("早报"))
        self.assertEqual("evening", normalize_review_slot("晚报"))

    def test_fetch_review_topics_matches_slot_rules(self):
        from backend.services.daily_review_topic_export_service import fetch_review_topics

        conn = _Connection(
            [
                _row(topic_id=1, talk_text="盘前热点事件\n一、昨日热点"),
                _row(topic_id=2, create_time="2026-05-22T17:12:00.000+0800", talk_text="5月22日复盘笔记：PCB/P..."),
                _row(topic_id=3, talk_text="普通调研纪要"),
            ]
        )

        morning = fetch_review_topics(
            conn,
            group_ids=["15552822451452"],
            report_date=date(2026, 5, 22),
            slot="morning",
        )
        evening = fetch_review_topics(
            conn,
            group_ids=["15552822451452"],
            report_date=date(2026, 5, 22),
            slot="evening",
        )

        self.assertEqual(["1"], [topic["topic_id"] for topic in morning])
        self.assertEqual("盘前热点事件", morning[0]["matched_rule"])
        self.assertEqual(["2"], [topic["topic_id"] for topic in evening])
        self.assertEqual("复盘笔记", evening[0]["matched_rule"])

    def test_write_review_topic_export_writes_summary_topics_and_markdown(self):
        from backend.services.daily_review_topic_export_service import build_review_topic_export, write_review_topic_export

        topic = {
            "slot": "morning",
            "slot_label": "早报",
            "matched_rule": "盘前热点事件",
            "group_id": "15552822451452",
            "group_name": "调研鹅纪要",
            "topic_id": "1",
            "type": "talk",
            "title": "",
            "author": "鹅鹅",
            "create_time": "2026-05-22T08:19:00.000+0800",
            "metrics": {"likes_count": 1, "comments_count": 2, "reading_count": 3, "readers_count": 4},
            "first_line": "盘前热点事件",
            "content": "盘前热点事件\n一、昨日热点",
        }
        payload = build_review_topic_export(
            group_ids=["15552822451452"],
            report_date=date(2026, 5, 22),
            slot="morning",
            topics=[topic],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            files = write_review_topic_export(payload, Path(temp_dir))

            self.assertEqual([topic], json.loads(Path(files["topics_json"]).read_text(encoding="utf-8")))
            summary = json.loads(Path(files["summary_json"]).read_text(encoding="utf-8"))
            self.assertEqual("OK", summary["level"])
            self.assertEqual(1, summary["matched_count"])
            markdown = Path(files["markdown"]).read_text(encoding="utf-8")
            self.assertIn("# 早报话题导出 2026-05-22", markdown)
            self.assertIn("盘前热点事件", markdown)


if __name__ == "__main__":
    unittest.main()
