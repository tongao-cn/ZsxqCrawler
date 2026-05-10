from datetime import datetime
from unittest.mock import patch
import unittest


class _FakeAShareCursor:
    def __init__(self):
        self.calls = []
        self._rows = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "FROM topics" in sql:
            self._rows = [
                (1001, "topic title", "2026-05-07T10:00:00+0800"),
                (1002, "fallback title", "2026-05-07T11:00:00+0800"),
            ]
        elif "FROM talks" in sql:
            self._rows = [(1001, "talk body")]
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeAShareConnection:
    def __init__(self):
        self.cursor_obj = _FakeAShareCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


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

    def test_parse_topic_stock_extraction_output_supports_new_schema(self):
        from backend.services.a_share_analysis_service import _parse_company_extraction_output, _parse_topic_stock_extraction_output

        message = """
        {
          "stocks": [
            {
              "stock_name": "宁德时代",
              "concepts": ["固态电池", "储能"],
              "reason": "话题明确讨论宁德时代电池链。",
              "confidence": 0.86
            },
            {
              "stock_name": "沪深300ETF",
              "concepts": ["指数"],
              "reason": "不是股票",
              "confidence": 0.9
            }
          ]
        }
        """

        stocks = _parse_topic_stock_extraction_output(message)

        self.assertEqual(
            [
                {
                    "stock_name": "宁德时代",
                    "concepts": ["固态电池", "储能"],
                    "reason": "话题明确讨论宁德时代电池链。",
                    "confidence": 0.86,
                }
            ],
            stocks,
        )
        self.assertEqual(["宁德时代"], _parse_company_extraction_output(message))

    def test_parse_topic_stock_extraction_output_keeps_legacy_company_schema(self):
        from backend.services.a_share_analysis_service import _parse_topic_stock_extraction_output

        stocks = _parse_topic_stock_extraction_output('{"companies": ["宁德时代", "中信证券"]}')

        self.assertEqual(
            [{"stock_name": "宁德时代", "concepts": [], "reason": "", "confidence": 0.7}],
            stocks,
        )

    def test_backfill_topic_stock_extractions_uses_recent_seven_day_reset_range(self):
        from backend.services import a_share_analysis_service as service

        with patch.object(service, "datetime") as mock_datetime, patch.object(service, "run_analysis") as run_analysis:
            mock_datetime.now.return_value = datetime(2026, 5, 10, 12, 0, 0)
            mock_datetime.strptime.side_effect = datetime.strptime
            run_analysis.return_value = {"ok": True}

            result = service.backfill_topic_stock_extractions(group_id="123", days=7, concurrency=2)

        self.assertEqual({"ok": True}, result)
        run_analysis.assert_called_once()
        kwargs = run_analysis.call_args.kwargs
        self.assertEqual("123", kwargs["group_id"])
        self.assertEqual(7, kwargs["days"])
        self.assertEqual("2026-05-04", kwargs["reset_start_date"])
        self.assertEqual("2026-05-10", kwargs["reset_end_date"])
        self.assertEqual(2, kwargs["concurrency"])

    def test_read_topics_last_days_filters_topics_and_talks_by_group_scope(self):
        from backend.services import a_share_analysis_service as service

        fake_conn = _FakeAShareConnection()

        with patch.object(service, "connect", return_value=fake_conn), patch.object(
            service,
            "get_last_days_range",
            return_value=(datetime(2026, 5, 1), datetime(2026, 5, 8, 23, 59, 59)),
        ):
            items = service.read_topics_last_days("51111112855254", 21)

        topic_sql, topic_params = fake_conn.cursor_obj.calls[0]
        talk_sql, talk_params = fake_conn.cursor_obj.calls[1]

        self.assertIn("WHERE t.group_id = ?", topic_sql)
        self.assertEqual((51111112855254,), topic_params)
        self.assertIn("WHERE topic_id IN (?, ?)", talk_sql)
        self.assertEqual((1001, 1002), talk_params)
        self.assertTrue(fake_conn.closed)
        self.assertEqual(
            [
                {
                    "topic_id": 1001,
                    "title": "topic title",
                    "text": "talk body",
                    "create_time": "2026-05-07T10:00:00+0800",
                    "day": "2026-05-07",
                    "source": "topics",
                    "group_id": "51111112855254",
                },
                {
                    "topic_id": 1002,
                    "title": "fallback title",
                    "text": "fallback title",
                    "create_time": "2026-05-07T11:00:00+0800",
                    "day": "2026-05-07",
                    "source": "topics",
                    "group_id": "51111112855254",
                },
            ],
            items,
        )

    def test_get_source_topics_summary_filters_by_group_scope(self):
        from backend.services import a_share_analysis_service as service

        fake_conn = _FakeAShareConnection()
        fake_conn.cursor_obj._rows = [(2, "2026-05-01T10:00:00+0800", "2026-05-07T10:00:00+0800")]

        def execute(sql, params=None):
            fake_conn.cursor_obj.calls.append((sql, params))
            fake_conn.cursor_obj._rows = [(2, "2026-05-01T10:00:00+0800", "2026-05-07T10:00:00+0800")]

        fake_conn.cursor_obj.execute = execute

        with patch.object(service, "connect", return_value=fake_conn):
            summary = service.get_source_topics_summary("51111112855254")

        sql, params = fake_conn.cursor_obj.calls[0]
        self.assertIn("WHERE group_id = ?", sql)
        self.assertEqual((51111112855254,), params)
        self.assertTrue(fake_conn.closed)
        self.assertEqual(2, summary["topics_count"])


if __name__ == "__main__":
    unittest.main()
