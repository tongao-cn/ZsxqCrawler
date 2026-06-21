import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_OPENAI = find_spec("openai") is not None


class DailyTopicAnalysisAITests(unittest.TestCase):
    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_call_report_ai_builds_responses_image_request(self):
        from backend.services import daily_topic_analysis_ai as ai

        captured = {}

        def fake_call(request):
            captured["request"] = request
            return " report "

        image_part = {"type": "input_image", "image_url": "data:image/jpeg;base64,abc"}
        with patch.object(
            ai,
            "get_openai_compatible_config",
            return_value={
                "api_key": " sk-test ",
                "model": " model-a ",
                "base_url": " https://api.example.test ",
                "wire_api": " responses ",
            },
        ), patch.object(ai, "get_summary_reasoning_effort", return_value=" high "), patch.object(
            ai,
            "build_image_content_parts",
            return_value=[image_part],
        ) as build_images, patch.object(ai, "call_ai_text", side_effect=fake_call):
            result = ai.call_report_ai(
                "daily prompt",
                group_id="group-1",
                image_inputs=[{"url": "https://example.test/a.jpg"}],
                max_image_bytes=123,
            )

        self.assertEqual(("report", "model-a"), result)
        request = captured["request"]
        self.assertEqual("sk-test", request.api_key)
        self.assertEqual("model-a", request.model)
        self.assertEqual("https://api.example.test", request.api_base)
        self.assertEqual("responses", request.wire_api)
        self.assertEqual("high", request.reasoning_effort)
        self.assertEqual(180, request.timeout)
        self.assertEqual(
            [
                {"type": "input_text", "text": "daily prompt"},
                image_part,
            ],
            request.messages[1]["content"],
        )
        build_images.assert_called_once_with(
            "group-1",
            [{"url": "https://example.test/a.jpg"}],
            max_image_bytes=123,
        )

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_call_report_ai_builds_chat_image_request(self):
        from backend.services import daily_topic_analysis_ai as ai

        captured = {}

        def fake_call(request):
            captured["request"] = request
            return " chat report "

        with patch.object(
            ai,
            "get_openai_compatible_config",
            return_value={
                "api_key": "sk-test",
                "model": "model-chat",
                "base_url": "https://api.example.test",
                "wire_api": "chat_completions",
            },
        ), patch.object(ai, "get_summary_reasoning_effort", return_value=""), patch.object(
            ai,
            "build_image_content_parts",
            return_value=[{"type": "input_image", "image_url": "data:image/png;base64,xyz"}],
        ), patch.object(ai, "call_ai_text", side_effect=fake_call):
            result = ai.call_report_ai(
                "daily prompt",
                group_id="group-1",
                image_inputs=[{"url": "https://example.test/a.png"}],
                max_image_bytes=456,
            )

        self.assertEqual(("chat report", "model-chat"), result)
        request = captured["request"]
        self.assertEqual("chat_completions", request.wire_api)
        self.assertEqual(
            [
                {"type": "text", "text": "daily prompt"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,xyz"}},
            ],
            request.messages[1]["content"],
        )

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_call_report_ai_keeps_chat_text_prompt_plain_without_images(self):
        from backend.services import daily_topic_analysis_ai as ai

        captured = {}

        def fake_call(request):
            captured["request"] = request
            return " text report "

        with patch.object(
            ai,
            "get_openai_compatible_config",
            return_value={
                "api_key": "sk-test",
                "model": "model-chat",
                "base_url": "https://api.example.test",
                "wire_api": "chat_completions",
            },
        ), patch.object(ai, "get_summary_reasoning_effort", return_value=""), patch.object(
            ai,
            "build_image_content_parts",
            return_value=[],
        ) as build_images, patch.object(ai, "call_ai_text", side_effect=fake_call):
            result = ai.call_report_ai(
                "daily prompt",
                group_id="group-1",
                image_inputs=[],
                max_image_bytes=456,
            )

        self.assertEqual(("text report", "model-chat"), result)
        self.assertEqual("daily prompt", captured["request"].messages[1]["content"])
        build_images.assert_called_once_with("group-1", [], max_image_bytes=456)


if __name__ == "__main__":
    unittest.main()
