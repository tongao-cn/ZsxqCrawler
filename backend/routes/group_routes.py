from __future__ import annotations

import asyncio
import json
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from backend.crawlers.official_topic_client import (
    OfficialTopicClient,
    official_payload_groups,
    official_payload_user,
)
from backend.core.db_path_manager import get_db_path_manager
from backend.core.account_context import (
    build_account_group_detection,
    get_account_summary_for_group_auto,
)
from backend.core.local_group_runtime import (
    get_cached_local_group_ids,
    delete_group_local as delete_group_local_data,
    scan_local_groups,
)
from backend.storage.zsxq_database import ZSXQDatabase
from backend.storage.zsxq_file_database import ZSXQFileDatabase

router = APIRouter(prefix="/api", tags=["groups"])


def _warn(message: str):
    print(f"[WARN] {message}")


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


def _persist_group_meta_local(group_id: int, info: Dict[str, Any]):
    """
    将群组的封面、名称、群主与时间等元信息持久化到本地目录。
    这样即使后续账号 Cookie 失效，仅保留本地数据时，也能展示完整信息。
    """
    try:
        path_manager = get_db_path_manager()
        group_dir = path_manager.get_group_data_dir(str(group_id))
        meta_path = Path(group_dir) / "group_meta.json"

        meta = {
            "group_id": group_id,
            "name": info.get("name") or f"本地群（{group_id}）",
            "type": info.get("type", ""),
            "background_url": info.get("background_url", ""),
            "owner": info.get("owner", {}) or {},
            "statistics": info.get("statistics", {}) or {},
            "create_time": info.get("create_time"),
            "subscription_time": info.get("subscription_time"),
            "expiry_time": info.get("expiry_time"),
            "join_time": info.get("join_time"),
            "last_active_time": info.get("last_active_time"),
            "description": info.get("description", ""),
            "is_trial": info.get("is_trial", False),
            "trial_end_time": info.get("trial_end_time"),
            "membership_end_time": info.get("membership_end_time"),
        }

        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _warn(f"写入本地群组元数据失败: {e}")


def _default_local_group_fields(group_id: int) -> Dict[str, Any]:
    return {
        "local_name": f"本地群（{group_id}）",
        "local_type": "local",
        "local_bg": "",
        "owner": {},
        "join_time": None,
        "expiry_time": None,
        "last_active_time": None,
        "description": "",
        "statistics": {},
    }


def _read_local_group_meta(group_id: int) -> Dict[str, Any]:
    try:
        path_manager = get_db_path_manager()
        group_dir = path_manager.get_group_data_dir(str(group_id))
        meta_path = Path(group_dir) / "group_meta.json"
        if meta_path.exists():
            with meta_path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        _warn(f"读取本地群组 {group_id} 元数据文件失败: {e}")
    return {}


