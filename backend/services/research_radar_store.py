from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def _json_obj(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False)


def _parse_json(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _existing_run_ids(conn: Any, group_id: str, report_date: str) -> List[int]:
    rows = conn.execute(
        "SELECT id FROM research_radar_runs WHERE group_id = ? AND report_date = ?",
        (group_id, report_date),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def _delete_existing_runs(conn: Any, run_ids: List[int]) -> None:
    for run_id in run_ids:
        conn.execute(
            """
            DELETE FROM research_radar_evidence
            WHERE logic_id IN (SELECT id FROM research_radar_logic_items WHERE run_id = ?)
            """,
            (run_id,),
        )
        conn.execute("DELETE FROM research_radar_entities WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM research_radar_logic_items WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM research_radar_runs WHERE id = ?", (run_id,))


def _insert_run(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    task_id: str,
    status: str,
    model: str,
    summary: Dict[str, Any],
    error: str,
) -> int:
    now = _now()
    row = conn.execute(
        """
        INSERT INTO research_radar_runs (
            group_id, report_date, window_days, status, model,
            summary_json, task_id, error, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (group_id, report_date, 1, status, model, _json_obj(summary), task_id, error, now, now),
    ).fetchone()
    return int(row["id"])


def _insert_logic_item(conn: Any, *, run_id: int, rank: int, item: Dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO research_radar_logic_items (
            run_id, rank, tier, title, summary, direction, concepts_json,
            stocks_json, catalysts_json, risks_json, evidence_count,
            confidence, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            run_id,
            rank,
            str(item.get("tier") or "weak"),
            str(item.get("title") or ""),
            str(item.get("summary") or ""),
            str(item.get("direction") or ""),
            _json(item.get("concepts") or []),
            _json(item.get("stocks") or []),
            _json(item.get("catalysts") or []),
            _json(item.get("risks") or []),
            int(item.get("evidence_count") or len(item.get("evidence") or [])),
            float(item.get("confidence") or 0),
            _now(),
        ),
    ).fetchone()
    return int(row["id"]) if isinstance(row, dict) else 0


def _insert_evidence(conn: Any, *, logic_id: int, evidence: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO research_radar_evidence (
            logic_id, source_type, source_id, topic_id, source_time,
            excerpt, matched_entities_json, support_reason,
            navigation_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            logic_id,
            str(evidence.get("source_type") or ""),
            str(evidence.get("source_id") or ""),
            str(evidence.get("topic_id") or ""),
            str(evidence.get("source_time") or ""),
            str(evidence.get("excerpt") or ""),
            _json_obj(evidence.get("matched_entities")),
            str(evidence.get("support_reason") or ""),
            _json_obj(evidence.get("navigation")),
            _now(),
        ),
    )


def _insert_entities(conn: Any, *, run_id: int, logic_id: int, item: Dict[str, Any]) -> None:
    for concept in item.get("concepts") or []:
        conn.execute(
            """
            INSERT INTO research_radar_entities (
                run_id, logic_id, entity_type, name, code, market,
                weight, evidence_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                logic_id,
                "concept",
                str(concept),
                "",
                "",
                float(item.get("confidence") or 0),
                int(item.get("evidence_count") or 0),
                _now(),
            ),
        )
    for stock in item.get("stocks") or []:
        if not isinstance(stock, dict):
            continue
        conn.execute(
            """
            INSERT INTO research_radar_entities (
                run_id, logic_id, entity_type, name, code, market,
                weight, evidence_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                logic_id,
                "stock",
                str(stock.get("name") or ""),
                str(stock.get("code") or ""),
                str(stock.get("market") or ""),
                float(stock.get("confidence") or item.get("confidence") or 0),
                int(item.get("evidence_count") or 0),
                _now(),
            ),
        )


def save_research_radar_run(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    task_id: str,
    status: str,
    model: str,
    logic_items: List[Dict[str, Any]],
    summary: Dict[str, Any],
    error: str = "",
) -> int:
    _delete_existing_runs(conn, _existing_run_ids(conn, group_id, report_date))
    run_id = _insert_run(
        conn,
        group_id=group_id,
        report_date=report_date,
        task_id=task_id,
        status=status,
        model=model,
        summary=summary,
        error=error,
    )
    for rank, item in enumerate(logic_items, start=1):
        logic_id = _insert_logic_item(conn, run_id=run_id, rank=rank, item=item)
        for evidence in item.get("evidence") or []:
            if isinstance(evidence, dict):
                _insert_evidence(conn, logic_id=logic_id, evidence=evidence)
        _insert_entities(conn, run_id=run_id, logic_id=logic_id, item=item)
    conn.commit()
    return run_id


def _load_run_row(conn: Any, *, group_id: str, report_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if report_date:
        return conn.execute(
            """
            SELECT id, group_id, report_date, window_days, status, model, summary_json,
                   task_id, error, created_at, updated_at
            FROM research_radar_runs
            WHERE group_id = ? AND report_date = ?
            """,
            (group_id, report_date),
        ).fetchone()
    return conn.execute(
        """
        SELECT id, group_id, report_date, window_days, status, model, summary_json,
               task_id, error, created_at, updated_at
        FROM research_radar_runs
        WHERE group_id = ?
        ORDER BY report_date DESC, id DESC
        LIMIT 1
        """,
        (group_id,),
    ).fetchone()


def _load_logic_rows(conn: Any, run_id: int) -> List[Any]:
    return conn.execute(
        """
        SELECT id, rank, tier, title, summary, direction, concepts_json, stocks_json,
               catalysts_json, risks_json, evidence_count, confidence
        FROM research_radar_logic_items
        WHERE run_id = ?
        ORDER BY rank ASC, id ASC
        """,
        (run_id,),
    ).fetchall()


def _load_evidence_rows(conn: Any, logic_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    evidence_by_logic: Dict[int, List[Dict[str, Any]]] = {logic_id: [] for logic_id in logic_ids}
    for logic_id in logic_ids:
        rows = conn.execute(
            """
            SELECT id, logic_id, source_type, source_id, topic_id, source_time,
                   excerpt, matched_entities_json, support_reason, navigation_json
            FROM research_radar_evidence
            WHERE logic_id = ?
            ORDER BY id ASC
            """,
            (logic_id,),
        ).fetchall()
        evidence_by_logic[logic_id] = [
            {
                "id": row["id"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "topic_id": row["topic_id"],
                "source_time": row["source_time"],
                "excerpt": row["excerpt"],
                "matched_entities": _parse_json(row["matched_entities_json"], {}),
                "support_reason": row["support_reason"],
                "navigation": _parse_json(row["navigation_json"], {}),
            }
            for row in rows
        ]
    return evidence_by_logic


def _load_entity_rows(conn: Any, logic_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    entities_by_logic: Dict[int, List[Dict[str, Any]]] = {logic_id: [] for logic_id in logic_ids}
    for logic_id in logic_ids:
        rows = conn.execute(
            """
            SELECT logic_id, entity_type, name, code, market, weight, evidence_count
            FROM research_radar_entities
            WHERE logic_id = ?
            ORDER BY entity_type ASC, weight DESC, name ASC
            """,
            (logic_id,),
        ).fetchall()
        entities_by_logic[logic_id] = [
            {
                "entity_type": row["entity_type"],
                "name": row["name"],
                "code": row["code"],
                "market": row["market"],
                "weight": float(row["weight"] or 0),
                "evidence_count": int(row["evidence_count"] or 0),
            }
            for row in rows
        ]
    return entities_by_logic


def _map_run(conn: Any, run_row: Any) -> Dict[str, Any]:
    run_id = int(run_row["id"])
    logic_rows = _load_logic_rows(conn, run_id)
    logic_ids = [int(row["id"]) for row in logic_rows]
    evidence_by_logic = _load_evidence_rows(conn, logic_ids)
    entities_by_logic = _load_entity_rows(conn, logic_ids)
    return {
        "id": run_id,
        "group_id": run_row["group_id"],
        "report_date": run_row["report_date"],
        "window_days": int(run_row["window_days"] or 1),
        "status": run_row["status"],
        "model": run_row["model"],
        "summary": _parse_json(run_row["summary_json"], {}),
        "task_id": run_row["task_id"],
        "error": run_row["error"],
        "created_at": run_row["created_at"],
        "updated_at": run_row["updated_at"],
        "logic_items": [
            {
                "id": int(row["id"]),
                "rank": int(row["rank"] or 0),
                "tier": row["tier"],
                "title": row["title"],
                "summary": row["summary"],
                "direction": row["direction"],
                "concepts": _parse_json(row["concepts_json"], []),
                "stocks": _parse_json(row["stocks_json"], []),
                "catalysts": _parse_json(row["catalysts_json"], []),
                "risks": _parse_json(row["risks_json"], []),
                "evidence_count": int(row["evidence_count"] or 0),
                "confidence": float(row["confidence"] or 0),
                "evidence": evidence_by_logic.get(int(row["id"]), []),
                "entities": entities_by_logic.get(int(row["id"]), []),
            }
            for row in logic_rows
        ],
    }


def load_latest_research_radar_run(conn: Any, *, group_id: str) -> Optional[Dict[str, Any]]:
    row = _load_run_row(conn, group_id=group_id)
    return _map_run(conn, row) if row else None


def load_research_radar_run_by_date(conn: Any, *, group_id: str, report_date: str) -> Optional[Dict[str, Any]]:
    row = _load_run_row(conn, group_id=group_id, report_date=report_date)
    return _map_run(conn, row) if row else None
