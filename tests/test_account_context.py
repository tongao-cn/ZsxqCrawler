import unittest

from backend.core.account_context import build_stealth_headers, fetch_groups_from_api


class AccountContextTests(unittest.TestCase):
    def test_build_stealth_headers_includes_cookie_and_timestamp(self):
        headers = build_stealth_headers("cookie-value")

        self.assertEqual("cookie-value", headers["Cookie"])
        self.assertEqual("https://wx.zsxq.com", headers["Origin"])
        self.assertTrue(headers["X-Timestamp"].isdigit())
        self.assertIn("User-Agent", headers)

    def test_fetch_groups_from_api_supports_test_cookie(self):
        groups = fetch_groups_from_api("test_cookie")

        self.assertEqual(1, len(groups))
        self.assertEqual(123456, groups[0]["group_id"])


if __name__ == "__main__":
    unittest.main()
