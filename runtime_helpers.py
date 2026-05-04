from __future__ import annotations

import os
import random
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException

from accounts_sql_manager import get_accounts_sql_manager
from a_share_analysis_service import normalize_group_id
from db_path_manager import get_db_path_manager
from image_cache_manager import clear_group_cache_manager, get_image_cache_manager
from logger_config import log_debug, log_error, log_exception, log_info, log_warning
from zsxq_interactive_crawler import ZSXQInteractiveCrawler, load_config


crawler_instance: Optional[ZSXQInteractiveCrawler] = None

LOCAL_OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
try:
    LOCAL_SCAN_LIMIT = int(os.environ.get("LOCAL_GROUPS_SCAN_LIMIT", "10000"))
except Exception:
    LOCAL_SCAN_LIMIT = 10000

_local_groups_cache: Dict[str, Any] = {
    "ids": set(),
    "scanned_at": 0.0,
}

_account_detect_cache: Optional[Dict[str, Dict[str, Any]]] = None


def _safe_listdir(path: str):
    try:
        return os.listdir(path)
    except Exception:
        return []


def _collect_numeric_dirs(base: str, limit: int) -> set:
    ids = set()
    if not os.path.isdir(base):
        return ids

    try:
        entries = _safe_listdir(base)
        for name in entries:
            if len(ids) >= limit:
                break
            full = os.path.join(base, name)
            if not os.path.isdir(full):
                continue
            try:
                gid = int(name)
                if gid > 0:
                    ids.add(gid)
                    continue
            except Exception:
                pass
            try:
                for sub in _safe_listdir(full):
                    if len(ids) >= limit:
                        break
                    sub_full = os.path.join(full, sub)
                    if os.path.isdir(sub_full):
                        try:
                            gid = int(sub)
                            if gid > 0:
                                ids.add(gid)
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception:
        return ids

    return ids


def scan_local_groups(output_dir: str = None, limit: int = None) -> set:
    """扫描本地 output 的一级子目录，获取群ID集合。"""
    try:
        odir = output_dir or LOCAL_OUTPUT_DIR
        lim = int(limit or LOCAL_SCAN_LIMIT)

        ids_primary = _collect_numeric_dirs(odir, lim)
        ids_secondary = _collect_numeric_dirs(os.path.join(odir, "databases"), lim)
        ids = set(ids_primary) | set(ids_secondary)

        _local_groups_cache["ids"] = ids
        _local_groups_cache["scanned_at"] = time.time()

        return ids
    except Exception as e:
        print(f"⚠️ 本地群扫描异常: {e}")
        return _local_groups_cache.get("ids", set())


def get_cached_local_group_ids(force_refresh: bool = False) -> set:
    if force_refresh or not _local_groups_cache.get("ids"):
        return scan_local_groups()
    return _local_groups_cache.get("ids", set())


def clear_account_detect_cache() -> None:
    global _account_detect_cache
    _account_detect_cache = None


def get_crawler(log_callback=None) -> ZSXQInteractiveCrawler:
    global crawler_instance
    if crawler_instance is None:
        config = load_config()
        if not config:
            raise HTTPException(status_code=500, detail="配置文件加载失败")

        auth_config = config.get("auth", {})
        cookie = auth_config.get("cookie", "")
        group_id = auth_config.get("group_id", "")

        if cookie == "your_cookie_here" or group_id == "your_group_id_here" or not cookie or not group_id:
            raise HTTPException(status_code=400, detail="请先在config.toml中配置Cookie和群组ID")

        path_manager = get_db_path_manager()
        db_path = path_manager.get_topics_db_path(group_id)
        crawler_instance = ZSXQInteractiveCrawler(cookie, group_id, db_path, log_callback)

    return crawler_instance


def get_crawler_for_group(group_id: str, log_callback=None) -> ZSXQInteractiveCrawler:
    config = load_config()
    if not config:
        raise HTTPException(status_code=500, detail="配置文件加载失败")

    cookie = get_cookie_for_group(group_id)
    if not cookie or cookie == "your_cookie_here":
        raise HTTPException(status_code=400, detail="未找到可用Cookie，请先在账号管理或config.toml中配置")

    path_manager = get_db_path_manager()
    db_path = path_manager.get_topics_db_path(group_id)
    return ZSXQInteractiveCrawler(cookie, group_id, db_path, log_callback)


