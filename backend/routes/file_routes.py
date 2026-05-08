from __future__ import annotations

import asyncio
import gc
import os
import random
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
)
from backend.core.ai_provider_config import has_openai_api_key
from backend.core.crawler_runtime import get_crawler_for_group
from backend.core.db_path_manager import get_db_path_manager
from backend.core.account_context import get_cookie_for_group
from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.services.file_ai_analysis_service import (
    DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    analyze_group_file,
    get_group_file_analysis,
    resolve_local_file_path,
)
from backend.services.task_runtime import (
    add_task_log,
    create_task,
    create_ingestion_task,
    file_downloader_instances,
    is_task_stopped,
    update_task,
)
from backend.storage.zsxq_database import ZSXQDatabase
from backend.storage.zsxq_file_database import ZSXQFileDatabase
from backend.storage.db_compat import connect

router = APIRouter(prefix="/api/files", tags=["files"])


class FileDownloadRequest(BaseModel):
    max_files: Optional[int] = Field(default=None, description="最大下载文件数")
    sort_by: str = Field(default="download_count", description="排序方式: download_count 或 time")
    start_time: Optional[str] = Field(default=None, description="下载时间范围开始日期 YYYY-MM-DD")
    end_time: Optional[str] = Field(default=None, description="下载时间范围结束日期 YYYY-MM-DD")
    last_days: Optional[int] = Field(default=None, ge=1, le=3650, description="下载最近多少天的文件")
    download_interval: float = Field(default=1.0, ge=0.1, le=300.0, description="单次下载间隔（秒）")
    long_sleep_interval: float = Field(default=60.0, ge=10.0, le=3600.0, description="长休眠间隔（秒）")
    files_per_batch: int = Field(default=10, ge=1, le=100, description="下载多少文件后触发长休眠")
    download_interval_min: Optional[float] = Field(default=None, ge=1.0, le=300.0, description="随机下载间隔最小值（秒）")
    download_interval_max: Optional[float] = Field(default=None, ge=1.0, le=300.0, description="随机下载间隔最大值（秒）")
    long_sleep_interval_min: Optional[float] = Field(default=None, ge=10.0, le=3600.0, description="随机长休眠间隔最小值（秒）")
    long_sleep_interval_max: Optional[float] = Field(default=None, ge=10.0, le=3600.0, description="随机长休眠间隔最大值（秒）")


class FileCollectRequest(BaseModel):
    start_time: Optional[str] = Field(default=None, description="收集时间范围开始日期 YYYY-MM-DD")
    end_time: Optional[str] = Field(default=None, description="收集时间范围结束日期 YYYY-MM-DD")
    last_days: Optional[int] = Field(default=None, ge=1, le=3650, description="收集最近多少天的文件")


class FileAIAnalysisRequest(BaseModel):
    force: bool = Field(default=False, description="是否强制重新分析")


def _safe_filename(file_name: str, fallback: str) -> str:
    safe = "".join(c for c in file_name if c.isalnum() or c in "._-（）()[]{}")
    return safe or fallback


def _open_file_db(group_id: str) -> ZSXQFileDatabase:
    return ZSXQFileDatabase(group_id)


def _clear_group_file_data(group_id: str) -> dict:
    conn = connect()
    try:
        cursor = conn.cursor()
        deleted_counts = {}
        topic_ids_sql = "SELECT topic_id FROM topics WHERE group_id = ?"
        file_ids_sql = f"""
            SELECT file_id FROM files WHERE group_id = ?
            UNION
            SELECT file_id FROM file_topic_relations WHERE topic_id IN ({topic_ids_sql})
            UNION
            SELECT file_id FROM topic_files WHERE topic_id IN ({topic_ids_sql})
        """
        cursor.execute(
            f"DELETE FROM file_ai_analyses WHERE file_id IN ({file_ids_sql})",
            (group_id, group_id, group_id),
        )
        deleted_counts["file_ai_analyses"] = cursor.rowcount
        cursor.execute(
            f"DELETE FROM files WHERE file_id IN ({file_ids_sql})",
            (group_id, group_id, group_id),
        )
        deleted_counts["files"] = cursor.rowcount
        cursor.execute(
            f"DELETE FROM file_topic_relations WHERE topic_id IN ({topic_ids_sql})",
            (group_id,),
        )
        deleted_counts["file_topic_relations"] = cursor.rowcount
        cursor.execute(
            f"DELETE FROM topic_files WHERE topic_id IN ({topic_ids_sql})",
            (group_id,),
        )
        deleted_counts["topic_files"] = cursor.rowcount
        conn.commit()
        return deleted_counts
    finally:
        conn.close()


