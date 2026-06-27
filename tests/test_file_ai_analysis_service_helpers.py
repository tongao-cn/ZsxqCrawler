import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


HAS_FILE_AI_DEPS = find_spec("openai") is not None


class FileAIAnalysisServiceHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_cached_analysis_result_marks_completed_summary_as_cached(self):
        from backend.services.file_ai_analysis_service import _cached_analysis_result

        existing = {"status": "completed", "summary": "ok", "file_id": 123}

        result = _cached_analysis_result(existing, force=False)

        self.assertEqual({"status": "completed", "summary": "ok", "file_id": 123, "cached": True}, result)

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_cached_analysis_result_skips_force_and_incomplete_records(self):
        from backend.services.file_ai_analysis_service import _cached_analysis_result

        self.assertIsNone(_cached_analysis_result({"status": "completed", "summary": "ok"}, force=True))
        self.assertIsNone(_cached_analysis_result({"status": "failed", "summary": "ok"}, force=False))
        self.assertIsNone(_cached_analysis_result({"status": "completed", "summary": ""}, force=False))

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_extract_file_content_for_analysis_uses_audio_transcription(self):
        from backend.services.file_ai_content_analysis import extract_file_content_for_analysis

        text, content_type = extract_file_content_for_analysis(
            Path("voice.mp3"),
            transcribe_audio=lambda _path: "text",
        )

        self.assertEqual("text", text)
        self.assertEqual("audio/mp3", content_type)

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_extract_file_content_for_analysis_delegates_non_audio(self):
        from backend.services.file_ai_content_analysis import extract_file_content_for_analysis

        text, content_type = extract_file_content_for_analysis(
            Path("note.txt"),
            extract_text=lambda _path: ("text", "text/plain"),
        )

        self.assertEqual("text", text)
        self.assertEqual("text/plain", content_type)

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_summarize_text_with_ai_uses_deep_summary_prompt(self):
        from backend.services.ai_runtime_request import AIRuntimeTextResult
        from backend.services.file_ai_content_analysis import summarize_text_with_ai

        captured = {}

        def fake_call(messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return AIRuntimeTextResult(" Deep summary ", "gpt-5.5")

        with patch("backend.services.file_ai_content_analysis.call_runtime_ai_text", side_effect=fake_call):
            summary = summarize_text_with_ai(
                "正文内容",
                file_name="report.txt",
                model="gpt-5.5",
                api_base="https://api.openai.com/v1",
                wire_api="responses",
                reasoning_effort="high",
                get_ai_config=lambda: {"api_key": "sk-test"},
            )

        self.assertEqual("Deep summary", summary)
        self.assertEqual("gpt-5.5", captured["kwargs"]["model"])
        self.assertEqual("https://api.openai.com/v1", captured["kwargs"]["api_base"])
        self.assertEqual("responses", captured["kwargs"]["wire_api"])
        self.assertEqual("high", captured["kwargs"]["reasoning_effort"])
        self.assertNotIn("timeout", captured["kwargs"])
        messages = captured["messages"]
        self.assertIn("深入、结构化、可执行", messages[0]["content"])
        user_prompt = messages[1]["content"]
        self.assertIn("请深度阅读并总结文件《report.txt》", user_prompt)
        self.assertIn("不要为了简洁省略重要信息", user_prompt)
        self.assertIn("关键数据、预测、目标价、评级或情景假设", user_prompt)
        self.assertNotIn("3-8条", user_prompt)

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_summarize_pdf_with_ai_sends_pdf_file_input(self):
        from backend.services.ai_runtime_request import AIRuntimeTextResult
        from backend.services.file_ai_content_analysis import summarize_pdf_with_ai

        captured = {}

        def fake_call(messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return AIRuntimeTextResult(" PDF summary ", "gpt-5.5")

        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfake pdf")

            with patch("backend.services.file_ai_content_analysis.call_runtime_ai_text", side_effect=fake_call):
                summary = summarize_pdf_with_ai(
                    pdf_path,
                    file_name="report.pdf",
                    model="gpt-5.5",
                    api_base="https://api.openai.com/v1",
                    wire_api="responses",
                    reasoning_effort="medium",
                    get_ai_config=lambda: {"api_key": "sk-test"},
                )

        self.assertEqual("PDF summary", summary)
        self.assertEqual("gpt-5.5", captured["kwargs"]["model"])
        self.assertEqual("medium", captured["kwargs"]["reasoning_effort"])
        self.assertNotIn("timeout", captured["kwargs"])
        content = captured["messages"][0]["content"]
        self.assertEqual("input_file", content[0]["type"])
        self.assertEqual("report.pdf", content[0]["filename"])
        self.assertTrue(content[0]["file_data"].startswith("data:application/pdf;base64,"))
        self.assertEqual("input_text", content[1]["type"])
        self.assertIn("请深度阅读并总结文件《report.pdf》", content[1]["text"])
        self.assertIn("不要为了简洁省略重要信息", content[1]["text"])
        self.assertNotIn("3-8条", content[1]["text"])

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_analyze_file_content_returns_summary_preview_and_source_size(self):
        from backend.services.file_ai_content_analysis import analyze_file_content

        with TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "report.txt"
            source_path.write_text("raw file bytes", encoding="utf-8")
            result = analyze_file_content(
                source_path,
                file_name="report.txt",
                model="gpt-5.5",
                api_base="https://api.openai.com/v1",
                wire_api="responses",
                reasoning_effort="medium",
                extract_content=lambda _path: ("正文" * 3000, "text/plain"),
                summarize_text=lambda text, **_kwargs: f"summary:{len(text)}",
            )

        self.assertEqual("summary:6000", result.summary)
        self.assertEqual("text/plain", result.content_type)
        self.assertEqual("正文" * 2000, result.extracted_text_preview)
        self.assertEqual(len("raw file bytes".encode("utf-8")), result.source_size)


if __name__ == "__main__":
    unittest.main()
