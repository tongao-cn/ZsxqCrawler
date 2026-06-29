import unittest
from unittest.mock import patch


class AShareAnalysisResetTests(unittest.TestCase):
    def test_apply_analysis_reset_range_removes_daily_and_state_and_adjusts_days(self):
        from backend.services.a_share_analysis_reset import apply_analysis_reset_range

        daily = {
            "2026-05-01": {"宁德时代": 2},
            "2026-05-02": {"比亚迪": 1, "中际旭创": 3},
            "2026-05-03": {"东方财富": 4},
        }
        processed_keys = {
            "topics:1001:2026-05-01",
            "topics:1002:2026-05-02",
            "topics:1003:2026-05-03",
            "legacy-key",
        }

        with patch("backend.services.a_share_analysis_reset.get_required_days_for_start_date", return_value=9):
            result = apply_analysis_reset_range(
                daily,
                processed_keys,
                "2026-05-01",
                "2026-05-02",
                3,
            )

        self.assertEqual({"2026-05-03": {"东方财富": 4}}, result.daily)
        self.assertEqual({"topics:1003:2026-05-03", "legacy-key"}, result.processed_keys)
        self.assertEqual(
            {
                "start_date": "2026-05-01",
                "end_date": "2026-05-02",
                "removed_days": 2,
                "removed_rows": 3,
                "removed_mentions": 6,
                "removed_state_keys": 2,
            },
            result.reset_summary,
        )
        self.assertEqual(9, result.days)

    def test_apply_analysis_reset_range_keeps_requested_days_when_already_wide_enough(self):
        from backend.services.a_share_analysis_reset import apply_analysis_reset_range

        with patch("backend.services.a_share_analysis_reset.get_required_days_for_start_date", return_value=5):
            result = apply_analysis_reset_range({}, set(), "2026-05-01", "2026-05-02", 7)

        self.assertEqual(7, result.days)


if __name__ == "__main__":
    unittest.main()
