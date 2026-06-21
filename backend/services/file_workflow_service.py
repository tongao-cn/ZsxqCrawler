from __future__ import annotations

from typing import Any, Dict, Optional

from backend.services.file_analysis_workflow import run_file_analysis_task
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
from backend.services.file_task_lifecycle import (
    fail_file_task as _fail_file_task_impl,
    file_task_stopped_after_init as _file_task_stopped_after_init_impl,
)
from backend.services.file_topic_sync_workflow import (
    _complete_sync_files_from_topics_task,
    run_sync_files_from_topics_task,
)
from backend.services.task_launch import (
    TaskLaunchRecipe,
    launch_task_recipe,
)
from backend.services.task_runtime import (
    add_task_log,
    is_task_stopped,
    update_task,
)


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


def _launch_file_ingestion_task(
    task_type: str,
    description: str,
    task_func,
    group_id: str,
    *task_args,
    message: str = "任务已创建，正在后台执行",
) -> Dict[str, str]:
    return launch_task_recipe(
        TaskLaunchRecipe.ingestion(
            task_type,
            description,
            task_func,
            group_id,
            *task_args,
            message=message,
            prepend_group_id_to_args=False,
        )
    )


def _launch_file_analysis_task(
    task_type: str,
    description: str,
    group_id: str,
    file_ids: list[int],
    force: bool,
    message: str,
) -> Dict[str, str]:
    return launch_task_recipe(
        TaskLaunchRecipe(
            task_type=task_type,
            description=description,
            task_func=run_file_analysis_task,
            args=(group_id, file_ids, force),
            group_id=group_id,
            message=message,
        )
    )


def create_file_collect_task(group_id: str, request: Any) -> Dict[str, str]:
    return _launch_file_ingestion_task(
        "collect_files",
        "收集文件列表",
        run_collect_files_task,
        group_id,
        group_id,
        request,
    )


def create_file_download_task(group_id: str, request: Any) -> Dict[str, str]:
    return _launch_file_ingestion_task(
        "download_files",
        f"下载文件 (排序: {request.sort_by})",
        run_file_download_task,
        group_id,
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
    )


def create_single_file_download_task(
    group_id: str,
    file_id: int,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
) -> Dict[str, str]:
    return _launch_file_ingestion_task(
        "download_single_file",
        f"下载单个文件 (ID: {file_id})",
        run_single_file_download_task_with_info,
        group_id,
        group_id,
        file_id,
        file_name,
        file_size,
        message="单个文件下载任务已创建",
    )


def create_selected_file_download_task(group_id: str, request: Any) -> Dict[str, str]:
    return _launch_file_ingestion_task(
        "download_selected_files",
        f"下载选中文件 ({len(request.file_ids)} 个)",
        run_selected_file_download_task,
        group_id,
        group_id,
        request.file_ids,
        message="选中文件下载任务已创建",
    )


def create_filtered_file_download_task(group_id: str, request: Any) -> Dict[str, str]:
    return _launch_file_ingestion_task(
        "download_filtered_files",
        "下载筛选结果",
        run_filtered_file_download_task,
        group_id,
        group_id,
        request.status,
        request.search,
        request.max_files,
        message="筛选结果下载任务已创建",
    )


def create_file_ai_analysis_task(group_id: str, file_id: int, force: bool) -> Dict[str, str]:
    return _launch_file_analysis_task(
        "analyze_file",
        f"分析文件 (ID: {file_id})",
        group_id,
        [file_id],
        force,
        "文件 AI 分析任务已创建",
    )


def create_selected_file_ai_analysis_task(group_id: str, request: Any) -> Dict[str, str]:
    return _launch_file_analysis_task(
        "analyze_files",
        f"批量分析文件 ({len(request.file_ids)} 个)",
        group_id,
        request.file_ids,
        request.force,
        "批量文件 AI 分析任务已创建",
    )


def create_sync_files_from_topics_task(group_id: str) -> Dict[str, str]:
    return _launch_file_ingestion_task(
        "sync_files_from_topics",
        f"从话题同步文件记录 (群组: {group_id})",
        run_sync_files_from_topics_task,
        group_id,
        group_id,
        message="从话题同步文件记录任务已创建",
    )


def _file_task_stopped_after_init(task_id: str) -> bool:
    return _file_task_stopped_after_init_impl(
        task_id,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
    )
