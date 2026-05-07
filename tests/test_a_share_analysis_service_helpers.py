import unittest


class AShareAnalysisServiceHelperTests(unittest.TestCase):
    def test_normalize_date_range_validates_and_rejects_reversed_range(self):
        from backend.services.a_share_analysis_service import _normalize_date_range

        self.assertEqual(("2026-05-01", "2026-05-07"), _normalize_date_range(" 2026-05-01 ", "2026-05-07"))

        with self.assertRaisesRegex(ValueError, "start_date 不能晚于 end_date"):
            _normalize_date_range("2026-05-08", "2026-05-07")

        with self.assertRaisesRegex(ValueError, "reset_start_date 必须是 YYYY-MM-DD 格式"):
            _normalize_date_range(
                "20260501",
                "2026-05-07",
                "reset_start_date",
                "reset_end_date",
                "reset_start_date 不能晚于 reset_end_date",
            )

    def test_select_available_date_range_defaults_swaps_and_filters(self):
        from backend.services.a_share_analysis_service import _select_available_date_range

        available_dates = ["2026-05-01", "2026-05-02", "2026-05-03"]

        self.assertEqual(
            ("2026-05-01", "2026-05-03", available_dates),
            _select_available_date_range(available_dates),
        )
        self.assertEqual(
            ("2026-05-02", "2026-05-03", ["2026-05-02", "2026-05-03"]),
            _select_available_date_range(available_dates, "2026-05-03", "2026-05-02"),
        )
        self.assertEqual(
            ("2026-04-01", "2026-04-02", []),
            _select_available_date_range(available_dates, "2026-04-01", "2026-04-02"),
        )

    def test_empty_chart_payload_preserves_existing_shape(self):
        from backend.services.a_share_analysis_service import _empty_chart_payload

        self.assertEqual(
            {
                "group_id": "12345",
                "available_dates": ["2026-05-01"],
                "selected_start_date": "2026-05-02",
                "selected_end_date": "2026-05-03",
                "chart_data": [],
                "series": [],
                "rankings": {},
                "date_count": 0,
                "company_count": 0,
                "total_companies_in_range": 0,
                "top_n": 20,
                "ranking_top_n": 35,
            },
            _empty_chart_payload(" 12345 ", ["2026-05-01"], "2026-05-02", "2026-05-03", 20, 35),
        )


if __name__ == "__main__":
    unittest.main()
