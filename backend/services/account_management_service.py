from __future__ import annotations

from typing import Any, Dict, Optional

from backend.core.account_context import clear_account_detect_cache, get_account_summary_for_group_auto
from backend.storage.accounts_sql_manager import get_accounts_sql_manager


class AccountManagementError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def get_group_account_response(group_id: str) -> Dict[str, Any]:
    summary = get_account_summary_for_group_auto(group_id)
    return {"account": summary}


def list_accounts_response() -> Dict[str, Any]:
    sql_mgr = get_accounts_sql_manager()
    accounts = sql_mgr.get_accounts(mask_cookie=True)
    return {"accounts": accounts}


def create_account_response(cookie: str, name: Optional[str]) -> Dict[str, Any]:
    sql_mgr = get_accounts_sql_manager()
    acc = sql_mgr.add_account(cookie, name)
    safe_acc = sql_mgr.get_account_by_id(acc.get("id"), mask_cookie=True)
    clear_account_detect_cache()
    return {"account": safe_acc}


def remove_account_response(account_id: str) -> Dict[str, Any]:
    sql_mgr = get_accounts_sql_manager()
    ok = sql_mgr.delete_account(account_id)
    if not ok:
        raise AccountManagementError(404, "Account does not exist")
    clear_account_detect_cache()
    return {"success": True}


def assign_account_to_group_response(group_id: str, account_id: str) -> Dict[str, Any]:
    sql_mgr = get_accounts_sql_manager()
    ok, msg = sql_mgr.assign_group_account(group_id, account_id)
    if not ok:
        raise AccountManagementError(400, msg)
    return {"success": True, "message": msg}
