import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AShareRecommendationPoolRotationHelperTests(unittest.TestCase):
    def test_build_recommendation_pool_memberships_uses_trailing_window(self):
        from backend.services.a_share_research_return_smoke_service import build_recommendation_pool_memberships

        rows = build_recommendation_pool_memberships(
            {
                "2026-05-01": {"宁德时代": 2, "贵州茅台": 1},
                "2026-05-02": {"贵州茅台": 3, "中际旭创": 1},
            },
            group_id="511",
            start_date="2026-05-02",
            end_date="2026-05-02",
            windows=(2,),
            ranking_top_n=0,
        )

        self.assertEqual(
            [
                ("贵州茅台", 4, 1),
                ("宁德时代", 2, 2),
                ("中际旭创", 1, 3),
            ],
            [(row["stock_name"], row["mention_count"], row["rank"]) for row in rows],
        )

    def test_build_recommendation_pool_memberships_applies_top_n(self):
        from backend.services.a_share_research_return_smoke_service import build_recommendation_pool_memberships

        rows = build_recommendation_pool_memberships(
            {"2026-05-01": {"宁德时代": 2, "贵州茅台": 1}},
            group_id="511",
            windows=(3,),
            ranking_top_n=1,
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("宁德时代", rows[0]["stock_name"])

    def test_build_pool_rotation_daily_rows_uses_next_open_to_following_open_equal_weight(self):
        from backend.services.a_share_research_return_smoke_service import build_pool_rotation_daily_rows

        memberships = [
            {"group_id": "511", "window_days": 3, "signal_date": "2026-05-01", "rank": 1, "stock_name": "宁德时代"},
            {"group_id": "511", "window_days": 3, "signal_date": "2026-05-01", "rank": 2, "stock_name": "贵州茅台"},
        ]
        quotes = [
            {"ts_code": "300750.SZ", "trade_date": "2026-05-02", "open": 100, "close": 110, "vol": 100, "amount": 1000},
            {"ts_code": "300750.SZ", "trade_date": "2026-05-03", "open": 110, "close": 111, "vol": 100, "amount": 1000},
            {"ts_code": "600519.SH", "trade_date": "2026-05-02", "open": 50, "close": 45, "vol": 100, "amount": 1000},
            {"ts_code": "600519.SH", "trade_date": "2026-05-03", "open": 45, "close": 44, "vol": 100, "amount": 1000},
        ]

        rows = build_pool_rotation_daily_rows(
            memberships,
            quotes,
            trade_dates=("2026-05-02", "2026-05-03"),
            stock_basic_index={"宁德时代": "300750.SZ", "贵州茅台": "600519.SH"},
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("completed", rows[0]["status"])
        self.assertEqual("2026-05-02", rows[0]["entry_date"])
        self.assertEqual("2026-05-03", rows[0]["exit_date"])
        self.assertEqual(2, rows[0]["resolved_count"])
        self.assertEqual(0.0, rows[0]["portfolio_return"])

    def test_summarize_pool_rotation_period_returns_compounds_week_and_month(self):
        from backend.services.a_share_research_return_smoke_service import summarize_pool_rotation_period_returns

        rows = [
            {"group_id": "511", "window_days": 3, "exit_date": "2026-05-04", "portfolio_return": 0.1, "status": "completed"},
            {"group_id": "511", "window_days": 3, "exit_date": "2026-05-05", "portfolio_return": -0.05, "status": "completed"},
        ]

        period_rows = summarize_pool_rotation_period_returns(rows)

        self.assertEqual(2, len(period_rows))
        self.assertEqual({("month", "2026-05"), ("week", "2026-W19")}, {(row["period_type"], row["period"]) for row in period_rows})
        self.assertTrue(all(row["compound_return"] == 0.045 for row in period_rows))
        self.assertTrue(all(row["win_rate"] == 0.5 for row in period_rows))

    def test_build_pool_rotation_daily_rows_keeps_latest_signal_for_same_entry_date(self):
        from backend.services.a_share_research_return_smoke_service import build_pool_rotation_daily_rows

        memberships = [
            {"group_id": "511", "window_days": 3, "signal_date": "2026-05-01", "rank": 1, "stock_name": "宁德时代"},
            {"group_id": "511", "window_days": 3, "signal_date": "2026-05-02", "rank": 1, "stock_name": "贵州茅台"},
        ]
        quotes = [
            {"ts_code": "300750.SZ", "trade_date": "2026-05-04", "open": 100, "close": 110, "vol": 100, "amount": 1000},
            {"ts_code": "300750.SZ", "trade_date": "2026-05-05", "open": 110, "close": 111, "vol": 100, "amount": 1000},
            {"ts_code": "600519.SH", "trade_date": "2026-05-04", "open": 50, "close": 45, "vol": 100, "amount": 1000},
            {"ts_code": "600519.SH", "trade_date": "2026-05-05", "open": 45, "close": 44, "vol": 100, "amount": 1000},
        ]

        rows = build_pool_rotation_daily_rows(
            memberships,
            quotes,
            trade_dates=("2026-05-04", "2026-05-05"),
            stock_basic_index={"宁德时代": "300750.SZ", "贵州茅台": "600519.SH"},
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("2026-05-02", rows[0]["signal_date"])
        self.assertEqual("2026-05-04", rows[0]["entry_date"])
        self.assertEqual(-0.1, rows[0]["portfolio_return"])

    def test_build_pool_rotation_daily_rows_uses_calendar_dates_when_quotes_are_missing(self):
        from backend.services.a_share_research_return_smoke_service import build_pool_rotation_daily_rows

        rows = build_pool_rotation_daily_rows(
            [
                {"group_id": "511", "window_days": 3, "signal_date": "2026-05-01", "rank": 1, "stock_name": "宁德时代"},
            ],
            [],
            trade_dates=("2026-05-02", "2026-05-03"),
            stock_basic_index={"宁德时代": "300750.SZ"},
        )

        self.assertEqual("2026-05-02", rows[0]["entry_date"])
        self.assertEqual("2026-05-03", rows[0]["exit_date"])
        self.assertEqual("skipped_no_completed_holding", rows[0]["status"])
        self.assertEqual(1, rows[0]["missing_quote_count"])

    def test_run_recommendation_pool_rotation_backtest_loads_mentions_and_quotes(self):
        from backend.services import a_share_research_return_smoke_service as service

        daily_mentions = {"2026-05-01": {"宁德时代": 2}}
        quotes = [
            {"ts_code": "300750.SZ", "trade_date": "2026-05-02", "open": 100, "close": 110, "vol": 100, "amount": 1000},
            {"ts_code": "300750.SZ", "trade_date": "2026-05-03", "open": 110, "close": 111, "vol": 100, "amount": 1000},
        ]

        with patch.object(service, "read_existing_csv", return_value=daily_mentions) as load_mentions, patch.object(
            service, "load_knowaction_stock_basic_index", return_value={"宁德时代": "300750.SZ"}
        ), patch.object(
            service, "load_knowaction_trade_dates", return_value=["2026-05-02", "2026-05-03"]
        ) as load_trade_dates, patch.object(
            service, "load_knowaction_quotes", return_value=quotes
        ) as load_quotes:
            daily_rows, period_rows, summary = service.run_recommendation_pool_rotation_backtest(
                group_id="511",
                windows=(3,),
                ranking_top_n=35,
            )

        load_mentions.assert_called_once_with(group_id="511")
        load_trade_dates.assert_called_once()
        load_quotes.assert_called_once()
        self.assertEqual(1, len(daily_rows))
        self.assertEqual(2, len(period_rows))
        self.assertEqual(1, summary["completed"])
        self.assertEqual(0.1, summary["by_window"]["3"]["mean_daily_return"])

    def test_write_pool_rotation_csv_serializes_holdings(self):
        from backend.services.a_share_research_return_smoke_service import write_pool_rotation_daily_csv

        rows = [
            {
                "group_id": "511",
                "window_days": 3,
                "signal_date": "2026-05-01",
                "entry_date": "2026-05-02",
                "exit_date": "2026-05-03",
                "pool_size": 1,
                "resolved_count": 1,
                "unresolved_count": 0,
                "missing_quote_count": 0,
                "portfolio_return": 0.1,
                "status": "completed",
                "holdings_json": [{"stock_name": "宁德时代", "return": 0.1}],
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "daily.csv"
            write_pool_rotation_daily_csv(rows, output_path)

            with output_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
                read_rows = list(csv.DictReader(file_obj))

        self.assertEqual("宁德时代", json.loads(read_rows[0]["holdings_json"])[0]["stock_name"])


if __name__ == "__main__":
    unittest.main()