@contextmanager
def _file_db(group_id: str) -> Iterator[ZSXQFileDatabase]:
    file_db = _open_file_db(group_id)
    try:
        yield file_db
    finally:
        file_db.close()


def _get_download_file_status(group_id: str, file_name: str, file_size: int, fallback: str) -> Dict[str, Any]:
    safe_filename = _safe_filename(file_name, fallback)
    download_dir = os.path.join(get_db_path_manager().get_group_dir(group_id), "downloads")
    file_path = os.path.join(download_dir, safe_filename)
    local_exists = os.path.exists(file_path)
    local_size = os.path.getsize(file_path) if local_exists else 0
    return {
        "safe_filename": safe_filename,
        "local_exists": local_exists,
        "local_size": local_size,
        "local_path": file_path if local_exists else None,
        "is_complete": local_exists and (file_size == 0 or local_size == file_size),
        "download_dir": download_dir,
    }


def _resolve_download_record_status(
    group_id: str,
    file_id: int,
    file_name: str,
    stored_status: Optional[str],
    stored_local_path: Optional[str],
) -> Dict[str, Any]:
    resolved_local_path = resolve_local_file_path(group_id, file_id, file_name, stored_local_path)
    local_exists = resolved_local_path is not None
    effective_local_path = str(resolved_local_path) if resolved_local_path else None
    return {
        "download_status": "completed" if local_exists else (stored_status or "unknown"),
        "local_exists": local_exists,
        "local_path": effective_local_path,
    }


def _build_file_status_response(
    file_id: int,
    result: Optional[tuple],
    local_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not result:
        return {
            "file_id": file_id,
            "name": f"file_{file_id}",
            "size": 0,
            "download_status": "not_collected",
            "local_exists": False,
            "local_size": 0,
            "local_path": None,
            "is_complete": False,
            "message": "文件信息未收集，请先运行文件收集任务",
        }

    file_name, file_size, download_status = result
    local_status = local_status or {}
    return {
        "file_id": file_id,
        "name": file_name,
        "size": file_size,
        "download_status": download_status or "pending",
        "local_exists": local_status["local_exists"],
        "local_size": local_status["local_size"],
        "local_path": local_status["local_path"],
        "is_complete": local_status["is_complete"],
    }


def _build_check_local_file_status_response(
    file_name: str,
    file_size: int,
    local_status: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "file_name": file_name,
        "safe_filename": local_status["safe_filename"],
        "expected_size": file_size,
        "local_exists": local_status["local_exists"],
        "local_size": local_status["local_size"],
        "local_path": local_status["local_path"],
        "is_complete": local_status["is_complete"],
        "download_dir": local_status["download_dir"],
    }


def _build_sync_files_response(group_id: str, stats: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "success": True,
        "group_id": group_id,
        "stats": stats,
    }


def _log_file_route_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _close_crawler_file_databases(crawler) -> None:
    downloader = crawler.get_file_downloader()
    if hasattr(downloader, "file_db") and downloader.file_db:
        downloader.file_db.close()
    if hasattr(crawler, "db") and crawler.db:
        crawler.db.close()


def _create_file_downloader(
    task_id: str,
    group_id: str,
    **kwargs,
) -> ZSXQFileDownloader:
    def log_callback(message: str):
        add_task_log(task_id, message)

    def stop_check():
        return is_task_stopped(task_id)

    cookie = get_cookie_for_group(group_id)
    downloader = ZSXQFileDownloader(cookie=cookie, group_id=group_id, **kwargs)
    downloader.log_callback = log_callback
    downloader.stop_check_func = stop_check
    file_downloader_instances[task_id] = downloader
    return downloader


def _remove_file_downloader(task_id: str) -> None:
    file_downloader_instances.pop(task_id, None)


def _enqueue_file_task(
    background_tasks: BackgroundTasks,
    task_type: str,
    description: str,
    task_func,
    *args,
    message: str = "任务已创建，正在后台执行",
    ingestion_group_id: Optional[str] = None,
) -> Dict[str, str]:
    if ingestion_group_id is not None:
        task_id, existing = create_ingestion_task(task_type, description, ingestion_group_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "该群组已有采集或同步任务正在运行",
                    "task_id": existing.get("task_id"),
                    "type": existing.get("type"),
                    "status": existing.get("status"),
                },
            )
    else:
        task_id = create_task(task_type, description)
    background_tasks.add_task(task_func, task_id, *args)
    return {"task_id": task_id, "message": message}


