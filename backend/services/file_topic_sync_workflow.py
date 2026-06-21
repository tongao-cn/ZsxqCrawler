"""Workflow for syncing file records from topics."""

from __future__ import annotations

from typing import Any

from backend.services.file_downloader_runtime import _close_quietly
from backend.services.file_task_lifecycle import (
    file_task_stopped_after_init as _file_task_stopped_after_init_impl,
)
from backend.services.task_runtime import add_task_log, is_task_stopped, run_workflow, skip_workflow_completion
from backend.storage.zsxq_database import ZSXQDatabase


def _file_task_stopped_after_init(task_id: str) -> bool:
    return _file_task_stopped_after_init_impl(
        task_id,
        is_stopped=is_task_stopped,
        add_log=add_task_log,
    )


def _sync_files_from_topics(task_id: str, group_id: str) -> Any:
    topics_db = None
    try:
        if _file_task_stopped_after_init(task_id):
            return skip_workflow_completion()

        topics_db = ZSXQDatabase(group_id)
        stats = topics_db.backfill_topic_files_to_file_database()
        if is_task_stopped(task_id):
            return skip_workflow_completion()

        return stats
    finally:
        _close_quietly(topics_db)


def run_sync_files_from_topics_task(task_id: str, group_id: str):
    run_workflow(
        task_id,
        running_message="开始从话题同步文件记录...",
        completed_message="从话题同步文件记录完成",
        failure_label="从话题同步文件记录",
        work=lambda: _sync_files_from_topics(task_id, group_id),
    )
