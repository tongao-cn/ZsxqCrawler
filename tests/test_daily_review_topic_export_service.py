import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, rows, image_rows=None):
        self.rows = rows
        self.image_rows = image_rows or []
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "FROM images" in sql:
            return _Rows(self.image_rows)
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


def _image_row(**overrides):
    data = {
        "topic_id": 1,
        "image_id": 10,
        "type": "png",
        "thumbnail_url": "https://example.com/thumb.png",
        "thumbnail_width": 120,
        "thumbnail_height": 80,
        "large_url": "https://example.com/large.png",
        "large_width": 1200,
        "large_height": 800,
        "original_url": "https://example.com/original.png",
        "original_width": 1200,
        "original_height": 800,
        "local_path": "",
    }
    data.update(overrides)
    return data


class DailyReviewTopicExportServiceTests(unittest.TestCase):
    def test_normalize_review_slot_accepts_chinese_aliases(self):
        from backend.services.daily_review_topic_export_service import DEFAULT_GROUP_IDS, normalize_review_slot

        self.assertEqual("morning", normalize_review_slot("早报"))
        self.assertEqual("evening", normalize_review_slot("晚报"))
        self.assertIn("28888222124181", DEFAULT_GROUP_IDS)

    def test_new_group_tmt_and_daily_rules_are_classified(self):
        from backend.services.daily_review_topic_export_service import match_review_rule

        morning_rule = match_review_rule("morning", "TMT早间市场动态 | TMT...")
        evening_rule = match_review_rule("evening", "日报0616：")
        pre_market_rule = match_review_rule("morning", "6月17日，盘前热点")
        hot_topic_rule = match_review_rule("evening", "20260617盘后热门题材消息梳理")
        price_daily_rule = match_review_rule("evening", "国联民生化工价格日报👆")

        self.assertEqual("TMT早报", morning_rule.name)
        self.assertEqual("日报", evening_rule.name)
        self.assertEqual("盘前热点", pre_market_rule.name)
        self.assertEqual("盘后热门题材", hot_topic_rule.name)
        self.assertEqual("行业/价格日报", price_daily_rule.name)

    def test_review_topic_time_bounds_include_prior_evening_for_morning(self):
        from backend.services.daily_review_topic_export_service import review_topic_time_bounds

        morning_start, morning_end = review_topic_time_bounds(date(2026, 6, 17), "morning")
        evening_start, evening_end = review_topic_time_bounds(date(2026, 6, 17), "evening")

        self.assertEqual("2026-06-16T18:00:00.000+0800", morning_start)
        self.assertEqual("2026-06-17T11:30:00.000+0800", morning_end)
        self.assertEqual("2026-06-17T12:00:00.000+0800", evening_start)
        self.assertEqual("2026-06-18T01:30:00.000+0800", evening_end)

    def test_fetch_review_topics_matches_slot_rules(self):
        from backend.services.daily_review_topic_export_service import fetch_review_topics

        conn = _Connection(
            [
                _row(topic_id=1, talk_text="盘前热点事件\n一、昨日热点"),
                _row(topic_id=2, create_time="2026-05-22T17:12:00.000+0800", talk_text="5月22日复盘笔记：PCB/P..."),
                _row(topic_id=3, talk_text="普通调研纪要"),
            ],
            image_rows=[_image_row(topic_id=1)],
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
        self.assertEqual("https://example.com/original.png", morning[0]["images"][0]["original_url"])
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
            "content": "盘前热点事件\n一、昨日热点...\n盘前热点事件\n一、昨日热点",
            "images": [_image_row()],
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
            self.assertIn("# 2026-05-22 早报话题", markdown)
            self.assertIn("## 概览", markdown)
            self.assertIn("## 命中分布", markdown)
            self.assertIn("## 话题目录", markdown)
            self.assertIn("| 1 | 2026-05-22 08:19 | 调研鹅纪要 | 盘前热点事件 | 盘前热点事件 |", markdown)
            self.assertIn("### 1. 盘前热点事件", markdown)
            self.assertIn("盘前热点事件", markdown)
            self.assertNotIn("一、昨日热点...", markdown)
            self.assertIn("![1 image 1](https://example.com/original.png)", markdown)

    def test_load_review_topic_export_loads_topics_and_builds_payload(self):
        from backend.services.daily_review_topic_export_service import load_review_topic_export

        topic = {
            "matched_rule": "盘前热点事件",
            "group_name": "调研鹅纪要",
            "topic_id": "1",
        }
        crawl_results = [{"group_id": "15552822451452", "status": "completed"}]

        with patch(
            "backend.services.daily_review_topic_export_service.load_review_topics",
            return_value=[topic],
        ) as load_topics:
            payload = load_review_topic_export(
                group_ids=["15552822451452", "15552822451452"],
                report_date=date(2026, 5, 22),
                slot="morning",
                max_topic_chars=1234,
                crawl_results=crawl_results,
            )

        load_topics.assert_called_once_with(
            group_ids=["15552822451452"],
            report_date=date(2026, 5, 22),
            slot="morning",
            max_topic_chars=1234,
        )
        self.assertEqual("OK", payload["level"])
        self.assertEqual(["15552822451452"], payload["group_ids"])
        self.assertEqual("2026-05-22", payload["report_date"])
        self.assertEqual("morning", payload["slot"])
        self.assertEqual([topic], payload["topics"])
        self.assertEqual(crawl_results, payload["crawl_results"])


if __name__ == "__main__":
    unittest.main()