def run_collect_files_task(task_id: str, group_id: str, request: FileCollectRequest):
    """后台执行文件列表收集任务"""
    try:

        update_task(task_id, "running", "开始收集文件列表...")

        downloader = _create_file_downloader(task_id, group_id)

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        add_task_log(task_id, "📡 连接到知识星球API...")
        add_task_log(task_id, "📍 阶段一：收集文件列表")
        if request.start_time or request.end_time or request.last_days:
            add_task_log(
                task_id,
                f"📅 收集范围: {request.start_time or '-'} ~ {request.end_time or '-'}"
                if (request.start_time or request.end_time)
                else f"📅 收集最近天数: {request.last_days}天",
            )
            result = downloader.collect_files_for_date_range(
                start_date=request.start_time,
                end_date=request.end_time,
                last_days=request.last_days,
            )
        else:
            result = downloader.collect_incremental_files()

        if is_task_stopped(task_id):
            return

        add_task_log(task_id, "✅ 文件列表收集完成！")
        update_task(task_id, "completed", "文件列表收集完成", result)
    except Exception as e:
        try:
            if not is_task_stopped(task_id):
                add_task_log(task_id, f"❌ 文件列表收集失败: {str(e)}")
                update_task(task_id, "failed", f"文件列表收集失败: {str(e)}")
        except Exception:
            pass
    finally:
        try:
            _remove_file_downloader(task_id)
        except Exception:
            pass


