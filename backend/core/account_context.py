from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

import requests

from backend.crawlers.zsxq_interactive_crawler import load_config
from backend.storage.accounts_sql_manager import get_accounts_sql_manager


_account_detect_cache: Optional[Dict[str, Dict[str, Any]]] = None


def clear_account_detect_cache() -> None:
    global _account_detect_cache
    _account_detect_cache = None


def get_primary_cookie() -> Optional[str]:
    try:
        sql_mgr = get_accounts_sql_manager()
        first_acc = sql_mgr.get_first_account(mask_cookie=False)
        if first_acc:
            cookie = (first_acc.get("cookie") or "").strip()
            if cookie:
                return cookie
    except Exception:
        pass

    try:
        config = load_config()
        if not config:
            return None
        auth_config = config.get("auth", {}) or {}
        cookie = (auth_config.get("cookie") or "").strip()
        if cookie and cookie != "your_cookie_here":
            return cookie
    except Exception:
        return None

    return None


def is_configured() -> bool:
    return get_primary_cookie() is not None


def am_get_account_for_group(group_id: str) -> Optional[Dict[str, Any]]:
    try:
        sql_mgr = get_accounts_sql_manager()
        return sql_mgr.get_account_for_group(group_id, mask_cookie=False)
    except Exception:
        return None


def am_get_account_summary_for_group(group_id: str) -> Optional[Dict[str, Any]]:
    try:
        sql_mgr = get_accounts_sql_manager()
        return sql_mgr.get_account_summary_for_group(group_id)
    except Exception:
        return get_account_summary_for_group_auto(group_id)


def get_cookie_for_group(group_id: str) -> Optional[str]:
    try:
        sql_mgr = get_accounts_sql_manager()
        acc = sql_mgr.get_account_for_group(group_id, mask_cookie=False)
        if acc:
            cookie = (acc.get("cookie") or "").strip()
            if cookie:
                return cookie
    except Exception:
        pass
    return get_primary_cookie()


def get_account_summary_for_group_auto(group_id: str) -> Optional[Dict[str, Any]]:
    try:
        sql_mgr = get_accounts_sql_manager()
        summary = sql_mgr.get_account_summary_for_group(group_id)
        if summary:
            return summary

        first_acc = sql_mgr.get_first_account(mask_cookie=True)
        if first_acc:
            return {
                "id": first_acc.get("id"),
                "name": first_acc.get("name"),
                "created_at": first_acc.get("created_at"),
                "cookie": first_acc.get("cookie"),
            }
    except Exception:
        pass

    try:
        config = load_config()
        if not config:
            return None
        auth_config = config.get("auth", {}) or {}
        cookie = (auth_config.get("cookie") or "").strip()
        if cookie and cookie != "your_cookie_here":
            return {
                "id": "config",
                "name": auth_config.get("name") or "config",
                "created_at": None,
                "cookie": cookie[-8:] if len(cookie) > 8 else cookie,
            }
    except Exception:
        pass

    return None


def build_account_group_detection() -> Dict[str, Dict[str, Any]]:
    global _account_detect_cache
    if _account_detect_cache is not None:
        return _account_detect_cache

    mapping: Dict[str, Dict[str, Any]] = {}
    try:
        sql_mgr = get_accounts_sql_manager()
        group_map = sql_mgr.get_group_account_mapping()
        for group_id, account_id in group_map.items():
            account = sql_mgr.get_account_by_id(account_id, mask_cookie=True)
            if not account:
                continue
            mapping[str(group_id)] = {
                "id": account.get("id"),
                "name": account.get("name"),
                "created_at": account.get("created_at"),
                "cookie": account.get("cookie"),
            }
    except Exception as exc:
        print(f"⚠️ 构建群组账号映射失败: {exc}")

    _account_detect_cache = mapping
    return mapping


def build_stealth_headers(cookie: str) -> Dict[str, str]:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ]
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
        "Cache-Control": "no-cache",
        "Cookie": cookie,
        "Origin": "https://wx.zsxq.com",
        "Pragma": "no-cache",
        "Priority": "u=1, i",
        "Referer": "https://wx.zsxq.com/",
        "Sec-Ch-Ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": "\"Windows\"",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": random.choice(user_agents),
        "X-Aduid": "a3be07cd6-dd67-3912-0093-862d844e7fe",
        "X-Request-Id": f"dcc5cb6ab-1bc3-8273-cc26-{random.randint(100000000000, 999999999999)}",
        "X-Signature": "733fd672ddf6d4e367730d9622cdd1e28a4b6203",
        "X-Timestamp": str(int(time.time())),
        "X-Version": "2.77.0",
    }


def fetch_groups_from_api(cookie: str) -> List[dict]:
    """从知识星球API获取群组列表"""
    if cookie == "test_cookie":
        return [
            {
                "group_id": 123456,
                "name": "测试知识星球群组",
                "type": "public",
                "background_url": "https://via.placeholder.com/400x200/4f46e5/ffffff?text=Test+Group",
                "description": "这是一个用于测试的知识星球群组，包含各种技术讨论和学习资源分享。",
                "create_time": "2023-01-15T10:30:00+08:00",
                "subscription_time": "2024-01-01T00:00:00+08:00",
                "expiry_time": "2024-12-31T23:59:59+08:00",
                "status": "active",
                "owner": {
                    "user_id": 1001,
                    "name": "测试群主",
                    "avatar_url": "https://via.placeholder.com/64x64/10b981/ffffff?text=Owner",
                },
                "statistics": {
                    "members_count": 1250,
                    "topics_count": 89,
                    "files_count": 156,
                },
            }
        ]

    headers = build_stealth_headers(cookie)
    try:
        response = requests.get("https://api.zsxq.com/v2/groups", headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        if data.get("succeeded"):
            return data.get("resp_data", {}).get("groups", [])
        raise Exception(f"API返回失败: {data.get('error_message', '未知错误')}")
    except requests.RequestException as e:
        raise Exception(f"网络请求失败: {str(e)}")
    except Exception as e:
        raise Exception(f"获取群组列表失败: {str(e)}")
