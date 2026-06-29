import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_DAILY_SERVICE_DEPS = find_spec("openai") is not None


class FakeDailyTopicReportAI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, user_prompt, *, group_id, image_inputs=None):
        self.calls.append(
            {
                "prompt": user_prompt,
                "group_id": group_id,
                "image_inputs": image_inputs,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected report AI call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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
        from backend.services import daily_topic_report_generation as generation

        topics = [{"topic_id": "1", "talk_text": "small", "comments": [], "images": []}]

        with patch.object(generation, "generate_report_with_ai", return_value=("# report", "model-a")) as generate_report:
            summary, model, meta = generation.generate_daily_report_summary(
                group_id="group-1",
                report_date="2026-05-07",
                topics=topics,
            )

        self.assertEqual("# report", summary)
        self.assertEqual("model-a", model)
        self.assertEqual("single", meta["generation_mode"])
        generate_report.assert_called_once()

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_generate_daily_report_summary_uses_report_ai_adapter(self):
        from backend.services import daily_topic_report_generation as generation

        images = [{"image_ref": "topic_1_image_1", "url": "https://example.com/a.jpg"}]
        report_ai = FakeDailyTopicReportAI([("# report", "model-a")])
        topics = [{"topic_id": "1", "talk_text": "small", "comments": [], "images": images}]

        with patch.object(generation, "collect_report_images", return_value=images):
            summary, model, meta = generation.generate_daily_report_summary(
                group_id="group-1",
                report_date="2026-05-07",
                topics=topics,
                report_ai=report_ai,
            )

        self.assertEqual("# report", summary)
        self.assertEqual("model-a", model)
        self.assertEqual("single", meta["generation_mode"])
        self.assertEqual(1, len(report_ai.calls))
        self.assertEqual("group-1", report_ai.calls[0]["group_id"])
        self.assertEqual(images, report_ai.calls[0]["image_inputs"])
        self.assertIn("topic_1_image_1", report_ai.calls[0]["prompt"])

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_generate_daily_report_summary_retries_without_images(self):
        from backend.services import daily_topic_report_generation as generation

        topics = [{"topic_id": "1", "talk_text": "small", "comments": [], "images": [{"url": "https://example.com/a.jpg"}]}]

        with patch.object(
            generation,
            "collect_report_images",
            return_value=[{"image_ref": "topic_1_image_1", "url": "https://example.com/a.jpg"}],
        ), patch.object(
            generation,
            "generate_report_with_ai",
            side_effect=[RuntimeError("upstream failed"), ("# report", "model-a")],
        ) as generate_report:
            summary, model, meta = generation.generate_daily_report_summary(
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
        from backend.services import daily_topic_report_generation as generation

        topics = [
            {"topic_id": "1", "talk_text": "a" * 40, "comments": [], "images": []},
            {"topic_id": "2", "talk_text": "b" * 40, "comments": [], "images": []},
        ]

        with patch.object(generation, "MAX_PROMPT_CHARS", 100), patch.object(
            generation,
            "split_topics_for_report_chunks",
            return_value=[[topics[0]], [topics[1]]],
        ) as generate_chunk, patch.object(
            generation,
            "generate_chunk_summaries_concurrently",
            return_value=(["chunk-1", "chunk-2"], "model-a", 2),
        ) as generate_chunks, patch.object(
            generation,
            "generate_final_report_from_chunks_with_retry",
            return_value=("# final", "model-a", False, False),
        ) as generate_final:
            summary, model, meta = generation.generate_daily_report_summary(
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
        self.assertFalse(meta["final_summaries_clipped"])
        self.assertFalse(meta["final_retry_short"])
        generate_chunk.assert_called_once()
        generate_chunks.assert_called_once()
        generate_final.assert_called_once_with(["chunk-1", "chunk-2"], "2026-05-07", group_id="group-1", log_callback=None)

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_generate_final_report_from_chunks_retries_with_shorter_summaries(self):
        from backend.services import daily_topic_report_generation as generation

        prompts = []

        def fake_call(prompt, *, group_id, image_inputs, max_image_bytes):
            prompts.append(prompt)
            self.assertEqual("group-1", group_id)
            self.assertEqual([], image_inputs)
            self.assertEqual(generation.MAX_IMAGE_BYTES, max_image_bytes)
            if len(prompts) == 1:
                raise RuntimeError("upstream failed")
            return "# final", "model-a"

        with patch.object(generation, "MAX_FINAL_CHUNK_SUMMARY_CHARS", 20), patch.object(
            generation,
            "MAX_FINAL_RETRY_CHUNK_SUMMARY_CHARS",
            8,
        ), patch.object(generation, "call_report_ai", side_effect=fake_call):
            summary, model, clipped, retried = generation.generate_final_report_from_chunks_with_retry(
                ["a" * 40, "b" * 40],
                "2026-05-07",
                group_id="group-1",
            )

        self.assertEqual("# final", summary)
        self.assertEqual("model-a", model)
        self.assertTrue(clipped)
        self.assertTrue(retried)
        self.assertEqual(2, len(prompts))
        self.assertLess(len(prompts[1]), len(prompts[0]))

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_generate_final_report_from_chunks_uses_report_ai_adapter_for_retry(self):
        from backend.services import daily_topic_report_generation as generation

        report_ai = FakeDailyTopicReportAI([RuntimeError("upstream failed"), ("# final", "model-a")])

        with patch.object(generation, "MAX_FINAL_CHUNK_SUMMARY_CHARS", 20), patch.object(
            generation,
            "MAX_FINAL_RETRY_CHUNK_SUMMARY_CHARS",
            8,
        ):
            summary, model, clipped, retried = generation.generate_final_report_from_chunks_with_retry(
                ["a" * 40, "b" * 40],
                "2026-05-07",
                group_id="group-1",
                report_ai=report_ai,
            )

        self.assertEqual("# final", summary)
        self.assertEqual("model-a", model)
        self.assertTrue(clipped)
        self.assertTrue(retried)
        self.assertEqual(2, len(report_ai.calls))
        self.assertEqual("group-1", report_ai.calls[0]["group_id"])
        self.assertEqual([], report_ai.calls[0]["image_inputs"])
        self.assertLess(len(report_ai.calls[1]["prompt"]), len(report_ai.calls[0]["prompt"]))

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_generate_chunk_summaries_concurrently_preserves_chunk_order(self):
        from backend.services import daily_topic_report_generation as generation

        chunks = [
            [{"topic_id": "1", "talk_text": "a", "comments": [], "images": []}],
            [{"topic_id": "2", "talk_text": "b", "comments": [], "images": []}],
            [{"topic_id": "3", "talk_text": "c", "comments": [], "images": []}],
        ]

        def fake_generate(_payload, _report_date, *, group_id, chunk_index, chunk_count):
            self.assertEqual("group-1", group_id)
            self.assertEqual(3, chunk_count)
            return f"chunk-{chunk_index}", f"model-{chunk_index}"

        with patch.object(generation, "MAX_REPORT_CHUNK_WORKERS", 2), patch.object(
            generation,
            "generate_chunk_summary_with_ai",
            side_effect=fake_generate,
        ):
            summaries, model, workers = generation.generate_chunk_summaries_concurrently(
                chunks,
                "2026-05-07",
                group_id="group-1",
            )

        self.assertEqual(["chunk-1", "chunk-2", "chunk-3"], summaries)
        self.assertEqual("model-3", model)
        self.assertEqual(2, workers)

    @unittest.skipUnless(HAS_DAILY_SERVICE_DEPS, "daily topic analysis service dependencies are not installed")
    def test_analyze_daily_topics_uses_material_snapshot(self):
        from datetime import date
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        from backend.services import daily_topic_analysis_service as service

        conn = Mock()
        material = SimpleNamespace(
            topics=[{"topic_id": "101", "talk_text": "body", "images": [], "comments": []}],
            topic_count=1,
            prompt_payload_unclipped="snapshot payload",
        )

        with (
            patch.object(service, "_connect_topics_db", return_value=conn),
            patch.object(service, "_load_daily_topic_material", return_value=material) as load_material,
            patch.object(
                service,
                "_generate_daily_report_summary",
                return_value=("# report", "model-a", {"generation_mode": "single"}),
            ) as generate_summary,
            patch.object(service, "_write_report_file", return_value="report.md") as write_report,
            patch.object(service, "_build_report_metadata", return_value={"topic_ids": ["101"]}) as build_metadata,
            patch.object(service, "_upsert_report") as upsert_report,
        ):
            result = service.analyze_daily_topics("303", "2026-05-07", comments_per_topic=5)

        load_material.assert_called_once_with(
            "303",
            report_date=date(2026, 5, 7),
            comments_per_topic=5,
        )
        generate_summary.assert_called_once_with(
            group_id="303",
            report_date="2026-05-07",
            topics=material.topics,
            full_prompt_payload="snapshot payload",
            log_callback=None,
        )
        write_report.assert_called_once_with("303", "2026-05-07", "# report")
        build_metadata.assert_called_once_with(
            group_id="303",
            report_date="2026-05-07",
            topics=material.topics,
            report_path="report.md",
        )
        upsert_report.assert_called_once()
        conn.close.assert_called_once_with()
        self.assertEqual(1, result["topic_count"])
        self.assertEqual("# report", result["summary_markdown"])


if __name__ == "__main__":
    unittest.main()
