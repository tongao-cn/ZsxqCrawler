"""Workflow for syncing file records from topics."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.services.file_downloader_runtime import _close_quietly
from backend.services.task_runtime import add_task_log, is_task_stopped, update_task
from backend.storage.zsxq_database import ZSXQDatabase


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


def _file_task_stopped_after_init(task_id: str) -> bool:
    if is_task_stopped(task_id):
        add_task_log(task_id, "🛑 任务在初始化过程中被停止")
        return True
    return False


def _complete_sync_files_from_topics_task(task_id: str, stats: Dict[str, Any]) -> None:
    update_task(task_id, "completed", "从话题同步文件记录完成", stats)


def run_sync_files_from_topics_task(task_id: str, group_id: str):
    topics_db = None
    try:
        update_task(task_id, "running", "开始从话题同步文件记录...")
        if _file_task_stopped_after_init(task_id):
            return

        topics_db = ZSXQDatabase(group_id)
        stats = topics_db.backfill_topic_files_to_file_database()
        if is_task_stopped(task_id):
            return

        _complete_sync_files_from_topics_task(task_id, stats)
    except Exception as e:
        _fail_file_task(task_id, f"从话题同步文件记录失败: {e}", f"从话题同步文件记录失败: {e}")
    finally:
        _close_quietly(topics_db)
