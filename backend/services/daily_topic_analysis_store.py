"""Persistence helpers for daily AI reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.db_path_manager import get_db_path_manager
from backend.storage.db_compat import connect


def connect_topics_db(group_id: str):
    return connect(row_factory=True)


def ensure_report_table(conn: Any) -> None:
    """Schema is managed by manage-postgres-core-schema; runtime DDL is disabled."""
    return None


def upsert_report(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    topic_count: int,
    model: str,
    prompt_version: str,
    summary_markdown: str,
    raw_json: Dict[str, Any],
    status: str,
    error: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO daily_ai_reports (
            group_id, report_date, topic_count, model, prompt_version,
            summary_markdown, raw_json, status, error, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(group_id, report_date) DO UPDATE SET
            topic_count = excluded.topic_count,
            model = excluded.model,
            prompt_version = excluded.prompt_version,
            summary_markdown = excluded.summary_markdown,
            raw_json = excluded.raw_json,
            status = excluded.status,
            error = excluded.error,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            group_id,
            report_date,
            topic_count,
            model,
            prompt_version,
            summary_markdown,
            json.dumps(raw_json, ensure_ascii=False),
            status,
            error,
        ),
    )
    conn.commit()


def parse_report_raw_json(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def write_report_file(group_id: str, report_date: str, summary_markdown: str) -> str:
    group_dir = Path(get_db_path_manager().get_group_dir(group_id))
    report_dir = group_dir / "daily_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{report_date}.md"
    report_path.write_text(summary_markdown, encoding="utf-8")
    return str(report_path)


def get_daily_report_row(conn: Any, *, group_id: str, report_date: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT group_id, report_date, topic_count, model, prompt_version,
               summary_markdown, raw_json, status, error, created_at, updated_at
        FROM daily_ai_reports
        WHERE group_id = ? AND report_date = ?
        """,
        (group_id, report_date),
    ).fetchone()
    if not row:
        return None
    return {
        "group_id": row["group_id"],
        "report_date": row["report_date"],
        "topic_count": row["topic_count"],
        "model": row["model"],
        "prompt_version": row["prompt_version"],
        "summary_markdown": row["summary_markdown"],
        "raw_json": parse_report_raw_json(row["raw_json"]),
        "status": row["status"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
