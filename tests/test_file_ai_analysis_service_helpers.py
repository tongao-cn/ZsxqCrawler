import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


HAS_FILE_AI_DEPS = find_spec("openai") is not None


class FileAIAnalysisServiceHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_file_ai_analysis_default_reasoning_effort_is_medium(self):
        from backend.services.file_ai_content_analysis import (
            DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
        )

        self.assertEqual("medium", DEFAULT_FILE_ANALYSIS_REASONING_EFFORT)

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
    def test_analyze_file_content_converts_pdf_to_markdown_before_summarizing(self):
        from backend.services.file_ai_content_analysis import analyze_file_content

        captured = {}

        def fake_extract_pdf_markdown(path, **kwargs):
            captured["pdf_path"] = path
            captured["pdf_kwargs"] = kwargs
            return "## Page 1\n\nPDF markdown"

        def fake_summarize_text(text, **kwargs):
            captured["summary_text"] = text
            captured["summary_kwargs"] = kwargs
            return "summary from markdown"

        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfake pdf")

            result = analyze_file_content(
                pdf_path,
                file_name="report.pdf",
                model="gpt-5.5",
                api_base="https://api.openai.com/v1",
                wire_api="responses",
                reasoning_effort="medium",
                extract_pdf_markdown=fake_extract_pdf_markdown,
                summarize_text=fake_summarize_text,
            )

        self.assertEqual("summary from markdown", result.summary)
        self.assertEqual("## Page 1\n\nPDF markdown", result.extracted_text)
        self.assertEqual("text/markdown", result.content_type)
        self.assertEqual(pdf_path, captured["pdf_path"])
        self.assertEqual("report.pdf", captured["pdf_kwargs"]["file_name"])
        self.assertEqual("gpt-5.5", captured["pdf_kwargs"]["model"])
        self.assertEqual("https://api.openai.com/v1", captured["pdf_kwargs"]["api_base"])
        self.assertEqual("responses", captured["pdf_kwargs"]["wire_api"])
        self.assertEqual("medium", captured["pdf_kwargs"]["reasoning_effort"])
        self.assertEqual("## Page 1\n\nPDF markdown", captured["summary_text"])
        self.assertEqual("report.pdf", captured["summary_kwargs"]["file_name"])
        self.assertEqual("gpt-5.5", captured["summary_kwargs"]["model"])
        self.assertEqual("medium", captured["summary_kwargs"]["reasoning_effort"])

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_file_ai_analysis_service_pdf_wrapper_uses_markdown_conversion(self):
        from backend.services import file_ai_analysis_service

        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfake pdf")

            with (
                patch(
                    "backend.services.file_ai_analysis_service._extract_pdf_markdown_for_analysis",
                    return_value="## Page 1\n\nPDF markdown",
                ) as extract_pdf_markdown,
                patch(
                    "backend.services.file_ai_analysis_service._summarize_text_with_ai",
                    return_value="summary from markdown",
                ) as summarize_text,
            ):
                result = file_ai_analysis_service._analyze_file_content(
                    pdf_path,
                    file_name="report.pdf",
                    model="gpt-5.5",
                    api_base="https://api.openai.com/v1",
                    wire_api="responses",
                    reasoning_effort="medium",
                )

        self.assertEqual("summary from markdown", result.summary)
        self.assertEqual("## Page 1\n\nPDF markdown", result.extracted_text)
        self.assertEqual("text/markdown", result.content_type)
        extract_pdf_markdown.assert_called_once()
        summarize_text.assert_called_once()

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_extract_pdf_markdown_for_analysis_passes_reasoning_effort_to_conversion(self):
        from backend.services.file_ai_content_analysis import extract_pdf_markdown_for_analysis

        captured = {}

        class FakeConversionResult:
            markdown = "markdown"
            pages = []

        def fake_convert_pdf(path, output_dir, **kwargs):
            captured["path"] = path
            captured["output_dir"] = output_dir
            captured["kwargs"] = kwargs
            return FakeConversionResult()

        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfake pdf")

            markdown = extract_pdf_markdown_for_analysis(
                pdf_path,
                file_name="report.pdf",
                model="gpt-5.5",
                api_base="https://api.openai.com/v1",
                wire_api="responses",
                reasoning_effort="low",
                convert_pdf=fake_convert_pdf,
            )

        self.assertEqual("markdown", markdown)
        self.assertEqual(pdf_path, captured["path"])
        self.assertEqual("gpt-5.5", captured["kwargs"]["model"])
        self.assertEqual("https://api.openai.com/v1", captured["kwargs"]["api_base"])
        self.assertEqual("low", captured["kwargs"]["reasoning_effort"])

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
