import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ExportExternalStockSummaryScriptTests(unittest.TestCase):
    def test_main_writes_output_json_and_passes_arguments(self):
        from scripts.export_external_stock_summary import main

        payload = {
            "group_id": "51111112855254",
            "report_date": "2026-06-09",
            "stocks": [
                {
                    "stock_name": "宁德时代",
                    "concepts": ["储能"],
                    "summary_markdown": "summary",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "summary.json"
            with patch("scripts.export_external_stock_summary.get_external_stock_summaries", return_value=payload) as service:
                main(
                    [
                        "--group-id",
                        "51111112855254",
                        "--stock-names",
                        "宁德时代",
                        "中际旭创",
                        "--date",
                        "2026-06-09",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(payload, json.loads(output_path.read_text(encoding="utf-8")))
            service.assert_called_once_with(
                "51111112855254",
                ["宁德时代", "中际旭创"],
                report_date="2026-06-09",
            )


if __name__ == "__main__":
    unittest.main()
