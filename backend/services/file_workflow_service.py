from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional, Sequence

from fastapi import BackgroundTasks

from backend.core.account_context import get_cookie_for_group
from backend.core.db_path_manager import get_db_path_manager
from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.routes.ingestion_helpers import create_ingestion_task_or_raise
from backend.schemas.files import FileCollectRequest
from backend.services.file_ai_analysis_service import (
    DEFAULT_FILE_ANALYSIS_API_BASE,
    DEFAULT_FILE_ANALYSIS_MODEL,
    DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    DEFAULT_FILE_ANALYSIS_WIRE_API,
    analyze_group_file,
    resolve_local_file_path,
)
from backend.services.task_runtime import (
    add_task_log,
    create_task,
    enqueue_runtime_task,
    file_downloader_instances,
    is_task_stopped,
    update_task,
)
from backend.storage.db_compat import connect
from backend.storage.zsxq_database import ZSXQDatabase
from backend.storage.zsxq_file_database import ZSXQFileDatabase


def _safe_filename(file_name: str, fallback: str) -> str:
    safe = "".join(c for c in file_name if c.isalnum() or c in "._-（）()[]{}")
    return safe or fallback


def _open_file_db(group_id: str) -> ZSXQFileDatabase:
    return ZSXQFileDatabase(group_id)


def _query_group_id(group_id: str) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


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


def _build_download_task_stats(total_files: int, found: int, missing: int = 0) -> Dict[str, int]:
    return {
        "total_files": int(total_files),
        "found": int(found),
        "missing": int(missing),
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
    }


def _build_download_file_info(
    file_id: int,
    file_name: str,
    file_size: int,
    download_count: int = 0,
) -> Dict[str, Dict[str, Any]]:
    return {
        "file": {
            "id": file_id,
            "name": file_name,
            "size": file_size,
            "download_count": download_count,
        }
    }


def _download_result_stat_key(result: Any) -> str:
    if result == "skipped":
        return "skipped"
    if result:
        return "downloaded"
    return "failed"


def _get_file_status_response(group_id: str, file_id: int) -> dict:
    with _file_db(group_id) as file_db:
        file_db.cursor.execute(
            """
            SELECT name, size, download_status
            FROM files
            WHERE file_id = ? AND group_id = ?
        """,
            (file_id, _query_group_id(group_id)),
        )

        result = file_db.cursor.fetchone()

        if not result:
            return _build_file_status_response(file_id, result)

        file_name, file_size, _download_status = result
        local_status = _get_download_file_status(group_id, file_name, file_size, f"file_{file_id}")
        return _build_file_status_response(file_id, result, local_status)


def _check_local_file_status_response(group_id: str, file_name: str, file_size: int) -> dict:
    local_status = _get_download_file_status(group_id, file_name, file_size, file_name)
    return _build_check_local_file_status_response(file_name, file_size, local_status)


def _get_file_stats_response(group_id: str) -> dict:
    with _file_db(group_id) as file_db:
        stats = file_db.get_database_stats()

        file_db.cursor.execute(
            """
            SELECT
                COUNT(*) as total_files,
                COUNT(CASE WHEN download_status IN ('completed', 'downloaded', 'skipped') THEN 1 END) as downloaded,
                COUNT(CASE WHEN download_status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN download_status = 'failed' THEN 1 END) as failed
            FROM files
            WHERE group_id = ?
            """,
            (_query_group_id(group_id),),
        )
        download_stats = file_db.cursor.fetchone()

        return {
            "database_stats": stats,
            "download_stats": {
                "total_files": download_stats[0] if download_stats else 0,
                "downloaded": download_stats[1] if download_stats else 0,
                "pending": download_stats[2] if download_stats else 0,
                "failed": download_stats[3] if download_stats else 0,
            },
        }


def _clear_file_database_response(group_id: str) -> dict:
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


_FILES_FROM_CLAUSE = """
            FROM files f
            LEFT JOIN file_ai_analyses faa ON faa.file_id = f.file_id
        """


