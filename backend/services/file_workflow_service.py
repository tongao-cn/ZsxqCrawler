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
    _build_download_file_info,
    _build_download_task_stats,
    _complete_download_records_task,
    _download_result_stat_key,
    _load_download_file_records,
    _load_filtered_download_file_records,
    _run_download_records,
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
from backend.services.file_task_lifecycle import (
    fail_file_task as _fail_file_task_impl,
    file_task_stopped_after_init as _file_task_stopped_after_init_impl,
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


def _normalize_file_list_row(group_id: str, file: Any) -> Dict[str, Any]:
    file_id = file.file_id
    file_name = file.name
    stored_status = file.download_status
    stored_local_path = file.local_path

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
        "size": file.size,
        "download_count": file.download_count,
        "create_time": file.create_time,
        "download_status": local_status["download_status"],
        "local_exists": local_status["local_exists"],
        "local_path": local_status["local_path"],
        "download_error_code": file.download_error_code,
        "download_error_message": file.download_error_message,
        "last_download_attempt_at": file.last_download_attempt_at,
        "has_ai_analysis": bool(file.analysis_updated_at),
        "analysis_updated_at": file.analysis_updated_at,
    }


def _build_file_list_response(
    group_id: str,
    files: Sequence[Any],
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
        file_page = file_db.load_file_list_page(
            page=page,
            per_page=per_page,
            status=status,
            search=search,
            analysis_status=analysis_status,
        )
        return _build_file_list_response(group_id, file_page.records, file_page.total, page, per_page)


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
    _fail_file_task_impl(
        task_id,
        log_message,
        task_message,
        result,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
        update=update_task,
    )


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


def create_file_collect_task(group_id: str, request: Any) -> Dict[str, str]:
    return launch_ingestion_task(
        "collect_files",
        "收集文件列表",
        run_collect_files_task,
        group_id,
        group_id,
        request,
        prepend_group_id_to_args=False,
    )


def _file_task_stopped_after_init(task_id: str) -> bool:
    return _file_task_stopped_after_init_impl(
        task_id,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
    )
