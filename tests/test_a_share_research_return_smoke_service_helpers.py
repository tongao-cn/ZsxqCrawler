import csv
from datetime import date
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AShareResearchReturnSmokeServiceHelperTests(unittest.TestCase):
    def test_get_knowaction_postgres_dsn_reads_env_file(self):
        from backend.services.a_share_knowaction_market_data import get_knowaction_postgres_dsn

        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "DB_HOST=localhost",
                        "DB_PORT=15432",
                        "DB_NAME=knowaction",
                        "DB_USER=reader",
                        "DB_PASSWORD=test-password",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"KNOW_ACTION_POSTGRES_DSN": "", "KNOWACTION_POSTGRES_DSN": ""}):
                dsn = get_knowaction_postgres_dsn(env_path)

        self.assertEqual("dbname=knowaction user=reader password=test-password host=localhost port=15432", dsn)

    def test_load_knowaction_quotes_normalizes_rows(self):
        from backend.services import a_share_knowaction_market_data as market_data

        class FakeCursor:
            def __init__(self):
                self.params = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def execute(self, _sql, params):
                self.params = params

            def fetchall(self):
                return [("300750.sz", date(2026, 5, 11), "100.5", "102", "3", "4")]

        class FakeConnection:
            def __init__(self, cursor):
                self._cursor = cursor

            def cursor(self):
                return self._cursor

        class FakeConnectionContext:
            def __init__(self, cursor):
                self._cursor = cursor

            def __enter__(self):
                return FakeConnection(self._cursor)

            def __exit__(self, exc_type, exc, traceback):
                return None

        cursor = FakeCursor()
        with patch.object(market_data, "get_knowaction_connection", return_value=FakeConnectionContext(cursor)):
            rows = market_data.load_knowaction_quotes(["", "300750.sz"], date(2026, 5, 10), date(2026, 5, 12))

        self.assertEqual((["300750.SZ"], date(2026, 5, 10), date(2026, 5, 12)), cursor.params)
        self.assertEqual(
            [
                {
                    "ts_code": "300750.SZ",
                    "trade_date": "2026-05-11",
                    "open": 100.5,
                    "close": 102.0,
                    "vol": 3.0,
                    "amount": 4.0,
                }
            ],
            rows,
        )

    def test_resolve_signal_ts_code_prefers_explicit_code_and_market(self):
        from backend.services.a_share_research_return_smoke_service import resolve_signal_ts_code

        self.assertEqual("300750.SZ", resolve_signal_ts_code({"stock_code": "300750", "market": "SZ"}))
        self.assertEqual("600519.SH", resolve_signal_ts_code({"stock_code": "600519"}))
        self.assertEqual("300750.SZ", resolve_signal_ts_code({"stock_name": "宁德时代"}, {"宁德时代": "300750.SZ"}))
        self.assertEqual("688256.SH", resolve_signal_ts_code({"stock_name": "寒武纪"}, {"寒武纪": "688256.SH"}))
        self.assertEqual("688256.SH", resolve_signal_ts_code({"stock_name": "寒武纪-U"}, {"寒武纪": "688256.SH"}))

    def test_build_stock_basic_index_drops_ambiguous_company_keys(self):
        from backend.services.a_share_signal_codes import build_stock_basic_index

        index = build_stock_basic_index(
            [
                ("300750.SZ", "300750", "宁德时代"),
                ("688256.SH", "688256", "寒武纪-U"),
                ("688001.SH", "688001", "重名科技"),
                ("688002.SH", "688002", "重名科技"),
            ]
        )

        self.assertEqual("300750.SZ", index["宁德时代"])
        self.assertEqual("688256.SH", index["寒武纪"])
        self.assertNotIn("重名科技", index)

    def test_build_return_smoke_rows_uses_tplus1_open_and_hold_close(self):
        from backend.services.a_share_research_return_smoke_service import build_return_smoke_rows

        signals = [
            {
                "group_id": "511",
                "signal_date": "2026-05-10",
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
                "mention_count": 4,
                "topic_count": 2,
                "concepts": ["固态电池"],
                "avg_confidence": 0.7,
                "max_confidence": 0.8,
            }
        ]
        quotes = [
            {"ts_code": "300750.SZ", "trade_date": "2026-05-10", "open": 90, "close": 100, "vol": 100, "amount": 1000},
            {"ts_code": "300750.SZ", "trade_date": "2026-05-11", "open": 100, "close": 102, "vol": 100, "amount": 1000},
            {"ts_code": "300750.SZ", "trade_date": "2026-05-12", "open": 103, "close": 110, "vol": 100, "amount": 1000},
            {"ts_code": "300750.SZ", "trade_date": "2026-05-13", "open": 108, "close": 120, "vol": 100, "amount": 1000},
        ]

        rows = build_return_smoke_rows(signals, quotes, hold_days=2)

        self.assertEqual(1, len(rows))
        self.assertEqual("completed", rows[0]["status"])
        self.assertEqual("2026-05-11", rows[0]["entry_date"])
        self.assertEqual("2026-05-12", rows[0]["exit_date"])
        self.assertEqual(100, rows[0]["entry_open"])
        self.assertEqual(110, rows[0]["exit_close"])
        self.assertEqual(0.1, rows[0]["gross_return"])

    def test_build_return_smoke_rows_marks_unresolved_or_missing_quotes(self):
        from backend.services.a_share_research_return_smoke_service import build_return_smoke_rows

        rows = build_return_smoke_rows(
            [
                {"group_id": "511", "signal_date": "2026-05-10", "stock_name": "未知公司"},
                {"group_id": "511", "signal_date": "2026-05-10", "stock_name": "宁德时代", "stock_code": "300750", "market": "SZ"},
            ],
            [],
            hold_days=2,
        )

        self.assertEqual("skipped_unresolved_ts_code", rows[0]["status"])
        self.assertEqual("skipped_no_tradable_entry", rows[1]["status"])

    def test_summarize_return_smoke_counts_completed_rows(self):
        from backend.services.a_share_research_return_smoke_service import summarize_return_smoke

        summary = summarize_return_smoke(
            [
                {"status": "completed", "gross_return": 0.1},
                {"status": "completed", "gross_return": -0.02},
                {"status": "completed_forced_end_of_sample", "gross_return": 0.0},
                {"status": "skipped_no_tradable_entry", "gross_return": ""},
            ]
        )

        self.assertEqual(4, summary["rows"])
        self.assertEqual(3, summary["completed"])
        self.assertEqual(1, summary["skipped"])
        self.assertEqual(0.026667, summary["mean_return"])
        self.assertEqual(0.0, summary["median_return"])
        self.assertEqual(0.333333, summary["win_rate"])
        self.assertEqual(1, summary["status_counts"]["skipped_no_tradable_entry"])

    def test_return_smoke_quote_range_bounds_extends_hold_window(self):
        from backend.services.a_share_return_smoke_backtest import return_smoke_quote_range_bounds

        start_day, end_day = return_smoke_quote_range_bounds(
            [
                {"signal_date": "2026-05-10"},
                {"signal_date": "2026-05-12"},
            ],
            hold_days=2,
        )

        self.assertEqual("2026-05-10", start_day.isoformat())
        self.assertEqual("2026-05-28", end_day.isoformat())

    def test_build_recommendation_pool_memberships_keeps_service_defaults(self):
        from backend.services.a_share_research_return_smoke_service import (
            DEFAULT_POOL_ROTATION_WINDOWS,
            build_recommendation_pool_memberships,
        )

        rows = build_recommendation_pool_memberships({"2026-05-10": {"宁德时代": 2}}, group_id="511")

        self.assertEqual(set(DEFAULT_POOL_ROTATION_WINDOWS), {row["window_days"] for row in rows})
        self.assertEqual("511", rows[0]["group_id"])
        self.assertEqual("宁德时代", rows[0]["stock_name"])

    def test_build_recommendation_pool_memberships_uses_rolling_windows_and_top_n(self):
        from backend.services.a_share_research_return_smoke_service import build_recommendation_pool_memberships

        rows = build_recommendation_pool_memberships(
            {
                "2026-05-10": {"A": 2, "B": 1},
                "2026-05-11": {"B": 3, "C": 4},
            },
            group_id="511",
            start_date="2026-05-11",
            end_date="2026-05-11",
            windows=[2],
            ranking_top_n=2,
        )

        self.assertEqual(
            [
                {
                    "group_id": "511",
                    "window_days": 2,
                    "signal_date": "2026-05-11",
                    "rank": 1,
                    "stock_name": "B",
                    "mention_count": 4,
                },
                {
                    "group_id": "511",
                    "window_days": 2,
                    "signal_date": "2026-05-11",
                    "rank": 2,
                    "stock_name": "C",
                    "mention_count": 4,
                },
            ],
            rows,
        )

    def test_pool_rotation_daily_rows_and_summaries_use_next_trade_open(self):
        from backend.services.a_share_research_return_smoke_service import (
            build_pool_rotation_daily_rows,
            summarize_pool_rotation_backtest,
            summarize_pool_rotation_period_returns,
        )

        rows = build_pool_rotation_daily_rows(
            [
                {
                    "group_id": "511",
                    "window_days": 2,
                    "signal_date": "2026-05-10",
                    "rank": 1,
                    "stock_name": "宁德时代",
                    "stock_code": "300750",
                    "market": "SZ",
                    "mention_count": 4,
                },
                {
                    "group_id": "511",
                    "window_days": 2,
                    "signal_date": "2026-05-10",
                    "rank": 2,
                    "stock_name": "未知公司",
                    "mention_count": 1,
                },
            ],
            [
                {"ts_code": "300750.SZ", "trade_date": "2026-05-11", "open": 100, "close": 101, "vol": 1, "amount": 1},
                {"ts_code": "300750.SZ", "trade_date": "2026-05-12", "open": 110, "close": 111, "vol": 1, "amount": 1},
            ],
            trade_dates=["2026-05-11", "2026-05-12"],
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("completed", rows[0]["status"])
        self.assertEqual("2026-05-11", rows[0]["entry_date"])
        self.assertEqual("2026-05-12", rows[0]["exit_date"])
        self.assertEqual(2, rows[0]["pool_size"])
        self.assertEqual(1, rows[0]["resolved_count"])
        self.assertEqual(1, rows[0]["unresolved_count"])
        self.assertEqual(0.1, rows[0]["portfolio_return"])

        summary = summarize_pool_rotation_backtest(rows)
        self.assertEqual(1, summary["completed"])
        self.assertEqual(0.1, summary["by_window"]["2"]["mean_daily_return"])

        period_rows = summarize_pool_rotation_period_returns(rows)
        self.assertEqual({"week", "month"}, {row["period_type"] for row in period_rows})
        self.assertEqual({0.1}, {row["mean_daily_return"] for row in period_rows})

    def test_run_a_share_return_smoke_loads_signals_and_quotes(self):
        from backend.services import a_share_research_return_smoke_service as service

        signals = [
            {
                "group_id": "511",
                "signal_date": "2026-05-10",
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
            }
        ]
        quotes = [
            {"ts_code": "300750.SZ", "trade_date": "2026-05-11", "open": 100, "close": 102, "vol": 100, "amount": 1000},
        ]

        with patch.object(service, "load_a_share_research_dataset", return_value=signals) as load_signals, patch.object(
            service, "load_knowaction_stock_basic_index", return_value={}
        ), patch.object(service, "load_knowaction_quotes", return_value=quotes) as load_quotes:
            rows, summary = service.run_a_share_return_smoke(group_id="511", hold_days=1)

        load_signals.assert_called_once_with(group_id="511", start_date=None, end_date=None)
        load_quotes.assert_called_once()
        self.assertEqual("completed", rows[0]["status"])
        self.assertEqual(1, summary["completed"])

    def test_write_return_smoke_csv_serializes_concepts(self):
        from backend.services.a_share_research_return_smoke_service import write_return_smoke_csv

        rows = [
            {
                "group_id": "511",
                "signal_date": "2026-05-10",
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
                "ts_code": "300750.SZ",
                "concepts": ["固态电池"],
                "status": "completed",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "returns.csv"
            write_return_smoke_csv(rows, output_path)

            with output_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
                read_rows = list(csv.DictReader(file_obj))

        self.assertEqual("宁德时代", read_rows[0]["stock_name"])
        self.assertEqual(["固态电池"], json.loads(read_rows[0]["concepts"]))


if __name__ == "__main__":
    unittest.main()
