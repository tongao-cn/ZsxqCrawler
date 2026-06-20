from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List

from backend.crawlers.official_topic_client import (
    OfficialTopicClient,
    official_payload_groups,
    official_payload_user,
)
from backend.core.account_context import build_account_group_detection
from backend.core.db_path_manager import get_db_path_manager
from backend.core.local_group_runtime import get_cached_local_group_ids
from backend.storage.zsxq_database import ZSXQDatabase


def _warn(message: str):
    print(f"[WARN] {message}")


def _persist_group_meta_local(group_id: int, info: Dict[str, Any]):
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
    try:
        with closing(ZSXQDatabase(str(group_id))) as db:
            return db.load_local_group_db_fields(fields)
    except Exception as e:
        _warn(f"读取本地群组 {group_id} 元数据失败: {e}")
    return dict(fields)


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


def fetch_official_groups(client: OfficialTopicClient | None = None) -> List[dict]:
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
        "source": "account",
    }


def get_groups_response() -> Dict[str, Any]:
    group_account_map = build_account_group_detection()
    local_ids = get_cached_local_group_ids(force_refresh=False)

    groups_data: List[dict] = []
    try:
        groups_data = fetch_official_groups()
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
