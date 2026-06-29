"""Neutral PostgreSQL store for topic-level stock evidence."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

import psycopg2
from psycopg2.extras import execute_values

from backend.services.a_share_analysis_storage_rows import (
    build_topic_stock_extraction_rows,
    normalize_group_id,
)
from backend.storage.db_compat import get_postgres_dsn as get_zsxq_postgres_dsn
from backend.storage.postgres_core_schema import (
    CORE_SCHEMA,
    is_schema_missing_error,
    quote_identifier,
    schema_not_ready_message,
)


DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))
TOPIC_STOCK_EXTRACTIONS_TABLE = "zsxq_a_share_topic_stock_extractions"


def _core_table_ref(table_name: str) -> str:
    return f"{quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)}"


def get_postgres_dsn(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> str:
    zsxq_dsn = get_zsxq_postgres_dsn()
    if zsxq_dsn:
        return zsxq_dsn

    raise RuntimeError("未找到 ZsxqCrawler PostgreSQL DSN，请设置 ZSXQ_POSTGRES_DSN 或 config.toml [database].postgres_dsn")


@contextmanager
def get_connection(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Iterator[Any]:
    conn = psycopg2.connect(get_postgres_dsn(env_path))
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if is_schema_missing_error(exc):
            raise RuntimeError(schema_not_ready_message(exc)) from exc
        raise
    finally:
        conn.close()


def parse_json_list(value: Any) -> List[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def upsert_topic_stock_extraction_rows(
    cur: Any,
    rows: Sequence[Any],
    *,
    execute_values_fn: Any = None,
) -> None:
    if not rows:
        return

    values_executor = execute_values_fn or execute_values
    values_executor(
        cur,
        f"""
        INSERT INTO {_core_table_ref(TOPIC_STOCK_EXTRACTIONS_TABLE)} (
            group_id, topic_id, topic_date, stock_name, stock_code, market,
            concepts_json, excerpt, reason, confidence, model, prompt_version, updated_at
        )
        VALUES %s
        ON CONFLICT (group_id, topic_id, stock_name) DO UPDATE SET
            topic_date = excluded.topic_date,
            stock_code = excluded.stock_code,
            market = excluded.market,
            concepts_json = excluded.concepts_json,
            excerpt = excluded.excerpt,
            reason = excluded.reason,
            confidence = excluded.confidence,
            model = excluded.model,
            prompt_version = excluded.prompt_version,
            updated_at = excluded.updated_at
        """,
        rows,
        template="(%s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
    )


def save_topic_stock_extractions(
    extractions: Sequence[Dict[str, Any]],
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
    *,
    connection_factory: Any = None,
    execute_values_fn: Any = None,
) -> int:
    rows = build_topic_stock_extraction_rows(extractions, group_id, datetime.now())

    if not rows:
        return 0

    connect = connection_factory or get_connection
    with connect(env_path) as conn:
        with conn.cursor() as cur:
            upsert_topic_stock_extraction_rows(cur, rows, execute_values_fn=execute_values_fn)
    return len(rows)


def load_topic_stock_extractions(
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    *,
    connection_factory: Any = None,
) -> List[Dict[str, Any]]:
    normalized_group_id = normalize_group_id(group_id)
    conditions = ["group_id = %s"]
    params: List[Any] = [normalized_group_id]
    if start_date:
        conditions.append("topic_date >= %s::date")
        params.append(start_date)
    if end_date:
        conditions.append("topic_date <= %s::date")
        params.append(end_date)

    connect = connection_factory or get_connection
    with connect(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT group_id, topic_id, topic_date::text, stock_name, stock_code, market,
                       concepts_json, excerpt, reason, confidence, model, prompt_version, updated_at
                FROM {_core_table_ref(TOPIC_STOCK_EXTRACTIONS_TABLE)}
                WHERE {" AND ".join(conditions)}
                ORDER BY topic_date ASC, topic_id ASC, stock_name ASC
                """,
                params,
            )
            return [
                {
                    "group_id": str(row[0] or ""),
                    "topic_id": str(row[1] or ""),
                    "topic_date": str(row[2] or ""),
                    "stock_name": str(row[3] or ""),
                    "stock_code": str(row[4] or ""),
                    "market": str(row[5] or ""),
                    "concepts": [str(item) for item in parse_json_list(row[6]) if str(item).strip()],
                    "excerpt": str(row[7] or ""),
                    "reason": str(row[8] or ""),
                    "confidence": float(row[9] or 0),
                    "model": str(row[10] or ""),
                    "prompt_version": str(row[11] or ""),
                    "updated_at": row[12].isoformat() if hasattr(row[12], "isoformat") else str(row[12] or ""),
                }
                for row in cur.fetchall()
            ]


__all__ = [
    "DEFAULT_KNOW_ACTION_ENV_PATH",
    "TOPIC_STOCK_EXTRACTIONS_TABLE",
    "get_connection",
    "get_postgres_dsn",
    "load_topic_stock_extractions",
    "parse_json_list",
    "save_topic_stock_extractions",
    "upsert_topic_stock_extraction_rows",
]
