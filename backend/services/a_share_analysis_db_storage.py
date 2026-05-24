"""PostgreSQL-backed storage for ZSXQ A-share analysis."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

import psycopg2
from psycopg2.extras import Json, execute_values

from backend.storage.db_compat import get_postgres_dsn as get_zsxq_postgres_dsn
from backend.storage.postgres_core_schema import (
    CORE_SCHEMA,
    is_schema_missing_error,
    quote_identifier,
    schema_not_ready_message,
)


DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))

DAILY_MENTIONS_TABLE = "zsxq_a_share_daily_mentions"
PROCESSED_STATE_TABLE = "zsxq_a_share_processed_state"
TOPIC_STOCK_EXTRACTIONS_TABLE = "zsxq_a_share_topic_stock_extractions"
TDX_EXPORTS_TABLE = "zsxq_a_share_tdx_exports"
TDX_EXPORT_BLOCKS_TABLE = "zsxq_a_share_tdx_export_blocks"
STOCK_BASIC_TABLE = "stock_basic"


def _core_table_ref(table_name: str) -> str:
    return f"{quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)}"


def _public_table_ref(table_name: str) -> str:
    return f"{quote_identifier('public')}.{quote_identifier(table_name)}"


def _normalize_group_id(group_id: Optional[str]) -> str:
    return str(group_id or "").strip()


def _load_env_file(path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _resolve_setting(key: str, env_values: Dict[str, str]) -> str:
    return (os.getenv(key) or env_values.get(key) or "").strip()


def get_postgres_dsn(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> str:
    zsxq_dsn = get_zsxq_postgres_dsn()
    if zsxq_dsn:
        return zsxq_dsn

    raise RuntimeError("未找到 ZsxqCrawler PostgreSQL DSN，请设置 ZSXQ_POSTGRES_DSN 或 config.toml [database].postgres_dsn")


def get_stock_basic_postgres_dsn(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> str:
    zsxq_dsn = get_zsxq_postgres_dsn()
    if zsxq_dsn:
        return zsxq_dsn

    env_values = _load_env_file(env_path)
    host = _resolve_setting("DB_HOST", env_values)
    port = _resolve_setting("DB_PORT", env_values) or "5432"
    name = _resolve_setting("DB_NAME", env_values)
    user = _resolve_setting("DB_USER", env_values)
    password = _resolve_setting("DB_PASSWORD", env_values)

    if not all([host, port, name, user]):
        raise RuntimeError(
            "未找到 KnowActionSystem PostgreSQL 配置，请检查环境变量或 C:\\Dev\\KnowActionSystem\\.env"
        )

    return f"dbname={name} user={user} password={password} host={host} port={port}"


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


def ensure_analysis_tables(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> None:
    """Schema is managed by manage-postgres-core-schema; runtime DDL is disabled."""
    return None


def get_storage_health(
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_group_id = _normalize_group_id(group_id)
    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            database_name = str(cur.fetchone()[0])
            cur.execute(
                f"SELECT COUNT(*) FROM {_core_table_ref(DAILY_MENTIONS_TABLE)} WHERE group_id = %s",
                (normalized_group_id,),
            )
            daily_rows = int(cur.fetchone()[0])
            cur.execute(
                f"SELECT COUNT(*) FROM {_core_table_ref(PROCESSED_STATE_TABLE)} WHERE group_id = %s",
                (normalized_group_id,),
            )
            processed_rows = int(cur.fetchone()[0])
            cur.execute(
                f"""
                SELECT GREATEST(
                    COALESCE(MAX(updated_at), TIMESTAMPTZ 'epoch'),
                    COALESCE((
                        SELECT MAX(processed_at)
                        FROM {_core_table_ref(PROCESSED_STATE_TABLE)}
                        WHERE group_id = %s
                    ), TIMESTAMPTZ 'epoch')
                )
                FROM {_core_table_ref(DAILY_MENTIONS_TABLE)}
                WHERE group_id = %s
                """,
                (normalized_group_id, normalized_group_id),
            )
            latest_updated_at = cur.fetchone()[0]
    return {
        "enabled": True,
        "mode": "postgres_primary",
        "label": f"ZsxqCrawler PostgreSQL {CORE_SCHEMA}",
        "database_name": database_name,
        "group_id": normalized_group_id or None,
        "daily_rows": daily_rows,
        "processed_rows": processed_rows,
        "latest_updated_at": latest_updated_at.isoformat() if latest_updated_at else None,
    }


def load_daily_mentions(
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
) -> Dict[str, Dict[str, int]]:
    normalized_group_id = _normalize_group_id(group_id)
    daily: Dict[str, Dict[str, int]] = {}

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT mention_date::text, company, mentions_count
                FROM {_core_table_ref(DAILY_MENTIONS_TABLE)}
                WHERE group_id = %s
                ORDER BY mention_date ASC, company ASC
                """,
                (normalized_group_id,),
            )
            for day, company, mentions_count in cur.fetchall():
                daily.setdefault(str(day), {})[str(company)] = int(mentions_count or 0)
    return daily


