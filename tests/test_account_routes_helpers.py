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


if __name__ == "__main__":
    unittest.main()
