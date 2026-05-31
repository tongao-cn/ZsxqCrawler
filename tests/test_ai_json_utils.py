import unittest

from backend.services.ai_json_utils import extract_json_object


class AiJsonUtilsTests(unittest.TestCase):
    def test_extract_json_object_parses_plain_object(self):
        self.assertEqual({"a": 1}, extract_json_object('{"a": 1}'))

    def test_extract_json_object_strips_markdown_fence(self):
        self.assertEqual({"stocks": []}, extract_json_object("```json\n{\"stocks\": []}\n```"))

    def test_extract_json_object_recovers_embedded_object(self):
        self.assertEqual({"keywords": ["AI"]}, extract_json_object('结果如下：{"keywords":["AI"]}'))

    def test_extract_json_object_rejects_non_object_or_invalid_json(self):
        self.assertEqual({}, extract_json_object("[1, 2]"))
        self.assertEqual({}, extract_json_object("not json"))


if __name__ == "__main__":
    unittest.main()
