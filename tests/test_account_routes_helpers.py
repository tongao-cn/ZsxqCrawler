import unittest
from unittest.mock import patch

try:
    from fastapi import HTTPException

    from backend.routes import account_routes

    HAS_ACCOUNT_ROUTE_DEPS = True
except Exception:
    HAS_ACCOUNT_ROUTE_DEPS = False


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_called = False

    def raise_for_status(self):
        self.raise_called = True

    def json(self):
        return self.payload


class FakeSelfInfoDb:
    def __init__(self):
        self.saved = None

    def upsert_self_info(self, account_id, self_info, raw_json=None):
        self.saved = (account_id, self_info, raw_json)

    def get_self_info(self, account_id):
        return {"id": account_id, **self.saved[1]}


class FakeAccountsSqlManager:
    def __init__(self, account):
        self.account = account
        self.calls = []

    def get_account_by_id(self, account_id, mask_cookie=True):
        self.calls.append((account_id, mask_cookie))
        return self.account


class FakeAccountsListSqlManager:
    def __init__(self, accounts):
        self.accounts = accounts
        self.calls = []

    def get_accounts(self, mask_cookie=True):
        self.calls.append(mask_cookie)
        return self.accounts


class FakeAccountsCreateSqlManager:
    def __init__(self, created_account, safe_account):
        self.created_account = created_account
        self.safe_account = safe_account
        self.calls = []

    def add_account(self, cookie, name):
        self.calls.append(("add_account", cookie, name))
        return self.created_account

    def get_account_by_id(self, account_id, mask_cookie=True):
        self.calls.append(("get_account_by_id", account_id, mask_cookie))
        return self.safe_account


class FakeAccountsDeleteSqlManager:
    def __init__(self, deleted):
        self.deleted = deleted
        self.calls = []

    def delete_account(self, account_id):
        self.calls.append(account_id)
        return self.deleted