def save_daily_mentions(
    daily: Dict[str, Dict[str, int]],
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
) -> None:
    normalized_group_id = _normalize_group_id(group_id)

    rows: List[Tuple[str, str, int]] = []
    for day in sorted(daily.keys()):
        for company, count in sorted(daily[day].items(), key=lambda item: item[0]):
            rows.append((day, company, int(count or 0)))

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {_core_table_ref(DAILY_MENTIONS_TABLE)} WHERE group_id = %s", (normalized_group_id,))
            if rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {_core_table_ref(DAILY_MENTIONS_TABLE)} (group_id, mention_date, company, mentions_count, updated_at)
                    VALUES %s
                    """,
                    [(normalized_group_id, day, company, count, datetime.now()) for day, company, count in rows],
                    template="(%s, %s::date, %s, %s, %s)",
                )


def save_topic_stock_extractions(
    extractions: Sequence[Dict[str, Any]],
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
) -> int:
    rows = _build_topic_stock_extraction_rows(extractions, group_id, datetime.now())

    if not rows:
        return 0

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            execute_values(
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
    return len(rows)


def _build_topic_stock_extraction_rows(
    extractions: Sequence[Dict[str, Any]],
    group_id: Optional[str],
    now: datetime,
) -> List[Tuple[str, str, str, str, str, str, str, str, str, float, str, str, datetime]]:
    normalized_group_id = _normalize_group_id(group_id)
    rows: List[Tuple[str, str, str, str, str, str, str, str, str, float, str, str, datetime]] = []
    for item in extractions:
        stock_name = str(item.get("stock_name") or "").strip()
        topic_id = str(item.get("topic_id") or "").strip()
        topic_date = str(item.get("topic_date") or item.get("day") or "").strip()
        if not stock_name or not topic_id or not topic_date:
            continue
        rows.append(
            (
                str(item.get("group_id") or normalized_group_id),
                topic_id,
                topic_date,
                stock_name,
                str(item.get("stock_code") or ""),
                str(item.get("market") or ""),
                json.dumps(list(item.get("concepts") or []), ensure_ascii=False),
                str(item.get("excerpt") or ""),
                str(item.get("reason") or ""),
                float(item.get("confidence") or 0),
                str(item.get("model") or ""),
                str(item.get("prompt_version") or ""),
                now,
            )
        )
    return rows


def _build_processed_state_rows(
    processed_keys: Iterable[str],
    group_id: Optional[str],
    now: datetime,
) -> List[Tuple[str, str, str, str, datetime]]:
    normalized_group_id = _normalize_group_id(group_id)
    rows: List[Tuple[str, str, str, str, datetime]] = []
    for key in sorted(set(processed_keys or [])):
        parsed = _parse_state_key(key)
        if parsed is None:
            continue
        source, topic_id, day = parsed
        rows.append((normalized_group_id, source, topic_id, day, now))
    return rows


def save_recommendation_pool_checkpoint(
    *,
    daily_delta: Dict[str, Dict[str, int]],
    processed_keys: Iterable[str],
    topic_stock_extractions: Sequence[Dict[str, Any]],
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
) -> Dict[str, int]:
    normalized_group_id = _normalize_group_id(group_id)
    now = datetime.now()
    mention_rows: List[Tuple[str, str, str, int, datetime]] = []
    for day in sorted(daily_delta.keys()):
        for company, count in sorted(daily_delta[day].items(), key=lambda item: item[0]):
            mention_count = int(count or 0)
            if not company or mention_count <= 0:
                continue
            mention_rows.append((normalized_group_id, day, company, mention_count, now))

    extraction_rows = _build_topic_stock_extraction_rows(topic_stock_extractions, normalized_group_id, now)
    state_rows = _build_processed_state_rows(processed_keys, normalized_group_id, now)

    if not mention_rows and not extraction_rows and not state_rows:
        return {"daily_mentions": 0, "topic_stock_extractions": 0, "processed_state": 0}

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            if extraction_rows:
                execute_values(
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
                    extraction_rows,
                    template="(%s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                )
            if mention_rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {_core_table_ref(DAILY_MENTIONS_TABLE)}
                        (group_id, mention_date, company, mentions_count, updated_at)
                    VALUES %s
                    ON CONFLICT (group_id, mention_date, company) DO UPDATE SET
                        mentions_count = {_core_table_ref(DAILY_MENTIONS_TABLE)}.mentions_count + excluded.mentions_count,
                        updated_at = excluded.updated_at
                    """,
                    mention_rows,
                    template="(%s, %s::date, %s, %s, %s)",
                )
            if state_rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {_core_table_ref(PROCESSED_STATE_TABLE)} (group_id, source, topic_id, day, processed_at)
                    VALUES %s
                    ON CONFLICT (group_id, source, topic_id, day) DO UPDATE SET
                        processed_at = excluded.processed_at
                    """,
                    state_rows,
                    template="(%s, %s, %s, %s::date, %s)",
                )
    return {
        "daily_mentions": len(mention_rows),
        "topic_stock_extractions": len(extraction_rows),
        "processed_state": len(state_rows),
    }


def _parse_json_list(value: Any) -> List[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def load_topic_stock_extractions(
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    normalized_group_id = _normalize_group_id(group_id)
    conditions = ["group_id = %s"]
    params: List[Any] = [normalized_group_id]
    if start_date:
        conditions.append("topic_date >= %s::date")
        params.append(start_date)
    if end_date:
        conditions.append("topic_date <= %s::date")
        params.append(end_date)

    with get_connection(env_path) as conn:
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
                    "concepts": [str(item) for item in _parse_json_list(row[6]) if str(item).strip()],
                    "excerpt": str(row[7] or ""),
                    "reason": str(row[8] or ""),
                    "confidence": float(row[9] or 0),
                    "model": str(row[10] or ""),
                    "prompt_version": str(row[11] or ""),
                    "updated_at": row[12].isoformat() if hasattr(row[12], "isoformat") else str(row[12] or ""),
                }
                for row in cur.fetchall()
            ]


def _parse_state_key(key: str) -> Optional[Tuple[str, str, str]]:
    parts = str(key or "").split(":")
    if len(parts) < 3:
        return None
    source = parts[0].strip()
    topic_id = parts[1].strip()
    day = parts[-1].strip()
    if not source or not topic_id or len(day) != 10:
        return None
    return source, topic_id, day


def load_processed_state(
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
) -> Set[str]:
    normalized_group_id = _normalize_group_id(group_id)
    processed: Set[str] = set()

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT source, topic_id, day::text
                FROM {_core_table_ref(PROCESSED_STATE_TABLE)}
                WHERE group_id = %s
                ORDER BY day ASC, source ASC, topic_id ASC
                """,
                (normalized_group_id,),
            )
            for source, topic_id, day in cur.fetchall():
                processed.add(f"{source}:{topic_id}:{day}")
    return processed


