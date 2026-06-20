from __future__ import annotations

import asyncio
from contextlib import closing
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.core.db_path_manager import get_db_path_manager
from backend.core.account_context import get_account_summary_for_group_auto
from backend.core.local_group_runtime import (
    get_cached_local_group_ids,
    delete_group_local as delete_group_local_data,
    scan_local_groups,
)
from backend.services.group_workflow_service import (
    fetch_official_groups as _fetch_official_groups,
    get_groups_response as _get_groups_response,
)
from backend.storage.zsxq_database import ZSXQDatabase
from backend.storage.zsxq_file_database import ZSXQFileDatabase

router = APIRouter(prefix="/api", tags=["groups"])


@router.post("/local-groups/refresh")
async def refresh_local_groups():
    """
    手动刷新本地群（output）扫描缓存；不抛错，异常时返回旧缓存。
    """
    try:
        ids = await asyncio.to_thread(scan_local_groups)
        return {"success": True, "count": len(ids), "groups": sorted(list(ids))}
    except Exception as e:
        cached = get_cached_local_group_ids(force_refresh=False) or set()
        # 不报错，返回降级结果
        return {"success": False, "count": len(cached), "groups": sorted(list(cached)), "error": str(e)}


def _coerce_group_id(group_id: str) -> int | str:
    try:
        return int(group_id)
    except Exception:
        return group_id


def _count_group_files(group_id: str) -> int:
    try:
        with closing(ZSXQFileDatabase(group_id)) as files_db:
            return files_db.count_files()
    except Exception:
        return 0


def _build_group_info_fallback(
    group_id: str,
    account: Any,
    files_count: int,
    source: str = "fallback",
    note: str | None = None,
) -> Dict[str, Any]:
    result = {
        "group_id": _coerce_group_id(group_id),
        "name": f"群组 {group_id}",
        "description": "",
        "statistics": {"files": {"count": files_count}},
        "background_url": None,
        "account": account,
        "source": source,
    }
    if note:
        result["note"] = note
    return result


def _get_group_info_response(group_id: str) -> Dict[str, Any]:
    def build_fallback(source: str = "fallback", note: str = None) -> dict:
        return _build_group_info_fallback(
            group_id,
            account=get_account_summary_for_group_auto(group_id),
            files_count=_count_group_files(group_id),
            source=source,
            note=note,
        )

    try:
        for group_data in _fetch_official_groups():
            if str(group_data.get("group_id")) == str(group_id):
                return {
                    "group_id": group_data.get("group_id"),
                    "name": group_data.get("name"),
                    "description": group_data.get("description"),
                    "statistics": group_data.get("statistics", {}),
                    "background_url": group_data.get("background_url"),
                    "account": get_account_summary_for_group_auto(group_id),
                    "source": "official",
                }

        return build_fallback(note="official_group_not_found")
    except Exception:
        return build_fallback(note="exception_fallback")


def _get_group_stats_response(group_id: int) -> Dict[str, Any]:
    with closing(ZSXQDatabase(str(group_id))) as db:
        return db.get_group_stats_summary()


def _get_group_database_info_response(group_id: int) -> Dict[str, Any]:
    with closing(ZSXQDatabase(str(group_id))) as topics_db, closing(ZSXQFileDatabase(str(group_id))) as files_db:
        db_info = {
            "group_id": str(group_id),
            "schema": "zsxq_core",
            "group_dir": get_db_path_manager().get_group_dir(str(group_id)),
            "topics": topics_db.get_database_stats(),
            "files": files_db.get_database_stats(),
        }

    return {
        "group_id": group_id,
        "database_info": db_info,
    }


async def _groups() -> Dict[str, Any]:
    return await asyncio.to_thread(_get_groups_response)


async def _group_info(group_id: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_get_group_info_response, group_id)


async def _group_stats(group_id: int) -> Dict[str, Any]:
    return await asyncio.to_thread(_get_group_stats_response, group_id)


async def _group_database_info(group_id: int) -> Dict[str, Any]:
    return await asyncio.to_thread(_get_group_database_info_response, group_id)


def _group_route_error(message: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


@router.get("/groups")
async def get_groups():
    """获取群组列表：账号群 ∪ 本地目录群（去重合并）"""
    try:
        return await _groups()
    except Exception as e:
        raise _group_route_error("获取群组列表失败", e)


@router.get("/groups/{group_id}/info")
async def get_group_info(group_id: str):
    """获取群组信息（带本地回退，避免401/500导致前端报错）"""
    try:
        return await _group_info(group_id)
    except Exception as e:
        raise _group_route_error("获取群组信息失败", e)


@router.get("/groups/{group_id}/stats")
async def get_group_stats(group_id: int):
    """获取指定群组的统计信息"""
    try:
        return await _group_stats(group_id)
    except Exception as e:
        raise _group_route_error("获取群组统计失败", e)


@router.get("/groups/{group_id}/database-info")
async def get_group_database_info(group_id: int):
    """获取指定群组的数据库信息"""
    try:
        return await _group_database_info(group_id)
    except Exception as e:
        raise _group_route_error("获取数据库信息失败", e)


@router.delete("/groups/{group_id}")
async def delete_group_local_api(group_id: str):
    """删除指定社群的本地数据（复用主模块实现）"""
    return await delete_group_local_data(group_id)