@unittest.skipUnless(HAS_ACCOUNT_ROUTE_DEPS, "account route dependencies are not installed")
class AccountRoutesHelperTests(unittest.TestCase):
    def test_fetch_self_api_data_returns_payload_and_uses_stealth_headers(self):
        payload = {"succeeded": True, "resp_data": {"user": {"uid": "u1"}}}
        response = FakeResponse(payload)

        with patch.object(account_routes, "build_stealth_headers", return_value={"Cookie": "c"}), patch.object(
            account_routes.requests, "get", return_value=response
        ) as mock_get:
            data = account_routes._fetch_self_api_data("cookie-value", "API returned failure")

        self.assertIs(data, payload)
        self.assertTrue(response.raise_called)
        mock_get.assert_called_once_with(
            "https://api.zsxq.com/v3/users/self",
            headers={"Cookie": "c"},
            timeout=30,
        )

    def test_fetch_self_api_data_raises_configured_failure_detail(self):
        with patch.object(account_routes, "build_stealth_headers", return_value={}), patch.object(
            account_routes.requests,
            "get",
            return_value=FakeResponse({"succeeded": False}),
        ):
            with self.assertRaises(HTTPException) as ctx:
                account_routes._fetch_self_api_data("cookie-value", "API返回失败")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "API返回失败")

    def test_save_self_info_response_persists_normalized_self_info(self):
        db = FakeSelfInfoDb()
        payload = {
            "succeeded": True,
            "resp_data": {
                "user": {"uid": "u1", "name": "", "location": "SH"},
                "accounts": {"wechat": {"name": "wechat-name", "avatar_url": "avatar.png"}},
            },
        }

        result = account_routes._save_self_info_response(db, "acc-1", payload)

        account_id, self_info, raw_json = db.saved
        self.assertEqual(account_id, "acc-1")
        self.assertEqual(self_info["name"], "wechat-name")
        self.assertEqual(self_info["avatar_url"], "avatar.png")
        self.assertIs(raw_json, payload)
        self.assertEqual(result["self"]["id"], "acc-1")

    def test_get_account_cookie_or_raise_uses_unmasked_lookup(self):
        manager = FakeAccountsSqlManager({"id": "acc-1", "cookie": "cookie-value"})

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager):
            cookie = account_routes._get_account_cookie_or_raise("acc-1")

        self.assertEqual(cookie, "cookie-value")
        self.assertEqual(manager.calls, [("acc-1", False)])

    def test_get_account_cookie_or_raise_preserves_missing_cookie_error(self):
        manager = FakeAccountsSqlManager({"id": "acc-1", "cookie": ""})

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager):
            with self.assertRaises(HTTPException) as ctx:
                account_routes._get_account_cookie_or_raise("acc-1")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Account has no configured Cookie")

    def test_get_group_account_context_or_raise_defaults_account_id(self):
        with patch.object(account_routes, "get_account_summary_for_group_auto", return_value=None), patch.object(
            account_routes, "get_cookie_for_group", return_value="group-cookie"
        ):
            account_id, cookie = account_routes._get_group_account_context_or_raise("group-1")

        self.assertEqual(account_id, "default")
        self.assertEqual(cookie, "group-cookie")

    def test_get_group_account_route_preserves_summary_response(self):
        import asyncio

        summary = {"id": "acc-1", "name": "Account A"}

        with patch.object(account_routes, "get_account_summary_for_group_auto", return_value=summary) as get_summary:
            result = asyncio.run(account_routes.get_group_account("group-1"))

        self.assertEqual({"account": summary}, result)
        get_summary.assert_called_once_with("group-1")

    def test_get_group_account_response_preserves_summary_lookup(self):
        summary = {"id": "acc-1", "name": "Account A"}

        with patch.object(account_routes, "get_account_summary_for_group_auto", return_value=summary) as get_summary:
            result = account_routes._get_group_account_response("group-1")

        self.assertEqual({"account": summary}, result)
        get_summary.assert_called_once_with("group-1")

    def test_list_accounts_route_preserves_masked_response(self):
        import asyncio

        accounts = [{"id": "acc-1", "cookie": "***"}]
        manager = FakeAccountsListSqlManager(accounts)

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager):
            result = asyncio.run(account_routes.list_accounts())

        self.assertEqual({"accounts": accounts}, result)
        self.assertEqual([True], manager.calls)

    def test_list_accounts_response_preserves_masked_lookup(self):
        accounts = [{"id": "acc-1", "cookie": "***"}]
        manager = FakeAccountsListSqlManager(accounts)

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager):
            result = account_routes._list_accounts_response()

        self.assertEqual({"accounts": accounts}, result)
        self.assertEqual([True], manager.calls)

    def test_create_account_route_preserves_add_mask_and_cache_clear(self):
        import asyncio

        manager = FakeAccountsCreateSqlManager(
            {"id": "acc-1", "cookie": "raw-cookie"},
            {"id": "acc-1", "cookie": "***"},
        )
        request = account_routes.AccountCreateRequest(cookie="raw-cookie", name="Account A")

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_routes, "clear_account_detect_cache"
        ) as clear_cache:
            result = asyncio.run(account_routes.create_account(request))

        self.assertEqual({"account": {"id": "acc-1", "cookie": "***"}}, result)
        self.assertEqual(
            [
                ("add_account", "raw-cookie", "Account A"),
                ("get_account_by_id", "acc-1", True),
            ],
            manager.calls,
        )
        clear_cache.assert_called_once_with()

    def test_create_account_response_preserves_add_mask_and_cache_clear(self):
        manager = FakeAccountsCreateSqlManager(
            {"id": "acc-1", "cookie": "raw-cookie"},
            {"id": "acc-1", "cookie": "***"},
        )
        request = account_routes.AccountCreateRequest(cookie="raw-cookie", name="Account A")

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_routes, "clear_account_detect_cache"
        ) as clear_cache:
            result = account_routes._create_account_response(request)

        self.assertEqual({"account": {"id": "acc-1", "cookie": "***"}}, result)
        self.assertEqual(
            [
                ("add_account", "raw-cookie", "Account A"),
                ("get_account_by_id", "acc-1", True),
            ],
            manager.calls,
        )
        clear_cache.assert_called_once_with()

    def test_remove_account_route_preserves_success_response_and_cache_clear(self):
        import asyncio

        manager = FakeAccountsDeleteSqlManager(True)

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_routes, "clear_account_detect_cache"
        ) as clear_cache:
            result = asyncio.run(account_routes.remove_account("acc-1"))

        self.assertEqual({"success": True}, result)
        self.assertEqual(["acc-1"], manager.calls)
        clear_cache.assert_called_once_with()

    def test_remove_account_route_preserves_missing_account_404(self):
        import asyncio

        manager = FakeAccountsDeleteSqlManager(False)

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_routes, "clear_account_detect_cache"
        ) as clear_cache:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.remove_account("missing"))

        self.assertEqual(404, ctx.exception.status_code)
        self.assertEqual("Account does not exist", ctx.exception.detail)
        self.assertEqual(["missing"], manager.calls)
        clear_cache.assert_not_called()

    def test_remove_account_response_preserves_success_response_and_cache_clear(self):
        manager = FakeAccountsDeleteSqlManager(True)

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_routes, "clear_account_detect_cache"
        ) as clear_cache:
            result = account_routes._remove_account_response("acc-1")

        self.assertEqual({"success": True}, result)
        self.assertEqual(["acc-1"], manager.calls)
        clear_cache.assert_called_once_with()

    def test_remove_account_response_preserves_missing_account_404(self):
        manager = FakeAccountsDeleteSqlManager(False)

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager), patch.object(
            account_routes, "clear_account_detect_cache"
        ) as clear_cache:
            with self.assertRaises(HTTPException) as ctx:
                account_routes._remove_account_response("missing")

        self.assertEqual(404, ctx.exception.status_code)
        self.assertEqual("Account does not exist", ctx.exception.detail)
        self.assertEqual(["missing"], manager.calls)
        clear_cache.assert_not_called()


