import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AShareResearchReturnSmokeServiceHelperTests(unittest.TestCase):
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
