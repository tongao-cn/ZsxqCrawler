import unittest

from backend.core.log_redaction import redact_json_like, redact_mapping, redact_response_text, redact_text


class LogRedactionTests(unittest.TestCase):
    def test_redact_mapping_hides_sensitive_headers(self):
        redacted = redact_mapping({
            "Cookie": "session=secret",
            "X-Signature": "signature-secret",
            "X-Timestamp": "123",
            "User-Agent": "ua",
        })

        self.assertEqual("<redacted>", redacted["Cookie"])
        self.assertEqual("<redacted>", redacted["X-Signature"])
        self.assertEqual("123", redacted["X-Timestamp"])
        self.assertEqual("ua", redacted["User-Agent"])

    def test_redact_json_like_hides_nested_signed_download_url(self):
        redacted = redact_json_like({
            "succeeded": True,
            "resp_data": {"download_url": "https://files.example/signed-token"},
        })

        self.assertEqual("<redacted>", redacted["resp_data"]["download_url"])

    def test_redact_text_hides_header_style_values(self):
        text = "Cookie: session=secret\nX-Signature: abc\nsafe: ok"

        redacted = redact_text(text)

        self.assertNotIn("session=secret", redacted)
        self.assertNotIn("abc", redacted)
        self.assertIn("safe: ok", redacted)

    def test_redact_response_text_parses_json_before_clipping(self):
        redacted = redact_response_text(
            '{"resp_data": {"download_url": "https://files.example/signed-token"}, "ok": true}',
            limit=200,
        )

        self.assertIn("<redacted>", redacted)
        self.assertNotIn("signed-token", redacted)


if __name__ == "__main__":
    unittest.main()
