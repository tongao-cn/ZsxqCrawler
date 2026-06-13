import tempfile
import unittest
from pathlib import Path

from scripts.csv_chart_server import read_csv


class CsvChartServerTests(unittest.TestCase):
    def test_read_csv_skips_header_and_aggregates_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "mentions.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "day,company,count",
                        "2026-06-01,Alpha,2",
                        "2026-06-01,Alpha,3",
                        "2026-06-02,Beta,bad",
                        "short,row",
                    ]
                ),
                encoding="utf-8",
            )

            dates, daily = read_csv(str(csv_path))

        self.assertEqual(["2026-06-01", "2026-06-02"], dates)
        self.assertEqual(
            {
                "2026-06-01": {"Alpha": 5},
                "2026-06-02": {"Beta": 0},
            },
            daily,
        )

    def test_read_csv_missing_file_returns_empty_data(self):
        dates, daily = read_csv("missing.csv")

        self.assertEqual([], dates)
        self.assertEqual({}, daily)


if __name__ == "__main__":
    unittest.main()
