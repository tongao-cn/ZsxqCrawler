import os
import unittest

from backend.storage.accounts_sql_manager import (
    AccountsSQLManager,
    _account_row_to_dict,
    _close_quietly,
)
from backend.storage.db_compat import get_postgres_dsn


class AccountsSqlManagerHelperTests(unittest.TestCase):
    def test_account_row_to_dict_preserves_unmasked_shape(self):
        row = ("acc_1", "Account A", "abcdef1234567890", "2026-05-07T10:00:00", None)

        self.assertEqual(
            _account_row_to_dict(row, mask_cookie=False),
            {
                "id": "acc_1",
                "name": "Account A",
                "cookie": "abcdef1234567890",
                "created_at": "2026-05-07T10:00:00",
                "updated_at": None,
            },
        )

    def test_account_row_to_dict_masks_cookie_when_requested(self):
        row = ("acc_1", "Account A", "abcdef1234567890", "2026-05-07T10:00:00", "2026-05-07T10:01:00")

        self.assertEqual(_account_row_to_dict(row, mask_cookie=True)["cookie"], "***34567890")

    def test_close_quietly_ignores_close_errors(self):
        class BrokenClose:
            def close(self):
                raise RuntimeError("close failed")

        _close_quietly(BrokenClose())

    def test_runtime_ensure_schema_is_noop(self):
        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((sql, params))

        manager = object.__new__(AccountsSQLManager)
        manager.cursor = FakeCursor()

        self.assertIsNone(AccountsSQLManager._ensure_schema(manager))
        self.assertEqual([], manager.cursor.calls)

    @unittest.skipUnless(
        get_postgres_dsn() and os.getenv("ZSXQ_RUN_PG_INTEGRATION_TESTS") == "1",
        "PostgreSQL integration tests are disabled",
    )
    def test_manager_get_account_uses_same_account_shape(self):
        manager = AccountsSQLManager()
        try:
            account = manager.add_account("cookie-value-12345678", name="Account A")

            self.assertEqual(
                set(account.keys()),
                {"id", "name", "cookie", "created_at", "updated_at"},
            )
            self.assertEqual(account["name"], "Account A")
            self.assertEqual(account["cookie"], "cookie-value-12345678")
            self.assertIsNone(account["updated_at"])

            masked = manager.get_account_by_id(account["id"], mask_cookie=True)
            self.assertEqual(masked["cookie"], "***12345678")
        finally:
            manager.close()


if __name__ == "__main__":
    unittest.main()
