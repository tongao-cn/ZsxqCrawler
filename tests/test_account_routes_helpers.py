import unittest
from unittest.mock import patch

try:
    from fastapi import HTTPException

    from backend.routes import account_routes

    HAS_ACCOUNT_ROUTE_DEPS = True
except Exception:
    HAS_ACCOUNT_ROUTE_DEPS = False


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


class FakeAccountsAssignSqlManager:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def assign_group_account(self, group_id, account_id):
        self.calls.append((group_id, account_id))
        return self.result


@unittest.skipUnless(HAS_ACCOUNT_ROUTE_DEPS, "account route dependencies are not installed")
class AccountRoutesHelperTests(unittest.TestCase):
    def test_account_route_error_preserves_status_and_detail_format(self):
        default_error = account_routes._account_route_error("Failed to create account", RuntimeError("boom"))
        network_error = account_routes._account_route_error(
            "Network request failed",
            RuntimeError("boom"),
            status_code=502,
        )

        self.assertEqual(500, default_error.status_code)
        self.assertEqual("Failed to create account: boom", default_error.detail)
        self.assertEqual(502, network_error.status_code)
        self.assertEqual("Network request failed: boom", network_error.detail)

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

    def test_list_accounts_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch.object(account_routes, "_list_accounts_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.list_accounts())

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("Failed to retrieve account list: boom", ctx.exception.detail)

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

    def test_create_account_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        request = account_routes.AccountCreateRequest(cookie="raw-cookie", name="Account A")

        with patch.object(account_routes, "_create_account_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.create_account(request))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("Failed to create account: boom", ctx.exception.detail)

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

    def test_remove_account_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch.object(account_routes, "_remove_account_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.remove_account("acc-1"))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("Failed to delete account: boom", ctx.exception.detail)

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

    def test_assign_account_to_group_route_preserves_success_response(self):
        import asyncio

        manager = FakeAccountsAssignSqlManager((True, "assigned"))
        request = account_routes.AssignGroupAccountRequest(account_id="acc-1")

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager):
            result = asyncio.run(account_routes.assign_account_to_group("group-1", request))

        self.assertEqual({"success": True, "message": "assigned"}, result)
        self.assertEqual([("group-1", "acc-1")], manager.calls)

    def test_assign_account_to_group_route_preserves_failure_400(self):
        import asyncio

        manager = FakeAccountsAssignSqlManager((False, "missing account"))
        request = account_routes.AssignGroupAccountRequest(account_id="missing")

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.assign_account_to_group("group-1", request))

        self.assertEqual(400, ctx.exception.status_code)
        self.assertEqual("missing account", ctx.exception.detail)
        self.assertEqual([("group-1", "missing")], manager.calls)

    def test_assign_account_to_group_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        request = account_routes.AssignGroupAccountRequest(account_id="acc-1")

        with patch.object(account_routes, "_assign_account_to_group_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.assign_account_to_group("group-1", request))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("Failed to assign account: boom", ctx.exception.detail)

    def test_assign_account_to_group_response_preserves_success_response(self):
        manager = FakeAccountsAssignSqlManager((True, "assigned"))
        request = account_routes.AssignGroupAccountRequest(account_id="acc-1")

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager):
            result = account_routes._assign_account_to_group_response("group-1", request)

        self.assertEqual({"success": True, "message": "assigned"}, result)
        self.assertEqual([("group-1", "acc-1")], manager.calls)

    def test_assign_account_to_group_response_preserves_failure_400(self):
        manager = FakeAccountsAssignSqlManager((False, "missing account"))
        request = account_routes.AssignGroupAccountRequest(account_id="missing")

        with patch.object(account_routes, "get_accounts_sql_manager", return_value=manager):
            with self.assertRaises(HTTPException) as ctx:
                account_routes._assign_account_to_group_response("group-1", request)

        self.assertEqual(400, ctx.exception.status_code)
        self.assertEqual("missing account", ctx.exception.detail)
        self.assertEqual([("group-1", "missing")], manager.calls)

    def test_get_group_account_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch.object(account_routes, "_get_group_account_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.get_group_account("group-1"))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("获取群组账号失败: boom", ctx.exception.detail)


@unittest.skipUnless(HAS_ACCOUNT_ROUTE_DEPS, "account route dependencies are not installed")
class AccountRoutesAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_self_routes_offload_blocking_work_to_thread(self):
        route_cases = [
            (account_routes.get_account_self, account_routes.get_account_self_info, "acc-1", False),
            (account_routes.refresh_account_self, account_routes.get_account_self_info, "acc-1", True),
            (account_routes.get_group_account_self, account_routes.get_group_account_self_info, "group-1", False),
            (account_routes.refresh_group_account_self, account_routes.get_group_account_self_info, "group-1", True),
        ]

        async def fake_to_thread(func, *args, **kwargs):
            return {"self": {"called": func.__name__, "args": args, "kwargs": kwargs}}

        with patch.object(account_routes.asyncio, "to_thread", new=fake_to_thread):
            for route_func, helper_func, identifier, refresh in route_cases:
                with self.subTest(route=route_func.__name__):
                    result = await route_func(identifier)

                self.assertEqual(
                    result,
                    {
                        "self": {
                            "called": helper_func.__name__,
                            "args": (identifier,),
                            "kwargs": {"refresh": refresh},
                        }
                    },
                )

    async def test_self_routes_preserve_network_error_details(self):
        route_cases = [
            (account_routes.get_account_self, "acc-1", "Network request failed: boom"),
            (account_routes.refresh_account_self, "acc-1", "Network request failed: boom"),
            (account_routes.get_group_account_self, "group-1", "网络请求失败: boom"),
            (account_routes.refresh_group_account_self, "group-1", "网络请求失败: boom"),
        ]

        async def fake_to_thread(func, *args, **kwargs):
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

        async def fake_to_thread(func, *args, **kwargs):
            raise RuntimeError("boom")

        with patch.object(account_routes.asyncio, "to_thread", new=fake_to_thread):
            for route_func, identifier, expected_detail in route_cases:
                with self.subTest(route=route_func.__name__):
                    with self.assertRaises(HTTPException) as ctx:
                        await route_func(identifier)

                self.assertEqual(ctx.exception.status_code, 500)
                self.assertEqual(ctx.exception.detail, expected_detail)

    async def test_self_routes_preserve_service_error_details(self):
        async def fake_to_thread(func, *args, **kwargs):
            raise account_routes.AccountSelfInfoError(400, "service detail")

        with patch.object(account_routes.asyncio, "to_thread", new=fake_to_thread):
            with self.assertRaises(HTTPException) as ctx:
                await account_routes.get_account_self("acc-1")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "service detail")


if __name__ == "__main__":
    unittest.main()
