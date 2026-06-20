import unittest
from unittest.mock import patch

try:
    from backend.services import account_self_info_service as service

    HAS_ACCOUNT_SELF_INFO_SERVICE_DEPS = True
except Exception:
    HAS_ACCOUNT_SELF_INFO_SERVICE_DEPS = False


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_called = False

    def raise_for_status(self):
        self.raise_called = True

    def json(self):
        return self.payload


class FakeSelfInfoDb:
    def __init__(self, existing=None):
        self.existing = existing
        self.saved = None
        self.get_calls = []

    def upsert_self_info(self, account_id, self_info, raw_json=None):
        self.saved = (account_id, self_info, raw_json)

    def get_self_info(self, account_id):
        self.get_calls.append(account_id)
        if self.saved:
            return {"id": account_id, **self.saved[1]}
        return self.existing


class FakeAccountsSqlManager:
    def __init__(self, account):
        self.account = account
        self.calls = []

    def get_account_by_id(self, account_id, mask_cookie=True):
        self.calls.append((account_id, mask_cookie))
        return self.account


@unittest.skipUnless(HAS_ACCOUNT_SELF_INFO_SERVICE_DEPS, "account self-info service dependencies are not installed")
class AccountSelfInfoServiceTests(unittest.TestCase):
    def test_fetch_self_api_data_returns_payload_and_uses_stealth_headers(self):
        payload = {"succeeded": True, "resp_data": {"user": {"uid": "u1"}}}
        response = FakeResponse(payload)

        with patch.object(service, "build_stealth_headers", return_value={"Cookie": "c"}), patch.object(
            service.requests, "get", return_value=response
        ) as mock_get:
            data = service.fetch_self_api_data("cookie-value", "API returned failure")

        self.assertIs(data, payload)
        self.assertTrue(response.raise_called)
        mock_get.assert_called_once_with(
            service.SELF_INFO_URL,
            headers={"Cookie": "c"},
            timeout=30,
        )

    def test_fetch_self_api_data_raises_configured_failure_detail(self):
        with patch.object(service, "build_stealth_headers", return_value={}), patch.object(
            service.requests,
            "get",
            return_value=FakeResponse({"succeeded": False}),
        ):
            with self.assertRaises(service.AccountSelfInfoError) as ctx:
                service.fetch_self_api_data("cookie-value", "API返回失败")

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

        result = service._save_self_info_response(db, "acc-1", payload)

        account_id, self_info, raw_json = db.saved
        self.assertEqual(account_id, "acc-1")
        self.assertEqual(self_info["name"], "wechat-name")
        self.assertEqual(self_info["avatar_url"], "avatar.png")
        self.assertIs(raw_json, payload)
        self.assertEqual(result["self"]["id"], "acc-1")

    def test_get_account_cookie_or_raise_uses_unmasked_lookup(self):
        manager = FakeAccountsSqlManager({"id": "acc-1", "cookie": "cookie-value"})

        with patch.object(service, "get_accounts_sql_manager", return_value=manager):
            cookie = service._get_account_cookie_or_raise("acc-1")

        self.assertEqual(cookie, "cookie-value")
        self.assertEqual(manager.calls, [("acc-1", False)])

    def test_get_account_cookie_or_raise_preserves_missing_account_error(self):
        manager = FakeAccountsSqlManager(None)

        with patch.object(service, "get_accounts_sql_manager", return_value=manager):
            with self.assertRaises(service.AccountSelfInfoError) as ctx:
                service._get_account_cookie_or_raise("missing")

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Account does not exist")

    def test_get_account_cookie_or_raise_preserves_missing_cookie_error(self):
        manager = FakeAccountsSqlManager({"id": "acc-1", "cookie": ""})

        with patch.object(service, "get_accounts_sql_manager", return_value=manager):
            with self.assertRaises(service.AccountSelfInfoError) as ctx:
                service._get_account_cookie_or_raise("acc-1")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Account has no configured Cookie")

    def test_get_group_account_context_or_raise_defaults_account_id(self):
        with patch.object(service, "get_account_summary_for_group_auto", return_value=None), patch.object(
            service, "get_cookie_for_group", return_value="group-cookie"
        ):
            account_id, cookie = service._get_group_account_context_or_raise("group-1")

        self.assertEqual(account_id, "default")
        self.assertEqual(cookie, "group-cookie")

    def test_get_group_account_context_or_raise_preserves_missing_cookie_error(self):
        with patch.object(service, "get_account_summary_for_group_auto", return_value=None), patch.object(
            service, "get_cookie_for_group", return_value=None
        ):
            with self.assertRaises(service.AccountSelfInfoError) as ctx:
                service._get_group_account_context_or_raise("group-1")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "未找到可用Cookie，请先配置账号或默认Cookie")

    def test_get_account_self_info_returns_cached_self_without_fetching(self):
        db = FakeSelfInfoDb(existing={"id": "acc-1", "name": "cached"})

        with patch.object(service, "get_account_info_db", return_value=db), patch.object(
            service, "fetch_self_api_data"
        ) as fetch_self:
            result = service.get_account_self_info("acc-1")

        self.assertEqual({"self": {"id": "acc-1", "name": "cached"}}, result)
        fetch_self.assert_not_called()
        self.assertEqual(["acc-1"], db.get_calls)

    def test_get_account_self_info_fetches_and_persists_cache_miss(self):
        db = FakeSelfInfoDb()
        manager = FakeAccountsSqlManager({"id": "acc-1", "cookie": "cookie-value"})
        payload = {"succeeded": True, "resp_data": {"user": {"uid": "u1", "name": "name"}}}

        with (
            patch.object(service, "get_account_info_db", return_value=db),
            patch.object(service, "get_accounts_sql_manager", return_value=manager),
            patch.object(service, "fetch_self_api_data", return_value=payload) as fetch_self,
        ):
            result = service.get_account_self_info("acc-1")

        fetch_self.assert_called_once_with("cookie-value", "API returned failure")
        self.assertEqual(("acc-1", False), manager.calls[0])
        self.assertEqual("name", result["self"]["name"])
        self.assertIs(db.saved[2], payload)

    def test_refresh_account_self_info_skips_cache_before_fetch(self):
        db = FakeSelfInfoDb(existing={"id": "acc-1", "name": "cached"})
        manager = FakeAccountsSqlManager({"id": "acc-1", "cookie": "cookie-value"})
        payload = {"succeeded": True, "resp_data": {"user": {"uid": "u1", "name": "fresh"}}}

        with (
            patch.object(service, "get_account_info_db", return_value=db),
            patch.object(service, "get_accounts_sql_manager", return_value=manager),
            patch.object(service, "fetch_self_api_data", return_value=payload),
        ):
            result = service.get_account_self_info("acc-1", refresh=True)

        self.assertEqual(["acc-1"], db.get_calls)
        self.assertEqual("fresh", result["self"]["name"])

    def test_get_group_account_self_info_fetches_with_default_account_id(self):
        db = FakeSelfInfoDb()
        payload = {"succeeded": True, "resp_data": {"user": {"uid": "u1", "name": "group-user"}}}

        with (
            patch.object(service, "get_account_summary_for_group_auto", return_value=None),
            patch.object(service, "get_cookie_for_group", return_value="group-cookie"),
            patch.object(service, "get_account_info_db", return_value=db),
            patch.object(service, "fetch_self_api_data", return_value=payload) as fetch_self,
        ):
            result = service.get_group_account_self_info("group-1")

        fetch_self.assert_called_once_with("group-cookie", "API返回失败")
        self.assertEqual("default", db.saved[0])
        self.assertEqual("group-user", result["self"]["name"])

    def test_account_and_group_workflows_preserve_api_failure_details(self):
        def fail_with_detail(cookie, failure_detail):
            raise service.AccountSelfInfoError(400, failure_detail)

        with (
            patch.object(service, "get_account_info_db", return_value=FakeSelfInfoDb()),
            patch.object(service, "get_accounts_sql_manager", return_value=FakeAccountsSqlManager({"cookie": "c"})),
            patch.object(service, "fetch_self_api_data", side_effect=fail_with_detail),
        ):
            with self.assertRaises(service.AccountSelfInfoError) as account_ctx:
                service.get_account_self_info("acc-1")

        with (
            patch.object(service, "get_account_summary_for_group_auto", return_value={"id": "acc-1"}),
            patch.object(service, "get_cookie_for_group", return_value="c"),
            patch.object(service, "get_account_info_db", return_value=FakeSelfInfoDb()),
            patch.object(service, "fetch_self_api_data", side_effect=fail_with_detail),
        ):
            with self.assertRaises(service.AccountSelfInfoError) as group_ctx:
                service.get_group_account_self_info("group-1")

        self.assertEqual("API returned failure", account_ctx.exception.detail)
        self.assertEqual("API返回失败", group_ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
