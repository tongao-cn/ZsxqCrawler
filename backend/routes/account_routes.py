from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional, Tuple

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.account_context import (
    build_stealth_headers,
    clear_account_detect_cache,
    get_account_summary_for_group_auto,
    get_cookie_for_group,
)
from backend.storage.account_info_db import get_account_info_db
from backend.storage.accounts_sql_manager import get_accounts_sql_manager

router = APIRouter(prefix="/api", tags=["accounts"])


class AccountCreateRequest(BaseModel):
    cookie: str = Field(..., description="账号Cookie")
    name: Optional[str] = Field(default=None, description="账号名称")


class AssignGroupAccountRequest(BaseModel):
    account_id: str = Field(..., description="账号ID")


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
        raise HTTPException(status_code=404, detail="Account does not exist")

    cookie = acc.get("cookie", "")
    if not cookie:
        raise HTTPException(status_code=400, detail="Account has no configured Cookie")
    return cookie


def _get_group_account_context_or_raise(group_id: str) -> Tuple[str, str]:
    summary = get_account_summary_for_group_auto(group_id)
    cookie = get_cookie_for_group(group_id)
    account_id = (summary or {}).get("id", "default")

    if not cookie:
        raise HTTPException(status_code=400, detail="未找到可用Cookie，请先配置账号或默认Cookie")
    return account_id, cookie


def _fetch_self_api_data(cookie: str, failure_detail: str) -> Dict[str, Any]:
    headers = build_stealth_headers(cookie)
    resp = requests.get("https://api.zsxq.com/v3/users/self", headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("succeeded"):
        raise HTTPException(status_code=400, detail=failure_detail)
    return data


def _save_self_info_response(db: Any, account_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    self_info = _build_self_info(data)
    db.upsert_self_info(account_id, self_info, raw_json=data)
    return {"self": db.get_self_info(account_id)}


def _account_route_error(message: str, error: Exception, *, status_code: int = 500) -> HTTPException:
    return HTTPException(status_code=status_code, detail=f"{message}: {str(error)}")


def _get_account_self_response(account_id: str) -> Dict[str, Any]:
    db = get_account_info_db()
    info = db.get_self_info(account_id)
    if info:
        return {"self": info}

    cookie = _get_account_cookie_or_raise(account_id)
    data = _fetch_self_api_data(cookie, "API returned failure")
    return _save_self_info_response(db, account_id, data)


def _refresh_account_self_response(account_id: str) -> Dict[str, Any]:
    cookie = _get_account_cookie_or_raise(account_id)
    data = _fetch_self_api_data(cookie, "API returned failure")
    db = get_account_info_db()
    return _save_self_info_response(db, account_id, data)


def _get_group_account_self_response(group_id: str) -> Dict[str, Any]:
    account_id, cookie = _get_group_account_context_or_raise(group_id)
    db = get_account_info_db()
    info = db.get_self_info(account_id)
    if info:
        return {"self": info}

    data = _fetch_self_api_data(cookie, "API返回失败")
    return _save_self_info_response(db, account_id, data)


def _refresh_group_account_self_response(group_id: str) -> Dict[str, Any]:
    account_id, cookie = _get_group_account_context_or_raise(group_id)
    data = _fetch_self_api_data(cookie, "API返回失败")
    db = get_account_info_db()
    return _save_self_info_response(db, account_id, data)


def _get_group_account_response(group_id: str) -> Dict[str, Any]:
    summary = get_account_summary_for_group_auto(group_id)
    return {"account": summary}


def _list_accounts_response() -> Dict[str, Any]:
    sql_mgr = get_accounts_sql_manager()
    accounts = sql_mgr.get_accounts(mask_cookie=True)
    return {"accounts": accounts}


def _create_account_response(request: AccountCreateRequest) -> Dict[str, Any]:
    sql_mgr = get_accounts_sql_manager()
    acc = sql_mgr.add_account(request.cookie, request.name)
    safe_acc = sql_mgr.get_account_by_id(acc.get("id"), mask_cookie=True)
    clear_account_detect_cache()
    return {"account": safe_acc}


def _remove_account_response(account_id: str) -> Dict[str, Any]:
    sql_mgr = get_accounts_sql_manager()
    ok = sql_mgr.delete_account(account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account does not exist")
    clear_account_detect_cache()
    return {"success": True}


def _assign_account_to_group_response(group_id: str, request: AssignGroupAccountRequest) -> Dict[str, Any]:
    sql_mgr = get_accounts_sql_manager()
    ok, msg = sql_mgr.assign_group_account(group_id, request.account_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


async def _run_self_response_route(
    helper: Callable[[str], Dict[str, Any]],
    identifier: str,
    *,
    network_error_prefix: str,
    generic_error_prefix: str,
) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(helper, identifier)
    except HTTPException:
        raise
    except requests.RequestException as e:
        raise _account_route_error(network_error_prefix, e, status_code=502)
    except Exception as e:
        raise _account_route_error(generic_error_prefix, e)


@router.get("/accounts")
async def list_accounts():
    """获取所有账号列表"""
    try:
        return _list_accounts_response()
    except Exception as e:
        raise _account_route_error("Failed to retrieve account list", e)


@router.post("/accounts")
async def create_account(request: AccountCreateRequest):
    """创建新账号"""
    try:
        return _create_account_response(request)
    except Exception as e:
        raise _account_route_error("Failed to create account", e)


@router.delete("/accounts/{account_id}")
async def remove_account(account_id: str):
    """删除账号"""
    try:
        return _remove_account_response(account_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _account_route_error("Failed to delete account", e)


@router.post("/groups/{group_id}/assign-account")
async def assign_account_to_group(group_id: str, request: AssignGroupAccountRequest):
    """分配群组到指定账号"""
    try:
        return _assign_account_to_group_response(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _account_route_error("Failed to assign account", e)


@router.get("/groups/{group_id}/account")
async def get_group_account(group_id: str):
    try:
        return _get_group_account_response(group_id)
    except Exception as e:
        raise _account_route_error("获取群组账号失败", e)


@router.get("/accounts/{account_id}/self")
async def get_account_self(account_id: str):
    """获取并返回指定账号的已持久化自我信息；若无则尝试抓取并保存"""
    return await _run_self_response_route(
        _get_account_self_response,
        account_id,
        network_error_prefix="Network request failed",
        generic_error_prefix="Failed to retrieve account info",
    )


@router.post("/accounts/{account_id}/self/refresh")
async def refresh_account_self(account_id: str):
    """强制抓取 /v3/users/self 并更新持久化"""
    return await _run_self_response_route(
        _refresh_account_self_response,
        account_id,
        network_error_prefix="Network request failed",
        generic_error_prefix="Failed to refresh account info",
    )


@router.get("/groups/{group_id}/self")
async def get_group_account_self(group_id: str):
    """获取群组当前使用账号的自我信息（若无则尝试抓取并保存）"""
    return await _run_self_response_route(
        _get_group_account_self_response,
        group_id,
        network_error_prefix="网络请求失败",
        generic_error_prefix="获取群组账号信息失败",
    )


@router.post("/groups/{group_id}/self/refresh")
async def refresh_group_account_self(group_id: str):
    """强制抓取群组当前使用账号的自我信息并持久化"""
    return await _run_self_response_route(
        _refresh_group_account_self_response,
        group_id,
        network_error_prefix="网络请求失败",
        generic_error_prefix="刷新群组账号信息失败",
    )
