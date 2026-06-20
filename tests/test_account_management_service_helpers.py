import unittest
from unittest.mock import patch


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


class AccountManagementServiceHelperTests(unittest.TestCase):
    def test_get_group_account_response_preserves_summary_lookup(self):
        from backend.services import account_management_service as service

        summary = {"id": "acc-1", "name": "Account A"}

        with patch.object(service, "get_account_summary_for_group_auto", return_value=summary) as get_summary:
            result = service.get_group_account_response("group-1")

        self.assertEqual({"account": summary}, result)
        get_summary.assert_called_once_with("group-1")

    def test_list_accounts_response_preserves_masked_lookup(self):
        from backend.services import account_management_service as service

        accounts = [{"id": "acc-1", "cookie": "***"}]
        manager = FakeAccountsListSqlManager(accounts)

        with patch.object(service, "get_accounts_sql_manager", return_value=manager):
            result = service.list_accounts_response()

        self.assertEqual({"accounts": accounts}, result)
        self.assertEqual([True], manager.calls)

    def test_create_account_response_preserves_add_mask_and_cache_clear(self):
        from backend.services import account_management_service as service

        manager = FakeAccountsCreateSqlManager(
            {"id": "acc-1", "cookie": "raw-cookie"},
            {"id": "acc-1", "cookie": "***"},
        )

        with patch.object(service, "get_accounts_sql_manager", return_value=manager), patch.object(
            service, "clear_account_detect_cache"
        ) as clear_cache:
            result = service.create_account_response("raw-cookie", "Account A")

        self.assertEqual({"account": {"id": "acc-1", "cookie": "***"}}, result)
        self.assertEqual(
            [
                ("add_account", "raw-cookie", "Account A"),
                ("get_account_by_id", "acc-1", True),
            ],
            manager.calls,
        )
        clear_cache.assert_called_once_with()

    def test_remove_account_response_preserves_success_response_and_cache_clear(self):
        from backend.services import account_management_service as service

        manager = FakeAccountsDeleteSqlManager(True)

        with patch.object(service, "get_accounts_sql_manager", return_value=manager), patch.object(
            service, "clear_account_detect_cache"
        ) as clear_cache:
            result = service.remove_account_response("acc-1")

        self.assertEqual({"success": True}, result)
        self.assertEqual(["acc-1"], manager.calls)
        clear_cache.assert_called_once_with()

    def test_remove_account_response_preserves_missing_account_error(self):
        from backend.services import account_management_service as service

        manager = FakeAccountsDeleteSqlManager(False)

        with patch.object(service, "get_accounts_sql_manager", return_value=manager), patch.object(
            service, "clear_account_detect_cache"
        ) as clear_cache:
            with self.assertRaises(service.AccountManagementError) as ctx:
                service.remove_account_response("missing")

        self.assertEqual(404, ctx.exception.status_code)
        self.assertEqual("Account does not exist", ctx.exception.detail)
        self.assertEqual(["missing"], manager.calls)
        clear_cache.assert_not_called()

    def test_assign_account_to_group_response_preserves_success_response(self):
        from backend.services import account_management_service as service

        manager = FakeAccountsAssignSqlManager((True, "assigned"))

        with patch.object(service, "get_accounts_sql_manager", return_value=manager):
            result = service.assign_account_to_group_response("group-1", "acc-1")

        self.assertEqual({"success": True, "message": "assigned"}, result)
        self.assertEqual([("group-1", "acc-1")], manager.calls)

    def test_assign_account_to_group_response_preserves_failure_error(self):
        from backend.services import account_management_service as service

        manager = FakeAccountsAssignSqlManager((False, "missing account"))

        with patch.object(service, "get_accounts_sql_manager", return_value=manager):
            with self.assertRaises(service.AccountManagementError) as ctx:
                service.assign_account_to_group_response("group-1", "missing")

        self.assertEqual(400, ctx.exception.status_code)
        self.assertEqual("missing account", ctx.exception.detail)
        self.assertEqual([("group-1", "missing")], manager.calls)