def save_processed_state(
    processed_keys: Iterable[str],
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
) -> None:
    normalized_group_id = _normalize_group_id(group_id)

    rows: List[Tuple[str, str, str, str, datetime]] = []
    for key in sorted(set(processed_keys or [])):
        parsed = _parse_state_key(key)
        if parsed is None:
            continue
        source, topic_id, day = parsed
        rows.append((normalized_group_id, source, topic_id, day, datetime.now()))

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {_core_table_ref(PROCESSED_STATE_TABLE)} WHERE group_id = %s", (normalized_group_id,))
            if rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {_core_table_ref(PROCESSED_STATE_TABLE)} (group_id, source, topic_id, day, processed_at)
                    VALUES %s
                    """,
                    rows,
                    template="(%s, %s, %s, %s::date, %s)",
                )


def reset_a_share_analysis_range(
    start_date: str,
    end_date: str,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    group_id: Optional[str] = None,
) -> Dict[str, int]:
    normalized_group_id = _normalize_group_id(group_id)
    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT topic_id
                FROM {_core_table_ref(TOPIC_STOCK_EXTRACTIONS_TABLE)}
                WHERE group_id = %s
                  AND topic_date BETWEEN %s::date AND %s::date
                """,
                (normalized_group_id, start_date, end_date),
            )
            topic_ids = [str(row[0]).strip() for row in cur.fetchall() if row and str(row[0]).strip()]
            cur.execute(
                f"DELETE FROM {_core_table_ref(DAILY_MENTIONS_TABLE)} WHERE group_id = %s AND mention_date BETWEEN %s::date AND %s::date",
                (normalized_group_id, start_date, end_date),
            )
            daily_deleted = int(getattr(cur, "rowcount", 0) or 0)
            cur.execute(
                f"DELETE FROM {_core_table_ref(PROCESSED_STATE_TABLE)} WHERE group_id = %s AND day BETWEEN %s::date AND %s::date",
                (normalized_group_id, start_date, end_date),
            )
            processed_deleted = int(getattr(cur, "rowcount", 0) or 0)
            cur.execute(
                f"DELETE FROM {_core_table_ref(TOPIC_STOCK_EXTRACTIONS_TABLE)} WHERE group_id = %s AND topic_date BETWEEN %s::date AND %s::date",
                (normalized_group_id, start_date, end_date),
            )
            extractions_deleted = int(getattr(cur, "rowcount", 0) or 0)
            stock_states_deleted = 0
            if topic_ids:
                cur.execute(
                    f"DELETE FROM {_core_table_ref('stock_topic_processed_states')} WHERE group_id = %s AND topic_id = ANY(%s::text[])",
                    (normalized_group_id, topic_ids),
                )
                stock_states_deleted = int(getattr(cur, "rowcount", 0) or 0)
            stock_analyses_deleted = 0
            if topic_ids:
                cur.execute(
                    f"""
                    DELETE FROM {_core_table_ref('stock_topic_analyses')}
                    WHERE group_id = %s
                      AND COALESCE(NULLIF(topic_ids_json, ''), '[]')::jsonb ?| %s::text[]
                    """,
                    (normalized_group_id, topic_ids),
                )
                stock_analyses_deleted = int(getattr(cur, "rowcount", 0) or 0)
            stock_analysis_versions_deleted = 0
            if topic_ids:
                cur.execute(
                    f"""
                    DELETE FROM {_core_table_ref('stock_topic_analysis_versions')}
                    WHERE group_id = %s
                      AND COALESCE(NULLIF(topic_ids_json, ''), '[]')::jsonb ?| %s::text[]
                    """,
                    (normalized_group_id, topic_ids),
                )
                stock_analysis_versions_deleted = int(getattr(cur, "rowcount", 0) or 0)
    return {
        "daily_mentions": daily_deleted,
        "processed_state": processed_deleted,
        "topic_stock_extractions": extractions_deleted,
        "stock_topic_processed_states": stock_states_deleted,
        "stock_topic_analyses": stock_analyses_deleted,
        "stock_topic_analysis_versions": stock_analysis_versions_deleted,
    }