def run_file_download_task(
    task_id: str,
    group_id: str,
    max_files: Optional[int],
    sort_by: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    last_days: Optional[int] = None,
    download_interval: float = 1.0,
    long_sleep_interval: float = 60.0,
    files_per_batch: int = 10,
    download_interval_min: Optional[float] = None,
    download_interval_max: Optional[float] = None,
    long_sleep_interval_min: Optional[float] = None,
    long_sleep_interval_max: Optional[float] = None,
):
    """后台执行文件下载任务"""
    try:

        update_task(task_id, "running", "开始文件下载...")

        downloader = _create_file_downloader(
            task_id,
            group_id,
            download_interval=download_interval,
            long_sleep_interval=long_sleep_interval,
            files_per_batch=files_per_batch,
            download_interval_min=download_interval_min,
            download_interval_max=download_interval_max,
            long_sleep_interval_min=long_sleep_interval_min,
            long_sleep_interval_max=long_sleep_interval_max,
        )

        add_task_log(task_id, "⚙️ 下载配置:")
        add_task_log(task_id, f"   ⏱️ 单次下载间隔: {download_interval}秒")
        add_task_log(task_id, f"   😴 长休眠间隔: {long_sleep_interval}秒")
        add_task_log(task_id, f"   📦 批次大小: {files_per_batch}个文件")
        if sort_by == "create_time":
            if start_time or end_time:
                add_task_log(task_id, f"   📅 下载区间: {start_time or '-'} ~ {end_time or '-'}")
            elif last_days:
                add_task_log(task_id, f"   📅 下载最近天数: {last_days}天")

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        add_task_log(task_id, "📡 连接到知识星球API...")
        downloader.file_db.cursor.execute("SELECT COUNT(*) FROM files")
        existing_files_count = downloader.file_db.cursor.fetchone()[0] or 0

        collect_result = None
        if existing_files_count == 0:
            add_task_log(task_id, "📍 阶段一：收集文件列表")
            add_task_log(task_id, "🔍 文件库为空，开始收集文件列表...")
            if sort_by == "create_time":
                collect_result = downloader.collect_files_for_date_range(
                    start_date=start_time,
                    end_date=end_time,
                    last_days=last_days,
                )
            else:
                collect_result = downloader.collect_incremental_files()
        else:
            add_task_log(task_id, f"📚 文件库已有 {existing_files_count} 条记录，跳过收集阶段，直接下载")

        if is_task_stopped(task_id):
            return

        if collect_result is not None:
            add_task_log(task_id, f"📊 文件收集完成: {collect_result}")
        add_task_log(task_id, "📍 阶段二：下载文件本体")
        add_task_log(task_id, "🚀 开始下载文件...")

        if sort_by == "download_count":
            result = downloader.download_files_from_database(
                max_files=max_files,
                status_filter="pending",
                sort_by="download_count",
            )
        else:
            result = downloader.download_files_from_database(
                max_files=max_files,
                status_filter="pending",
                sort_by="create_time",
                start_date=start_time,
                end_date=end_time,
                last_days=last_days,
            )

        if is_task_stopped(task_id):
            return

        add_task_log(task_id, "✅ 文件下载完成！")
        update_task(task_id, "completed", "文件下载完成", {"downloaded_files": result})
    except Exception as e:
        try:
            if not is_task_stopped(task_id):
                add_task_log(task_id, f"❌ 文件下载失败: {str(e)}")
                update_task(task_id, "failed", f"文件下载失败: {str(e)}")
        except Exception:
            pass
    finally:
        try:
            _remove_file_downloader(task_id)
        except Exception:
            pass


def run_single_file_download_task_with_info(
    task_id: str,
    group_id: str,
    file_id: int,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
):
    """运行单个文件下载任务（带文件信息）"""
    try:

        update_task(task_id, "running", f"开始下载文件 (ID: {file_id})...")

        downloader = _create_file_downloader(task_id, group_id)

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        if file_name and file_size:
            add_task_log(task_id, f"📄 使用提供的文件信息: {file_name} ({file_size} bytes)")
            file_info = {
                "file": {
                    "id": file_id,
                    "name": file_name,
                    "size": file_size,
                    "download_count": 0,
                }
            }
        else:
            downloader.file_db.cursor.execute(
                """
                SELECT file_id, name, size, download_count
                FROM files
                WHERE file_id = ?
            """,
                (file_id,),
            )

            result = downloader.file_db.cursor.fetchone()
            if result:
                _, db_file_name, db_file_size, download_count = result
                add_task_log(task_id, f"📄 从数据库获取文件信息: {db_file_name} ({db_file_size} bytes)")
                file_info = {
                    "file": {
                        "id": file_id,
                        "name": db_file_name,
                        "size": db_file_size,
                        "download_count": download_count,
                    }
                }
            else:
                add_task_log(task_id, f"📄 直接下载文件 ID: {file_id}")
                file_info = {
                    "file": {
                        "id": file_id,
                        "name": f"file_{file_id}",
                        "size": 0,
                        "download_count": 0,
                    }
                }

        result = downloader.download_file(file_info)

        if result == "skipped":
            add_task_log(task_id, "✅ 文件已存在，跳过下载")
            update_task(task_id, "completed", "文件已存在")
        elif result:
            add_task_log(task_id, "✅ 文件下载成功")

            actual_file_info = file_info["file"]
            actual_file_name = actual_file_info.get("name", f"file_{file_id}")
            actual_file_size = actual_file_info.get("size", 0)

            safe_filename = _safe_filename(actual_file_name, f"file_{file_id}")
            local_path = os.path.join(downloader.download_dir, safe_filename)

            if os.path.exists(local_path):
                actual_file_size = os.path.getsize(local_path)

            downloader.file_db.cursor.execute(
                """
                INSERT OR REPLACE INTO files
                (file_id, name, size, download_status, local_path, download_time, download_count)
                VALUES (?, ?, ?, 'downloaded', ?, CURRENT_TIMESTAMP, ?)
            """,
                (
                    file_id,
                    actual_file_name,
                    actual_file_size,
                    local_path,
                    actual_file_info.get("download_count", 0),
                ),
            )
            downloader.file_db.conn.commit()

            update_task(task_id, "completed", "下载成功")
        else:
            add_task_log(task_id, "❌ 文件下载失败")
            update_task(task_id, "failed", "下载失败")
    except Exception as e:
        try:
            if not is_task_stopped(task_id):
                add_task_log(task_id, f"❌ 任务执行失败: {str(e)}")
                update_task(task_id, "failed", f"任务失败: {str(e)}")
        except Exception:
            pass
    finally:
        try:
            _remove_file_downloader(task_id)
        except Exception:
            pass


