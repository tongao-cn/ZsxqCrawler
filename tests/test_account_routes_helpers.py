import unittest
from unittest.mock import patch

try:
    from fastapi import HTTPException

    from backend.routes import account_routes

    HAS_ACCOUNT_ROUTE_DEPS = True
except Exception:
    HAS_ACCOUNT_ROUTE_DEPS = False


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

        with patch.object(account_routes, "get_group_account_response", return_value={"account": summary}) as get_account:
            result = asyncio.run(account_routes.get_group_account("group-1"))

        self.assertEqual({"account": summary}, result)
        get_account.assert_called_once_with("group-1")

    def test_get_group_account_response_preserves_summary_lookup(self):
        summary = {"id": "acc-1", "name": "Account A"}

        with patch.object(account_routes, "get_group_account_response", return_value={"account": summary}) as get_account:
            result = account_routes._get_group_account_response("group-1")

        self.assertEqual({"account": summary}, result)
        get_account.assert_called_once_with("group-1")

    def test_list_accounts_route_preserves_masked_response(self):
        import asyncio

        accounts = [{"id": "acc-1", "cookie": "***"}]

        with patch.object(account_routes, "list_accounts_response", return_value={"accounts": accounts}) as list_accounts:
            result = asyncio.run(account_routes.list_accounts())

        self.assertEqual({"accounts": accounts}, result)
        list_accounts.assert_called_once_with()

    def test_list_accounts_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch.object(account_routes, "_list_accounts_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.list_accounts())

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("Failed to retrieve account list: boom", ctx.exception.detail)

    def test_list_accounts_response_preserves_masked_lookup(self):
        accounts = [{"id": "acc-1", "cookie": "***"}]

        with patch.object(account_routes, "list_accounts_response", return_value={"accounts": accounts}) as list_accounts:
            result = account_routes._list_accounts_response()

        self.assertEqual({"accounts": accounts}, result)
        list_accounts.assert_called_once_with()

    def test_create_account_route_preserves_add_mask_and_cache_clear(self):
        import asyncio

        request = account_routes.AccountCreateRequest(cookie="raw-cookie", name="Account A")

        with patch.object(
            account_routes,
            "create_account_response",
            return_value={"account": {"id": "acc-1", "cookie": "***"}},
        ) as create_account:
            result = asyncio.run(account_routes.create_account(request))

        self.assertEqual({"account": {"id": "acc-1", "cookie": "***"}}, result)
        create_account.assert_called_once_with("raw-cookie", "Account A")

    def test_create_account_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        request = account_routes.AccountCreateRequest(cookie="raw-cookie", name="Account A")

        with patch.object(account_routes, "_create_account_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.create_account(request))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("Failed to create account: boom", ctx.exception.detail)

    def test_create_account_response_preserves_add_mask_and_cache_clear(self):
        request = account_routes.AccountCreateRequest(cookie="raw-cookie", name="Account A")

        with patch.object(
            account_routes,
            "create_account_response",
            return_value={"account": {"id": "acc-1", "cookie": "***"}},
        ) as create_account:
            result = account_routes._create_account_response(request)

        self.assertEqual({"account": {"id": "acc-1", "cookie": "***"}}, result)
        create_account.assert_called_once_with("raw-cookie", "Account A")

    def test_remove_account_route_preserves_success_response_and_cache_clear(self):
        import asyncio

        with patch.object(account_routes, "remove_account_response", return_value={"success": True}) as remove_account:
            result = asyncio.run(account_routes.remove_account("acc-1"))

        self.assertEqual({"success": True}, result)
        remove_account.assert_called_once_with("acc-1")

    def test_remove_account_route_preserves_missing_account_404(self):
        import asyncio

        with patch.object(
            account_routes,
            "remove_account_response",
            side_effect=account_routes.AccountManagementError(404, "Account does not exist"),
        ) as remove_account:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.remove_account("missing"))

        self.assertEqual(404, ctx.exception.status_code)
        self.assertEqual("Account does not exist", ctx.exception.detail)
        remove_account.assert_called_once_with("missing")

    def test_remove_account_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch.object(account_routes, "_remove_account_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.remove_account("acc-1"))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("Failed to delete account: boom", ctx.exception.detail)

    def test_remove_account_response_preserves_success_response_and_cache_clear(self):
        with patch.object(account_routes, "remove_account_response", return_value={"success": True}) as remove_account:
            result = account_routes._remove_account_response("acc-1")

        self.assertEqual({"success": True}, result)
        remove_account.assert_called_once_with("acc-1")

    def test_remove_account_response_preserves_missing_account_404(self):
        with patch.object(
            account_routes,
            "remove_account_response",
            side_effect=account_routes.AccountManagementError(404, "Account does not exist"),
        ) as remove_account:
            with self.assertRaises(HTTPException) as ctx:
                account_routes._remove_account_response("missing")

        self.assertEqual(404, ctx.exception.status_code)
        self.assertEqual("Account does not exist", ctx.exception.detail)
        remove_account.assert_called_once_with("missing")

    def test_assign_account_to_group_route_preserves_success_response(self):
        import asyncio

        request = account_routes.AssignGroupAccountRequest(account_id="acc-1")

        with patch.object(
            account_routes,
            "assign_account_to_group_response",
            return_value={"success": True, "message": "assigned"},
        ) as assign_account:
            result = asyncio.run(account_routes.assign_account_to_group("group-1", request))

        self.assertEqual({"success": True, "message": "assigned"}, result)
        assign_account.assert_called_once_with("group-1", "acc-1")

    def test_assign_account_to_group_route_preserves_failure_400(self):
        import asyncio

        request = account_routes.AssignGroupAccountRequest(account_id="missing")

        with patch.object(
            account_routes,
            "assign_account_to_group_response",
            side_effect=account_routes.AccountManagementError(400, "missing account"),
        ) as assign_account:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.assign_account_to_group("group-1", request))

        self.assertEqual(400, ctx.exception.status_code)
        self.assertEqual("missing account", ctx.exception.detail)
        assign_account.assert_called_once_with("group-1", "missing")

    def test_assign_account_to_group_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        request = account_routes.AssignGroupAccountRequest(account_id="acc-1")

        with patch.object(account_routes, "_assign_account_to_group_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(account_routes.assign_account_to_group("group-1", request))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("Failed to assign account: boom", ctx.exception.detail)

    def test_assign_account_to_group_response_preserves_success_response(self):
        request = account_routes.AssignGroupAccountRequest(account_id="acc-1")

        with patch.object(
            account_routes,
            "assign_account_to_group_response",
            return_value={"success": True, "message": "assigned"},
        ) as assign_account:
            result = account_routes._assign_account_to_group_response("group-1", request)

        self.assertEqual({"success": True, "message": "assigned"}, result)
        assign_account.assert_called_once_with("group-1", "acc-1")

    def test_assign_account_to_group_response_preserves_failure_400(self):
        request = account_routes.AssignGroupAccountRequest(account_id="missing")

        with patch.object(
            account_routes,
            "assign_account_to_group_response",
            side_effect=account_routes.AccountManagementError(400, "missing account"),
        ) as assign_account:
            with self.assertRaises(HTTPException) as ctx:
                account_routes._assign_account_to_group_response("group-1", request)

        self.assertEqual(400, ctx.exception.status_code)
        self.assertEqual("missing account", ctx.exception.detail)
        assign_account.assert_called_once_with("group-1", "missing")

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
