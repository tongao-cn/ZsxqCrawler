import argparse
import asyncio
import unittest
from unittest.mock import patch


class ExportDailyReviewTopicsScriptTests(unittest.TestCase):
    def _args(self, **overrides):
        args = {
            "slot": "morning",
            "group_id": ["28888222124181"],
            "date": "2026-06-17",
            "output_dir": None,
            "max_topic_chars": 8000,
            "crawl_latest_first": False,
            "include_prior_evening": False,
            "poll_seconds": 0,
            "crawl_timeout_seconds": 0,
            "log_tail": 0,
        }
        args.update(overrides)
        return argparse.Namespace(**args)

    def test_run_morning_can_include_prior_evening_export(self):
        from scripts.export_daily_review_topics import _run

        morning_topic = {"topic_id": "morning", "matched_rule": "TMT早报", "group_name": "橙子不糊涂的科技花园"}
        evening_topic = {"topic_id": "evening", "matched_rule": "日报", "group_name": "橙子不糊涂的科技花园"}

        def fake_load_review_topics(*, report_date, slot, **_kwargs):
            if slot == "morning":
                self.assertEqual("2026-06-17", report_date.isoformat())
                return [morning_topic]
            self.assertEqual("evening", slot)
            self.assertEqual("2026-06-16", report_date.isoformat())
            return [evening_topic]

        def fake_write(payload, output_dir=None):
            return {"summary_json": f"{payload['report_date']}-{payload['slot']}.json"}

        with patch("scripts.export_daily_review_topics.load_review_topics", side_effect=fake_load_review_topics), patch(
            "scripts.export_daily_review_topics.write_review_topic_export", side_effect=fake_write
        ):
            payload = asyncio.run(_run(self._args(include_prior_evening=True)))

        self.assertEqual("morning", payload["slot"])
        self.assertEqual("2026-06-17", payload["report_date"])
        self.assertEqual(1, len(payload["additional_exports"]))
        self.assertEqual("evening", payload["additional_exports"][0]["slot"])
        self.assertEqual("2026-06-16", payload["additional_exports"][0]["report_date"])
        self.assertEqual("2026-06-16-evening.json", payload["additional_exports"][0]["output_files"]["summary_json"])

    def test_prior_evening_flag_requires_morning_slot(self):
        from scripts.export_daily_review_topics import _run

        with self.assertRaisesRegex(ValueError, "include-prior-evening"):
            asyncio.run(_run(self._args(slot="evening", include_prior_evening=True)))


if __name__ == "__main__":
    unittest.main()
