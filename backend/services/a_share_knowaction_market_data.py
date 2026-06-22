"""KnowAction market data reader for A-share research workflows."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Sequence

import psycopg2

from backend.services.a_share_signal_codes import build_stock_basic_index


DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))
DEFAULT_TRADE_CALENDAR_EXCHANGE = "SSE"


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


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


def _resolve_setting(key: str, env_values: Mapping[str, str]) -> str:
    return _normalize_text(os.getenv(key) or env_values.get(key))


def get_knowaction_postgres_dsn(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> str:
    direct_dsn = _normalize_text(os.getenv("KNOW_ACTION_POSTGRES_DSN") or os.getenv("KNOWACTION_POSTGRES_DSN"))
    if direct_dsn:
        return direct_dsn

    env_values = _load_env_file(env_path)
    host = _resolve_setting("DB_HOST", env_values)
    port = _resolve_setting("DB_PORT", env_values) or "5432"
    name = _resolve_setting("DB_NAME", env_values)
    user = _resolve_setting("DB_USER", env_values)
    password = _resolve_setting("DB_PASSWORD", env_values)
    if not all([host, port, name, user]):
        raise RuntimeError("未找到 KnowActionSystem PostgreSQL 配置，请检查 KNOW_ACTION_ENV_PATH 或 C:\\Dev\\KnowActionSystem\\.env")
    return f"dbname={name} user={user} password={password} host={host} port={port}"


@contextmanager
def get_knowaction_connection(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Iterator[Any]:
    conn = psycopg2.connect(get_knowaction_postgres_dsn(env_path))
    try:
        yield conn
    finally:
        conn.close()


def load_knowaction_stock_basic_index(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Dict[str, str]:
    with get_knowaction_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ts_code, symbol, name
                FROM stock_basic
                ORDER BY ts_code ASC
                """
            )
            rows = cur.fetchall()

    return build_stock_basic_index(rows)


def load_knowaction_quotes(
    ts_codes: Sequence[str],
    start_date: date,
    end_date: date,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> List[Dict[str, Any]]:
    normalized_ts_codes = sorted({_normalize_text(code).upper() for code in ts_codes if _normalize_text(code)})
    if not normalized_ts_codes:
        return []

    with get_knowaction_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ts_code, trade_date, open, close, vol, amount
                FROM daily_quotes
                WHERE ts_code = ANY(%s)
                  AND trade_date >= %s
                  AND trade_date <= %s
                ORDER BY ts_code ASC, trade_date ASC
                """,
                (normalized_ts_codes, start_date, end_date),
            )
            return [
                {
                    "ts_code": _normalize_text(row[0]).upper(),
                    "trade_date": row[1].isoformat() if hasattr(row[1], "isoformat") else _normalize_text(row[1]),
                    "open": _safe_float(row[2]),
                    "close": _safe_float(row[3]),
                    "vol": _safe_float(row[4]),
                    "amount": _safe_float(row[5]),
                }
                for row in cur.fetchall()
            ]


def load_knowaction_trade_dates(
    start_date: date,
    end_date: date,
    *,
    exchange: str = DEFAULT_TRADE_CALENDAR_EXCHANGE,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> List[str]:
    normalized_exchange = _normalize_text(exchange).upper() or DEFAULT_TRADE_CALENDAR_EXCHANGE
    with get_knowaction_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cal_date
                FROM trade_calendar
                WHERE exchange = %s
                  AND cal_date >= %s
                  AND cal_date <= %s
                  AND is_open = 1
                ORDER BY cal_date ASC
                """,
                (normalized_exchange, start_date, end_date),
            )
            return [
                row[0].isoformat() if hasattr(row[0], "isoformat") else _normalize_text(row[0])
                for row in cur.fetchall()
            ]
