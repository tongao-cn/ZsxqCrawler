import unittest
from unittest.mock import patch

from backend.core import account_context
from backend.core.account_context import build_stealth_headers, fetch_groups_from_api


class FakeAccountsSqlManager:
    def __init__(self, *, first_account=None, group_account=None):
        self.first_account = first_account
        self.group_account = group_account
        self.first_calls = []
        self.group_calls = []

    def get_first_account(self, mask_cookie=False):
        self.first_calls.append(mask_cookie)
        return self.first_account

    def get_account_for_group(self, group_id, mask_cookie=False):
        self.group_calls.append((group_id, mask_cookie))
        return self.group_account


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

    def test_get_primary_cookie_prefers_trimmed_database_cookie(self):
        manager = FakeAccountsSqlManager(first_account={"cookie": "  db-cookie  "})

        with patch.object(account_context, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_context, "load_config"
        ) as load_config:
            cookie = account_context.get_primary_cookie()

        self.assertEqual("db-cookie", cookie)
        self.assertEqual([False], manager.first_calls)
        load_config.assert_not_called()

    def test_get_primary_cookie_falls_back_to_trimmed_config_cookie(self):
        manager = FakeAccountsSqlManager(first_account={"cookie": "  "})

        with patch.object(account_context, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_context,
            "load_config",
            return_value={"auth": {"cookie": "  config-cookie  "}},
        ):
            cookie = account_context.get_primary_cookie()

        self.assertEqual("config-cookie", cookie)
        self.assertEqual([False], manager.first_calls)

    def test_get_primary_cookie_ignores_placeholder_config_cookie(self):
        manager = FakeAccountsSqlManager(first_account=None)

        with patch.object(account_context, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_context,
            "load_config",
            return_value={"auth": {"cookie": "your_cookie_here"}},
        ):
            cookie = account_context.get_primary_cookie()

        self.assertIsNone(cookie)
        self.assertEqual([False], manager.first_calls)

    def test_get_cookie_for_group_prefers_trimmed_group_cookie(self):
        manager = FakeAccountsSqlManager(group_account={"cookie": "  group-cookie  "})

        with patch.object(account_context, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_context, "get_primary_cookie"
        ) as get_primary_cookie:
            cookie = account_context.get_cookie_for_group("group-1")

        self.assertEqual("group-cookie", cookie)
        self.assertEqual([("group-1", False)], manager.group_calls)
        get_primary_cookie.assert_not_called()

    def test_get_cookie_for_group_falls_back_to_primary_cookie(self):
        manager = FakeAccountsSqlManager(group_account={"cookie": "  "}, first_account={"cookie": " primary-cookie "})

        with patch.object(account_context, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_context,
            "load_config",
            return_value={"auth": {"cookie": ""}},
        ):
            cookie = account_context.get_cookie_for_group("group-1")

        self.assertEqual("primary-cookie", cookie)
        self.assertEqual([("group-1", False)], manager.group_calls)
        self.assertEqual([False], manager.first_calls)


if __name__ == "__main__":
    unittest.main()