def _apply_local_group_meta(fields: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(fields)
    result["local_name"] = meta.get("name", result["local_name"])
    result["local_type"] = meta.get("type", result["local_type"])
    result["local_bg"] = meta.get("background_url", result["local_bg"])
    result["owner"] = meta.get("owner", {}) or result["owner"]
    result["statistics"] = meta.get("statistics", {}) or result["statistics"]
    result["join_time"] = meta.get("join_time", result["join_time"])
    result["expiry_time"] = meta.get("expiry_time", result["expiry_time"])
    result["last_active_time"] = meta.get("last_active_time", result["last_active_time"])
    result["description"] = meta.get("description", result["description"])
    return result


def _load_local_group_db_fields(group_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(fields)
    try:
        with closing(ZSXQDatabase(str(group_id))) as db:
            cur = db.cursor
            if not result["local_bg"] or result["local_name"].startswith("本地群（"):
                cur.execute(
                    "SELECT name, type, background_url FROM groups WHERE group_id = ? LIMIT 1",
                    (group_id,),
                )
                row = cur.fetchone()
                if row:
                    if row[0]:
                        result["local_name"] = row[0]
                    if row[1]:
                        result["local_type"] = row[1]
                    if row[2]:
                        result["local_bg"] = row[2]

            if not result["join_time"] or not result["expiry_time"]:
                cur.execute(
                    """
                    SELECT MIN(create_time), MAX(create_time)
                    FROM topics
                    WHERE group_id = ? AND create_time IS NOT NULL AND create_time != ''
                    """,
                    (group_id,),
                )
                trow = cur.fetchone()
                if trow:
                    if not result["join_time"]:
                        result["join_time"] = trow[0]
                    if not result["expiry_time"]:
                        result["expiry_time"] = trow[1]
                    if not result["last_active_time"]:
                        result["last_active_time"] = trow[1]

            if not result["statistics"]:
                cur.execute(
                    "SELECT COUNT(*) FROM topics WHERE group_id = ?",
                    (group_id,),
                )
                topics_count = cur.fetchone()[0] or 0
                result["statistics"] = {
                    "topics": {
                        "topics_count": topics_count,
                        "answers_count": 0,
                        "digests_count": 0,
                    }
                }
    except Exception as e:
        _warn(f"读取本地群组 {group_id} 元数据失败: {e}")
    return result


def _build_local_group_entry(group_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "group_id": group_id,
        "name": fields["local_name"],
        "type": fields["local_type"],
        "background_url": fields["local_bg"],
        "owner": fields["owner"],
        "statistics": fields["statistics"],
        "status": None,
        "create_time": fields["join_time"],
        "subscription_time": None,
        "expiry_time": fields["expiry_time"],
        "join_time": fields["join_time"],
        "last_active_time": fields["last_active_time"],
        "description": fields["description"],
        "is_trial": False,
        "trial_end_time": None,
        "membership_end_time": None,
        "account": None,
        "source": "local",
    }


def _build_local_group_entry_from_sources(group_id: int) -> Dict[str, Any]:
    fields = _default_local_group_fields(group_id)
    fields = _apply_local_group_meta(fields, _read_local_group_meta(group_id))
    fields = _load_local_group_db_fields(group_id, fields)
    return _build_local_group_entry(group_id, fields)


def _coerce_group_id(group_id: str) -> int | str:
    try:
        return int(group_id)
    except Exception:
        return group_id


def _count_group_files(group_id: str) -> int:
    try:
        with closing(ZSXQFileDatabase(group_id)) as files_db:
            files_db.cursor.execute("SELECT COUNT(*) FROM files WHERE group_id = ?", (_coerce_group_id(group_id),))
            row = files_db.cursor.fetchone()
            return (row[0] or 0) if row else 0
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


def _fetch_official_groups(client: OfficialTopicClient | None = None) -> List[dict]:
    client = client or OfficialTopicClient()
    user = official_payload_user(client.get_self_info())
    user_id = user.get("user_id")
    if not user_id:
        return []
    return official_payload_groups(client.get_user_groups(user_id, limit=200, scope="all"))


def _build_official_group_entry(group: Dict[str, Any], account: Any = None) -> Dict[str, Any] | None:
    gid = group.get("group_id")
    try:
        gid = int(gid)
    except Exception:
        return None

    return {
        "group_id": gid,
        "name": group.get("name", ""),
        "type": group.get("type", ""),
        "background_url": group.get("background_url", ""),
        "owner": group.get("owner", {}) or {},
        "statistics": group.get("statistics", {}) or {},
        "status": None,
        "create_time": group.get("create_time"),
        "subscription_time": None,
        "expiry_time": None,
        "join_time": None,
        "last_active_time": None,
        "description": group.get("description", ""),
        "is_trial": False,
        "trial_end_time": None,
        "membership_end_time": None,
        "account": account,
        # The UI uses "account" for remote/network groups; this data is fetched
        # through the official MCP client, not the cookie crawler.
        "source": "account",
    }


def _get_groups_response() -> Dict[str, Any]:
    group_account_map = build_account_group_detection()
    local_ids = get_cached_local_group_ids(force_refresh=False)

    groups_data: List[dict] = []
    try:
        groups_data = _fetch_official_groups()
    except Exception as e:
        _warn(f"获取官方群组失败，降级为本地集合: {e}")
        groups_data = []

    by_id: Dict[int, dict] = {}

    for group in groups_data or []:
        info = _build_official_group_entry(group, account=group_account_map.get(str(group.get("group_id"))))
        if not info:
            continue
        by_id[info["group_id"]] = info

    for gid in local_ids or []:
        try:
            gid_int = int(gid)
        except Exception:
            continue
        if gid_int in by_id:
            src = by_id[gid_int].get("source", "official")
            if "local" not in src:
                by_id[gid_int]["source"] = f"{src}|local"
            _persist_group_meta_local(gid_int, by_id[gid_int])
        else:
            by_id[gid_int] = _build_local_group_entry_from_sources(gid_int)

    merged = [by_id[k] for k in sorted(by_id.keys())]

    return {
        "groups": merged,
        "total": len(merged),
    }


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
        cursor = db.cursor

        cursor.execute("SELECT COUNT(*) FROM topics WHERE group_id = ?", (group_id,))
        topics_count = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(DISTINCT t.owner_user_id)
            FROM talks t
            JOIN topics tp ON t.topic_id = tp.topic_id
            WHERE tp.group_id = ?
        """,
            (group_id,),
        )
        users_count = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(create_time) FROM topics WHERE group_id = ?", (group_id,))
        latest_topic_time = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(create_time) FROM topics WHERE group_id = ?", (group_id,))
        earliest_topic_time = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(likes_count) FROM topics WHERE group_id = ?", (group_id,))
        total_likes = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(comments_count) FROM topics WHERE group_id = ?", (group_id,))
        total_comments = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(reading_count) FROM topics WHERE group_id = ?", (group_id,))
        total_readings = cursor.fetchone()[0] or 0

    return {
        "group_id": group_id,
        "topics_count": topics_count,
        "users_count": users_count,
        "latest_topic_time": latest_topic_time,
        "earliest_topic_time": earliest_topic_time,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_readings": total_readings,
    }


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


@router.get("/groups")
async def get_groups():
    """获取群组列表：账号群 ∪ 本地目录群（去重合并）"""
    try:
        return await _groups()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取群组列表失败: {str(e)}")


@router.get("/groups/{group_id}/info")
async def get_group_info(group_id: str):
    """获取群组信息（带本地回退，避免401/500导致前端报错）"""
    try:
        return await _group_info(group_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取群组信息失败: {str(e)}")


@router.get("/groups/{group_id}/stats")
async def get_group_stats(group_id: int):
    """获取指定群组的统计信息"""
    try:
        return await _group_stats(group_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取群组统计失败: {str(e)}")


@router.get("/groups/{group_id}/database-info")
async def get_group_database_info(group_id: int):
    """获取指定群组的数据库信息"""
    try:
        return await _group_database_info(group_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取数据库信息失败: {str(e)}")


@router.delete("/groups/{group_id}")
async def delete_group_local_api(group_id: str):
    """删除指定社群的本地数据（复用主模块实现）"""
    return await delete_group_local_data(group_id)
