import unittest
from unittest.mock import patch


class RetentionCleanupScriptTests(unittest.TestCase):
    def test_script_run_defaults_to_preview(self):
        from scripts import run_retention_cleanup

        args = run_retention_cleanup._build_parser().parse_args(["--group-id", "303"])

        with patch(
            "scripts.run_retention_cleanup.preview_group_retention_cleanup",
            return_value={"matched_topics": 2},
        ) as preview:
            result = run_retention_cleanup._run(args)

        self.assertEqual({"matched_topics": 2}, result)
        preview.assert_called_once_with("303", retention_days=365)

    def test_script_run_applies_cleanup_only_with_apply_flag(self):
        from scripts import run_retention_cleanup

        args = run_retention_cleanup._build_parser().parse_args(
            ["--group-id", "303", "--retention-days", "400", "--apply"]
        )

        with patch(
            "scripts.run_retention_cleanup.run_group_retention_cleanup",
            return_value={"deleted": {"topics": 2}},
        ) as cleanup:
            result = run_retention_cleanup._run(args)

        self.assertEqual({"deleted": {"topics": 2}}, result)
        cleanup.assert_called_once_with("303", retention_days=400, log_callback=run_retention_cleanup._log)


if __name__ == "__main__":
    unittest.main()
