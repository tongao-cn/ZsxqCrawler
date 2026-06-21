import unittest
from importlib.util import find_spec


HAS_OPENAI = find_spec("openai") is not None


class AIRuntimeRequestTests(unittest.TestCase):
    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_resolve_runtime_text_settings_requires_api_key(self):
        from backend.services.ai_runtime_request import (
            MISSING_OPENAI_RUNTIME_API_KEY_MESSAGE,
            resolve_runtime_text_settings,
        )

        with self.assertRaises(RuntimeError) as raised:
            resolve_runtime_text_settings(get_ai_config=lambda: {"api_key": "  "})
        self.assertEqual(MISSING_OPENAI_RUNTIME_API_KEY_MESSAGE, str(raised.exception))

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_build_runtime_ai_text_request_uses_runtime_config(self):
        from backend.services.ai_runtime_request import build_runtime_ai_text_request

        request = build_runtime_ai_text_request(
            [{"role": "user", "content": "hello"}],
            get_ai_config=lambda: {
                "api_key": " sk-test ",
                "model": " model-a ",
                "base_url": " https://api.example.test ",
                "wire_api": " responses ",
            },
            reasoning_effort=" high ",
            timeout=33,
            responses_text_format={"format": {"type": "text"}},
        )

        self.assertEqual("sk-test", request.api_key)
        self.assertEqual("model-a", request.model)
        self.assertEqual("https://api.example.test", request.api_base)
        self.assertEqual("responses", request.wire_api)
        self.assertEqual("high", request.reasoning_effort)
        self.assertEqual(33, request.timeout)
        self.assertEqual({"format": {"type": "text"}}, request.responses_text_format)

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_build_runtime_ai_text_request_allows_explicit_overrides(self):
        from backend.services.ai_runtime_request import build_runtime_ai_text_request

        request = build_runtime_ai_text_request(
            [{"role": "user", "content": "hello"}],
            get_ai_config=lambda: {
                "api_key": "sk-test",
                "model": "model-from-config",
                "base_url": "https://config.example.test",
                "wire_api": "responses",
            },
            model="model-explicit",
            api_base="https://explicit.example.test",
            wire_api="chat_completions",
            chat_response_format={"type": "json_object"},
        )

        self.assertEqual("model-explicit", request.model)
        self.assertEqual("https://explicit.example.test", request.api_base)
        self.assertEqual("chat_completions", request.wire_api)
        self.assertEqual({"type": "json_object"}, request.chat_response_format)

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_build_runtime_ai_text_request_can_reuse_resolved_settings(self):
        from backend.services.ai_runtime_request import AIRuntimeTextSettings, build_runtime_ai_text_request

        def fail_config():
            raise AssertionError("config should already be resolved")

        request = build_runtime_ai_text_request(
            [{"role": "user", "content": "hello"}],
            settings=AIRuntimeTextSettings(
                api_key="sk-test",
                model="model-a",
                api_base="https://api.example.test",
                wire_api="responses",
            ),
            get_ai_config=fail_config,
            reasoning_effort=" medium ",
        )

        self.assertEqual("sk-test", request.api_key)
        self.assertEqual("model-a", request.model)
        self.assertEqual("https://api.example.test", request.api_base)
        self.assertEqual("responses", request.wire_api)
        self.assertEqual("medium", request.reasoning_effort)


if __name__ == "__main__":
    unittest.main()