def load_stock_basic_records(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> List[Dict[str, str]]:
    with psycopg2.connect(get_stock_basic_postgres_dsn(env_path)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT ts_code, symbol, name
                FROM {_public_table_ref(STOCK_BASIC_TABLE)}
                ORDER BY ts_code ASC
                """
            )
            return [
                {
                    "ts_code": str(ts_code),
                    "symbol": str(symbol or ""),
                    "name": str(name or ""),
                }
                for ts_code, symbol, name in cur.fetchall()
                if ts_code and name
            ]


def log_tdx_export(
    *,
    start_date: Optional[str],
    end_date: Optional[str],
    tdx_root: str,
    ranking_top_n: int,
    total_written: int,
    unresolved_companies: Sequence[str],
    backup_files: Sequence[str],
    stock_basic_source: str,
    source_detail: Optional[str],
    blocks: Sequence[Dict[str, Any]],
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> int:
    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_core_table_ref(TDX_EXPORTS_TABLE)} (
                    start_date,
                    end_date,
                    tdx_root,
                    ranking_top_n,
                    total_written,
                    unresolved_count,
                    stock_basic_source,
                    source_detail,
                    backup_files
                )
                VALUES (%s::date, %s::date, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    start_date,
                    end_date,
                    tdx_root,
                    int(ranking_top_n),
                    int(total_written),
                    len(list(unresolved_companies or [])),
                    stock_basic_source,
                    source_detail,
                    Json(list(backup_files or [])),
                ),
            )
            export_id = int(cur.fetchone()[0])

            block_rows: List[Tuple[int, int, str, str, str, int, int, Json]] = []
            for block in blocks:
                block_rows.append(
                    (
                        export_id,
                        int(block.get("window_days") or 0),
                        str(block.get("block_name") or ""),
                        str(block.get("block_code") or ""),
                        str(block.get("block_path") or ""),
                        int(block.get("written_count") or 0),
                        int(block.get("skipped_count") or 0),
                        Json(list(block.get("skipped_companies") or [])),
                    )
                )

            if block_rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {_core_table_ref(TDX_EXPORT_BLOCKS_TABLE)} (
                        export_id,
                        window_days,
                        block_name,
                        block_code,
                        block_path,
                        written_count,
                        skipped_count,
                        skipped_companies
                    )
                    VALUES %s
                    """,
                    block_rows,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s)",
                )
    return export_id


