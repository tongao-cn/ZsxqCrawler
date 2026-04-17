"""PostgreSQL-backed storage for ZSXQ A-share analysis, reusing KnowActionSystem DB."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

import psycopg2
from psycopg2.extras import Json, execute_values


DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))

DAILY_MENTIONS_TABLE = "zsxq_a_share_daily_mentions"
PROCESSED_STATE_TABLE = "zsxq_a_share_processed_state"
TDX_EXPORTS_TABLE = "zsxq_a_share_tdx_exports"
TDX_EXPORT_BLOCKS_TABLE = "zsxq_a_share_tdx_export_blocks"
STOCK_BASIC_TABLE = "stock_basic"


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
    statements = [
        f"""
        CREATE TABLE IF NOT EXISTS {DAILY_MENTIONS_TABLE} (
            mention_date DATE NOT NULL,
            company TEXT NOT NULL,
            mentions_count INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (mention_date, company)
        )
        """,
        f"CREATE INDEX IF NOT EXISTS idx_{DAILY_MENTIONS_TABLE}_date ON {DAILY_MENTIONS_TABLE} (mention_date)",
        f"""
        CREATE TABLE IF NOT EXISTS {PROCESSED_STATE_TABLE} (
            source TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            day DATE NOT NULL,
            group_id TEXT,
            processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (source, topic_id, day)
        )
        """,
        f"CREATE INDEX IF NOT EXISTS idx_{PROCESSED_STATE_TABLE}_day ON {PROCESSED_STATE_TABLE} (day)",
        f"""
        CREATE TABLE IF NOT EXISTS {TDX_EXPORTS_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            exported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            start_date DATE,
            end_date DATE,
            tdx_root TEXT NOT NULL,
            ranking_top_n INTEGER NOT NULL,
            total_written INTEGER NOT NULL DEFAULT 0,
            unresolved_count INTEGER NOT NULL DEFAULT 0,
            stock_basic_source TEXT NOT NULL DEFAULT 'unknown',
            source_detail TEXT,
            backup_files JSONB NOT NULL DEFAULT '[]'::jsonb
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {TDX_EXPORT_BLOCKS_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            export_id BIGINT NOT NULL REFERENCES {TDX_EXPORTS_TABLE}(id) ON DELETE CASCADE,
            window_days INTEGER NOT NULL,
            block_name TEXT NOT NULL,
            block_code TEXT NOT NULL,
            block_path TEXT NOT NULL,
            written_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            skipped_companies JSONB NOT NULL DEFAULT '[]'::jsonb
        )
        """,
        f"CREATE INDEX IF NOT EXISTS idx_{TDX_EXPORT_BLOCKS_TABLE}_export_id ON {TDX_EXPORT_BLOCKS_TABLE} (export_id)",
    ]

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)


def get_storage_health(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Dict[str, Any]:
    ensure_analysis_tables(env_path)
    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            database_name = str(cur.fetchone()[0])
            cur.execute(f"SELECT COUNT(*) FROM {DAILY_MENTIONS_TABLE}")
            daily_rows = int(cur.fetchone()[0])
            cur.execute(f"SELECT COUNT(*) FROM {PROCESSED_STATE_TABLE}")
            processed_rows = int(cur.fetchone()[0])
            cur.execute(
                f"""
                SELECT GREATEST(
                    COALESCE(MAX(updated_at), TIMESTAMPTZ 'epoch'),
                    COALESCE((SELECT MAX(processed_at) FROM {PROCESSED_STATE_TABLE}), TIMESTAMPTZ 'epoch')
                )
                FROM {DAILY_MENTIONS_TABLE}
                """
            )
            latest_updated_at = cur.fetchone()[0]
    return {
        "enabled": True,
        "mode": "postgres_primary",
        "label": "KnowActionSystem PostgreSQL",
        "database_name": database_name,
        "daily_rows": daily_rows,
        "processed_rows": processed_rows,
        "latest_updated_at": latest_updated_at.isoformat() if latest_updated_at else None,
    }


def load_daily_mentions(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Dict[str, Dict[str, int]]:
    ensure_analysis_tables(env_path)
    daily: Dict[str, Dict[str, int]] = {}

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT mention_date::text, company, mentions_count
                FROM {DAILY_MENTIONS_TABLE}
                ORDER BY mention_date ASC, company ASC
                """
            )
            for day, company, mentions_count in cur.fetchall():
                daily.setdefault(str(day), {})[str(company)] = int(mentions_count or 0)
    return daily


