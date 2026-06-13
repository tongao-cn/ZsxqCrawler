import unittest
from unittest.mock import patch

from backend.core import account_context
from backend.core.account_context import build_stealth_headers, fetch_groups_from_api


class FakeAccountsSqlManager:
    def __init__(
        self,
        *,
        first_account=None,
        group_account=None,
        group_summary=None,
        group_mapping=None,
        accounts_by_id=None,
    ):
        self.first_account = first_account
        self.group_account = group_account
        self.group_summary = group_summary
        self.group_mapping = group_mapping or {}
        self.accounts_by_id = accounts_by_id or {}
        self.first_calls = []
        self.group_calls = []
        self.group_summary_calls = []
        self.group_mapping_calls = 0
        self.account_by_id_calls = []

    def get_first_account(self, mask_cookie=False):
        self.first_calls.append(mask_cookie)
        return self.first_account

    def get_account_for_group(self, group_id, mask_cookie=False):
        self.group_calls.append((group_id, mask_cookie))
        return self.group_account

    def get_account_summary_for_group(self, group_id):
        self.group_summary_calls.append(group_id)
        return self.group_summary

    def get_group_account_mapping(self):
        self.group_mapping_calls += 1
        return self.group_mapping

    def get_account_by_id(self, account_id, mask_cookie=True):
        self.account_by_id_calls.append((account_id, mask_cookie))
        return self.accounts_by_id.get(account_id)


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

    def test_get_account_summary_for_group_auto_prefers_sql_summary(self):
        summary = {"id": "acc-1", "name": "Account A", "created_at": "2026-05-07", "cookie": "***cookie"}
        manager = FakeAccountsSqlManager(group_summary=summary)

        with patch.object(account_context, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_context, "load_config"
        ) as load_config:
            result = account_context.get_account_summary_for_group_auto("group-1")

        self.assertIs(summary, result)
        self.assertEqual(["group-1"], manager.group_summary_calls)
        self.assertEqual([], manager.first_calls)
        load_config.assert_not_called()

    def test_get_account_summary_for_group_auto_falls_back_to_first_account_summary(self):
        manager = FakeAccountsSqlManager(
            group_summary=None,
            first_account={
                "id": "acc-1",
                "name": "Account A",
                "created_at": "2026-05-07T10:00:00",
                "cookie": "***34567890",
                "updated_at": "ignored",
            },
        )

        with patch.object(account_context, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_context, "load_config"
        ) as load_config:
            result = account_context.get_account_summary_for_group_auto("group-1")

        self.assertEqual(
            {
                "id": "acc-1",
                "name": "Account A",
                "created_at": "2026-05-07T10:00:00",
                "cookie": "***34567890",
            },
            result,
        )
        self.assertEqual(["group-1"], manager.group_summary_calls)
        self.assertEqual([True], manager.first_calls)
        load_config.assert_not_called()

    def test_build_account_group_detection_skips_missing_accounts_and_caches_result(self):
        manager = FakeAccountsSqlManager(
            group_mapping={"group-1": "acc-1", "group-2": "missing"},
            accounts_by_id={
                "acc-1": {
                    "id": "acc-1",
                    "name": "Account A",
                    "created_at": "2026-05-07T10:00:00",
                    "cookie": "***34567890",
                    "updated_at": "ignored",
                }
            },
        )

        account_context.clear_account_detect_cache()
        try:
            with patch.object(account_context, "get_accounts_sql_manager", return_value=manager):
                first = account_context.build_account_group_detection()
                second = account_context.build_account_group_detection()
        finally:
            account_context.clear_account_detect_cache()

        self.assertEqual(
            {
                "group-1": {
                    "id": "acc-1",
                    "name": "Account A",
                    "created_at": "2026-05-07T10:00:00",
                    "cookie": "***34567890",
                }
            },
            first,
        )
        self.assertIs(first, second)
        self.assertEqual(1, manager.group_mapping_calls)
        self.assertEqual([("acc-1", True), ("missing", True)], manager.account_by_id_calls)


if __name__ == "__main__":
    unittest.main()
