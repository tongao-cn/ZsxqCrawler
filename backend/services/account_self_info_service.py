from __future__ import annotations

from typing import Any, Dict, Tuple

import requests

from backend.core.account_context import (
    build_stealth_headers,
    get_account_summary_for_group_auto,
    get_cookie_for_group,
)
from backend.storage.account_info_db import get_account_info_db
from backend.storage.accounts_sql_manager import get_accounts_sql_manager

SELF_INFO_URL = "https://api.zsxq.com/v3/users/self"


class AccountSelfInfoError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _build_self_info(data: Dict[str, Any]) -> Dict[str, Any]:
    rd = data.get("resp_data", {}) or {}
    user = rd.get("user", {}) or {}
    wechat = (rd.get("accounts", {}) or {}).get("wechat", {}) or {}
    return {
        "uid": user.get("uid"),
        "name": user.get("name") or wechat.get("name"),
        "avatar_url": user.get("avatar_url") or wechat.get("avatar_url"),
        "location": user.get("location"),
        "user_sid": user.get("user_sid"),
        "grade": user.get("grade"),
    }


def _get_account_cookie_or_raise(account_id: str) -> str:
    sql_mgr = get_accounts_sql_manager()
    acc = sql_mgr.get_account_by_id(account_id, mask_cookie=False)
    if not acc:
        raise AccountSelfInfoError(404, "Account does not exist")

    cookie = acc.get("cookie", "")
    if not cookie:
        raise AccountSelfInfoError(400, "Account has no configured Cookie")
    return cookie


def _get_group_account_context_or_raise(group_id: str) -> Tuple[str, str]:
    summary = get_account_summary_for_group_auto(group_id)
    cookie = get_cookie_for_group(group_id)
    account_id = (summary or {}).get("id", "default")

    if not cookie:
        raise AccountSelfInfoError(400, "未找到可用Cookie，请先配置账号或默认Cookie")
    return account_id, cookie


def fetch_self_api_data(cookie: str, failure_detail: str) -> Dict[str, Any]:
    headers = build_stealth_headers(cookie)
    resp = requests.get(SELF_INFO_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("succeeded"):
        raise AccountSelfInfoError(400, failure_detail)
    return data


def _save_self_info_response(db: Any, account_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    self_info = _build_self_info(data)
    db.upsert_self_info(account_id, self_info, raw_json=data)
    return {"self": db.get_self_info(account_id)}


def get_account_self_info(account_id: str, *, refresh: bool = False) -> Dict[str, Any]:
    db = None
    if not refresh:
        db = get_account_info_db()
        info = db.get_self_info(account_id)
        if info:
            return {"self": info}

    cookie = _get_account_cookie_or_raise(account_id)
    data = fetch_self_api_data(cookie, "API returned failure")
    db = db or get_account_info_db()
    return _save_self_info_response(db, account_id, data)


def get_group_account_self_info(group_id: str, *, refresh: bool = False) -> Dict[str, Any]:
    account_id, cookie = _get_group_account_context_or_raise(group_id)

    db = None
    if not refresh:
        db = get_account_info_db()
        info = db.get_self_info(account_id)
        if info:
            return {"self": info}

    data = fetch_self_api_data(cookie, "API返回失败")
    db = db or get_account_info_db()
    return _save_self_info_response(db, account_id, data)
