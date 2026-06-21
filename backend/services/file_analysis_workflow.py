"""Task workflow for file AI analysis."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from backend.services.file_ai_analysis_service import (
    DEFAULT_FILE_ANALYSIS_API_BASE,
    DEFAULT_FILE_ANALYSIS_MODEL,
    DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    DEFAULT_FILE_ANALYSIS_WIRE_API,
    analyze_group_file,
)
from backend.services.file_task_lifecycle import fail_file_task as _fail_file_task_impl
from backend.services.task_runtime import add_task_log, is_task_stopped, update_task


def _analyze_group_file_with_defaults(group_id: str, file_id: int, force: bool) -> Dict[str, Any]:
    return analyze_group_file(
        group_id,
        file_id,
        force=force,
        model=DEFAULT_FILE_ANALYSIS_MODEL,
        api_base=DEFAULT_FILE_ANALYSIS_API_BASE,
        wire_api=DEFAULT_FILE_ANALYSIS_WIRE_API,
        reasoning_effort=DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    )


def _record_file_analysis_result(stats: Dict[str, int], result: Dict[str, Any]) -> None:
    if result.get("cached"):
        stats["cached"] += 1
    else:
        stats["completed"] += 1


def _finish_file_analysis_task(task_id: str, stats: Dict[str, int]) -> None:
    if stats["failed"] and stats["completed"] == 0 and stats["cached"] == 0:
        update_task(task_id, "failed", "文件分析全部失败", {"analysis": stats})
    else:
        update_task(task_id, "completed", "文件分析完成", {"analysis": stats})


def _unique_file_analysis_ids(file_ids: Sequence[Any]) -> list[int]:
    return [int(file_id) for file_id in dict.fromkeys(file_ids)]


def _build_file_analysis_stats(total_files: int) -> Dict[str, int]:
    return {
        "total_files": total_files,
        "completed": 0,
        "cached": 0,
        "failed": 0,
    }


def _run_file_analysis_item(
    task_id: str,
    group_id: str,
    file_id: int,
    index: int,
    total_files: int,
    stats: Dict[str, int],
    force: bool,
) -> None:
    try:
        add_task_log(task_id, f"【{index}/{total_files}】分析文件 ID: {file_id}")
        result = _analyze_group_file_with_defaults(group_id, file_id, force)
        _record_file_analysis_result(stats, result)
        add_task_log(task_id, f"✅ 文件分析完成: {file_id}")
    except Exception as exc:
        stats["failed"] += 1
        add_task_log(task_id, f"❌ 文件分析失败: {file_id}, {exc}")


def _run_file_analysis_items(
    task_id: str,
    group_id: str,
    file_ids: Sequence[int],
    stats: Dict[str, int],
    force: bool,
) -> bool:
    total_files = len(file_ids)
    for index, file_id in enumerate(file_ids, 1):
        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 文件分析任务被停止")
            return False

        _run_file_analysis_item(task_id, group_id, file_id, index, total_files, stats, force)

    return True


def _fail_file_analysis_task(task_id: str, message: str, stats: Dict[str, int]) -> None:
    _fail_file_task_impl(
        task_id,
        message,
        message,
        {"analysis": stats},
        is_stopped=is_task_stopped,
        add_log=add_task_log,
        update=update_task,
    )


def run_file_analysis_task(
    task_id: str,
    group_id: str,
    file_ids: Sequence[int],
    force: bool = False,
) -> None:
    unique_file_ids = _unique_file_analysis_ids(file_ids)
    stats = _build_file_analysis_stats(len(unique_file_ids))
    try:
        update_task(task_id, "running", f"开始分析 {len(unique_file_ids)} 个文件...")
        if not _run_file_analysis_items(task_id, group_id, unique_file_ids, stats, force):
            return

        _finish_file_analysis_task(task_id, stats)
    except Exception as exc:
        _fail_file_analysis_task(task_id, f"文件分析任务失败: {exc}", stats)