def get_crawler_safe() -> Optional[ZSXQInteractiveCrawler]:
    try:
        return get_crawler()
    except Exception:
        return None


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


async def delete_group_local(group_id: str):
    """
    删除指定社群的本地数据（数据库、下载文件、图片缓存），不影响账号对该社群的访问权限
    """
    try:
        details = {
            "topics_db_removed": False,
            "files_db_removed": False,
            "downloads_dir_removed": False,
            "images_cache_removed": False,
            "group_dir_removed": False,
        }

        try:
            crawler = get_crawler_for_group(group_id)
            try:
                if hasattr(crawler, "file_downloader") and crawler.file_downloader:
                    if hasattr(crawler.file_downloader, "file_db") and crawler.file_downloader.file_db:
                        crawler.file_downloader.file_db.close()
                        print(f"✅ 已关闭文件数据库连接（群 {group_id}）")
            except Exception as e:
                print(f"⚠️ 关闭文件数据库连接时出错: {e}")
            try:
                if hasattr(crawler, "db") and crawler.db:
                    crawler.db.close()
                    print(f"✅ 已关闭话题数据库连接（群 {group_id}）")
            except Exception as e:
                print(f"⚠️ 关闭话题数据库连接时出错: {e}")
        except Exception as e:
            print(f"⚠️ 获取爬虫实例以关闭连接失败: {e}")

        import gc
        import shutil

        gc.collect()
        time.sleep(0.3)

        path_manager = get_db_path_manager()
        group_dir = path_manager.get_group_dir(group_id)
        topics_db = path_manager.get_topics_db_path(group_id)
        files_db = path_manager.get_files_db_path(group_id)

        try:
            if os.path.exists(topics_db):
                os.remove(topics_db)
                details["topics_db_removed"] = True
                print(f"🗑️ 已删除话题数据库: {topics_db}")
        except PermissionError as pe:
            raise HTTPException(status_code=500, detail=f"话题数据库被占用，无法删除: {pe}")
        except Exception as e:
            print(f"⚠️ 删除话题数据库失败: {e}")

        try:
            if os.path.exists(files_db):
                os.remove(files_db)
                details["files_db_removed"] = True
                print(f"🗑️ 已删除文件数据库: {files_db}")
        except PermissionError as pe:
            raise HTTPException(status_code=500, detail=f"文件数据库被占用，无法删除: {pe}")
        except Exception as e:
            print(f"⚠️ 删除文件数据库失败: {e}")

        downloads_dir = os.path.join(group_dir, "downloads")
        if os.path.exists(downloads_dir):
            try:
                shutil.rmtree(downloads_dir, ignore_errors=False)
                details["downloads_dir_removed"] = True
                print(f"🗑️ 已删除下载目录: {downloads_dir}")
            except Exception as e:
                print(f"⚠️ 删除下载目录失败: {e}")

        try:
            cache_manager = get_image_cache_manager(group_id)
            ok, msg = cache_manager.clear_cache()
            if ok:
                details["images_cache_removed"] = True
                print(f"🗑️ 图片缓存清空: {msg}")
            images_dir = os.path.join(group_dir, "images")
            if os.path.exists(images_dir):
                try:
                    shutil.rmtree(images_dir, ignore_errors=True)
                    print(f"🗑️ 已删除图片缓存目录: {images_dir}")
                except Exception as e:
                    print(f"⚠️ 删除图片缓存目录失败: {e}")
            clear_group_cache_manager(group_id)
        except Exception as e:
            print(f"⚠️ 清理图片缓存失败: {e}")

        try:
            if os.path.exists(group_dir) and len(os.listdir(group_dir)) == 0:
                os.rmdir(group_dir)
                details["group_dir_removed"] = True
                print(f"🗑️ 已删除空群组目录: {group_dir}")
        except Exception as e:
            print(f"⚠️ 删除群组目录失败: {e}")

        try:
            gid_int = int(group_id)
            if gid_int in _local_groups_cache.get("ids", set()):
                _local_groups_cache["ids"].discard(gid_int)
                _local_groups_cache["scanned_at"] = time.time()
        except Exception as e:
            print(f"⚠️ 更新本地群缓存失败: {e}")

        any_removed = any(details.values())
        return {
            "success": True,
            "message": f"群组 {group_id} 本地数据" + ("已删除" if any_removed else "不存在"),
            "details": details,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除群组本地数据失败: {str(e)}")