@router.post("/collect/{group_id}")
async def collect_files(group_id: str, request: FileCollectRequest, background_tasks: BackgroundTasks):
    """收集文件列表"""
    try:
        return _enqueue_file_task(
            background_tasks,
            "collect_files",
            "收集文件列表",
            run_collect_files_task,
            group_id,
            request,
            ingestion_group_id=group_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建文件收集任务失败: {str(e)}")


@router.post("/download/{group_id}")
async def download_files(group_id: str, request: FileDownloadRequest, background_tasks: BackgroundTasks):
    """下载文件"""
    try:
        return _enqueue_file_task(
            background_tasks,
            "download_files",
            f"下载文件 (排序: {request.sort_by})",
            run_file_download_task,
            group_id,
            request.max_files,
            request.sort_by,
            request.start_time,
            request.end_time,
            request.last_days,
            request.download_interval,
            request.long_sleep_interval,
            request.files_per_batch,
            request.download_interval_min,
            request.download_interval_max,
            request.long_sleep_interval_min,
            request.long_sleep_interval_max,
            ingestion_group_id=group_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建文件下载任务失败: {str(e)}")


@router.post("/download-single/{group_id}/{file_id}")
async def download_single_file(
    group_id: str,
    file_id: int,
    background_tasks: BackgroundTasks,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
):
    """下载单个文件"""
    try:
        return _enqueue_file_task(
            background_tasks,
            "download_single_file",
            f"下载单个文件 (ID: {file_id})",
            run_single_file_download_task_with_info,
            group_id,
            file_id,
            file_name,
            file_size,
            message="单个文件下载任务已创建",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建单个文件下载任务失败: {str(e)}")


@router.get("/status/{group_id}/{file_id}")
async def get_file_status(group_id: str, file_id: int):
    """获取文件下载状态"""
    try:
        with _file_db(group_id) as file_db:
            file_db.cursor.execute(
                """
                SELECT name, size, download_status
                FROM files
                WHERE file_id = ?
            """,
                (file_id,),
            )

            result = file_db.cursor.fetchone()

            if not result:
                return _build_file_status_response(file_id, result)

            file_name, file_size, download_status = result

            local_status = _get_download_file_status(group_id, file_name, file_size, f"file_{file_id}")
            return _build_file_status_response(file_id, result, local_status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件状态失败: {str(e)}")


@router.get("/check-local/{group_id}")
async def check_local_file_status(group_id: str, file_name: str, file_size: int):
    """检查本地文件状态（不依赖数据库）"""
    try:
        local_status = _get_download_file_status(group_id, file_name, file_size, file_name)
        return _build_check_local_file_status_response(file_name, file_size, local_status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查本地文件失败: {str(e)}")


@router.get("/analysis/{group_id}/{file_id}")
async def get_file_analysis(group_id: str, file_id: int):
    """获取文件 AI 分析缓存"""
    try:
        result = await asyncio.to_thread(get_group_file_analysis, group_id, file_id)
        return {"analysis": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件 AI 分析失败: {str(e)}")


@router.post("/analysis/{group_id}/{file_id}")
async def create_file_analysis(group_id: str, file_id: int, request: FileAIAnalysisRequest):
    """分析文件内容并生成 AI 摘要"""
    try:
        if not has_openai_api_key():
            raise HTTPException(
                status_code=400,
                detail="未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key",
            )

        result = await asyncio.to_thread(
            analyze_group_file,
            group_id,
            file_id,
            force=request.force,
            model=A_SHARE_DEFAULT_MODEL,
            api_base=A_SHARE_DEFAULT_API_BASE,
            wire_api=A_SHARE_DEFAULT_WIRE_API,
            reasoning_effort=DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
        )
        return {"analysis": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件 AI 分析失败: {str(e)}")


@router.get("/stats/{group_id}")
async def get_file_stats(group_id: str):
    """获取指定群组的文件统计信息"""
    try:
        with _file_db(group_id) as file_db:
            stats = file_db.get_database_stats()

            file_db.cursor.execute("PRAGMA table_info(files)")
            columns = [col[1] for col in file_db.cursor.fetchall()]

            if "download_status" in columns:
                file_db.cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total_files,
                        COUNT(CASE WHEN download_status IN ('completed', 'downloaded', 'skipped') THEN 1 END) as downloaded,
                        COUNT(CASE WHEN download_status = 'pending' THEN 1 END) as pending,
                        COUNT(CASE WHEN download_status = 'failed' THEN 1 END) as failed
                    FROM files
                """
                )
                download_stats = file_db.cursor.fetchone()
            else:
                file_db.cursor.execute("SELECT COUNT(*) FROM files")
                total_files = file_db.cursor.fetchone()[0]
                download_stats = (total_files, 0, 0, 0)

            return {
                "database_stats": stats,
                "download_stats": {
                    "total_files": download_stats[0] if download_stats else 0,
                    "downloaded": download_stats[1] if download_stats else 0,
                    "pending": download_stats[2] if download_stats else 0,
                    "failed": download_stats[3] if download_stats else 0,
                },
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件统计失败: {str(e)}")


@router.post("/clear/{group_id}")
async def clear_file_database(group_id: str):
    """删除指定群组的 PostgreSQL 文件数据"""
    try:
        try:
            crawler = get_crawler_for_group(group_id)
            _close_crawler_file_databases(crawler)
            _log_file_route_event("INFO", "已关闭爬虫实例的数据库连接")
        except Exception as e:
            _log_file_route_event("WARN", f"关闭爬虫数据库连接时出错: {e}")

        gc.collect()
        time.sleep(0.1)
        deleted_counts = _clear_group_file_data(group_id)

        try:
            from backend.core.image_cache_manager import clear_group_cache_manager, get_image_cache_manager

            cache_manager = get_image_cache_manager(group_id)
            success, message = cache_manager.clear_cache()
            if success:
                _log_file_route_event("INFO", f"图片缓存已清空: {message}")
            else:
                _log_file_route_event("WARN", f"清空图片缓存失败: {message}")
            clear_group_cache_manager(group_id)
        except Exception as cache_error:
            _log_file_route_event("WARN", f"清空图片缓存时出错: {cache_error}")

        return {"message": f"群组 {group_id} 的文件数据和图片缓存已删除", "deleted": deleted_counts}
    except HTTPException:
        raise
    except Exception as e:
        _log_file_route_event("ERROR", f"删除文件数据库失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除文件数据库失败: {str(e)}")


@router.post("/sync-from-topics/{group_id}")
async def sync_files_from_topics(group_id: str):
    """从话题库 topic_files 回填/重建文件库记录。"""
    topics_db = None
    task_id = None
    try:
        task_id, existing = create_ingestion_task("sync_files_from_topics", f"从话题同步文件记录 (群组: {group_id})", group_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "该群组已有采集或同步任务正在运行",
                    "task_id": existing.get("task_id"),
                    "type": existing.get("type"),
                    "status": existing.get("status"),
                },
            )
        update_task(task_id, "running", "开始从话题同步文件记录...")
        topics_db = ZSXQDatabase(group_id)
        stats = topics_db.backfill_topic_files_to_file_database()
        update_task(task_id, "completed", "从话题同步文件记录完成", stats)
        return _build_sync_files_response(group_id, stats)
    except HTTPException:
        if task_id:
            update_task(task_id, "failed", "从话题同步文件记录失败")
        raise
    except Exception as e:
        if task_id:
            update_task(task_id, "failed", f"从话题同步文件记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"同步文件记录失败: {str(e)}")
    finally:
        if topics_db:
            try:
                topics_db.close()
            except Exception:
                pass


@router.get("/{group_id}")
async def get_files(
    group_id: str,
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """获取指定群组的文件列表"""
    try:
        with _file_db(group_id) as file_db:
            offset = (page - 1) * per_page

            conditions = []
            params_prefix = []

            if status:
                if status == "completed":
                    conditions.append("f.download_status IN (?, ?, ?)")
                    params_prefix.extend(["completed", "downloaded", "skipped"])
                else:
                    conditions.append("f.download_status = ?")
                    params_prefix.append(status)

            search_text = (search or "").strip()
            if search_text:
                conditions.append("f.name LIKE ?")
                params_prefix.append(f"%{search_text}%")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            query = f"""
                SELECT
                    f.file_id,
                    f.name,
                    f.size,
                    f.download_count,
                    f.create_time,
                    f.download_status,
                    f.local_path,
                    faa.updated_at
                FROM files f
                LEFT JOIN file_ai_analyses faa ON faa.file_id = f.file_id
                {where_clause}
                ORDER BY f.create_time DESC
                LIMIT ? OFFSET ?
            """
            params = (*params_prefix, per_page, offset)

            file_db.cursor.execute(query, params)
            files = file_db.cursor.fetchall()

            count_query = f"SELECT COUNT(*) FROM files f {where_clause}"
            file_db.cursor.execute(count_query, tuple(params_prefix))
            total = file_db.cursor.fetchone()[0]

            normalized_files = []
            for file in files:
                file_id = file[0]
                file_name = file[1]
                file_size = file[2]
                stored_status = file[5] if len(file) > 5 else "unknown"
                stored_local_path = file[6] if len(file) > 6 else None

                local_status = _resolve_download_record_status(
                    group_id,
                    file_id,
                    file_name,
                    stored_status,
                    stored_local_path,
                )

                if local_status["local_exists"] and (
                    stored_status != "completed"
                    or str(stored_local_path or "").strip() != local_status["local_path"]
                ):
                    file_db.update_file_download_status(file_id, "completed", local_status["local_path"])

                normalized_files.append(
                    {
                        "file_id": file_id,
                        "name": file_name,
                        "size": file_size,
                        "download_count": file[3],
                        "create_time": file[4],
                        "download_status": local_status["download_status"],
                        "local_exists": local_status["local_exists"],
                        "local_path": local_status["local_path"],
                        "has_ai_analysis": bool(file[7]) if len(file) > 7 and file[7] else False,
                        "analysis_updated_at": file[7] if len(file) > 7 else None,
                    }
                )

            return {
                "files": normalized_files,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "pages": (total + per_page - 1) // per_page,
                },
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")
