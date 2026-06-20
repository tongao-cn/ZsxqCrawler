from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from backend.services.file_analysis_workflow import run_file_analysis_task
from backend.services.file_clear_workflow import (
    _clear_file_database_response,
    _clear_group_file_data,
    _clear_group_image_cache,
)
from backend.services.file_collect_workflow import (
    _collect_files_for_request,
    _complete_collect_files_task,
    run_collect_files_task,
)
from backend.services.file_download_workflow import (
    _build_file_download_options,
    _build_file_download_range_log,
    _collect_files_for_download,
    _complete_file_download_task,
    _count_existing_file_records,
    _download_prepared_files,
    _log_file_download_config,
    _prepare_files_for_download,
    run_file_download_task,
)
from backend.services.file_download_records_workflow import (
    _add_file_download_status_condition,
    _add_file_search_condition,
    _build_download_file_info,
    _build_download_task_stats,
    _build_filtered_download_file_records_query,
    _build_selected_download_file_records_query,
    _complete_download_records_task,
    _download_result_stat_key,
    _fetch_download_file_rows,
    _load_download_file_records,
    _load_filtered_download_file_records,
    _normalize_download_file_record,
    _query_group_id,
    _run_download_records,
    _unique_int_file_ids,
    run_filtered_file_download_task,
    run_selected_file_download_task,
)
from backend.services.file_downloader_runtime import (
    _create_file_downloader,
    _safe_remove_file_downloader,
)
from backend.services.file_single_download_workflow import (
    _build_single_download_fallback_info,
    _complete_failed_single_file_download,
    _complete_single_file_download,
    _complete_skipped_single_file_download,
    _complete_successful_single_file_download,
    _download_and_complete_single_file,
    _fetch_single_download_file_record,
    _resolve_single_download_file_info,
    _single_file_download_local_path,
    run_single_file_download_task_with_info,
)
from backend.services.file_status_service import (
    _build_check_local_file_status_response,
    _build_file_stats_response,
    _build_file_status_response,
    _build_sync_files_response,
    _check_local_file_status_response,
    _file_db,
    _get_download_file_status,
    _get_file_stats_response,
    _get_file_status_response,
    _open_file_db,
    _resolve_download_record_status,
    _safe_filename,
)
from backend.services.file_topic_sync_workflow import (
    _complete_sync_files_from_topics_task,
    run_sync_files_from_topics_task,
)
from backend.services.task_launch import launch_ingestion_task, launch_task
from backend.services.task_runtime import (
    add_task_log,
    is_task_stopped,
    update_task,
)
from backend.storage.zsxq_file_database import ZSXQFileDatabase


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

    _add_file_download_status_condition(conditions, params_prefix, status)

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


def _fetch_file_list_page(
    file_db: ZSXQFileDatabase,
    where_clause: str,
    params_prefix: Sequence[Any],
    per_page: int,
    offset: int,
) -> tuple[Sequence[Sequence[Any]], int]:
    query = _build_file_list_query(where_clause)
    params = (*params_prefix, per_page, offset)

    file_db.cursor.execute(query, params)
    files = file_db.cursor.fetchall()

    count_query = _build_file_count_query(where_clause)
    file_db.cursor.execute(count_query, tuple(params_prefix))
    total = file_db.cursor.fetchone()[0]
    return files, total


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
        files, total = _fetch_file_list_page(file_db, where_clause, params_prefix, per_page, offset)
        return _build_file_list_response(group_id, files, total, page, per_page)


def _log_file_route_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _close_crawler_file_databases(crawler) -> None:
    downloader = crawler.get_file_downloader()
    if hasattr(downloader, "file_db") and downloader.file_db:
        downloader.file_db.close()
    if hasattr(crawler, "db") and crawler.db:
        crawler.db.close()


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
    _background_tasks: Any,
    task_type: str,
    description: str,
    task_func,
    *args,
    message: str = "任务已创建，正在后台执行",
    ingestion_group_id: Optional[str] = None,
    task_group_id: Optional[str] = None,
) -> Dict[str, str]:
    if ingestion_group_id is not None:
        return launch_ingestion_task(
            task_type,
            description,
            task_func,
            ingestion_group_id,
            *args,
            message=message,
            prepend_group_id_to_args=False,
        )
    return launch_task(
        task_type,
        description,
        task_func,
        *args,
        group_id=task_group_id,
        message=message,
    )


def _file_task_stopped_after_init(task_id: str) -> bool:
    if is_task_stopped(task_id):
        add_task_log(task_id, "🛑 任务在初始化过程中被停止")
        return True
    return False