def _build_file_list_filters(
    group_id: str,
    status: Optional[str],
    search: Optional[str],
    analysis_status: Optional[str],
) -> tuple[str, list[Any]]:
    conditions = []
    params_prefix = [_query_group_id(group_id)]
    conditions.append("f.group_id = ?")

    if status:
        if status == "completed":
            conditions.append("f.download_status IN (?, ?, ?)")
            params_prefix.extend(["completed", "downloaded", "skipped"])
        else:
            conditions.append("f.download_status = ?")
            params_prefix.append(status)

    if analysis_status == "analyzed":
        conditions.append("faa.updated_at IS NOT NULL")
    elif analysis_status == "pending":
        conditions.append("faa.updated_at IS NULL")

    _add_file_search_condition(conditions, params_prefix, search)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, params_prefix


def _build_file_list_query(where_clause: str) -> str:
    return f"""
            SELECT
                f.file_id,
                f.name,
                f.size,
                f.download_count,
                f.create_time,
                f.download_status,
                f.local_path,
                f.download_error_code,
                f.download_error_message,
                f.last_download_attempt_at,
                faa.updated_at
            {_FILES_FROM_CLAUSE}
            {where_clause}
            ORDER BY f.create_time DESC
            LIMIT ? OFFSET ?
        """


def _build_file_count_query(where_clause: str) -> str:
    return f"SELECT COUNT(*) {_FILES_FROM_CLAUSE} {where_clause}"


def _normalize_file_list_row(group_id: str, file: Sequence[Any]) -> Dict[str, Any]:
    file_id = file[0]
    file_name = file[1]
    stored_status = file[5] if len(file) > 5 else "unknown"
    stored_local_path = file[6] if len(file) > 6 else None

    local_status = _resolve_download_record_status(
        group_id,
        file_id,
        file_name,
        stored_status,
        stored_local_path,
    )

    return {
        "file_id": file_id,
        "name": file_name,
        "size": file[2],
        "download_count": file[3],
        "create_time": file[4],
        "download_status": local_status["download_status"],
        "local_exists": local_status["local_exists"],
        "local_path": local_status["local_path"],
        "download_error_code": file[7] if len(file) > 7 else None,
        "download_error_message": file[8] if len(file) > 8 else None,
        "last_download_attempt_at": file[9] if len(file) > 9 else None,
        "has_ai_analysis": bool(file[10]) if len(file) > 10 and file[10] else False,
        "analysis_updated_at": file[10] if len(file) > 10 else None,
    }


def _build_file_list_response(
    group_id: str,
    files: Sequence[Sequence[Any]],
    total: int,
    page: int,
    per_page: int,
) -> Dict[str, Any]:
    return {
        "files": [_normalize_file_list_row(group_id, file) for file in files],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    }


def _get_files_response(
    group_id: str,
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    analysis_status: Optional[str] = None,
) -> dict:
    with _file_db(group_id) as file_db:
        offset = (page - 1) * per_page
        where_clause, params_prefix = _build_file_list_filters(group_id, status, search, analysis_status)
        query = _build_file_list_query(where_clause)
        params = (*params_prefix, per_page, offset)

        file_db.cursor.execute(query, params)
        files = file_db.cursor.fetchall()

        count_query = _build_file_count_query(where_clause)
        file_db.cursor.execute(count_query, tuple(params_prefix))
        total = file_db.cursor.fetchone()[0]

        return _build_file_list_response(group_id, files, total, page, per_page)


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


def _safe_remove_file_downloader(task_id: str) -> None:
    try:
        _remove_file_downloader(task_id)
    except Exception:
        pass


def _close_quietly(resource: Any) -> None:
    if not resource:
        return
    try:
        resource.close()
    except Exception:
        pass


def _rollback_downloader_file_db(downloader: Optional[ZSXQFileDownloader]) -> None:
    try:
        if downloader and getattr(downloader, "file_db", None):
            downloader.file_db.conn.rollback()
    except Exception:
        pass


