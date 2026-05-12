import csv
import json
import tempfile
import unittest
from pathlib import Path


class AShareResearchExportServiceHelperTests(unittest.TestCase):
    def test_validate_date_range_accepts_optional_bounds(self):
        from backend.services.a_share_research_export_service import validate_date_range

        self.assertEqual((None, None), validate_date_range(None, None))
        self.assertEqual(("2026-05-01", "2026-05-07"), validate_date_range(" 2026-05-01 ", "2026-05-07"))

    def test_validate_date_range_rejects_invalid_or_reversed_bounds(self):
        from backend.services.a_share_research_export_service import validate_date_range

        with self.assertRaisesRegex(ValueError, "start_date 必须是 YYYY-MM-DD 格式"):
            validate_date_range("20260501", None)

        with self.assertRaisesRegex(ValueError, "start_date 不能晚于 end_date"):
            validate_date_range("2026-05-08", "2026-05-07")

    def test_build_research_dataset_aggregates_topic_metrics_and_mentions(self):
        from backend.services.a_share_research_export_service import build_research_dataset

        rows = [
            {
                "group_id": "511",
                "signal_date": "2026-05-10",
                "topic_id": "1001",
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
                "concepts": ["固态电池"],
                "reason": "提到固态电池。",
                "confidence": 0.6,
                "title": "电池链更新",
                "likes_count": 2,
                "comments_count": 1,
                "reading_count": 30,
            },
            {
                "group_id": "511",
                "signal_date": "2026-05-10",
                "topic_id": "1002",
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
                "concepts": '["储能", "固态电池"]',
                "reason": "提到储能。",
                "confidence": 0.8,
                "title": "储能扩散",
                "likes_count": 3,
                "comments_count": 2,
                "reading_count": 40,
            },
            {
                "group_id": "511",
                "signal_date": "2026-05-10",
                "topic_id": "1002",
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
                "concepts": ["储能"],
                "reason": "提到储能。",
                "confidence": 0.7,
                "title": "储能扩散",
                "likes_count": 3,
                "comments_count": 2,
                "reading_count": 40,
            },
        ]

        dataset = build_research_dataset(rows, {("2026-05-10", "宁德时代"): 4})

        self.assertEqual(1, len(dataset))
        row = dataset[0]
        self.assertEqual("511", row["group_id"])
        self.assertEqual("2026-05-10", row["signal_date"])
        self.assertEqual("宁德时代", row["stock_name"])
        self.assertEqual("300750", row["stock_code"])
        self.assertEqual("SZ", row["market"])
        self.assertEqual(4, row["mention_count"])
        self.assertEqual(2, row["topic_count"])
        self.assertEqual(["1001", "1002"], row["topic_ids"])
        self.assertEqual(["固态电池", "储能"], row["concepts"])
        self.assertEqual(0.7, row["avg_confidence"])
        self.assertEqual(0.8, row["max_confidence"])
        self.assertEqual(5, row["likes_count"])
        self.assertEqual(3, row["comments_count"])
        self.assertEqual(70, row["reading_count"])
        self.assertEqual(["电池链更新", "储能扩散"], row["topic_titles"])
        self.assertEqual(["提到固态电池。", "提到储能。"], row["reasons"])

    def test_write_research_dataset_csv_serializes_lists_as_json(self):
        from backend.services.a_share_research_export_service import write_a_share_research_dataset_csv

        rows = [
            {
                "group_id": "511",
                "signal_date": "2026-05-10",
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
                "mention_count": 4,
                "topic_count": 2,
                "topic_ids": ["1001", "1002"],
                "concepts": ["固态电池", "储能"],
                "avg_confidence": 0.7,
                "max_confidence": 0.8,
                "likes_count": 5,
                "comments_count": 3,
                "reading_count": 70,
                "topic_titles": ["电池链更新"],
                "reasons": ["提到固态电池。"],
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "dataset.csv"
            write_a_share_research_dataset_csv(rows, output_path)

            with output_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
                read_rows = list(csv.DictReader(file_obj))

        self.assertEqual(1, len(read_rows))
        self.assertEqual("宁德时代", read_rows[0]["stock_name"])
        self.assertEqual(["1001", "1002"], json.loads(read_rows[0]["topic_ids"]))
        self.assertEqual(["固态电池", "储能"], json.loads(read_rows[0]["concepts"]))


if __name__ == "__main__":
    unittest.main()
