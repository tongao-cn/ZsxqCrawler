from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.account_management_service import (
    AccountManagementError,
    assign_account_to_group_response,
    create_account_response,
    get_group_account_response,
    list_accounts_response,
    remove_account_response,
)
from backend.services.account_self_info_service import (
    AccountSelfInfoError,
    get_account_self_info,
    get_group_account_self_info,
)

router = APIRouter(prefix="/api", tags=["accounts"])


class AccountCreateRequest(BaseModel):
    cookie: str = Field(..., description="账号Cookie")
    name: Optional[str] = Field(default=None, description="账号名称")


class AssignGroupAccountRequest(BaseModel):
    account_id: str = Field(..., description="账号ID")


def _account_route_error(message: str, error: Exception, *, status_code: int = 500) -> HTTPException:
    return HTTPException(status_code=status_code, detail=f"{message}: {str(error)}")


def _account_management_http_error(error: AccountManagementError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _get_group_account_response(group_id: str) -> Dict[str, Any]:
    return get_group_account_response(group_id)


def _list_accounts_response() -> Dict[str, Any]:
    return list_accounts_response()


def _create_account_response(request: AccountCreateRequest) -> Dict[str, Any]:
    return create_account_response(request.cookie, request.name)


def _remove_account_response(account_id: str) -> Dict[str, Any]:
    try:
        return remove_account_response(account_id)
    except AccountManagementError as e:
        raise _account_management_http_error(e)


def _assign_account_to_group_response(group_id: str, request: AssignGroupAccountRequest) -> Dict[str, Any]:
    try:
        return assign_account_to_group_response(group_id, request.account_id)
    except AccountManagementError as e:
        raise _account_management_http_error(e)


async def _run_self_response_route(
    helper: Callable[..., Dict[str, Any]],
    identifier: str,
    *,
    refresh: bool,
    network_error_prefix: str,
    generic_error_prefix: str,
) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(helper, identifier, refresh=refresh)
    except AccountSelfInfoError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
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
        get_account_self_info,
        account_id,
        refresh=False,
        network_error_prefix="Network request failed",
        generic_error_prefix="Failed to retrieve account info",
    )


@router.post("/accounts/{account_id}/self/refresh")
async def refresh_account_self(account_id: str):
    """强制抓取 /v3/users/self 并更新持久化"""
    return await _run_self_response_route(
        get_account_self_info,
        account_id,
        refresh=True,
        network_error_prefix="Network request failed",
        generic_error_prefix="Failed to refresh account info",
    )


@router.get("/groups/{group_id}/self")
async def get_group_account_self(group_id: str):
    """获取群组当前使用账号的自我信息（若无则尝试抓取并保存）"""
    return await _run_self_response_route(
        get_group_account_self_info,
        group_id,
        refresh=False,
        network_error_prefix="网络请求失败",
        generic_error_prefix="获取群组账号信息失败",
    )


@router.post("/groups/{group_id}/self/refresh")
async def refresh_group_account_self(group_id: str):
    """强制抓取群组当前使用账号的自我信息并持久化"""
    return await _run_self_response_route(
        get_group_account_self_info,
        group_id,
        refresh=True,
        network_error_prefix="网络请求失败",
        generic_error_prefix="刷新群组账号信息失败",
    )
