"""Storage contract for daily stock concept snapshots."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional


def save_daily_stock_concepts(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    stocks: List[Dict[str, Any]],
    model: str,
    status: str,
    error: str = "",
) -> None:
    _delete_stock_concepts(conn, group_id, report_date)
    _insert_stock_concepts(
        conn,
        group_id=group_id,
        report_date=report_date,
        stocks=stocks,
        model=model,
        status=status,
        error=error,
    )
    conn.commit()


def load_daily_stock_concepts(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
) -> Optional[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT stock_name, stock_code, market, concepts_json, reason,
               topic_ids_json, confidence, model, status, error, updated_at
        FROM daily_stock_concepts
        WHERE group_id = ? AND report_date = ?
        ORDER BY confidence DESC, stock_name ASC
        """,
        (group_id, report_date),
    ).fetchall()
    if not rows:
        return None

    first = rows[0]
    stocks = []
    for row in rows:
        if not row["stock_name"]:
            continue
        stocks.append(
            {
                "stock_name": row["stock_name"],
                "stock_code": row["stock_code"] or "",
                "market": row["market"] or "",
                "concepts": _parse_json_list(row["concepts_json"]),
                "reason": row["reason"] or "",
                "topic_ids": _parse_json_list(row["topic_ids_json"]),
                "confidence": float(row["confidence"] or 0),
                "model": row["model"] or "",
            }
        )
    return {
        "group_id": group_id,
        "report_date": report_date,
        "stocks": stocks,
        "status": first["status"],
        "error": first["error"],
        "updated_at": first["updated_at"],
    }


def _delete_stock_concepts(conn: Any, group_id: str, report_date: str) -> None:
    conn.execute(
        "DELETE FROM daily_stock_concepts WHERE group_id = ? AND report_date = ?",
        (group_id, report_date),
    )


def _insert_stock_concepts(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    stocks: List[Dict[str, Any]],
    model: str,
    status: str,
    error: str = "",
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    if not stocks:
        conn.execute(
            """
            INSERT INTO daily_stock_concepts (
                group_id, report_date, stock_name, stock_code, market,
                concepts_json, reason, topic_ids_json, confidence,
                model, status, error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (group_id, report_date, "", "", "", "[]", error, "[]", 0, model, status, error, now, now),
        )
        return

    for stock in stocks:
        conn.execute(
            """
            INSERT INTO daily_stock_concepts (
                group_id, report_date, stock_name, stock_code, market,
                concepts_json, reason, topic_ids_json, confidence,
                model, status, error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group_id,
                report_date,
                stock["stock_name"],
                stock.get("stock_code", ""),
                stock.get("market", ""),
                json.dumps(stock.get("concepts", []), ensure_ascii=False),
                stock.get("reason", ""),
                json.dumps(stock.get("topic_ids", []), ensure_ascii=False),
                stock.get("confidence", 0),
                model,
                status,
                error,
                now,
                now,
            ),
        )


def _parse_json_list(value: Any) -> List[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []
