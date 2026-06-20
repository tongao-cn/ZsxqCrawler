import unittest
import base64
import json
import threading
import time
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
        self.assertEqual(50, len(parse_stock_names([f"股票{i}" for i in range(55)])))

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_parse_stock_names_preserves_group_suffix(self):
        from backend.services.stock_topic_analysis_service import parse_stock_names

        self.assertEqual(["朗新集团", "君正集团"], parse_stock_names("朗新集团、君正集团"))

    def test_topic_id_helpers_dedupe_merge_exclude_and_limit(self):
        from backend.services.stock_topic_analysis_helpers import (
            _exclude_topic_ids,
            _merge_topic_ids,
            _serialize_json_list,
            _topic_id_set,
            _topic_ids_from_result,
        )

        result = {"topics": [{"topic_id": 101}, {"topic_id": "102"}, {"topic_id": 101}, {"topic_id": ""}]}

        self.assertEqual(["101", "102"], _topic_ids_from_result(result))
        self.assertEqual(["101", "102", "103"], _merge_topic_ids(["101", 102], ["102", 103]))
        self.assertEqual(["102", "103"], _exclude_topic_ids(["101", "102", "103"], [101]))
        self.assertEqual({"101", "102"}, _topic_id_set(["101", 102, "102"]))
        self.assertEqual('["101", "102"]', _serialize_json_list(["101", "102", "101"]))
        self.assertEqual(["1", "2"], _merge_topic_ids([1, 2, 3], limit=2))

    def test_reconcile_processed_topic_ids_prefers_processed_ids(self):
        from backend.services.stock_topic_analysis_helpers import _reconcile_processed_topic_ids

        latest = {"processed_topic_ids": ["101", "102"], "analyzed_topic_ids": ["old"]}
        search_result = {
            "topics": [{"topic_id": "102"}, {"topic_id": "103"}, {"topic_id": "104"}],
            "processed_topic_ids": ["102", "103"],
            "skipped_topic_ids": ["101", "104", "105"],
        }

        result = _reconcile_processed_topic_ids(latest, search_result)

        self.assertEqual(["101", "102"], result["saved_topic_ids"])
        self.assertEqual(["102", "103", "104"], result["current_topic_ids"])
        self.assertEqual(["103", "104"], result["new_topic_ids"])
        self.assertEqual(["104", "105"], result["new_skipped_topic_ids"])
        self.assertEqual(["101", "102", "103", "104", "105"], result["processed_topic_ids"])
        self.assertTrue(result["has_new_processed_topic_ids"])

    def test_reconcile_processed_topic_ids_falls_back_to_analyzed_ids(self):
        from backend.services.stock_topic_analysis_helpers import _reconcile_processed_topic_ids

        latest = {"analyzed_topic_ids": ["101"]}
        search_result = {
            "topics": [{"topic_id": "101"}],
            "processed_topic_ids": ["101"],
            "skipped_topic_ids": ["101"],
        }

        result = _reconcile_processed_topic_ids(latest, search_result)

        self.assertEqual(["101"], result["saved_topic_ids"])
        self.assertEqual([], result["new_topic_ids"])
        self.assertEqual([], result["new_skipped_topic_ids"])
        self.assertEqual(["101"], result["processed_topic_ids"])
        self.assertFalse(result["has_new_processed_topic_ids"])

    def test_reconcile_processed_topic_ids_handles_empty_latest(self):
        from backend.services.stock_topic_analysis_helpers import _reconcile_processed_topic_ids

        search_result = {
            "topics": [{"topic_id": "101"}, {"topic_id": "101"}, {"topic_id": "102"}],
            "processed_topic_ids": ["101"],
        }

        result = _reconcile_processed_topic_ids(None, search_result)

        self.assertEqual([], result["saved_topic_ids"])
        self.assertEqual(["101", "102"], result["current_topic_ids"])
        self.assertEqual(["101", "102"], result["new_topic_ids"])
        self.assertEqual([], result["new_skipped_topic_ids"])
        self.assertEqual(["101"], result["processed_topic_ids"])
        self.assertTrue(result["has_new_processed_topic_ids"])

    def test_build_saved_stock_analysis_result_keeps_saved_metadata(self):
        from backend.services.stock_topic_analysis_helpers import _build_saved_stock_analysis_result

        search_result = {"group_id": "group-1", "stock_name": "宁德时代", "topics": []}
        latest = {
            "summary_markdown": "saved",
            "model": "test-model",
            "status": "completed",
            "error": "",
            "created_at": "2026-05-10T10:00:00",
            "updated_at": "2026-05-10T10:01:00",
        }

        result = _build_saved_stock_analysis_result(
            search_result,
            latest,
            processed_topic_ids=["101", "102"],
            analyzed_topic_ids=["101"],
        )

        self.assertEqual("saved", result["summary_markdown"])
        self.assertEqual("test-model", result["model"])
        self.assertEqual(["101", "102"], result["processed_topic_ids"])
        self.assertEqual(["101"], result["analyzed_topic_ids"])
        self.assertEqual(0, result["new_topic_count"])
        self.assertEqual("up_to_date", result["analysis_mode"])
        self.assertEqual("2026-05-10T10:01:00", result["updated_at"])

    def test_build_stock_analysis_result_can_omit_status_for_failed_upsert(self):
        from backend.services.stock_topic_analysis_helpers import _build_stock_analysis_result

        result = _build_stock_analysis_result(
            {"group_id": "group-1", "stock_name": "宁德时代", "topics": [{"topic_id": "101"}]},
            topics=[],
            summary_markdown="partial",
            model="test-model",
            status=None,
            processed_topic_ids=["101"],
            new_topic_count=1,
            analysis_mode="initialize",
        )

        self.assertNotIn("status", result)
        self.assertEqual([], result["topics"])
        self.assertEqual(["101"], result["processed_topic_ids"])
        self.assertEqual(["101"], result["analyzed_topic_ids"])
        self.assertEqual("partial", result["summary_markdown"])

    def test_stock_analysis_mode_distinguishes_empty_and_incremental_paths(self):
        from backend.services.stock_topic_analysis_helpers import _stock_analysis_mode

        self.assertEqual(
            "initialize",
            _stock_analysis_mode(has_existing_summary=False, has_topics_to_analyze=False),
        )
        self.assertEqual(
            "up_to_date",
            _stock_analysis_mode(has_existing_summary=True, has_topics_to_analyze=False),
        )
        self.assertEqual(
            "incremental",
            _stock_analysis_mode(has_existing_summary=True, has_topics_to_analyze=True),
        )

    def test_chunks_splits_without_reordering(self):
        from backend.services.stock_topic_analysis_helpers import _chunks

        rows = [{"topic_id": index} for index in range(5)]

        self.assertEqual(
            [[{"topic_id": 0}, {"topic_id": 1}], [{"topic_id": 2}, {"topic_id": 3}], [{"topic_id": 4}]],
            _chunks(rows, 2),
        )

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

        with (
            patch("backend.services.stock_topic_analysis_service.OpenAI", FakeClient),
            patch("backend.services.stock_topic_analysis_service.get_openai_compatible_config", return_value={"api_key": "test-key", "model": "test-model", "base_url": "http://test"}),
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

        stock_names = [f"股票{i}" for i in range(55)]

        class FakeResponses:
            def create(self, **kwargs):
                self.kwargs = kwargs
                response = Mock()
                response.output_text = json.dumps({"stockNames": [*stock_names, stock_names[0]]}, ensure_ascii=False)
                return response

        class FakeClient:
            responses_instance = None

            def __init__(self, **kwargs):
                self.responses = FakeResponses()
                FakeClient.responses_instance = self.responses

        encoded = base64.b64encode(b"image-bytes").decode("ascii")
        with (
            patch("backend.services.stock_topic_analysis_service.OpenAI", FakeClient),
            patch("backend.services.stock_topic_analysis_service.get_openai_compatible_config", return_value={"api_key": "test-key", "model": "test-model", "base_url": "http://test"}),
        ):
            result = extract_stock_names_from_image(f"data:image/png;base64,{encoded}")

        self.assertEqual(stock_names[:50], result["stockNames"])
        self.assertEqual("test-model", result["model"])
        prompt_text = FakeClient.responses_instance.kwargs["input"][0]["content"][0]["text"]
        self.assertIn("最多 50 个", prompt_text)

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

        encoded = base64.b64encode(b"image-bytes").decode("ascii")
        with (
            patch("backend.services.stock_topic_analysis_service.OpenAI", FakeClient),
            patch("backend.services.stock_topic_analysis_service.get_openai_compatible_config", return_value={"api_key": "test-key", "model": "test-model", "base_url": "http://test"}),
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
    def test_search_stock_topics_raises_without_stored_excerpt(self):
        from backend.services.stock_topic_analysis_service import search_stock_topics

        conn = Mock()
        state_cursor = Mock()
        state_cursor.fetchall.return_value = []
        latest_cursor = Mock()
        latest_cursor.fetchone.return_value = None
        search_cursor = Mock()
        search_cursor.fetchall.return_value = [
            {
                "topic_id": "101",
                "title": "宁德时代业绩交流",
                "create_time": "2026-05-10T09:00:00",
                "likes_count": 1,
                "comments_count": 2,
                "reading_count": 3,
                "stock_name": "宁德时代",
                "stock_code": "",
                "market": "",
                "concepts_json": '["储能"]',
                "excerpt": "",
                "reason": "",
                "confidence": 0,
            },
        ]
        conn.execute.side_effect = [state_cursor, latest_cursor, search_cursor]

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            with self.assertRaisesRegex(RuntimeError, "缺少 宁德时代 的 excerpt"):
                search_stock_topics("51111112855254", "宁德时代")

        conn.close.assert_called_once()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_search_stock_topics_prefers_stored_excerpt(self):
        from backend.services.stock_topic_analysis_service import search_stock_topics

        conn = Mock()
        state_cursor = Mock()
        state_cursor.fetchall.return_value = []
        latest_cursor = Mock()
        latest_cursor.fetchone.return_value = None
        search_cursor = Mock()
        search_cursor.fetchall.return_value = [
            {
                "topic_id": "101",
                "title": "多公司交流",
                "create_time": "2026-05-10T09:00:00",
                "likes_count": 1,
                "comments_count": 2,
                "reading_count": 3,
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
                "concepts_json": '["储能"]',
                "excerpt": "宁德时代储能订单持续增长。",
                "reason": "",
                "confidence": 0.8,
            },
        ]
        counts_cursor = Mock()
        counts_cursor.fetchall.return_value = []
        conn.execute.side_effect = [state_cursor, latest_cursor, search_cursor, counts_cursor]

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            result = search_stock_topics("51111112855254", "宁德时代")

        self.assertEqual(1, result["topic_count"])
        topic = result["topics"][0]
        self.assertEqual("stored_excerpt", topic["extract_mode"])
        self.assertEqual("宁德时代储能订单持续增长。", topic["analysis_content"])
        self.assertEqual("宁德时代储能订单持续增长。", topic["excerpt"])
        self.assertIn("宁德时代储能订单持续增长", topic["content_preview"])

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_search_stock_topics_keeps_requested_stock_name_for_alias_hit(self):
        from backend.services.stock_topic_analysis_service import search_stock_topics

        conn = Mock()
        state_cursor = Mock()
        state_cursor.fetchall.return_value = []
        latest_cursor = Mock()
        latest_cursor.fetchone.return_value = None
        search_cursor = Mock()
        search_cursor.fetchall.return_value = [
            {
                "topic_id": "101",
                "title": "泽璟制药交流",
                "create_time": "2026-05-10T09:00:00",
                "likes_count": 1,
                "comments_count": 2,
                "reading_count": 3,
                "stock_name": "泽璟制药U",
                "stock_code": "688266",
                "market": "SH",
                "concepts_json": "[]",
                "excerpt": "泽璟制药管线进展。",
                "reason": "",
                "confidence": 0.8,
            },
        ]
        counts_cursor = Mock()
        counts_cursor.fetchall.return_value = []
        conn.execute.side_effect = [state_cursor, latest_cursor, search_cursor, counts_cursor]

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            result = search_stock_topics("51111112855254", "泽璟制药")

        self.assertEqual("泽璟制药", result["stock_name"])
        self.assertEqual("688266", result["stock_code"])
        self.assertEqual(1, result["topic_count"])

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
        self.assertEqual(["51111112855254", "宁德时代", "analyzed", "skipped"], conn.execute.call_args.args[1])

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
            processed_state_topic_ids=["102"],
            processed_topic_status="analyzed",
            extract_mode="snippet",
        )

        state_calls = [
            call.args
            for call in conn.execute.call_args_list
            if "INSERT INTO stock_topic_processed_states" in call.args[0]
        ]
        self.assertEqual(
            [
                (
                    """
            INSERT INTO stock_topic_processed_states (
                group_id, stock_name, topic_id, status, extract_mode, model,
                error, processed_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(group_id, stock_name, topic_id) DO UPDATE SET
                status = excluded.status,
                extract_mode = excluded.extract_mode,
                model = excluded.model,
                error = excluded.error,
                processed_at = excluded.processed_at,
                updated_at = CURRENT_TIMESTAMP
            """,
                    ("51111112855254", "宁德时代", "102", "analyzed", "snippet", "test-model", ""),
                )
            ],
            state_calls,
        )
        self.assertIn("INSERT INTO stock_topic_analyses", conn.execute.call_args_list[-1].args[0])
        conn.commit.assert_called_once()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_upsert_stock_topic_analysis_can_skip_processed_state_write(self):
        from backend.services.stock_topic_analysis_service import _upsert_stock_topic_analysis

        conn = Mock()
        result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topics": [],
            "concepts": [],
            "recommendation_count": 0,
            "summary_markdown": "summary",
            "model": "test-model",
        }

        _upsert_stock_topic_analysis(
            conn,
            result=result,
            status="completed",
            analyzed_topic_ids=["101", "102"],
            write_processed_state=False,
        )

        conn.executemany.assert_not_called()
        self.assertIn("INSERT INTO stock_topic_analyses", conn.execute.call_args.args[0])
        conn.commit.assert_called_once()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_upsert_stock_topic_analysis_can_defer_commit(self):
        from backend.services.stock_topic_analysis_service import _upsert_stock_topic_analysis

        conn = Mock()
        result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topics": [],
            "concepts": [],
            "recommendation_count": 0,
            "summary_markdown": "summary",
            "model": "test-model",
        }

        _upsert_stock_topic_analysis(
            conn,
            result=result,
            status="completed",
            analyzed_topic_ids=["101"],
            write_processed_state=False,
            commit=False,
        )

        self.assertIn("INSERT INTO stock_topic_analyses", conn.execute.call_args.args[0])
        conn.commit.assert_not_called()

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_insert_stock_topic_analysis_version_records_snapshot(self):
        from backend.services.stock_topic_analysis_service import _insert_stock_topic_analysis_version

        conn = Mock()
        result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "concepts": ["固态电池"],
            "recommendation_count": 3,
            "summary_markdown": "summary",
            "model": "test-model",
            "analysis_mode": "incremental",
            "new_topic_count": 1,
        }

        _insert_stock_topic_analysis_version(
            conn,
            result=result,
            status="completed",
            analyzed_topic_ids=["101", "102"],
        )

        self.assertIn("INSERT INTO stock_topic_analysis_versions", conn.execute.call_args.args[0])
        params = conn.execute.call_args.args[1]
        self.assertEqual("51111112855254", params[0])
        self.assertEqual("宁德时代", params[1])
        self.assertEqual('["101", "102"]', params[4])
        self.assertEqual("incremental", params[11])
        self.assertEqual(1, params[12])

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
        fallback_cursor = Mock()
        fallback_cursor.fetchall.return_value = []
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
                "excerpt": "excerpt 101",
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
                "excerpt": "excerpt 102",
            },
        ]
        conn = Mock()
        conn.execute.side_effect = [latest_cursor, fallback_cursor, topics_cursor]

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            result = get_latest_stock_topic_analysis("51111112855254", "宁德时代")

        self.assertIsNotNone(result)
        self.assertEqual(["固态电池"], result["concepts"])
        self.assertEqual(2, result["topic_count"])
        self.assertEqual("summary", result["summary_markdown"])
        self.assertEqual(["101", "102"], result["analyzed_topic_ids"])
        self.assertEqual(2, len(result["topics"]))
        self.assertEqual("excerpt 101", result["topics"][0]["excerpt"])
        self.assertEqual("excerpt 101", result["topics"][0]["content_preview"])

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_get_latest_stock_topic_analysis_raises_without_excerpt(self):
        from backend.services.stock_topic_analysis_service import get_latest_stock_topic_analysis

        row = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topic_ids_json": '["101"]',
            "concepts_json": "[]",
            "recommendation_count": 1,
            "summary_markdown": "summary",
            "model": "test-model",
            "status": "completed",
            "error": "",
            "created_at": "2026-05-10T10:00:00",
            "updated_at": "2026-05-10T10:01:00",
        }
        latest_cursor = Mock()
        latest_cursor.fetchone.return_value = row
        fallback_cursor = Mock()
        fallback_cursor.fetchall.return_value = []
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
                "excerpt": "",
            },
        ]
        conn = Mock()
        conn.execute.side_effect = [latest_cursor, fallback_cursor, topics_cursor]

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            with self.assertRaisesRegex(RuntimeError, "缺少 宁德时代 的 excerpt"):
                get_latest_stock_topic_analysis("51111112855254", "宁德时代")

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_get_latest_stock_topic_analysis_uses_alias_excerpt_fallback(self):
        from backend.services.stock_topic_analysis_service import get_latest_stock_topic_analysis

        row = {
            "group_id": "51111112855254",
            "stock_name": "信科移动",
            "stock_code": "",
            "market": "",
            "topic_ids_json": '["101"]',
            "concepts_json": "[]",
            "recommendation_count": 1,
            "summary_markdown": "summary",
            "model": "test-model",
            "status": "completed",
            "error": "",
            "created_at": "2026-05-10T10:00:00",
            "updated_at": "2026-05-10T10:01:00",
        }
        latest_cursor = Mock()
        latest_cursor.fetchone.return_value = row
        fallback_cursor = Mock()
        fallback_cursor.fetchall.return_value = [
            {
                "topic_id": "101",
                "excerpt": "信科移动U 商业航天相关摘录。",
            }
        ]
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
                "excerpt": "",
            },
        ]
        conn = Mock()
        conn.execute.side_effect = [latest_cursor, fallback_cursor, topics_cursor]

        with patch("backend.services.stock_topic_analysis_service.connect", return_value=conn):
            result = get_latest_stock_topic_analysis("51111112855254", "信科移动")

        self.assertEqual("信科移动U 商业航天相关摘录。", result["topics"][0]["excerpt"])
        self.assertEqual("信科移动U 商业航天相关摘录。", result["topics"][0]["content_preview"])

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_build_analysis_topic_payload_uses_search_result_excerpt(self):
        from backend.services.stock_topic_analysis_service import _build_analysis_topic_payload

        search_result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "topics": [
                {
                    "topic_id": "101",
                    "title": "topic 101",
                    "create_time": "2026-05-10T09:00:00",
                    "likes_count": 1,
                    "comments_count": 2,
                    "reading_count": 3,
                    "concepts": ["储能"],
                    "excerpt": "宁德时代储能订单持续增长。",
                }
            ],
        }
        with patch("backend.services.stock_topic_analysis_service.connect") as connect:
            payload = _build_analysis_topic_payload(search_result)

        self.assertEqual("宁德时代储能订单持续增长。", payload[0]["excerpt"])
        self.assertNotIn("content", payload[0])
        connect.assert_not_called()

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
    def test_analyze_stock_topics_batch_runs_stocks_concurrently_and_keeps_order(self):
        from backend.services.stock_topic_analysis_service import analyze_stock_topics_batch

        entered = threading.Barrier(2)
        release = threading.Event()
        started = []

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
            started.append(stock_name)
            entered.wait(timeout=2)
            release.wait(timeout=2)
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
        ):
            start_time = time.monotonic()
            release.set()
            result = analyze_stock_topics_batch("51111112855254", ["宁德时代", "德龙激光"])

        self.assertLess(time.monotonic() - start_time, 1.5)
        self.assertCountEqual(["宁德时代", "德龙激光"], started)
        self.assertEqual(["宁德时代", "德龙激光"], [stock["stock_name"] for stock in result["stocks"]])
        self.assertEqual(2, result["summary"]["success"])

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
            "processed_topic_ids": ["101", "102"],
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
            "skipped_topic_ids": ["103"],
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
        self.assertTrue(any("INSERT INTO stock_topic_processed_states" in call.args[0] for call in conn.execute.call_args_list))
        self.assertIn(
            ("51111112855254", "宁德时代", "103", "skipped", "", "test-model", ""),
            [call.args[1] for call in conn.execute.call_args_list if "INSERT INTO stock_topic_processed_states" in call.args[0]],
        )

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
            "processed_topic_ids": ["101", "102"],
            "skipped_topic_ids": [],
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
            "processed_topic_ids": ["101", "102"],
            "analyzed_topic_ids": ["101", "102"],
        }
        payload_topics = [
            {"topic_id": "101", "excerpt": "old-1"},
            {"topic_id": "102", "excerpt": "old-2"},
            {"topic_id": "103", "excerpt": "new"},
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
        self.assertNotIn('"excerpt": "old-1"', call_ai.call_args.args[0])
        self.assertIn('"existing_summary_markdown": "old summary"', call_ai.call_args.args[0])
        self.assertNotIn('"analyzed_topic_ids"', call_ai.call_args.args[0])
        self.assertIn("old summary", call_ai.call_args.args[0])
        self.assertEqual(2, conn.commit.call_count)
        self.assertTrue(any("INSERT INTO stock_topic_analysis_versions" in call.args[0] for call in conn.execute.call_args_list))
        state_writes = [
            call.args[1]
            for call in conn.execute.call_args_list
            if "INSERT INTO stock_topic_processed_states" in call.args[0]
        ]
        self.assertEqual([("51111112855254", "宁德时代", "103", "analyzed", "", "new-model", "")], state_writes)

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
            "processed_topic_ids": [],
            "skipped_topic_ids": [],
        }
        payload_topics = [
            {"topic_id": topic["topic_id"], "excerpt": f"excerpt-{topic['topic_id']}"}
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
        self.assertIn('"existing_summary_markdown": "summary batch 1"', call_ai.call_args_list[1].args[0])
        self.assertEqual(8, conn.commit.call_count)
        self.assertEqual(
            1,
            sum(1 for call in conn.execute.call_args_list if "INSERT INTO stock_topic_analysis_versions" in call.args[0]),
        )

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_analyze_stock_topics_preserves_checkpoint_summary_on_batch_failure(self):
        from backend.services.stock_topic_analysis_service import analyze_stock_topics

        search_topics = [{"topic_id": str(1000 + index)} for index in range(15)]
        search_result = {
            "group_id": "51111112855254",
            "stock_name": "宁德时代",
            "stock_code": "300750",
            "market": "SZ",
            "topics": search_topics,
            "concepts": ["固态电池"],
            "topic_count": len(search_topics),
            "recommendation_count": 10,
            "processed_topic_ids": [],
            "skipped_topic_ids": [],
        }
        payload_topics = [
            {"topic_id": topic["topic_id"], "excerpt": f"excerpt-{topic['topic_id']}"}
            for topic in search_topics
        ]
        conn = Mock()

        def fake_ai(prompt_payload, *, incremental=False):
            if fake_ai.call_count == 0:
                fake_ai.call_count += 1
                return "summary batch 1", "test-model"
            raise RuntimeError("upstream failed")

        fake_ai.call_count = 0

        with (
            patch("backend.services.stock_topic_analysis_service.search_stock_topics", return_value=search_result),
            patch("backend.services.stock_topic_analysis_service.get_latest_stock_topic_analysis", return_value=None),
            patch("backend.services.stock_topic_analysis_service._build_analysis_topic_payload", return_value=payload_topics),
            patch("backend.services.stock_topic_analysis_service._call_stock_analysis_ai", side_effect=fake_ai),
            patch("backend.services.stock_topic_analysis_service.connect", return_value=conn),
            self.assertRaises(RuntimeError),
        ):
            analyze_stock_topics("51111112855254", "宁德时代")

        analysis_writes = [
            call.args[1]
            for call in conn.execute.call_args_list
            if "INSERT INTO stock_topic_analyses" in call.args[0]
        ]
        self.assertEqual("summary batch 1", analysis_writes[-1][7])
        self.assertEqual("test-model", analysis_writes[-1][8])
        self.assertEqual("failed", analysis_writes[-1][9])
        self.assertEqual("upstream failed", analysis_writes[-1][10])

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_build_analysis_topic_payload_does_not_truncate_stock_excerpts(self):
        from backend.services.stock_topic_analysis_service import _build_analysis_topic_payload

        topics = [
            {
                "topic_id": str(1000 + index),
                "title": f"title-{index}",
                "create_time": "2026-05-01T00:00:00+0800",
                "likes_count": 0,
                "comments_count": 0,
                "reading_count": 0,
                "concepts": [],
                "excerpt": f"excerpt-{index}",
            }
            for index in range(65)
        ]

        payload = _build_analysis_topic_payload(
            {
                "group_id": "51111112855254",
                "stock_name": "宁德时代",
                "topics": topics,
            }
        )

        self.assertEqual(65, len(payload))
        self.assertEqual("1000", payload[0]["topic_id"])
        self.assertEqual("1064", payload[-1]["topic_id"])

    @unittest.skipUnless(HAS_SERVICE_DEPS, "stock topic analysis service dependencies are not installed")
    def test_stock_analysis_prompt_uses_excerpt_and_incremental_dedupe_guidance(self):
        from backend.services.stock_topic_analysis_service import _call_stock_analysis_ai

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            class responses:
                @staticmethod
                def create(**kwargs):
                    FakeClient.kwargs = kwargs
                    return type("Response", (), {"output_text": "summary"})()

        with (
            patch("backend.services.stock_topic_analysis_service.OpenAI", FakeClient),
            patch("backend.services.stock_topic_analysis_service.get_openai_compatible_config", return_value={"api_key": "test-key", "model": "test-model", "base_url": "http://test"}),
        ):
            _call_stock_analysis_ai('{"new_topics":[]}')

        prompt = FakeClient.kwargs["input"][1]["content"]
        self.assertIn("输入原文摘录", prompt)
        self.assertIn("输入中的 excerpt", prompt)
        self.assertIn("关键数据与经营口径", prompt)
        self.assertIn("报告基准日", prompt)
        self.assertIn("历史业绩", prompt)
        self.assertIn("成稿前先做内部清洗", prompt)
        self.assertIn("过期内容删除标准", prompt)
        self.assertIn("投资摘要时间要求", prompt)
        self.assertIn("任何收入预测、利润预测、出货预测、财务预测、目标价、评级、估值倍数及其具体数值都不得作为摘要 bullet", prompt)
        self.assertIn("不要把历史高增写成当前亮点", prompt)
        self.assertIn("不进入任何章节", prompt)
        self.assertIn("旧报告中已有的也要删除", prompt)
        self.assertIn("不要降级保留为历史口径", prompt)
        self.assertIn("删除后不要解释", prompt)
        self.assertIn("当前有效数据披露有限", prompt)
        self.assertIn("不要放进关键数据表", prompt)
        self.assertIn("核心逻辑写法", prompt)
        self.assertIn("不得用已过季度或年度的高增", prompt)
        self.assertIn("不要默认输出表格、项目清单或逐条数字罗列", prompt)
        self.assertIn("只有当数据之间存在清晰对比关系且确实有助于阅读时，才可以使用极简表格", prompt)
        self.assertIn("不要为了显得完整而收录低价值数字", prompt)
        self.assertIn("旧季度/旧年度业绩数据不要进入该章节", prompt)
        self.assertIn("评级、目标价、估值倍数、市值空间", prompt)
        self.assertIn("应合并成一句完整表述", prompt)
        self.assertIn("催化与跟踪分工", prompt)
        self.assertIn("增量融合", prompt)
        self.assertIn("旧报告清洗", prompt)
        self.assertIn("用实际结果替代旧预测", prompt)
        self.assertIn("不要为了增量而强行扩写", prompt)
        self.assertIn("不要为了完整而扩写", prompt)
        self.assertIn("最终报告中不要保留这些市场观点", prompt)
        self.assertIn("禁止输出内部字段名或系统统计口径", prompt)


if __name__ == "__main__":
    unittest.main()
