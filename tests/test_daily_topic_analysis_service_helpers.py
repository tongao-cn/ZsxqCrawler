import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_DAILY_SERVICE_DEPS = find_spec("openai") is not None


class DailyTopicAnalysisServiceHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_build_empty_report_summary_preserves_expected_content(self):
        from backend.services.daily_topic_analysis_service import _build_empty_report_summary

        summary = _build_empty_report_summary("2026-05-07")

        self.assertIn("# 每日话题分析报告", summary)
        self.assertIn("日期：2026-05-07", summary)
        self.assertIn("当天没有采集到话题", summary)

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_build_report_metadata_collects_topic_ids_and_limited_image_refs(self):
        from backend.services.daily_topic_analysis_service import MAX_IMAGES_PER_REPORT, _build_report_metadata

        topics = [
            {
                "topic_id": "topic-1",
                "images": [{"image_ref": f"topic-image-{index}", "url": f"https://example.com/{index}.jpg"}],
                "comments": [],
            }
            for index in range(MAX_IMAGES_PER_REPORT + 2)
        ]

        metadata = _build_report_metadata(
            group_id="group-1",
            report_date="2026-05-07",
            topics=topics,
            report_path="C:/tmp/report.md",
        )

        self.assertEqual("group-1", metadata["group_id"])
        self.assertEqual("2026-05-07", metadata["report_date"])
        self.assertEqual(MAX_IMAGES_PER_REPORT + 2, metadata["topic_count"])
        self.assertEqual(["topic-1"] * (MAX_IMAGES_PER_REPORT + 2), metadata["topic_ids"])
        self.assertEqual(MAX_IMAGES_PER_REPORT, len(metadata["image_refs"]))
        self.assertEqual("topic-image-0", metadata["image_refs"][0])
        self.assertEqual("C:/tmp/report.md", metadata["report_path"])

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_parse_report_raw_json_returns_dict_or_empty_dict(self):
        from backend.services.daily_topic_analysis_service import _parse_report_raw_json

        self.assertEqual({"ok": True}, _parse_report_raw_json('{"ok": true}'))
        self.assertEqual({}, _parse_report_raw_json(""))
        self.assertEqual({}, _parse_report_raw_json("{bad json"))
        self.assertEqual({}, _parse_report_raw_json("[1, 2]"))

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_build_report_user_prompt_returns_prompt_text(self):
        from backend.services.daily_topic_analysis_service import _build_report_user_prompt

        prompt = _build_report_user_prompt('{"topics":[]}', "2026-05-07", image_refs=["topic_1_image_1"])

        self.assertIsInstance(prompt, str)
        self.assertIn("请为 2026-05-07 的全部话题生成 AI 日报", prompt)
        self.assertIn("话题数据：", prompt)
        self.assertIn('{"topics":[]}', prompt)
        self.assertIn("图片已作为附件", prompt)

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_split_topics_for_report_chunks_keeps_topic_boundaries(self):
        from backend.services.daily_topic_analysis_service import _split_topics_for_report_chunks

        topics = [
            {"topic_id": "1", "talk_text": "a" * 30, "comments": [], "images": []},
            {"topic_id": "2", "talk_text": "b" * 30, "comments": [], "images": []},
            {"topic_id": "3", "talk_text": "c" * 30, "comments": [], "images": []},
        ]

        chunks = _split_topics_for_report_chunks("group-1", "2026-05-07", topics, max_chars=230)

        self.assertEqual([["1"], ["2"], ["3"]], [[topic["topic_id"] for topic in chunk] for chunk in chunks])

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_generate_daily_report_summary_uses_single_request_for_small_payload(self):
        from backend.services import daily_topic_analysis_service as service

        topics = [{"topic_id": "1", "talk_text": "small", "comments": [], "images": []}]

        with patch.object(service, "_generate_report_with_ai", return_value=("# report", "model-a")) as generate_report:
            summary, model, meta = service._generate_daily_report_summary(
                group_id="group-1",
                report_date="2026-05-07",
                topics=topics,
            )

        self.assertEqual("# report", summary)
        self.assertEqual("model-a", model)
        self.assertEqual("single", meta["generation_mode"])
        generate_report.assert_called_once()

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_generate_daily_report_summary_retries_without_images(self):
        from backend.services import daily_topic_analysis_service as service

        topics = [{"topic_id": "1", "talk_text": "small", "comments": [], "images": [{"url": "https://example.com/a.jpg"}]}]

        with patch.object(
            service,
            "_collect_report_images",
            return_value=[{"image_ref": "topic_1_image_1", "url": "https://example.com/a.jpg"}],
        ), patch.object(
            service,
            "_generate_report_with_ai",
            side_effect=[RuntimeError("upstream failed"), ("# report", "model-a")],
        ) as generate_report:
            summary, model, meta = service._generate_daily_report_summary(
                group_id="group-1",
                report_date="2026-05-07",
                topics=topics,
            )

        self.assertEqual("# report", summary)
        self.assertEqual("model-a", model)
        self.assertTrue(meta["image_retry_without_images"])
        self.assertEqual(2, generate_report.call_count)
        self.assertEqual([], generate_report.call_args.kwargs["image_inputs"])

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_generate_daily_report_summary_chunks_large_payload(self):
        from backend.services import daily_topic_analysis_service as service

        topics = [
            {"topic_id": "1", "talk_text": "a" * 40, "comments": [], "images": []},
            {"topic_id": "2", "talk_text": "b" * 40, "comments": [], "images": []},
        ]

        with patch.object(service, "MAX_PROMPT_CHARS", 100), patch.object(
            service,
            "_split_topics_for_report_chunks",
            return_value=[[topics[0]], [topics[1]]],
        ) as generate_chunk, patch.object(
            service,
            "_generate_chunk_summaries_concurrently",
            return_value=(["chunk-1", "chunk-2"], "model-a", 2),
        ) as generate_chunks, patch.object(
            service,
            "_generate_final_report_from_chunks_with_ai",
            return_value=("# final", "model-a"),
        ) as generate_final:
            summary, model, meta = service._generate_daily_report_summary(
                group_id="group-1",
                report_date="2026-05-07",
                topics=topics,
            )

        self.assertEqual("# final", summary)
        self.assertEqual("model-a", model)
        self.assertEqual("chunked", meta["generation_mode"])
        self.assertEqual(2, meta["chunk_count"])
        self.assertEqual([1, 1], meta["chunk_topic_counts"])
        self.assertEqual(2, meta["chunk_workers"])
        generate_chunk.assert_called_once()
        generate_chunks.assert_called_once()
        generate_final.assert_called_once_with(["chunk-1", "chunk-2"], "2026-05-07", group_id="group-1")

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_generate_chunk_summaries_concurrently_preserves_chunk_order(self):
        from backend.services import daily_topic_analysis_service as service

        chunks = [
            [{"topic_id": "1", "talk_text": "a", "comments": [], "images": []}],
            [{"topic_id": "2", "talk_text": "b", "comments": [], "images": []}],
            [{"topic_id": "3", "talk_text": "c", "comments": [], "images": []}],
        ]

        def fake_generate(_payload, _report_date, *, group_id, chunk_index, chunk_count):
            self.assertEqual("group-1", group_id)
            self.assertEqual(3, chunk_count)
            return f"chunk-{chunk_index}", f"model-{chunk_index}"

        with patch.object(service, "MAX_REPORT_CHUNK_WORKERS", 2), patch.object(
            service,
            "_generate_chunk_summary_with_ai",
            side_effect=fake_generate,
        ):
            summaries, model, workers = service._generate_chunk_summaries_concurrently(
                chunks,
                "2026-05-07",
                group_id="group-1",
            )

        self.assertEqual(["chunk-1", "chunk-2", "chunk-3"], summaries)
        self.assertEqual("model-3", model)
        self.assertEqual(2, workers)

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_fetch_topics_for_date_scopes_child_queries_by_group(self):
        from datetime import date

        from backend.services.daily_topic_analysis_service import _fetch_topics_for_date

        class FakeResult:
            def __init__(self, rows):
                self.rows = rows

            def fetchall(self):
                return self.rows

        class FakeConn:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                normalized = " ".join(sql.split())
                self.calls.append((normalized, tuple(params)))
                if "FROM topics t" in normalized:
                    return FakeResult(
                        [
                            {
                                "topic_id": 101,
                                "group_id": "303",
                                "type": "talk",
                                "title": "topic",
                                "create_time": "2026-05-07T10:00:00.000+0800",
                                "likes_count": 1,
                                "comments_count": 2,
                                "reading_count": 3,
                                "readers_count": 4,
                                "digested": 0,
                                "sticky": 0,
                                "talk_text": "body",
                                "talk_owner_name": "owner",
                                "question_text": None,
                                "question_owner_name": None,
                                "answer_text": None,
                                "answer_owner_name": None,
                            }
                        ]
                    )
                return FakeResult([])

        conn = FakeConn()
        topics = _fetch_topics_for_date(conn, group_id="303", report_date=date(2026, 5, 7), comments_per_topic=5)

        self.assertEqual(1, len(topics))
        child_sql = "\n".join(sql for sql, _params in conn.calls[1:])
        self.assertIn("c.group_id = ?", child_sql)
        self.assertIn("tt.topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", child_sql)
        self.assertIn("topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", child_sql)
        self.assertIn((101, "303", 5), [params for _sql, params in conn.calls])


if __name__ == "__main__":
    unittest.main()