@unittest.skipUnless(HAS_ACCOUNT_ROUTE_DEPS, "account route dependencies are not installed")
class AccountRoutesAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_self_routes_offload_blocking_work_to_thread(self):
        route_cases = [
            (account_routes.get_account_self, account_routes._get_account_self_response, "acc-1"),
            (account_routes.refresh_account_self, account_routes._refresh_account_self_response, "acc-1"),
            (account_routes.get_group_account_self, account_routes._get_group_account_self_response, "group-1"),
            (account_routes.refresh_group_account_self, account_routes._refresh_group_account_self_response, "group-1"),
        ]

        async def fake_to_thread(func, *args):
            return {"self": {"called": func.__name__, "args": args}}

        with patch.object(account_routes.asyncio, "to_thread", new=fake_to_thread):
            for route_func, helper_func, identifier in route_cases:
                with self.subTest(route=route_func.__name__):
                    result = await route_func(identifier)

                self.assertEqual(
                    result,
                    {"self": {"called": helper_func.__name__, "args": (identifier,)}},
                )

    async def test_self_routes_preserve_network_error_details(self):
        route_cases = [
            (account_routes.get_account_self, "acc-1", "Network request failed: boom"),
            (account_routes.refresh_account_self, "acc-1", "Network request failed: boom"),
            (account_routes.get_group_account_self, "group-1", "网络请求失败: boom"),
            (account_routes.refresh_group_account_self, "group-1", "网络请求失败: boom"),
        ]

        async def fake_to_thread(func, *args):
            raise account_routes.requests.RequestException("boom")

        with patch.object(account_routes.asyncio, "to_thread", new=fake_to_thread):
            for route_func, identifier, expected_detail in route_cases:
                with self.subTest(route=route_func.__name__):
                    with self.assertRaises(HTTPException) as ctx:
                        await route_func(identifier)

                self.assertEqual(ctx.exception.status_code, 502)
                self.assertEqual(ctx.exception.detail, expected_detail)

    async def test_self_routes_preserve_generic_error_details(self):
        route_cases = [
            (account_routes.get_account_self, "acc-1", "Failed to retrieve account info: boom"),
            (account_routes.refresh_account_self, "acc-1", "Failed to refresh account info: boom"),
            (account_routes.get_group_account_self, "group-1", "获取群组账号信息失败: boom"),
            (account_routes.refresh_group_account_self, "group-1", "刷新群组账号信息失败: boom"),
        ]

        async def fake_to_thread(func, *args):
            raise RuntimeError("boom")

        with patch.object(account_routes.asyncio, "to_thread", new=fake_to_thread):
            for route_func, identifier, expected_detail in route_cases:
                with self.subTest(route=route_func.__name__):
                    with self.assertRaises(HTTPException) as ctx:
                        await route_func(identifier)

                self.assertEqual(ctx.exception.status_code, 500)
                self.assertEqual(ctx.exception.detail, expected_detail)


if __name__ == "__main__":
    unittest.main()
