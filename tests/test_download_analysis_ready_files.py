import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.download_analysis_ready_files import _download_rows, main


class FakeDownloader:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.risk_event_log_path = "unchanged"
        self.downloaded = []
        self.closed = False
        self.instances.append(self)

    def download_file(self, file_info):
        self.downloaded.append(file_info)
        return True

    def close(self):
        self.closed = True


class DownloadAnalysisReadyFilesTests(unittest.TestCase):
    def setUp(self):
        FakeDownloader.instances = []

    def _download_rows_kwargs(self, risk_log_path=None):
        return {
            "group_id": "group-1",
            "rows": [
                {
                    "file_id": 101,
                    "name": "memo.pdf",
                    "size": 4,
                    "download_count": 0,
                }
            ],
            "download_interval": 1.0,
            "long_sleep_interval": 60.0,
            "files_per_batch": 10,
            "download_interval_min": None,
            "download_interval_max": None,
            "long_sleep_interval_min": None,
            "long_sleep_interval_max": None,
            "risk_log_path": risk_log_path,
        }

    def test_download_rows_leaves_risk_log_disabled_by_default(self):
        with (
            patch("scripts.download_analysis_ready_files.get_cookie_for_group", return_value="cookie"),
            patch("scripts.download_analysis_ready_files.ZSXQFileDownloader", FakeDownloader),
        ):
            stats = _download_rows(**self._download_rows_kwargs())

        self.assertEqual({"total_files": 1, "downloaded": 1, "skipped": 0, "failed": 0}, stats)
        self.assertIsNone(FakeDownloader.instances[0].risk_event_log_path)
        self.assertTrue(FakeDownloader.instances[0].closed)

    def test_download_rows_sets_opt_in_risk_log_path(self):
        risk_log_path = Path("output") / "scratch" / "risk.csv"
        with (
            patch("scripts.download_analysis_ready_files.get_cookie_for_group", return_value="cookie"),
            patch("scripts.download_analysis_ready_files.ZSXQFileDownloader", FakeDownloader),
        ):
            _download_rows(**self._download_rows_kwargs(risk_log_path=risk_log_path))

        self.assertEqual(str(risk_log_path), FakeDownloader.instances[0].risk_event_log_path)

    def test_dry_run_does_not_print_default_risk_log_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.csv"
            argv = [
                "download_analysis_ready_files",
                "--group-id",
                "group-1",
                "--start-date",
                "2026-06-01",
                "--end-date",
                "2026-06-02",
                "--dry-run",
                "--manifest",
                str(manifest_path),
            ]
            output = io.StringIO()
            with (
                patch.object(sys, "argv", argv),
                patch("scripts.download_analysis_ready_files._load_candidate_rows", return_value=[]),
                contextlib.redirect_stdout(output),
            ):
                exit_code = main()

        self.assertEqual(0, exit_code)
        self.assertIn(f"manifest={manifest_path}", output.getvalue())
        self.assertNotIn("risk_log=", output.getvalue())


if __name__ == "__main__":
    unittest.main()
