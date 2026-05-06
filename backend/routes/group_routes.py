from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import requests
from fastapi import APIRouter, HTTPException

from backend.core.db_path_manager import get_db_path_manager
from backend.core.account_context import (
    build_account_group_detection,
    fetch_groups_from_api,
    get_account_summary_for_group_auto,
    get_cookie_for_group,
    get_primary_cookie,
)
from backend.core.crawler_runtime import get_crawler_for_group
from backend.core.local_group_runtime import (
    get_cached_local_group_ids,
    delete_group_local as delete_group_local_data,
    scan_local_groups,
)
from backend.storage.zsxq_database import ZSXQDatabase

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
        print(f"⚠️ 写入本地群组元数据失败: {e}")


@router.get("/groups")
async def get_groups():
    """获取群组列表：账号群 ∪ 本地目录群（去重合并）"""
    try:
        # 自动构建群组→账号映射（多账号支持）
        group_account_map = build_account_group_detection()
        local_ids = get_cached_local_group_ids(force_refresh=False)

        # 获取“当前账号”的群列表（优先账号默认账号，其次config.toml；若未配置则视为空集合）
        groups_data: List[dict] = []
        try:
            primary_cookie = get_primary_cookie()
            if primary_cookie:
                groups_data = fetch_groups_from_api(primary_cookie)
        except Exception as e:
            # 不阻断，记录告警
            print(f"⚠️ 获取账号群失败，降级为本地集合: {e}")
            groups_data = []

        # 组装账号侧群为字典（id -> info）
        by_id: Dict[int, dict] = {}

        for group in groups_data or []:
            # 提取用户特定信息
            user_specific = group.get("user_specific", {}) or {}
            validity = user_specific.get("validity", {}) or {}
            trial = user_specific.get("trial", {}) or {}

            # 过期信息与状态
            actual_expiry_time = trial.get("end_time") or validity.get("end_time")
            is_trial = bool(trial.get("end_time"))

            status = None
            if actual_expiry_time:
                from datetime import datetime, timezone

                try:
                    end_time = datetime.fromisoformat(actual_expiry_time.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    days_until_expiry = (end_time - now).days
                    if days_until_expiry < 0:
                        status = "expired"
                    elif days_until_expiry <= 7:
                        status = "expiring_soon"
                    else:
                        status = "active"
                except Exception:
                    pass

            gid = group.get("group_id")
            try:
                gid = int(gid)
            except Exception:
                continue

            info = {
                "group_id": gid,
                "name": group.get("name", ""),
                "type": group.get("type", ""),
                "background_url": group.get("background_url", ""),
                "owner": group.get("owner", {}) or {},
                "statistics": group.get("statistics", {}) or {},
                "status": status,
                "create_time": group.get("create_time"),
                "subscription_time": validity.get("begin_time"),
                "expiry_time": actual_expiry_time,
                "join_time": user_specific.get("join_time"),
                "last_active_time": user_specific.get("last_active_time"),
                "description": group.get("description", ""),
                "is_trial": is_trial,
                "trial_end_time": trial.get("end_time"),
                "membership_end_time": validity.get("end_time"),
                "account": group_account_map.get(str(gid)),
                "source": "account",
            }
            by_id[gid] = info

        # 合并本地目录群
        for gid in local_ids or []:
            try:
                gid_int = int(gid)
            except Exception:
                continue
            if gid_int in by_id:
                # 标注来源为 account|local，并持久化一份元信息到本地
                src = by_id[gid_int].get("source", "account")
                if "local" not in src:
                    by_id[gid_int]["source"] = "account|local"
                _persist_group_meta_local(gid_int, by_id[gid_int])
            else:
                # 仅存在于本地：优先从 group_meta.json 读取元信息，其次从本地数据库补全
                local_name = f"本地群（{gid_int}）"
                local_type = "local"
                local_bg = ""
                owner: Dict[str, Any] = {}
                join_time = None
                expiry_time = None
                last_active_time = None
                description = ""
                statistics: Dict[str, Any] = {}

                # 1. 优先读取本地元数据文件（如果之前有账号+本地时已经落盘）
                try:
                    path_manager = get_db_path_manager()
                    group_dir = path_manager.get_group_data_dir(str(gid_int))
                    meta_path = Path(group_dir) / "group_meta.json"
                    if meta_path.exists():
                        with meta_path.open("r", encoding="utf-8") as f:
                            meta = json.load(f)
                        local_name = meta.get("name", local_name)
                        local_type = meta.get("type", local_type)
                        local_bg = meta.get("background_url", local_bg)
                        owner = meta.get("owner", {}) or owner
                        statistics = meta.get("statistics", {}) or statistics
                        join_time = meta.get("join_time", join_time)
                        expiry_time = meta.get("expiry_time", expiry_time)
                        last_active_time = meta.get("last_active_time", last_active_time)
                        description = meta.get("description", description)
                except Exception as e:
                    print(f"⚠️ 读取本地群组 {gid_int} 元数据文件失败: {e}")

                # 2. 若元数据文件中仍缺少信息，再从本地数据库补充
                try:
                    path_manager = get_db_path_manager()
                    db_paths = path_manager.list_group_databases(str(gid_int))
                    topics_db = db_paths.get("topics")
                    if topics_db and os.path.exists(topics_db):
                        db = ZSXQDatabase(topics_db)
                        try:
                            cur = db.cursor
                            # 群组基础信息
                            if not local_bg or local_name.startswith("本地群（"):
                                cur.execute(
                                    "SELECT name, type, background_url FROM groups WHERE group_id = ? LIMIT 1",
                                    (gid_int,),
                                )
                                row = cur.fetchone()
                                if row:
                                    if row[0]:
                                        local_name = row[0]
                                    if row[1]:
                                        local_type = row[1]
                                    if row[2]:
                                        local_bg = row[2]

                            # 本地数据时间范围（以话题时间替代“加入/过期时间”的近似）
                            if not join_time or not expiry_time:
                                cur.execute(
                                    """
                                    SELECT MIN(create_time), MAX(create_time)
                                    FROM topics
                                    WHERE group_id = ? AND create_time IS NOT NULL AND create_time != ''
                                    """,
                                    (gid_int,),
                                )
                                trow = cur.fetchone()
                                if trow:
                                    if not join_time:
                                        join_time = trow[0]
                                    if not expiry_time:
                                        expiry_time = trow[1]
                                    if not last_active_time:
                                        last_active_time = trow[1]

                            # 简单统计：话题数量
                            if not statistics:
                                cur.execute(
                                    "SELECT COUNT(*) FROM topics WHERE group_id = ?",
                                    (gid_int,),
                                )
                                topics_count = cur.fetchone()[0] or 0
                                statistics = {
                                    "topics": {
                                        "topics_count": topics_count,
                                        "answers_count": 0,
                                        "digests_count": 0,
                                    }
                                }
                        finally:
                            db.close()
                except Exception as e:
                    # 出错时降级为占位信息，不中断整个接口
                    print(f"⚠️ 读取本地群组 {gid_int} 元数据失败: {e}")

                by_id[gid_int] = {
                    "group_id": gid_int,
                    "name": local_name,
                    "type": local_type,
                    "background_url": local_bg,
                    "owner": owner,
                    "statistics": statistics,
                    "status": None,
                    "create_time": join_time,
                    "subscription_time": None,
                    "expiry_time": expiry_time,
                    "join_time": join_time,
                    "last_active_time": last_active_time,
                    "description": description,
                    "is_trial": False,
                    "trial_end_time": None,
                    "membership_end_time": None,
                    "account": None,
                    "source": "local",
                }

        # 排序：按群ID升序；如需二级排序再按来源（账号优先）
        merged = [by_id[k] for k in sorted(by_id.keys())]

        return {
            "groups": merged,
            "total": len(merged),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取群组列表失败: {str(e)}")


@router.get("/groups/{group_id}/info")
async def get_group_info(group_id: str):
    """获取群组信息（带本地回退，避免401/500导致前端报错）"""
    try:
        # 本地回退数据构造（不访问官方API）
        def build_fallback(source: str = "fallback", note: str = None) -> dict:
            files_count = 0
            try:
                crawler = get_crawler_for_group(group_id)
                downloader = crawler.get_file_downloader()
                try:
                    downloader.file_db.cursor.execute("SELECT COUNT(*) FROM files")
                    row = downloader.file_db.cursor.fetchone()
                    files_count = (row[0] or 0) if row else 0
                except Exception:
                    files_count = 0
            except Exception:
                files_count = 0

            try:
                gid = int(group_id)
            except Exception:
                gid = group_id

            result = {
                "group_id": gid,
                "name": f"群组 {group_id}",
                "description": "",
                "statistics": {"files": {"count": files_count}},
                "background_url": None,
                "account": get_account_summary_for_group_auto(group_id),
                "source": source,
            }
            if note:
                result["note"] = note
            return result

        # 自动匹配该群组所属账号，获取对应Cookie
        cookie = get_cookie_for_group(group_id)

        # 若没有可用 Cookie，直接返回本地回退，避免抛 400/500
        if not cookie:
            return build_fallback(note="no_cookie")

        # 调用官方接口
        url = f"https://api.zsxq.com/v2/groups/{group_id}"
        headers = {
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()
            if data.get("succeeded"):
                group_data = data.get("resp_data", {}).get("group", {})
                return {
                    "group_id": group_data.get("group_id"),
                    "name": group_data.get("name"),
                    "description": group_data.get("description"),
                    "statistics": group_data.get("statistics", {}),
                    "background_url": group_data.get("background_url"),
                    "account": get_account_summary_for_group_auto(group_id),
                    "source": "remote",
                }
            # 官方返回非 succeeded，也走回退
            return build_fallback(note="remote_response_failed")
        else:
            # 授权失败/权限不足 → 使用本地回退（200返回，减少前端告警）
            if response.status_code in (401, 403):
                return build_fallback(note=f"remote_api_{response.status_code}")
            # 其他状态码也回退
            return build_fallback(note=f"remote_api_{response.status_code}")

    except Exception:
        # 任何异常都回退为本地信息，避免 500
        return build_fallback(note="exception_fallback")


@router.get("/groups/{group_id}/stats")
async def get_group_stats(group_id: int):
    """获取指定群组的统计信息"""
    try:
        # 使用指定群组的爬虫实例
        crawler = get_crawler_for_group(str(group_id))
        cursor = crawler.db.cursor

        # 获取话题统计
        cursor.execute("SELECT COUNT(*) FROM topics WHERE group_id = ?", (group_id,))
        topics_count = cursor.fetchone()[0]

        # 获取用户统计 - 从talks表获取，因为topics表没有user_id字段
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

        # 获取最新话题时间
        cursor.execute("SELECT MAX(create_time) FROM topics WHERE group_id = ?", (group_id,))
        latest_topic_time = cursor.fetchone()[0]

        # 获取最早话题时间
        cursor.execute("SELECT MIN(create_time) FROM topics WHERE group_id = ?", (group_id,))
        earliest_topic_time = cursor.fetchone()[0]

        # 获取总点赞数
        cursor.execute("SELECT SUM(likes_count) FROM topics WHERE group_id = ?", (group_id,))
        total_likes = cursor.fetchone()[0] or 0

        # 获取总评论数
        cursor.execute("SELECT SUM(comments_count) FROM topics WHERE group_id = ?", (group_id,))
        total_comments = cursor.fetchone()[0] or 0

        # 获取总阅读数
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取群组统计失败: {str(e)}")


@router.get("/groups/{group_id}/database-info")
async def get_group_database_info(group_id: int):
    """获取指定群组的数据库信息"""
    try:
        path_manager = get_db_path_manager()
        db_info = path_manager.get_database_info(str(group_id))

        return {
            "group_id": group_id,
            "database_info": db_info,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取数据库信息失败: {str(e)}")


@router.delete("/groups/{group_id}")
async def delete_group_local_api(group_id: str):
    """删除指定社群的本地数据（复用主模块实现）"""
    return await delete_group_local_data(group_id)
