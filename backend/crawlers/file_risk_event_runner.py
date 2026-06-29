"""Risk event logging runner for ZSXQ file downloads."""

from __future__ import annotations

import csv
import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from backend.crawlers.file_request_fingerprint import (
    risk_event_header_profile_label,
    risk_event_row,
    risk_event_user_agent_label,
)


class RiskEventRuntime(Protocol):
    group_id: Any
    risk_event_log_path: Any


def user_agent_label(user_agent: str) -> str:
    return risk_event_user_agent_label(user_agent)


def header_profile_label(headers: Dict[str, str]) -> str:
    return risk_event_header_profile_label(headers)


def prepare_risk_event_log_path(runtime: RiskEventRuntime) -> Optional[Any]:
    if not getattr(runtime, "risk_event_log_path", None):
        return None

    path = Path(runtime.risk_event_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_risk_event_row(path: Any, row: Dict[str, Any]) -> None:
    fieldnames = tuple(row.keys())
    write_header = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def risk_event_row_for_runtime(
    runtime: RiskEventRuntime,
    *,
    file_id: int,
    phase: str,
    attempt: int = 0,
    headers: Optional[Dict[str, str]] = None,
    http_status: Optional[int] = None,
    api_code: Optional[Any] = None,
    api_message: Optional[str] = None,
    status: str = "observed",
) -> Dict[str, Any]:
    return risk_event_row(
        datetime.datetime.now().isoformat(timespec="seconds"),
        runtime.group_id,
        file_id,
        phase,
        attempt,
        headers,
        http_status,
        api_code,
        api_message,
        status,
    )


def record_risk_event(
    runtime: RiskEventRuntime,
    *,
    file_id: int,
    phase: str,
    attempt: int = 0,
    headers: Optional[Dict[str, str]] = None,
    http_status: Optional[int] = None,
    api_code: Optional[Any] = None,
    api_message: Optional[str] = None,
    status: str = "observed",
) -> None:
    path = prepare_risk_event_log_path(runtime)
    if path is None:
        return

    row = risk_event_row_for_runtime(
        runtime,
        file_id=file_id,
        phase=phase,
        attempt=attempt,
        headers=headers,
        http_status=http_status,
        api_code=api_code,
        api_message=api_message,
        status=status,
    )
    write_risk_event_row(path, row)
