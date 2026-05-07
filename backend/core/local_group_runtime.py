from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from fastapi import HTTPException

from backend.core.crawler_runtime import get_crawler_for_group
from backend.core.db_path_manager import get_db_path_manager
from backend.core.image_cache_manager import clear_group_cache_manager, get_image_cache_manager
from backend.storage.db_compat import connect


LOCAL_OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
try:
    LOCAL_SCAN_LIMIT = int(os.environ.get("LOCAL_GROUPS_SCAN_LIMIT", "10000"))
except Exception:
    LOCAL_SCAN_LIMIT = 10000

_local_groups_cache: Dict[str, Any] = {
    "ids": set(),
    "scanned_at": 0.0,
}


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


def _collect_postgres_group_ids(limit: int) -> set:
    try:
        conn = connect("zsxq_core_groups")
        try:
            rows = conn.execute("SELECT group_id FROM groups LIMIT ?", (limit,)).fetchall()
        finally:
            conn.close()
        ids = set()
        for row in rows:
            try:
                gid = int(row[0])
                if gid > 0:
                    ids.add(gid)
            except Exception:
                continue
        return ids
    except Exception:
        return set()


def scan_local_groups(output_dir: Optional[str] = None, limit: Optional[int] = None) -> set:
    """扫描本地 output 的一级子目录，获取群ID集合。"""
    try:
        odir = output_dir or LOCAL_OUTPUT_DIR
        lim = int(limit or LOCAL_SCAN_LIMIT)

        ids_pg = _collect_postgres_group_ids(lim)
        ids_primary = _collect_numeric_dirs(odir, lim)
        ids_secondary = _collect_numeric_dirs(os.path.join(odir, "databases"), lim)
        ids = set(ids_pg) | set(ids_primary) | set(ids_secondary)

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
