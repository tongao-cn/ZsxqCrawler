import unittest
from importlib.util import find_spec
from unittest.mock import Mock, patch


HAS_SERVICE_DEPS = find_spec("openai") is not None


class StockTopicAnalysisServiceHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_normalize_company_name_removes_common_suffixes(self):
        from backend.services.stock_topic_analysis_service import _normalize_company_name

        self.assertEqual("宁德时代", _normalize_company_name("宁德时代股份有限公司"))
        self.assertEqual("中际旭创", _normalize_company_name(" 中际旭创 集团 "))

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_parse_json_list_keeps_only_non_empty_strings(self):
        from backend.services.stock_topic_analysis_service import _parse_json_list

        self.assertEqual(["算力", "光模块"], _parse_json_list('["算力", "", "光模块"]'))
        self.assertEqual([], _parse_json_list("not json"))

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_search_stock_topics_returns_empty_result_without_rows(self):
        from backend.services.stock_topic_analysis_service import search_stock_topics

        conn = Mock()
        conn.execute.return_value.fetchall.return_value = []

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            result = search_stock_topics("51111112855254", "宁德时代")

        self.assertEqual("51111112855254", result["group_id"])
        self.assertEqual("宁德时代", result["stock_name"])
        self.assertEqual([], result["topics"])
        self.assertEqual(0, result["recommendation_count"])
        conn.close.assert_called_once()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_analyze_stock_topics_saves_empty_result(self):
        from backend.services.stock_topic_analysis_service import analyze_stock_topics

        search_result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "",
            "market": "",
            "topics": [],
            "concepts": [],
            "topic_count": 0,
            "recommendation_count": 0,
        }
        conn = Mock()

        with (
            patch("backend.services.stock_topic_analysis_service.search_stock_topics", return_value=search_result),
            patch("backend.services.stock_topic_analysis_service._build_analysis_topic_payload", return_value=[]),
            patch("backend.services.stock_topic_analysis_service.connect", return_value=conn),
        ):
            result = analyze_stock_topics("51111112855254", "宁德时代")

        self.assertEqual("没有找到可分析的话题内容。", result["summary_markdown"])
        self.assertIn("INSERT INTO stock_topic_analyses", conn.execute.call_args.args[0])
        conn.commit.assert_called_once()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_get_latest_stock_topic_analysis_parses_saved_json_lists(self):
        from backend.services.stock_topic_analysis_service import get_latest_stock_topic_analysis

        row = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topic_ids_json": '["101", "102"]',
            "concepts_json": '["固态电池"]',
            "recommendation_count": 3,
            "summary_markdown": "summary",
            "model": "test-model",
            "status": "completed",
            "error": "",
            "created_at": "2026-05-10T10:00:00",
            "updated_at": "2026-05-10T10:01:00",
        }
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = row

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            result = get_latest_stock_topic_analysis("51111112855254", "宁德时代")

        self.assertIsNotNone(result)
        self.assertEqual(["固态电池"], result["concepts"])
        self.assertEqual(2, result["topic_count"])
        self.assertEqual("summary", result["summary_markdown"])


if __name__ == "__main__":
    unittest.main()