def _normalize_json_value(value: Any, default: Any):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return default


def _tdx_export_block_payload(row: Sequence[Any]) -> Dict[str, Any]:
    (
        window_days,
        block_name,
        block_code,
        block_path,
        written_count,
        skipped_count,
        skipped_companies,
    ) = row
    return {
        "window_days": int(window_days or 0),
        "block_name": str(block_name or ""),
        "block_code": str(block_code or ""),
        "block_path": str(block_path or ""),
        "written_count": int(written_count or 0),
        "skipped_count": int(skipped_count or 0),
        "skipped_companies": _normalize_json_value(skipped_companies, []),
    }


def _dedupe_company_names(values: Iterable[Any]) -> List[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def _latest_tdx_export_payload(row: Sequence[Any], blocks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    (
        export_id,
        exported_at,
        start_date,
        end_date,
        tdx_root,
        ranking_top_n,
        total_written,
        unresolved_count,
        stock_basic_source,
        source_detail,
        backup_files,
    ) = row

    unresolved_companies: List[Any] = []
    for block in blocks:
        unresolved_companies.extend(list(block.get("skipped_companies") or []))

    return {
        "export_id": int(export_id),
        "exported_at": exported_at.isoformat() if hasattr(exported_at, "isoformat") else str(exported_at),
        "start_date": start_date,
        "end_date": end_date,
        "tdx_root": str(tdx_root or ""),
        "ranking_top_n": int(ranking_top_n or 0),
        "total_written": int(total_written or 0),
        "unresolved_count": int(unresolved_count or 0),
        "unresolved_companies": _dedupe_company_names(unresolved_companies),
        "stock_basic_source": str(stock_basic_source or ""),
        "source_detail": str(source_detail or ""),
        "backup_files": _normalize_json_value(backup_files, []),
        "blocks": list(blocks),
    }


def get_latest_tdx_export(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    exported_at,
                    start_date::text,
                    end_date::text,
                    tdx_root,
                    ranking_top_n,
                    total_written,
                    unresolved_count,
                    stock_basic_source,
                    source_detail,
                    backup_files
                FROM {_core_table_ref(TDX_EXPORTS_TABLE)}
                ORDER BY exported_at DESC, id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                return None

            (
                export_id,
                exported_at,
                start_date,
                end_date,
                tdx_root,
                ranking_top_n,
                total_written,
                unresolved_count,
                stock_basic_source,
                source_detail,
                backup_files,
            ) = row

            cur.execute(
                f"""
                SELECT
                    window_days,
                    block_name,
                    block_code,
                    block_path,
                    written_count,
                    skipped_count,
                    skipped_companies
                FROM {_core_table_ref(TDX_EXPORT_BLOCKS_TABLE)}
                WHERE export_id = %s
                ORDER BY window_days ASC
                """,
                (export_id,),
            )
            blocks = [
                _tdx_export_block_payload(block_row)
                for block_row in cur.fetchall()
            ]

    return _latest_tdx_export_payload(row, blocks)


__all__ = [
    "DEFAULT_KNOW_ACTION_ENV_PATH",
    "DAILY_MENTIONS_TABLE",
    "PROCESSED_STATE_TABLE",
    "TOPIC_STOCK_EXTRACTIONS_TABLE",
    "TDX_EXPORTS_TABLE",
    "TDX_EXPORT_BLOCKS_TABLE",
    "ensure_analysis_tables",
    "get_storage_health",
    "get_latest_tdx_export",
    "load_daily_mentions",
    "load_processed_state",
    "load_stock_basic_records",
    "load_topic_stock_extractions",
    "log_tdx_export",
    "save_daily_mentions",
    "save_processed_state",
    "save_recommendation_pool_checkpoint",
    "save_topic_stock_extractions",
]
