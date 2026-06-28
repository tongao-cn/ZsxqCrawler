import argparse
import asyncio
import unittest
from unittest.mock import patch

from scripts import run_zsxq_daily_file_download as daily_download


class DailyFileDownloadScriptTests(unittest.TestCase):
    def _args(self, **overrides):
        defaults = {
            "group_id": ["51111112855254"],
            "date": "2026-06-28",
            "lookback_hours": None,
            "max_files_per_group": 20,
            "download_pdf_only": True,
            "download_concurrency": 5,
            "poll_seconds": 0.01,
            "task_timeout_seconds": 0,
            "download_interval": 2.0,
            "long_sleep_interval": 90.0,
            "files_per_batch": 10,
            "download_interval_min": 2.0,
            "download_interval_max": 5.0,
            "long_sleep_interval_min": 90.0,
            "long_sleep_interval_max": 180.0,
            "crawl_latest_first": True,
            "sync_files_from_topics": True,
            "analyze_pdf_after_download": False,
            "pdf_analysis_group_id": "51111112855254",
            "max_pdf_analyses": 0,
            "pdf_analysis_concurrency": 5,
            "pdf_ocr_concurrency": None,
            "pdf_ai_concurrency": None,
            "pdf_analysis_pending_any_date": False,
            "force_pdf_analysis": False,
            "log_tail": 0,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_run_crawls_latest_topics_before_sync_and_download(self):
        events = []

        def fake_crawl(group_id, args):
            events.append(("crawl", group_id))
            return {"task_id": "crawl-1", "type": "crawl_latest_until_complete", "status": "completed"}

        async def fake_sync(group_id):
            events.append(("sync", group_id))
            return {"task_id": "sync-1"}

        async def fake_download(group_id, args, *, start_time, end_time):
            events.append(("download", group_id, start_time, end_time))
            return [{"task_id": "download-1", "type": "selected_file_download", "status": "completed"}]

        with (
            patch.object(daily_download, "_crawl_latest_topics", side_effect=fake_crawl),
            patch.object(daily_download, "sync_files_from_topics", side_effect=fake_sync),
            patch.object(daily_download, "_wait_task", return_value={"task_id": "sync-1", "status": "completed"}),
            patch.object(daily_download, "_download_group_files", side_effect=fake_download),
            patch.object(daily_download, "_print_health_summary"),
            patch.object(daily_download, "_write_run_record"),
        ):
            asyncio.run(daily_download._run(self._args()))

        self.assertEqual(
            [
                ("crawl", "51111112855254"),
                ("sync", "51111112855254"),
                ("download", "51111112855254", "2026-06-28", "2026-06-28"),
            ],
            events,
        )

    def test_load_pending_pdf_file_ids_includes_retryable_download_url_failures(self):
        captured = {}

        class FakeCursor:
            def execute(self, sql, params):
                captured["sql"] = sql
                captured["params"] = params

            def fetchall(self):
                return [(101,), (102,)]

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

            def close(self):
                captured["closed"] = True

        with patch.object(daily_download, "connect", return_value=FakeConnection()):
            result = daily_download._load_pending_pdf_file_ids(
                group_id="51111112855254",
                start_time="2026-06-27T09:00:00+0800",
                end_time="2026-06-28T09:00:00+0800",
                max_files=None,
            )

        self.assertEqual([101, 102], result)
        self.assertIn("download_error_code", captured["sql"])
        self.assertIn("download_url_unavailable", captured["params"])
        self.assertTrue(captured["closed"])

    def test_pdf_analysis_configures_ocr_and_ai_concurrency_limits(self):
        args = self._args(
            analyze_pdf_after_download=True,
            pdf_ocr_concurrency=2,
            pdf_ai_concurrency=5,
        )

        with (
            patch.object(daily_download, "_load_downloaded_pdf_rows", return_value=[]),
            patch.object(daily_download, "configure_pdf_text_extraction_concurrency") as configure_ocr,
            patch.object(daily_download, "configure_file_ai_summary_concurrency") as configure_ai,
        ):
            result = daily_download._analyze_downloaded_pdfs(args, ("2026-06-28", "2026-06-28", "2026-06-28"))

        self.assertEqual([], result)
        configure_ocr.assert_called_once_with(2)
        configure_ai.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
