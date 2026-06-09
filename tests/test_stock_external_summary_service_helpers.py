import unittest
from unittest.mock import Mock, patch


class StockExternalSummaryServiceHelperTests(unittest.TestCase):
    def test_get_external_stock_summaries_merges_saved_sources(self):
        from backend.services.stock_external_summary_service import get_external_stock_summaries

        daily_cursor = Mock()
        daily_cursor.fetchone.return_value = {
            "report_date": "2026-06-09",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "concepts_json": '["储能","固态电池"]',
            "reason": "每日概念理由",
            "topic_ids_json": '["101"]',
            "confidence": 0.8,
            "model": "concept-model",
            "status": "completed",
            "error": "",
            "updated_at": "2026-06-09T10:00:00",
        }
        analysis_cursor = Mock()
        analysis_cursor.fetchone.return_value = {
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topic_ids_json": '["201","202"]',
            "concepts_json": '["固态电池","动力电池"]',
            "recommendation_count": 3,
            "summary_markdown": "个股总结报告",
            "model": "summary-model",
            "status": "completed",
            "error": "",
            "created_at": "2026-06-09T09:00:00",
            "updated_at": "2026-06-09T10:30:00",
        }
        evidence_cursor = Mock()
        evidence_cursor.fetchall.return_value = [
            {
                "topic_date": "2026-06-09",
                "topic_id": "301",
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
                "concepts_json": '["机器人"]',
                "excerpt": "话题摘录",
                "reason": "证据理由",
                "confidence": 0.7,
                "model": "extract-model",
                "updated_at": "2026-06-09T11:00:00",
            },
        ]
        latest_recommendation_date_cursor = Mock()
        latest_recommendation_date_cursor.fetchone.return_value = {"latest_date": "2026-06-09"}
        recommendation_7d_cursor = Mock()
        recommendation_7d_cursor.fetchone.return_value = {"mention_count": 4}
        recommendation_14d_cursor = Mock()
        recommendation_14d_cursor.fetchone.return_value = {"mention_count": 6}
        recommendation_30d_cursor = Mock()
        recommendation_30d_cursor.fetchone.return_value = {"mention_count": 9}
        conn = Mock()
        conn.execute.side_effect = [
            latest_recommendation_date_cursor,
            daily_cursor,
            analysis_cursor,
            evidence_cursor,
            recommendation_7d_cursor,
            recommendation_14d_cursor,
            recommendation_30d_cursor,
        ]

        with patch("backend.services.stock_external_summary_service.connect", return_value=conn):
            result = get_external_stock_summaries("51111112855254", ["宁德时代"], report_date="2026-06-09")

        stock = result["stocks"][0]
        self.assertEqual("51111112855254", result["group_id"])
        self.assertEqual("2026-06-09", result["report_date"])
        self.assertTrue(stock["has_data"])
        self.assertEqual(["储能", "固态电池", "动力电池", "机器人"], stock["concepts"])
        self.assertEqual({"as_of_date": "2026-06-09", "7d": 4, "14d": 6, "30d": 9}, stock["recommendation_counts"])
        self.assertEqual(4, stock["recommendation_count_7d"])
        self.assertEqual(6, stock["recommendation_count_14d"])
        self.assertEqual(9, stock["recommendation_count_30d"])
        self.assertEqual("个股总结报告", stock["summary_markdown"])
        self.assertEqual("每日概念理由", stock["daily_concept"]["reason"])
        self.assertEqual(2, stock["stock_topic_analysis"]["topic_count"])
        self.assertEqual("301", stock["recent_topic_evidence"][0]["topic_id"])
        self.assertEqual(["51111112855254", "%宁德时代%", "宁德时代", "2026-06-09"], conn.execute.call_args_list[1].args[1])
        self.assertEqual(
            ["51111112855254", "2026-06-03", "2026-06-09", "%宁德时代%"],
            conn.execute.call_args_list[4].args[1],
        )
        conn.close.assert_called_once()

    def test_get_external_stock_summaries_keeps_empty_rows_for_missing_stocks(self):
        from backend.services.stock_external_summary_service import get_external_stock_summaries

        conn = Mock()
        cursors = []
        latest_recommendation_date_cursor = Mock()
        latest_recommendation_date_cursor.fetchone.return_value = None
        cursors.append(latest_recommendation_date_cursor)
        for _ in range(3):
            cursor = Mock()
            cursor.fetchone.return_value = None
            cursor.fetchall.return_value = []
            cursors.append(cursor)
        conn.execute.side_effect = cursors

        with patch("backend.services.stock_external_summary_service.connect", return_value=conn):
            result = get_external_stock_summaries("51111112855254", "不存在股票")

        stock = result["stocks"][0]
        self.assertFalse(stock["has_data"])
        self.assertEqual("不存在股票", stock["stock_name"])
        self.assertEqual([], stock["concepts"])
        self.assertEqual({"as_of_date": "", "7d": 0, "14d": 0, "30d": 0}, stock["recommendation_counts"])
        self.assertEqual(0, stock["recommendation_count_7d"])
        self.assertEqual(0, stock["recommendation_count_14d"])
        self.assertEqual(0, stock["recommendation_count_30d"])
        self.assertEqual("", stock["summary_markdown"])
        self.assertIsNone(stock["daily_concept"])
        self.assertIsNone(stock["stock_topic_analysis"])
        self.assertEqual([], stock["recent_topic_evidence"])
        conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
