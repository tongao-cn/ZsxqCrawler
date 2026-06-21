from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from backend.services.a_share_analysis_service import normalize_group_id
from backend.services.workflow_registry import (
    INGESTION_LOCK_CATEGORY,
    INGESTION_WORKFLOW_TYPES,
    get_workflow_spec,
)


ACTIVE_TASK_STATUSES = {"pending", "running"}
RUNTIME_TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}

INGESTION_LOCK_TYPES = INGESTION_WORKFLOW_TYPES
INGESTION_LOCK_KEY = INGESTION_LOCK_CATEGORY


def _normalize_task_status(status: str) -> str:
    return "cancelled" if status == "stopped" else status


def _is_active_task_status(status: Any) -> bool:
    return status in ACTIVE_TASK_STATUSES


def _is_runtime_terminal_status(status: Any) -> bool:
    return _normalize_task_status(str(status or "")) in RUNTIME_TERMINAL_TASK_STATUSES


def _normalize_task(task: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not task:
        return None
    normalized = dict(task)
    normalized["status"] = _normalize_task_status(str(normalized.get("status") or ""))
    task_type = str(normalized.get("type") or "")
    if task_type:
        spec = get_workflow_spec(task_type)
        normalized["display_name"] = spec.display_name if spec else task_type
        normalized["cancellable"] = spec is None or spec.cancellable
    return normalized


def _has_ingestion_lock_identity(task: Dict[str, Any]) -> bool:
    return task.get("ingestion_lock_key") == INGESTION_LOCK_KEY or task.get("type") in INGESTION_LOCK_TYPES


def _matches_running_ingestion_task(task: Dict[str, Any], normalized_group_id: str) -> bool:
    if not _is_active_task_status(task.get("status")):
        return False
    if not _has_ingestion_lock_identity(task):
        return False
    return normalize_group_id(task.get("group_id")) == normalized_group_id


def _matches_latest_task_query(
    task: Dict[str, Any],
    task_type: str,
    status: Optional[str],
    normalized_group_id: Optional[str],
    group_filter_provided: bool = False,
) -> bool:
    if task.get("type") != task_type:
        return False
    if status and task.get("status") != status:
        return False
    if group_filter_provided and normalize_group_id(task.get("group_id")) != normalized_group_id:
        return False
    return True


def _task_created_at_sort_value(task: Dict[str, Any]) -> Any:
    return task.get("created_at") or datetime.min
