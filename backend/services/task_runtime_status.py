from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

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


@dataclass(frozen=True)
class TaskQuery:
    task_type: Optional[str] = None
    status: Optional[str] = None
    group_id: Any = None
    group_filter_provided: bool = False
    limit: Optional[int] = None

    @property
    def normalized_group_id(self) -> Optional[str]:
        return normalize_group_id(self.group_id) if self.group_filter_provided else None

    @property
    def has_filter(self) -> bool:
        return self.group_filter_provided or bool(self.task_type) or bool(self.status)


def _normalize_task_status(status: str) -> str:
    return "cancelled" if status == "stopped" else status


def _is_active_task_status(status: Any) -> bool:
    return status in ACTIVE_TASK_STATUSES


def _is_runtime_terminal_status(status: Any) -> bool:
    return _normalize_task_status(str(status or "")) in RUNTIME_TERMINAL_TASK_STATUSES


def is_terminal_task_status(status: Any) -> bool:
    return _is_runtime_terminal_status(status)


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


def _matches_task_query(
    task: Dict[str, Any],
    task_type: Optional[str] = None,
    normalized_group_id: Optional[str] = None,
    group_filter_provided: bool = False,
) -> bool:
    if task_type and task.get("type") != task_type:
        return False
    if group_filter_provided and normalize_group_id(task.get("group_id")) != normalized_group_id:
        return False
    return True


def _matches_latest_task_query(
    task: Dict[str, Any],
    task_type: str,
    status: Optional[str],
    normalized_group_id: Optional[str],
    group_filter_provided: bool = False,
) -> bool:
    if status and task.get("status") != status:
        return False
    return _matches_task_query(task, task_type, normalized_group_id, group_filter_provided)


def _task_created_at_sort_value(task: Dict[str, Any]) -> Any:
    return task.get("created_at") or datetime.min


def query_tasks(tasks: Iterable[Dict[str, Any]], query: TaskQuery) -> List[Dict[str, Any]]:
    normalized_group_id = query.normalized_group_id
    filtered = [
        normalized
        for normalized in (_normalize_task(task) for task in tasks)
        if normalized is not None
        and _matches_latest_task_query(
            normalized,
            query.task_type or "",
            query.status,
            normalized_group_id,
            query.group_filter_provided,
        )
    ]
    if query.limit is not None:
        return filtered[: query.limit]
    return filtered


def latest_task_for_query(tasks: Iterable[Dict[str, Any]], query: TaskQuery) -> Optional[Dict[str, Any]]:
    candidates = query_tasks(tasks, query)
    if not candidates:
        return None
    candidates.sort(key=_task_created_at_sort_value, reverse=True)
    return candidates[0]