def _fail_file_task(
    task_id: str,
    log_message: str,
    task_message: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        if is_task_stopped(task_id):
            return
        add_task_log(task_id, f"❌ {log_message}")
        if result is None:
            update_task(task_id, "failed", task_message)
        else:
            update_task(task_id, "failed", task_message, result)
    except Exception:
        pass


def _enqueue_file_task(
    background_tasks: BackgroundTasks,
    task_type: str,
    description: str,
    task_func,
    *args,
    message: str = "任务已创建，正在后台执行",
    ingestion_group_id: Optional[str] = None,
    task_group_id: Optional[str] = None,
) -> Dict[str, str]:
    if ingestion_group_id is not None:
        task_id = create_ingestion_task_or_raise(task_type, description, ingestion_group_id)
    else:
        metadata = {"group_id": str(task_group_id)} if task_group_id is not None else None
        task_id = create_task(task_type, description, metadata=metadata) if metadata else create_task(task_type, description)
    enqueue_runtime_task(task_func, task_id, *args)
    return {"task_id": task_id, "message": message}


def run_collect_files_task(task_id: str, group_id: str, request: FileCollectRequest):
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
        _fail_file_task(task_id, f"文件列表收集失败: {e}", f"文件列表收集失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)


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
        downloader.file_db.cursor.execute("SELECT COUNT(*) FROM files WHERE group_id = ?", (_query_group_id(group_id),))
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
        _fail_file_task(task_id, f"文件下载失败: {e}", f"文件下载失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)


def _load_download_file_records(
    downloader: ZSXQFileDownloader,
    group_id: str,
    file_ids: Sequence[int],
) -> tuple[list[tuple[int, str, int, int]], list[int]]:
    ordered_ids = [int(file_id) for file_id in dict.fromkeys(file_ids)]
    placeholders = ", ".join("?" for _ in ordered_ids)
    downloader.file_db.cursor.execute(
        f"""
        SELECT file_id, name, size, download_count
        FROM files
        WHERE group_id = ? AND file_id IN ({placeholders})
        """,
        (_query_group_id(group_id), *ordered_ids),
    )
    rows = downloader.file_db.cursor.fetchall()
    by_file_id = {int(row[0]): row for row in rows}
    records = [
        (
            int(row[0]),
            str(row[1] or f"file_{int(row[0])}"),
            int(row[2] or 0),
            int(row[3] or 0),
        )
        for row in (by_file_id[file_id] for file_id in ordered_ids if file_id in by_file_id)
    ]
    missing = [file_id for file_id in ordered_ids if file_id not in by_file_id]
    return records, missing


def _add_file_search_condition(conditions: list[str], params: list[Any], search: Optional[str]) -> None:
    search_text = (search or "").strip()
    if not search_text:
        return

    search_pattern = f"%{search_text.lower()}%"
    conditions.append(
        """
        (
            LOWER(COALESCE(f.name, '')) LIKE ?
            OR EXISTS (
                SELECT 1
                FROM file_topic_relations fr
                LEFT JOIN topics t ON t.topic_id = fr.topic_id
                LEFT JOIN talks tk ON tk.topic_id = fr.topic_id
                LEFT JOIN articles ar ON ar.topic_id = fr.topic_id
                WHERE fr.file_id = f.file_id
                  AND (
                      LOWER(COALESCE(t.title, '')) LIKE ?
                      OR LOWER(COALESCE(t.annotation, '')) LIKE ?
                      OR LOWER(COALESCE(tk.text, '')) LIKE ?
                      OR LOWER(COALESCE(ar.title, '')) LIKE ?
                  )
            )
            OR EXISTS (
                SELECT 1
                FROM topic_files tf
                LEFT JOIN topics t2 ON t2.topic_id = tf.topic_id
                WHERE tf.file_id = f.file_id
                  AND (
                      LOWER(COALESCE(tf.name, '')) LIKE ?
                      OR LOWER(COALESCE(t2.title, '')) LIKE ?
                      OR LOWER(COALESCE(t2.annotation, '')) LIKE ?
                  )
            )
        )
        """
    )
    params.extend([search_pattern] * 8)


def _load_filtered_download_file_records(
    downloader: ZSXQFileDownloader,
    group_id: str,
    *,
    status: Optional[str] = None,
    search: Optional[str] = None,
    max_files: Optional[int] = None,
) -> list[tuple[int, str, int, int]]:
    conditions = ["f.group_id = ?"]
    params: list[Any] = [_query_group_id(group_id)]
    requested_status = str(status or "").strip()
    if requested_status and requested_status != "all":
        if requested_status == "completed":
            conditions.append("f.download_status IN (?, ?, ?)")
            params.extend(["completed", "downloaded", "skipped"])
        else:
            conditions.append("f.download_status = ?")
            params.append(requested_status)
    else:
        conditions.append("(f.download_status IS NULL OR f.download_status NOT IN (?, ?, ?))")
        params.extend(["completed", "downloaded", "skipped"])

    _add_file_search_condition(conditions, params, search)
    limit_clause = "LIMIT ?" if max_files else ""
    if max_files:
        params.append(int(max_files))

    downloader.file_db.cursor.execute(
        f"""
        SELECT f.file_id, f.name, f.size, f.download_count
        FROM files f
        WHERE {' AND '.join(conditions)}
        ORDER BY f.create_time DESC, f.download_count DESC
        {limit_clause}
        """,
        tuple(params),
    )
    rows = downloader.file_db.cursor.fetchall()
    return [
        (
            int(row[0]),
            str(row[1] or f"file_{int(row[0])}"),
            int(row[2] or 0),
            int(row[3] or 0),
        )
        for row in rows
    ]


def _run_download_records(
    task_id: str,
    downloader: ZSXQFileDownloader,
    records: Sequence[tuple[int, str, int, int]],
    stats: Dict[str, int],
) -> Dict[str, int]:
    for index, (file_id, file_name, file_size, download_count) in enumerate(records, 1):
        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 下载任务被停止")
            return stats

        add_task_log(task_id, f"【{index}/{len(records)}】{file_name}")
        result = downloader.download_file(
            _build_download_file_info(file_id, file_name, file_size, download_count)
        )
        stats[_download_result_stat_key(result)] += 1
    return stats


def run_selected_file_download_task(task_id: str, group_id: str, file_ids: Sequence[int]):
    try:
        update_task(task_id, "running", f"开始下载选中的 {len(file_ids)} 个文件...")
        downloader = _create_file_downloader(task_id, group_id)

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        records, missing = _load_download_file_records(downloader, group_id, file_ids)
        stats = _build_download_task_stats(
            total_files=len(dict.fromkeys(int(file_id) for file_id in file_ids)),
            found=len(records),
            missing=len(missing),
        )
        if missing:
            add_task_log(task_id, f"⚠️ {len(missing)} 个文件未在文件库中找到，已跳过")
        if not records:
            update_task(task_id, "completed", "没有可下载的文件记录", {"downloaded_files": stats})
            return

        _run_download_records(task_id, downloader, records, stats)
        if is_task_stopped(task_id):
            return

        update_task(task_id, "completed", "选中文件下载完成", {"downloaded_files": stats})
    except Exception as e:
        _fail_file_task(task_id, f"选中文件下载失败: {e}", f"选中文件下载失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)


def run_filtered_file_download_task(
    task_id: str,
    group_id: str,
    status: Optional[str] = None,
    search: Optional[str] = None,
    max_files: Optional[int] = None,
):
    try:
        update_task(task_id, "running", "开始下载当前筛选结果...")
        downloader = _create_file_downloader(task_id, group_id)

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        records = _load_filtered_download_file_records(
            downloader,
            group_id,
            status=status,
            search=search,
            max_files=max_files,
        )
        stats = _build_download_task_stats(total_files=len(records), found=len(records))
        if not records:
            update_task(task_id, "completed", "当前筛选下没有可下载文件", {"downloaded_files": stats})
            return

        _run_download_records(task_id, downloader, records, stats)
        if is_task_stopped(task_id):
            return
        update_task(task_id, "completed", "筛选结果下载完成", {"downloaded_files": stats})
    except Exception as e:
        _fail_file_task(task_id, f"筛选结果下载失败: {e}", f"筛选结果下载失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)


def run_single_file_download_task_with_info(
    task_id: str,
    group_id: str,
    file_id: int,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
):
    downloader = None
    try:
        update_task(task_id, "running", f"开始下载文件 (ID: {file_id})...")
        downloader = _create_file_downloader(task_id, group_id)

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        downloader.file_db.cursor.execute(
            """
            SELECT file_id, name, size, download_count
            FROM files
            WHERE file_id = ? AND group_id = ?
            """,
            (file_id, _query_group_id(group_id)),
        )

        result = downloader.file_db.cursor.fetchone()
        if result:
            _, db_file_name, db_file_size, download_count = result
            add_task_log(task_id, f"📄 从数据库获取文件信息: {db_file_name} ({db_file_size} bytes)")
            file_info = _build_download_file_info(file_id, db_file_name, db_file_size, download_count)
        elif file_name and file_size is not None:
            add_task_log(task_id, f"📄 文件库未命中，使用请求中的文件信息: {file_name} ({file_size} bytes)")
            file_info = _build_download_file_info(file_id, file_name, file_size)
        else:
            add_task_log(task_id, f"📄 直接下载文件 ID: {file_id}")
            file_info = _build_download_file_info(file_id, f"file_{file_id}", 0)

        result = downloader.download_file(file_info)

        if result == "skipped":
            add_task_log(task_id, "✅ 文件已存在，跳过下载")
            update_task(task_id, "completed", "文件已存在")
        elif result:
            add_task_log(task_id, "✅ 文件下载成功")
            actual_file_info = file_info["file"]
            actual_file_name = actual_file_info.get("name", f"file_{file_id}")
            safe_filename = _safe_filename(actual_file_name, f"file_{file_id}")
            local_path = os.path.join(downloader.download_dir, safe_filename)
            downloader.file_db.update_file_download_status(file_id, "completed", local_path)
            update_task(task_id, "completed", "下载成功")
        else:
            add_task_log(task_id, "❌ 文件下载失败")
            update_task(task_id, "failed", "下载失败")
    except Exception as e:
        _rollback_downloader_file_db(downloader)
        _fail_file_task(task_id, f"任务执行失败: {e}", f"任务失败: {e}")
    finally:
        _safe_remove_file_downloader(task_id)


def run_sync_files_from_topics_task(task_id: str, group_id: str):
    topics_db = None
    try:
        update_task(task_id, "running", "开始从话题同步文件记录...")
        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        topics_db = ZSXQDatabase(group_id)
        stats = topics_db.backfill_topic_files_to_file_database()
        if is_task_stopped(task_id):
            return

        update_task(task_id, "completed", "从话题同步文件记录完成", stats)
    except Exception as e:
        _fail_file_task(task_id, f"从话题同步文件记录失败: {e}", f"从话题同步文件记录失败: {e}")
    finally:
        _close_quietly(topics_db)


def run_file_analysis_task(
    task_id: str,
    group_id: str,
    file_ids: Sequence[int],
    force: bool = False,
):
    unique_file_ids = [int(file_id) for file_id in dict.fromkeys(file_ids)]
    stats = {
        "total_files": len(unique_file_ids),
        "completed": 0,
        "cached": 0,
        "failed": 0,
    }
    try:
        update_task(task_id, "running", f"开始分析 {len(unique_file_ids)} 个文件...")
        for index, file_id in enumerate(unique_file_ids, 1):
            if is_task_stopped(task_id):
                add_task_log(task_id, "🛑 文件分析任务被停止")
                return

            try:
                add_task_log(task_id, f"【{index}/{len(unique_file_ids)}】分析文件 ID: {file_id}")
                result = analyze_group_file(
                    group_id,
                    file_id,
                    force=force,
                    model=DEFAULT_FILE_ANALYSIS_MODEL,
                    api_base=DEFAULT_FILE_ANALYSIS_API_BASE,
                    wire_api=DEFAULT_FILE_ANALYSIS_WIRE_API,
                    reasoning_effort=DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
                )
                if result.get("cached"):
                    stats["cached"] += 1
                else:
                    stats["completed"] += 1
                add_task_log(task_id, f"✅ 文件分析完成: {file_id}")
            except Exception as exc:
                stats["failed"] += 1
                add_task_log(task_id, f"❌ 文件分析失败: {file_id}, {exc}")

        if stats["failed"] and stats["completed"] == 0 and stats["cached"] == 0:
            update_task(task_id, "failed", "文件分析全部失败", {"analysis": stats})
            return
        update_task(task_id, "completed", "文件分析完成", {"analysis": stats})
    except Exception as e:
        _fail_file_task(task_id, f"文件分析任务失败: {e}", f"文件分析任务失败: {e}", {"analysis": stats})