def save_daily_mentions(
    daily: Dict[str, Dict[str, int]],
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> None:
    ensure_analysis_tables(env_path)

    rows: List[Tuple[str, str, int]] = []
    for day in sorted(daily.keys()):
        for company, count in sorted(daily[day].items(), key=lambda item: item[0]):
            rows.append((day, company, int(count or 0)))

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {DAILY_MENTIONS_TABLE}")
            if rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {DAILY_MENTIONS_TABLE} (mention_date, company, mentions_count, updated_at)
                    VALUES %s
                    """,
                    [(day, company, count, datetime.now()) for day, company, count in rows],
                    template="(%s::date, %s, %s, %s)",
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


def load_processed_state(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Set[str]:
    ensure_analysis_tables(env_path)
    processed: Set[str] = set()

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT source, topic_id, day::text
                FROM {PROCESSED_STATE_TABLE}
                ORDER BY day ASC, source ASC, topic_id ASC
                """
            )
            for source, topic_id, day in cur.fetchall():
                processed.add(f"{source}:{topic_id}:{day}")
    return processed


def save_processed_state(
    processed_keys: Iterable[str],
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> None:
    ensure_analysis_tables(env_path)

    rows: List[Tuple[str, str, str, Optional[str], datetime]] = []
    for key in sorted(set(processed_keys or [])):
        parsed = _parse_state_key(key)
        if parsed is None:
            continue
        source, topic_id, day = parsed
        rows.append((source, topic_id, day, None, datetime.now()))

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {PROCESSED_STATE_TABLE}")
            if rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {PROCESSED_STATE_TABLE} (source, topic_id, day, group_id, processed_at)
                    VALUES %s
                    """,
                    rows,
                    template="(%s, %s, %s::date, %s, %s)",
                )


def load_stock_basic_records(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> List[Dict[str, str]]:
    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT ts_code, symbol, name
                FROM {STOCK_BASIC_TABLE}
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
    ensure_analysis_tables(env_path)

    with get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TDX_EXPORTS_TABLE} (
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
                    INSERT INTO {TDX_EXPORT_BLOCKS_TABLE} (
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


def get_latest_tdx_export(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Optional[Dict[str, Any]]:
    ensure_analysis_tables(env_path)

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
                FROM {TDX_EXPORTS_TABLE}
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
                FROM {TDX_EXPORT_BLOCKS_TABLE}
                WHERE export_id = %s
                ORDER BY window_days ASC
                """,
                (export_id,),
            )
            blocks = [
                {
                    "window_days": int(window_days or 0),
                    "block_name": str(block_name or ""),
                    "block_code": str(block_code or ""),
                    "block_path": str(block_path or ""),
                    "written_count": int(written_count or 0),
                    "skipped_count": int(skipped_count or 0),
                    "skipped_companies": _normalize_json_value(skipped_companies, []),
                }
                for (
                    window_days,
                    block_name,
                    block_code,
                    block_path,
                    written_count,
                    skipped_count,
                    skipped_companies,
                ) in cur.fetchall()
            ]

    unresolved_companies: List[str] = []
    for block in blocks:
        unresolved_companies.extend(list(block.get("skipped_companies") or []))

    dedup_unresolved = sorted({str(company) for company in unresolved_companies if str(company).strip()})

    return {
        "export_id": int(export_id),
        "exported_at": exported_at.isoformat() if hasattr(exported_at, "isoformat") else str(exported_at),
        "start_date": start_date,
        "end_date": end_date,
        "tdx_root": str(tdx_root or ""),
        "ranking_top_n": int(ranking_top_n or 0),
        "total_written": int(total_written or 0),
        "unresolved_count": int(unresolved_count or 0),
        "unresolved_companies": dedup_unresolved,
        "stock_basic_source": str(stock_basic_source or ""),
        "source_detail": str(source_detail or ""),
        "backup_files": _normalize_json_value(backup_files, []),
        "blocks": blocks,
    }


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
