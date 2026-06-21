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

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_call_runtime_ai_text_returns_text_and_model(self):
        from backend.services.ai_runtime_request import call_runtime_ai_text

        captured = {}

        def fake_call(request):
            captured["request"] = request
            return " model output "

        result = call_runtime_ai_text(
            [{"role": "user", "content": "hello"}],
            get_ai_config=lambda: {
                "api_key": "sk-test",
                "model": "model-a",
                "base_url": "https://api.example.test",
                "wire_api": "responses",
            },
            reasoning_effort=" high ",
            timeout=42,
            call_text=fake_call,
        )

        self.assertEqual(" model output ", result.text)
        self.assertEqual("model-a", result.model)
        request = captured["request"]
        self.assertEqual("model-a", request.model)
        self.assertEqual("high", request.reasoning_effort)
        self.assertEqual(42, request.timeout)

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_call_structured_ai_object_builds_schema_formats_and_parses_payload(self):
        from backend.services.ai_runtime_request import call_structured_ai_object

        captured = {}
        schema = {"type": "object", "properties": {}, "additionalProperties": False}

        def fake_call(request):
            captured["request"] = request
            return '{"ok": true}'

        result = call_structured_ai_object(
            [{"role": "user", "content": "hello"}],
            schema_name="payload",
            schema=schema,
            label="Payload",
            get_ai_config=lambda: {
                "api_key": "sk-test",
                "model": "model-a",
                "base_url": "https://api.example.test",
                "wire_api": "responses",
            },
            reasoning_effort="medium",
            call_text=fake_call,
        )

        self.assertEqual({"ok": True}, result.payload)
        self.assertEqual('{"ok": true}', result.text)
        self.assertEqual("model-a", result.model)
        request = captured["request"]
        self.assertEqual(
            {
                "format": {
                    "type": "json_schema",
                    "name": "payload",
                    "strict": True,
                    "schema": schema,
                }
            },
            request.responses_text_format,
        )
        self.assertEqual(
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "payload",
                    "strict": True,
                    "schema": schema,
                },
            },
            request.chat_response_format,
        )

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_call_structured_ai_object_wraps_invalid_json_with_label(self):
        from backend.services.ai_runtime_request import AIRuntimeStructuredObjectParseError, call_structured_ai_object

        with self.assertRaisesRegex(AIRuntimeStructuredObjectParseError, "Payload不是合法 JSON") as raised:
            call_structured_ai_object(
                [{"role": "user", "content": "hello"}],
                schema_name="payload",
                schema={"type": "object", "properties": {}, "additionalProperties": False},
                label="Payload",
                get_ai_config=lambda: {
                    "api_key": "sk-test",
                    "model": "model-a",
                    "base_url": "https://api.example.test",
                    "wire_api": "responses",
                },
                call_text=lambda _request: "not json",
            )
        self.assertIsInstance(raised.exception, RuntimeError)
        self.assertEqual("Payload", raised.exception.label)
        self.assertEqual("not json", raised.exception.text)
        self.assertEqual("not json", raised.exception.preview)


if __name__ == "__main__":
    unittest.main()
