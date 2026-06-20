import unittest
from importlib.util import find_spec
from types import SimpleNamespace
from unittest.mock import patch


HAS_OPENAI = find_spec("openai") is not None


class AIClientTests(unittest.TestCase):
    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_extract_response_text_prefers_output_text(self):
        from backend.services.ai_client import extract_response_text

        response = SimpleNamespace(output_text="ready")

        self.assertEqual("ready", extract_response_text(response))

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_extract_response_text_collects_output_chunks(self):
        from backend.services.ai_client import extract_response_text

        response = SimpleNamespace(
            output=[
                SimpleNamespace(content=[SimpleNamespace(text="a"), SimpleNamespace(text="b")]),
                SimpleNamespace(content=[SimpleNamespace(text="c")]),
            ]
        )

        self.assertEqual("a\nb\nc", extract_response_text(response))

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_json_schema_helpers_build_wire_specific_shapes(self):
        from backend.services.ai_client import chat_json_schema_response_format, responses_json_schema_text_format

        schema = {"type": "object", "properties": {}, "additionalProperties": False}

        self.assertEqual(
            {
                "format": {
                    "type": "json_schema",
                    "name": "payload",
                    "strict": True,
                    "schema": schema,
                }
            },
            responses_json_schema_text_format("payload", schema),
        )
        self.assertEqual(
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "payload",
                    "strict": False,
                    "schema": schema,
                },
            },
            chat_json_schema_response_format("payload", schema, strict=False),
        )

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_call_ai_text_uses_responses_wire(self):
        from backend.services.ai_client import AITextRequest, call_ai_text

        class FakeResponses:
            kwargs = None

            def create(self, **kwargs):
                FakeResponses.kwargs = kwargs
                return SimpleNamespace(output_text="responses text")

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.responses = FakeResponses()

        with patch("backend.services.ai_client.OpenAI", FakeClient):
            text = call_ai_text(
                AITextRequest(
                    api_key="sk-test",
                    model="model-a",
                    api_base="https://api.example.test",
                    messages=[{"role": "user", "content": "hello"}],
                    wire_api="responses",
                    reasoning_effort="high",
                    responses_text_format={"format": {"type": "text"}},
                    timeout=33,
                )
            )

        self.assertEqual("responses text", text)
        self.assertEqual("model-a", FakeResponses.kwargs["model"])
        self.assertEqual([{"role": "user", "content": "hello"}], FakeResponses.kwargs["input"])
        self.assertEqual({"effort": "high"}, FakeResponses.kwargs["reasoning"])
        self.assertEqual({"format": {"type": "text"}}, FakeResponses.kwargs["text"])

    @unittest.skipUnless(HAS_OPENAI, "openai dependency is not installed")
    def test_call_ai_text_uses_chat_wire(self):
        from backend.services.ai_client import AITextRequest, call_ai_text

        class FakeChatCompletions:
            kwargs = None

            def create(self, **kwargs):
                FakeChatCompletions.kwargs = kwargs
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="chat text"))]
                )

        class FakeClient:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=FakeChatCompletions())

        with patch("backend.services.ai_client.OpenAI", FakeClient):
            text = call_ai_text(
                AITextRequest(
                    api_key="sk-test",
                    model="model-a",
                    api_base="https://api.example.test",
                    messages=[{"role": "user", "content": "hello"}],
                    wire_api="chat",
                    chat_response_format={"type": "json_object"},
                )
            )

        self.assertEqual("chat text", text)
        self.assertEqual("model-a", FakeChatCompletions.kwargs["model"])
        self.assertEqual([{"role": "user", "content": "hello"}], FakeChatCompletions.kwargs["messages"])
        self.assertFalse(FakeChatCompletions.kwargs["stream"])
        self.assertEqual({"type": "json_object"}, FakeChatCompletions.kwargs["response_format"])


if __name__ == "__main__":
    unittest.main()
