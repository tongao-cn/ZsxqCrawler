"""Persistence helpers for stock topic analysis."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, Iterable, List


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_company_name(value: Any) -> str:
    return (
        _normalize_text(value)
        .replace(" ", "")
        .replace("股份有限公司", "")
        .replace("有限责任公司", "")
        .replace("有限公司", "")
        .replace("集团", "")
    )


def _ordered_unique(values: Iterable[Any], *, limit: int = 50) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = _normalize_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
        if len(result) >= limit:
            break
    return result


def parse_json_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [_normalize_text(item) for item in value if _normalize_text(item)]
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [_normalize_text(item) for item in parsed if _normalize_text(item)]


def serialize_json_list(values: Iterable[Any], *, max_tracked_topic_ids: int) -> str:
    return json.dumps(_ordered_unique(values, limit=max_tracked_topic_ids), ensure_ascii=False)


def load_stock_topic_processed_state_ids(
    conn: Any,
    group_id: str,
    stock_name: str,
    *,
    processed_topic_statuses: set[str],
    max_tracked_topic_ids: int,
) -> List[str]:
    placeholders = ",".join("?" for _ in processed_topic_statuses)
    try:
        rows = conn.execute(
            f"""
            SELECT topic_id
            FROM stock_topic_processed_states
            WHERE group_id = ?
              AND stock_name = ?
              AND status IN ({placeholders})
            ORDER BY updated_at ASC
            """,
            [
                _normalize_text(group_id),
                _normalize_text(stock_name),
                *sorted(processed_topic_statuses),
            ],
        ).fetchall()
    except Exception:
        conn.rollback()
        return []
    return _ordered_unique((row["topic_id"] for row in rows), limit=max_tracked_topic_ids)


def load_latest_processed_topic_ids(
    conn: Any,
    group_id: str,
    stock_name: str,
    *,
    processed_topic_statuses: set[str],
    max_tracked_topic_ids: int,
) -> List[str]:
    query = _normalize_text(stock_name)
    if not query:
        return []
    state_ids = load_stock_topic_processed_state_ids(
        conn,
        group_id,
        query,
        processed_topic_statuses=processed_topic_statuses,
        max_tracked_topic_ids=max_tracked_topic_ids,
    )
    if state_ids:
        return state_ids
    try:
        row = conn.execute(
            """
            SELECT topic_ids_json
            FROM stock_topic_analyses
            WHERE group_id = ?
              AND stock_name = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (_normalize_text(group_id), query),
        ).fetchone()
    except Exception:
        conn.rollback()
        return []
    if not row:
        return []
    try:
        return parse_json_list(row["topic_ids_json"])
    except Exception:
        conn.rollback()
        return []


def upsert_stock_topic_processed_states(
    conn: Any,
    *,
    group_id: str,
    stock_name: str,
    topic_ids: Iterable[Any],
    status: str,
    max_tracked_topic_ids: int,
    extract_mode: str = "",
    model: str = "",
    error: str = "",
) -> None:
    normalized_topic_ids = _ordered_unique(topic_ids, limit=max_tracked_topic_ids)
    if not normalized_topic_ids:
        return
    params = [
        (
            _normalize_text(group_id),
            _normalize_text(stock_name),
            topic_id,
            status,
            extract_mode,
            model,
            error,
        )
        for topic_id in normalized_topic_ids
    ]
    for row in params:
        conn.execute(
            """
            INSERT INTO stock_topic_processed_states (
                group_id, stock_name, topic_id, status, extract_mode, model,
                error, processed_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(group_id, stock_name, topic_id) DO UPDATE SET
                status = excluded.status,
                extract_mode = excluded.extract_mode,
                model = excluded.model,
                error = excluded.error,
                processed_at = excluded.processed_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            row,
        )


def upsert_stock_topic_analysis(
    conn: Any,
    *,
    result: Dict[str, Any],
    status: str,
    topic_ids: List[Any],
    max_tracked_topic_ids: int,
    error: str = "",
    processed_state_topic_ids: Iterable[Any] | None = None,
    processed_topic_status: str = "analyzed",
    extract_mode: str = "",
    write_processed_state: bool = True,
    commit: bool = True,
) -> None:
    if write_processed_state:
        state_topic_ids = list(processed_state_topic_ids) if processed_state_topic_ids is not None else topic_ids
        upsert_stock_topic_processed_states(
            conn,
            group_id=result["group_id"],
            stock_name=result["stock_name"],
            topic_ids=state_topic_ids,
            status=processed_topic_status,
            max_tracked_topic_ids=max_tracked_topic_ids,
            extract_mode=extract_mode,
            model=result.get("model", ""),
            error=error,
        )
    conn.execute(
        """
        INSERT INTO stock_topic_analyses (
            group_id, stock_name, stock_code, market, topic_ids_json,
            concepts_json, recommendation_count, summary_markdown, model,
            status, error, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(group_id, stock_name) DO UPDATE SET
            stock_code = excluded.stock_code,
            market = excluded.market,
            topic_ids_json = excluded.topic_ids_json,
            concepts_json = excluded.concepts_json,
            recommendation_count = excluded.recommendation_count,
            summary_markdown = excluded.summary_markdown,
            model = excluded.model,
            status = excluded.status,
            error = excluded.error,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            result["group_id"],
            result["stock_name"],
            result.get("stock_code", ""),
            result.get("market", ""),
            serialize_json_list(topic_ids, max_tracked_topic_ids=max_tracked_topic_ids),
            serialize_json_list(result.get("concepts", []), max_tracked_topic_ids=max_tracked_topic_ids),
            int(result.get("recommendation_count") or 0),
            result.get("summary_markdown", ""),
            result.get("model", ""),
            status,
            error,
        ),
    )
    if commit:
        conn.commit()


def insert_stock_topic_analysis_version(
    conn: Any,
    *,
    result: Dict[str, Any],
    status: str,
    topic_ids: List[Any],
    max_tracked_topic_ids: int,
    error: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO stock_topic_analysis_versions (
            group_id, stock_name, stock_code, market, topic_ids_json,
            concepts_json, recommendation_count, summary_markdown, model,
            status, error, analysis_mode, new_topic_count, analysis_date,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            result["group_id"],
            result["stock_name"],
            result.get("stock_code", ""),
            result.get("market", ""),
            serialize_json_list(topic_ids, max_tracked_topic_ids=max_tracked_topic_ids),
            serialize_json_list(result.get("concepts", []), max_tracked_topic_ids=max_tracked_topic_ids),
            int(result.get("recommendation_count") or 0),
            result.get("summary_markdown", ""),
            result.get("model", ""),
            status,
            error,
            result.get("analysis_mode", ""),
            int(result.get("new_topic_count") or 0),
            date.today().isoformat(),
        ),
    )
