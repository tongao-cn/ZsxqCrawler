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
from backend.storage.postgres_core_schema import CORE_SCHEMA, quote_identifier


DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))

DAILY_MENTIONS_TABLE = "zsxq_a_share_daily_mentions"
PROCESSED_STATE_TABLE = "zsxq_a_share_processed_state"
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
    except Exception:
        conn.rollback()
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
    "TDX_EXPORTS_TABLE",
    "TDX_EXPORT_BLOCKS_TABLE",
    "ensure_analysis_tables",
    "get_storage_health",
    "get_latest_tdx_export",
    "load_daily_mentions",
    "load_processed_state",
    "load_stock_basic_records",
    "log_tdx_export",
    "save_daily_mentions",
    "save_processed_state",
]
