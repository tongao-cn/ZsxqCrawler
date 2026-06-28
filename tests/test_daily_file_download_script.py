import argparse
import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
            "pipeline_pdf_analysis": False,
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

    def test_pipeline_pdf_analysis_starts_analysis_before_download_task_finishes(self):
        events = []
        task_polls = 0

        async def fake_download_selected_files(group_id, request):
            events.append(("download_started", tuple(request.file_ids)))
            return {"task_id": "download-1"}

        def fake_get_task_state(task_id):
            nonlocal task_polls
            task_polls += 1
            if task_polls == 1:
                events.append(("task", "running"))
                return {"task_id": task_id, "status": "running", "message": "downloading"}
            events.append(("task", "completed"))
            return {"task_id": task_id, "status": "completed", "result": {"downloaded": 2}}

        def fake_load_rows(group_id, file_ids):
            rows = []
            if 101 in file_ids:
                rows.append(
                    {
                        "file_id": 101,
                        "name": "first.pdf",
                        "size": 10,
                        "create_time": "2026-06-28T09:00:00+0800",
                        "download_status": "completed",
                        "local_path": r"C:\downloads\first.pdf",
                    }
                )
            if task_polls >= 2 and 102 in file_ids:
                rows.append(
                    {
                        "file_id": 102,
                        "name": "second.pdf",
                        "size": 10,
                        "create_time": "2026-06-28T09:01:00+0800",
                        "download_status": "completed",
                        "local_path": r"C:\downloads\second.pdf",
                    }
                )
            return rows

        def fake_create_analysis(group_id, file_id, force):
            events.append(("analyze", file_id))
            return {
                "analysis": {
                    "summary": f"summary {file_id}",
                    "model": "test-model",
                    "source_path": rf"C:\downloads\{file_id}.pdf",
                }
            }

        with TemporaryDirectory() as temp_dir:
            args = self._args(
                analyze_pdf_after_download=True,
                pipeline_pdf_analysis=True,
                max_pdf_analyses=2,
                pdf_analysis_concurrency=2,
                pdf_ocr_concurrency=1,
                pdf_ai_concurrency=1,
            )

            with (
                patch.object(daily_download, "_load_pending_pdf_file_ids", return_value=[101, 102]),
                patch.object(daily_download, "download_selected_files", side_effect=fake_download_selected_files),
                patch.object(daily_download, "get_task_state", side_effect=fake_get_task_state),
                patch.object(daily_download, "get_task_logs_state", return_value=[]),
                patch.object(daily_download, "_load_pdf_rows_by_file_ids", side_effect=fake_load_rows),
                patch.object(daily_download, "_load_downloaded_pdf_rows", return_value=[]),
                patch.object(daily_download, "create_file_analysis_response", side_effect=fake_create_analysis),
                patch.object(daily_download, "_markdown_output_dir", return_value=Path(temp_dir)),
                patch.object(daily_download, "configure_pdf_text_extraction_concurrency"),
                patch.object(daily_download, "configure_file_ai_summary_concurrency"),
            ):
                download_tasks, analyses = asyncio.run(
                    daily_download._download_group_files_with_pipeline_analysis(
                        "51111112855254",
                        args,
                        run_window=("2026-06-28", "2026-06-28", "2026-06-28"),
                    )
                )

        self.assertEqual(["completed"], [task["status"] for task in download_tasks])
        self.assertEqual([101, 102], [item["file_id"] for item in analyses])
        self.assertLess(events.index(("analyze", 101)), events.index(("task", "completed")))


if __name__ == "__main__":
    unittest.main()
