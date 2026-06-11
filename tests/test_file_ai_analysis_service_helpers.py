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
        from backend.services.file_ai_analysis_service import _extract_file_content_for_analysis

        with patch("backend.services.file_ai_analysis_service._transcribe_audio_with_faster_whisper", return_value="text"):
            text, content_type = _extract_file_content_for_analysis(Path("voice.mp3"))

        self.assertEqual("text", text)
        self.assertEqual("audio/mp3", content_type)

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_extract_file_content_for_analysis_delegates_non_audio(self):
        from backend.services.file_ai_analysis_service import _extract_file_content_for_analysis

        with patch("backend.services.file_ai_analysis_service.extract_file_text", return_value=("text", "text/plain")):
            text, content_type = _extract_file_content_for_analysis(Path("note.txt"))

        self.assertEqual("text", text)
        self.assertEqual("text/plain", content_type)

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_summarize_text_with_ai_uses_deep_summary_prompt(self):
        from backend.services.file_ai_analysis_service import _summarize_text_with_ai

        class FakeResponses:
            def __init__(self):
                self.kwargs = None

            def create(self, **kwargs):
                self.kwargs = kwargs

                class Response:
                    output_text = "Deep summary"

                return Response()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        fake_client = FakeClient()

        with (
            patch(
                "backend.services.file_ai_analysis_service.get_openai_compatible_config",
                return_value={"api_key": "sk-test"},
            ),
            patch("backend.services.file_ai_analysis_service.OpenAI", return_value=fake_client),
        ):
            summary = _summarize_text_with_ai(
                "正文内容",
                file_name="report.txt",
                model="gpt-5.5",
                api_base="https://api.openai.com/v1",
                wire_api="responses",
                reasoning_effort="high",
            )

        self.assertEqual("Deep summary", summary)
        self.assertEqual({"effort": "high"}, fake_client.responses.kwargs["reasoning"])
        messages = fake_client.responses.kwargs["input"]
        self.assertIn("深入、结构化、可执行", messages[0]["content"])
        user_prompt = messages[1]["content"]
        self.assertIn("请深度阅读并总结文件《report.txt》", user_prompt)
        self.assertIn("不要为了简洁省略重要信息", user_prompt)
        self.assertIn("关键数据、预测、目标价、评级或情景假设", user_prompt)
        self.assertNotIn("3-8条", user_prompt)

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_summarize_pdf_with_ai_sends_pdf_file_input(self):
        from backend.services.file_ai_analysis_service import _summarize_pdf_with_ai

        class FakeResponses:
            def __init__(self):
                self.kwargs = None

            def create(self, **kwargs):
                self.kwargs = kwargs

                class Response:
                    output_text = "PDF summary"

                return Response()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        fake_client = FakeClient()

        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfake pdf")

            with (
                patch(
                    "backend.services.file_ai_analysis_service.get_openai_compatible_config",
                    return_value={"api_key": "sk-test"},
                ),
                patch("backend.services.file_ai_analysis_service.OpenAI", return_value=fake_client),
            ):
                summary = _summarize_pdf_with_ai(
                    pdf_path,
                    file_name="report.pdf",
                    model="gpt-5.5",
                    api_base="https://api.openai.com/v1",
                    wire_api="responses",
                    reasoning_effort="medium",
                )

        self.assertEqual("PDF summary", summary)
        self.assertEqual("gpt-5.5", fake_client.responses.kwargs["model"])
        self.assertEqual({"effort": "medium"}, fake_client.responses.kwargs["reasoning"])
        content = fake_client.responses.kwargs["input"][0]["content"]
        self.assertEqual("input_file", content[0]["type"])
        self.assertEqual("report.pdf", content[0]["filename"])
        self.assertTrue(content[0]["file_data"].startswith("data:application/pdf;base64,"))
        self.assertEqual("input_text", content[1]["type"])
        self.assertIn("请深度阅读并总结文件《report.pdf》", content[1]["text"])
        self.assertIn("不要为了简洁省略重要信息", content[1]["text"])
        self.assertNotIn("3-8条", content[1]["text"])


if __name__ == "__main__":
    unittest.main()
