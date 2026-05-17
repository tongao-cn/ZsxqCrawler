import unittest
import base64
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
    def test_parse_stock_names_splits_dedupes_and_limits(self):
        from backend.services.stock_topic_analysis_service import parse_stock_names

        names = parse_stock_names("宁德时代、德龙激光\n宁德时代 贵州茅台，中际旭创")
        self.assertEqual(["宁德时代", "德龙激光", "贵州茅台", "中际旭创"], names)
        self.assertEqual(20, len(parse_stock_names([f"股票{i}" for i in range(25)])))

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_extract_relevant_topic_content_filters_irrelevant_multi_company_text(self):
        from backend.services.stock_topic_analysis_service import _extract_relevant_topic_content

        terms = ["宁德时代", "300750"]
        full_text, mode, matched_terms = _extract_relevant_topic_content(
            "宁德时代",
            "A公司看好，宁德时代受益，B公司也同步跟进。",
            terms,
        )
        self.assertIn("宁德时代", full_text)
        self.assertIn("A公司看好", full_text)
        self.assertEqual("full", mode)
        self.assertIn("宁德时代", matched_terms)

        empty_text, empty_mode, empty_terms = _extract_relevant_topic_content(
            "多公司对比",
            "A公司表现亮眼，B公司维持增长，C公司也在扩产。",
            terms,
        )
        self.assertEqual("", empty_text)
        self.assertEqual("irrelevant", empty_mode)
        self.assertEqual([], empty_terms)

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_normalize_question_keywords_dedupes_and_limits(self):
        from backend.services.stock_topic_analysis_service import _normalize_question_keywords

        keywords = _normalize_question_keywords(["商业航天", "商业航天", "", "低空经济"])
        self.assertEqual(["商业航天", "低空经济"], keywords)

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_call_question_keyword_ai_parses_ai_json(self):
        from backend.services.stock_topic_analysis_service import _call_question_keyword_ai

        class FakeResponses:
            def create(self, **kwargs):
                response = Mock()
                response.output_text = '{"keywords":["商业航天","低空经济"]}'
                return response

        class FakeClient:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()
                self.chat = Mock()

        with (
            patch("backend.services.stock_topic_analysis_service.OpenAI", FakeClient),
            patch(
                "backend.services.stock_topic_analysis_service.get_openai_compatible_config",
                return_value={"api_key": "test-key", "model": "test-model", "base_url": "http://test", "wire_api": "responses"},
            ),
        ):
            keywords, model = _call_question_keyword_ai("商业航天板块最近怎么样，推荐吗")

        self.assertEqual(["商业航天", "低空经济"], keywords)
        self.assertEqual("test-model", model)

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_parse_image_data_url_validates_image_payload(self):
        from backend.services.stock_topic_analysis_service import _parse_image_data_url

        encoded = base64.b64encode(b"image-bytes").decode("ascii")
        mime_type, data_url, image_bytes = _parse_image_data_url(f"data:image/png;base64,{encoded}")

        self.assertEqual("image/png", mime_type)
        self.assertTrue(data_url.startswith("data:image/png;base64,"))
        self.assertEqual(b"image-bytes", image_bytes)

        with self.assertRaises(ValueError):
            _parse_image_data_url(f"data:text/plain;base64,{encoded}")

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_extract_stock_names_from_image_parses_ai_json(self):
        from backend.services.stock_topic_analysis_service import extract_stock_names_from_image

        class FakeResponses:
            def create(self, **kwargs):
                self.kwargs = kwargs
                response = Mock()
                response.output_text = '{"stockNames":["宁德时代","德龙激光","宁德时代"]}'
                return response

        class FakeClient:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()
                self.chat = Mock()

        encoded = base64.b64encode(b"image-bytes").decode("ascii")
        with (
            patch("backend.services.stock_topic_analysis_service.OpenAI", FakeClient),
            patch(
                "backend.services.stock_topic_analysis_service.get_openai_compatible_config",
                return_value={"api_key": "test-key", "model": "test-model", "base_url": "http://test", "wire_api": "responses"},
            ),
        ):
            result = extract_stock_names_from_image(f"data:image/png;base64,{encoded}")

        self.assertEqual(["宁德时代", "德龙激光"], result["stockNames"])
        self.assertEqual("test-model", result["model"])

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_extract_stock_names_from_image_rejects_empty_result(self):
        from backend.services.stock_topic_analysis_service import extract_stock_names_from_image

        class FakeResponses:
            def create(self, **kwargs):
                response = Mock()
                response.output_text = '{"stockNames":[]}'
                return response

        class FakeClient:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()
                self.chat = Mock()

        encoded = base64.b64encode(b"image-bytes").decode("ascii")
        with (
            patch("backend.services.stock_topic_analysis_service.OpenAI", FakeClient),
            patch(
                "backend.services.stock_topic_analysis_service.get_openai_compatible_config",
                return_value={"api_key": "test-key", "model": "test-model", "base_url": "http://test", "wire_api": "responses"},
            ),
        ):
            with self.assertRaises(ValueError) as raised:
                extract_stock_names_from_image(f"data:image/png;base64,{encoded}")

        self.assertIn("没有识别到明确股票名称", str(raised.exception))

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_search_stock_topics_returns_empty_result_without_rows(self):
        from backend.services.stock_topic_analysis_service import search_stock_topics

        conn = Mock()
        state_cursor = Mock()
        state_cursor.fetchall.return_value = []
        search_cursor = Mock()
        search_cursor.fetchall.return_value = []
        latest_cursor = Mock()
        latest_cursor.fetchone.return_value = None
        conn.execute.side_effect = [state_cursor, latest_cursor, search_cursor]

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            result = search_stock_topics("51111112855254", "宁德时代")

        self.assertEqual("51111112855254", result["group_id"])
        self.assertEqual("宁德时代", result["stock_name"])
        self.assertEqual([], result["topics"])
        self.assertEqual(0, result["recommendation_count"])
        conn.close.assert_called_once()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_load_processed_state_uses_only_completed_statuses(self):
        from backend.services.stock_topic_analysis_service import _load_stock_topic_processed_state_ids

        conn = Mock()
        cursor = Mock()
        cursor.fetchall.return_value = [{"topic_id": "101"}, {"topic_id": "102"}]
        conn.execute.return_value = cursor

        result = _load_stock_topic_processed_state_ids(conn, "51111112855254", "宁德时代")

        self.assertEqual(["101", "102"], result)
        self.assertIn("status IN", conn.execute.call_args.args[0])
        self.assertEqual(["51111112855254", "%宁德时代%", "analyzed", "skipped"], conn.execute.call_args.args[1])

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_upsert_stock_topic_analysis_records_processed_state(self):
        from backend.services.stock_topic_analysis_service import _upsert_stock_topic_analysis

        conn = Mock()
        result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topics": [],
            "concepts": ["固态电池"],
            "recommendation_count": 3,
            "summary_markdown": "summary",
            "model": "test-model",
        }

        _upsert_stock_topic_analysis(
            conn,
            result=result,
            status="completed",
            analyzed_topic_ids=["101", "102"],
            processed_topic_status="analyzed",
            extract_mode="snippet",
        )

        self.assertIn("INSERT INTO stock_topic_processed_states", conn.executemany.call_args.args[0])
        self.assertEqual(
            [
                ("51111112855254", "宁德时代", "101", "analyzed", "snippet", "test-model", ""),
                ("51111112855254", "宁德时代", "102", "analyzed", "snippet", "test-model", ""),
            ],
            conn.executemany.call_args.args[1],
        )
        self.assertIn("INSERT INTO stock_topic_analyses", conn.execute.call_args.args[0])
        conn.commit.assert_called_once()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_search_stock_question_topics_builds_keyword_query(self):
        from backend.services.stock_topic_analysis_service import search_stock_question_topics

        conn = Mock()
        conn.execute.return_value.fetchall.return_value = []

        with (
            patch("backend.services.stock_topic_analysis_service._call_question_keyword_ai", return_value=(["商业航天"], "test-model")),
            patch("backend.services.stock_topic_analysis_service.connect", return_value=conn),
        ):
            result = search_stock_question_topics("51111112855254", "商业航天板块最近怎么样，推荐吗")

        self.assertEqual("51111112855254", result["group_id"])
        self.assertEqual(["商业航天"], result["keywords"])
        self.assertEqual("test-model", result["keyword_model"])
        self.assertEqual([], result["topics"])
        self.assertIn("FROM topics t", conn.execute.call_args.args[0])
        conn.close.assert_called_once()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_answer_stock_question_returns_empty_answer_without_topics(self):
        from backend.services.stock_topic_analysis_service import answer_stock_question

        search_result = {
            "group_id": "51111112855254",
            "question": "固态电池怎么看",
            "keywords": ["固态电池"],
            "topics": [],
            "topic_count": 0,
        }

        with (
            patch("backend.services.stock_topic_analysis_service.search_stock_question_topics", return_value=search_result),
            patch("backend.services.stock_topic_analysis_service._build_question_topic_payload", return_value=[]),
        ):
            result = answer_stock_question("51111112855254", "固态电池怎么看")

        self.assertEqual("没有找到可回答该问题的话题内容。", result["summary_markdown"])
        self.assertEqual("completed", result["status"])

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
            patch("backend.services.stock_topic_analysis_service.get_latest_stock_topic_analysis", return_value=None),
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
        latest_cursor = Mock()
        latest_cursor.fetchone.return_value = row
        topics_cursor = Mock()
        topics_cursor.fetchall.return_value = [
            {
                "topic_id": "101",
                "title": "topic 101",
                "create_time": "2026-05-10T09:00:00",
                "likes_count": 1,
                "comments_count": 2,
                "reading_count": 3,
                "talk_text": "content 101",
                "question_text": "",
                "answer_text": "",
            },
            {
                "topic_id": "102",
                "title": "topic 102",
                "create_time": "2026-05-10T08:00:00",
                "likes_count": 1,
                "comments_count": 2,
                "reading_count": 3,
                "talk_text": "content 102",
                "question_text": "",
                "answer_text": "",
            },
        ]
        conn = Mock()
        conn.execute.side_effect = [latest_cursor, topics_cursor]

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            result = get_latest_stock_topic_analysis("51111112855254", "宁德时代")

        self.assertIsNotNone(result)
        self.assertEqual(["固态电池"], result["concepts"])
        self.assertEqual(2, result["topic_count"])
        self.assertEqual("summary", result["summary_markdown"])
        self.assertEqual(["101", "102"], result["analyzed_topic_ids"])
        self.assertEqual(2, len(result["topics"]))

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_get_latest_stock_topic_analyses_returns_missing_rows(self):
        from backend.services.stock_topic_analysis_service import get_latest_stock_topic_analyses

        def fake_latest(group_id, stock_name):
            if stock_name == "宁德时代":
                return {
                    "group_id": group_id,
                    "stock_name": stock_name,
                    "stock_code": "300750",
                    "market": "SZ",
                    "topics": [],
                    "concepts": ["固态电池"],
                    "topic_count": 2,
                    "recommendation_count": 3,
                    "summary_markdown": "summary",
                    "model": "test",
                    "status": "completed",
                    "error": "",
                    "created_at": "2026-05-10T10:00:00",
                    "updated_at": "2026-05-10T10:00:00",
                    "analyzed_topic_ids": ["宁德时代-1", "宁德时代-2"],
                }
            return None

        with patch("backend.services.stock_topic_analysis_service.get_latest_stock_topic_analysis", side_effect=fake_latest):
            result = get_latest_stock_topic_analyses("51111112855254", "宁德时代、德龙激光")

        self.assertEqual(2, len(result["stocks"]))
        self.assertEqual("completed", result["stocks"][0]["status"])
        self.assertEqual("missing", result["stocks"][1]["status"])

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_analyze_stock_topics_batch_continues_after_single_failure(self):
        from backend.services.stock_topic_analysis_service import analyze_stock_topics_batch

        def fake_search(group_id, stock_name, *, limit=None):
            return {
                "group_id": group_id,
                "stock_name": stock_name,
                "stock_code": "",
                "market": "",
                "topics": [{"topic_id": f"{stock_name}-1"}],
                "concepts": [],
                "topic_count": 1,
                "recommendation_count": 0,
            }

        def fake_analyze(group_id, stock_name, *, limit=None, log_callback=None):
            if stock_name == "失败股":
                raise RuntimeError("AI失败")
            return {
                "group_id": group_id,
                "stock_name": stock_name,
                "stock_code": "",
                "market": "",
                "topics": [{"topic_id": f"{stock_name}-1"}],
                "concepts": [],
                "topic_count": 1,
                "recommendation_count": 0,
                "summary_markdown": "summary",
                "model": "test",
                "status": "completed",
            }

        with (
            patch("backend.services.stock_topic_analysis_service.search_stock_topics", side_effect=fake_search),
            patch("backend.services.stock_topic_analysis_service.analyze_stock_topics", side_effect=fake_analyze),
            patch("backend.services.stock_topic_analysis_service.get_latest_stock_topic_analysis", return_value=None),
        ):
            result = analyze_stock_topics_batch("51111112855254", ["宁德时代", "失败股", "德龙激光"])

        self.assertEqual(2, result["summary"]["success"])
        self.assertEqual(1, result["summary"]["failed"])
        self.assertEqual("failed", result["stocks"][1]["status"])

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_analyze_stock_topics_skips_ai_when_saved_result_is_current(self):
        from backend.services.stock_topic_analysis_service import analyze_stock_topics

        search_result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topics": [{"topic_id": "101"}, {"topic_id": "102"}],
            "concepts": ["固态电池"],
            "topic_count": 2,
            "recommendation_count": 3,
        }
        latest = {
            **search_result,
            "summary_markdown": "saved summary",
            "model": "test-model",
            "status": "completed",
            "error": "",
            "created_at": "2026-05-10T10:00:00",
            "updated_at": "2026-05-10T10:01:00",
            "analyzed_topic_ids": ["101", "102"],
        }
        conn = Mock()

        with (
            patch("backend.services.stock_topic_analysis_service.search_stock_topics", return_value=search_result),
            patch("backend.services.stock_topic_analysis_service.get_latest_stock_topic_analysis", return_value=latest),
            patch("backend.services.stock_topic_analysis_service._build_analysis_topic_payload") as build_payload,
            patch("backend.services.stock_topic_analysis_service._call_stock_analysis_ai") as call_ai,
            patch("backend.services.stock_topic_analysis_service.connect", return_value=conn),
        ):
            result = analyze_stock_topics("51111112855254", "宁德时代")

        self.assertEqual("saved summary", result["summary_markdown"])
        self.assertEqual("up_to_date", result["analysis_mode"])
        self.assertEqual(0, result["new_topic_count"])
        build_payload.assert_not_called()
        call_ai.assert_not_called()
        conn.execute.assert_not_called()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_analyze_stock_topics_saves_new_processed_ids_without_ai_topics(self):
        from backend.services.stock_topic_analysis_service import analyze_stock_topics

        search_result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topics": [],
            "concepts": ["固态电池"],
            "topic_count": 0,
            "recommendation_count": 3,
            "processed_topic_ids": ["101", "102", "103"],
            "analyzed_topic_ids": ["101", "102", "103"],
        }
        latest = {
            **search_result,
            "processed_topic_ids": ["101", "102"],
            "analyzed_topic_ids": ["101", "102"],
            "summary_markdown": "saved summary",
            "model": "test-model",
            "status": "completed",
            "error": "",
            "created_at": "2026-05-10T10:00:00",
            "updated_at": "2026-05-10T10:01:00",
        }
        conn = Mock()

        with (
            patch("backend.services.stock_topic_analysis_service.search_stock_topics", return_value=search_result),
            patch("backend.services.stock_topic_analysis_service.get_latest_stock_topic_analysis", return_value=latest),
            patch("backend.services.stock_topic_analysis_service._build_analysis_topic_payload") as build_payload,
            patch("backend.services.stock_topic_analysis_service._call_stock_analysis_ai") as call_ai,
            patch("backend.services.stock_topic_analysis_service.connect", return_value=conn),
        ):
            result = analyze_stock_topics("51111112855254", "宁德时代")

        self.assertEqual("saved summary", result["summary_markdown"])
        self.assertEqual("up_to_date", result["analysis_mode"])
        self.assertEqual(["101", "102", "103"], result["processed_topic_ids"])
        build_payload.assert_not_called()
        call_ai.assert_not_called()
        conn.commit.assert_called_once()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_analyze_stock_topics_only_sends_new_topics_to_ai(self):
        from backend.services.stock_topic_analysis_service import analyze_stock_topics

        search_result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topics": [{"topic_id": "101"}, {"topic_id": "102"}, {"topic_id": "103"}],
            "concepts": ["固态电池", "储能"],
            "topic_count": 3,
            "recommendation_count": 4,
        }
        latest = {
            **search_result,
            "topics": [{"topic_id": "101"}, {"topic_id": "102"}],
            "summary_markdown": "old summary",
            "model": "old-model",
            "status": "completed",
            "error": "",
            "created_at": "2026-05-10T10:00:00",
            "updated_at": "2026-05-10T10:01:00",
            "analyzed_topic_ids": ["101", "102"],
        }
        payload_topics = [
            {"topic_id": "101", "content": "old-1"},
            {"topic_id": "102", "content": "old-2"},
            {"topic_id": "103", "content": "new"},
        ]
        conn = Mock()

        with (
            patch("backend.services.stock_topic_analysis_service.search_stock_topics", return_value=search_result),
            patch("backend.services.stock_topic_analysis_service.get_latest_stock_topic_analysis", return_value=latest),
            patch("backend.services.stock_topic_analysis_service._build_analysis_topic_payload", return_value=payload_topics),
            patch("backend.services.stock_topic_analysis_service._call_stock_analysis_ai", return_value=("updated summary", "new-model")) as call_ai,
            patch("backend.services.stock_topic_analysis_service.connect", return_value=conn),
        ):
            result = analyze_stock_topics("51111112855254", "宁德时代")

        self.assertEqual("incremental", result["analysis_mode"])
        self.assertEqual(1, result["new_topic_count"])
        self.assertEqual(["101", "102", "103"], result["processed_topic_ids"])
        self.assertEqual(["101", "102", "103"], result["analyzed_topic_ids"])
        self.assertIn('"new_topic_count": 1', call_ai.call_args.args[0])
        self.assertIn('"topic_id": "103"', call_ai.call_args.args[0])
        self.assertNotIn('"content": "old-1"', call_ai.call_args.args[0])
        self.assertNotIn("analyzed_topic_ids", call_ai.call_args.args[0])
        self.assertIn("old summary", call_ai.call_args.args[0])
        self.assertEqual(2, conn.commit.call_count)

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_analyze_stock_topics_processes_new_topics_in_batches(self):
        from backend.services.stock_topic_analysis_service import analyze_stock_topics

        search_topics = [{"topic_id": str(1000 + index)} for index in range(65)]
        search_result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topics": search_topics,
            "concepts": ["固态电池"],
            "topic_count": len(search_topics),
            "recommendation_count": 10,
        }
        payload_topics = [
            {"topic_id": topic["topic_id"], "content": f"content-{topic['topic_id']}"}
            for topic in search_topics
        ]
        conn = Mock()

        def fake_ai(prompt_payload, *, incremental=False):
            call_number = fake_ai.call_count + 1
            fake_ai.call_count = call_number
            return f"summary batch {call_number}", "test-model"

        fake_ai.call_count = 0

        with (
            patch("backend.services.stock_topic_analysis_service.search_stock_topics", return_value=search_result) as search,
            patch("backend.services.stock_topic_analysis_service.get_latest_stock_topic_analysis", return_value=None),
            patch("backend.services.stock_topic_analysis_service._build_analysis_topic_payload", return_value=payload_topics),
            patch("backend.services.stock_topic_analysis_service._call_stock_analysis_ai", side_effect=fake_ai) as call_ai,
            patch("backend.services.stock_topic_analysis_service.connect", return_value=conn),
        ):
            result = analyze_stock_topics("51111112855254", "宁德时代")

        self.assertEqual(7, call_ai.call_count)
        self.assertEqual("summary batch 7", result["summary_markdown"])
        self.assertEqual(65, result["new_topic_count"])
        self.assertEqual([topic["topic_id"] for topic in search_topics], result["processed_topic_ids"])
        self.assertEqual([topic["topic_id"] for topic in search_topics], result["analyzed_topic_ids"])
        search.assert_called_once()
        self.assertIsNone(search.call_args.kwargs["limit"])
        self.assertIn('"new_topic_count": 10', call_ai.call_args_list[0].args[0])
        self.assertIn('"new_topic_count": 5', call_ai.call_args_list[6].args[0])
        self.assertNotIn("analyzed_topic_ids", call_ai.call_args_list[0].args[0])
        self.assertIn("summary batch 1", call_ai.call_args_list[1].args[0])
        self.assertEqual(8, conn.commit.call_count)


if __name__ == "__main__":
    unittest.main()
