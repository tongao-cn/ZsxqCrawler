from __future__ import annotations

import asyncio
from typing import Any

from backend.core.ai_provider_config import has_openai_api_key
from backend.services.a_share_analysis_db_storage import get_storage_health
from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_CONCURRENCY as A_SHARE_DEFAULT_CONCURRENCY,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT as A_SHARE_DEFAULT_REASONING_EFFORT,
    DEFAULT_RANKING_WINDOWS as A_SHARE_DEFAULT_RANKING_WINDOWS,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
    get_analysis_summary,
    normalize_group_id,
)
from backend.services.task_runtime import get_latest_task_by_type
from backend.services.tdx_a_share_export_service import get_latest_tdx_export


def _analysis_defaults_payload() -> dict[str, Any]:
    return {
        "days": 21,
        "concurrency": A_SHARE_DEFAULT_CONCURRENCY,
        "model": A_SHARE_DEFAULT_MODEL,
        "api_base": A_SHARE_DEFAULT_API_BASE,
        "wire_api": A_SHARE_DEFAULT_WIRE_API,
        "reasoning_effort": A_SHARE_DEFAULT_REASONING_EFFORT,
        "ranking_windows": list(A_SHARE_DEFAULT_RANKING_WINDOWS),
    }


def _a_share_file_fallback_storage_status(summary: dict[str, Any], storage_error: Exception) -> dict[str, Any]:
    return {
        "enabled": False,
        "mode": "file_fallback",
        "label": f"本地文件降级（PostgreSQL 不可用: {storage_error}）",
        "daily_rows": summary.get("rows_count") or 0,
        "processed_rows": summary.get("processed_items") or 0,
    }


async def _a_share_storage_status(summary: dict[str, Any], normalized_group_id: str | None) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(get_storage_health, group_id=normalized_group_id)
    except Exception as storage_error:
        return _a_share_file_fallback_storage_status(summary, storage_error)


async def _latest_a_share_tdx_export(normalized_group_id: str | None) -> dict[str, Any] | None:
    try:
        return await asyncio.to_thread(get_latest_tdx_export, normalized_group_id)
    except Exception:
        return None


async def _a_share_analysis_summary(normalized_group_id: str | None) -> dict[str, Any]:
    return await asyncio.to_thread(get_analysis_summary, group_id=normalized_group_id)


def _a_share_status_tasks(normalized_group_id: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    latest_task = get_latest_task_by_type(
        "a_share_analysis",
        group_id=normalized_group_id,
    )
    running_task = get_latest_task_by_type(
        "a_share_analysis",
        status="running",
        group_id=normalized_group_id,
    )
    return latest_task, running_task


def _a_share_status_payload(
    normalized_group_id: str | None,
    summary: dict[str, Any],
    latest_task: dict[str, Any] | None,
    running_task: dict[str, Any] | None,
    storage: dict[str, Any],
    latest_tdx_export: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "summary": summary,
        "group_id": normalized_group_id,
        "defaults": _analysis_defaults_payload(),
        "api_key_configured": has_openai_api_key(),
        "latest_task": latest_task,
        "running_task": running_task,
        "storage": storage,
        "latest_tdx_export": latest_tdx_export,
    }


async def get_a_share_analysis_status_payload(group_id: str | int | None = None) -> dict[str, Any]:
    normalized_group_id = normalize_group_id(group_id)
    summary = await _a_share_analysis_summary(normalized_group_id)
    latest_task, running_task = _a_share_status_tasks(normalized_group_id)
    storage = await _a_share_storage_status(summary, normalized_group_id)
    latest_tdx_export = await _latest_a_share_tdx_export(normalized_group_id)

    return _a_share_status_payload(
        normalized_group_id,
        summary,
        latest_task,
        running_task,
        storage,
        latest_tdx_export,
    )
