"""A-share research return smoke backed by KnowActionSystem quotes."""

from __future__ import annotations

import csv
import json
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import psycopg2

from backend.services.a_share_analysis_service import (
    DEFAULT_RANKING_TOP_N,
    DEFAULT_RANKING_WINDOWS,
    normalize_group_id,
    read_existing_csv,
)
from backend.services.a_share_pool_rotation_backtest import (
    DEFAULT_POOL_ROTATION_DAILY_FIELDS,
    DEFAULT_POOL_ROTATION_PERIOD_FIELDS,
    build_pool_rotation_daily_rows,
    build_recommendation_pool_memberships as _build_recommendation_pool_memberships,
    pool_quote_range_bounds as _pool_quote_range_bounds,
    summarize_pool_rotation_backtest,
    summarize_pool_rotation_period_returns,
)
from backend.services.a_share_research_export_service import load_a_share_research_dataset
from backend.services.a_share_return_smoke_backtest import (
    DEFAULT_RETURN_HOLD_DAYS,
    DEFAULT_RETURN_SMOKE_FIELDS,
    build_return_smoke_rows,
    return_smoke_quote_range_bounds as _quote_range_bounds,
    summarize_return_smoke,
)
from backend.services.a_share_signal_codes import (
    build_stock_basic_index,
    resolve_signal_ts_code,
)


DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))
DEFAULT_POOL_ROTATION_WINDOWS = DEFAULT_RANKING_WINDOWS
DEFAULT_POOL_ROTATION_TOP_N = DEFAULT_RANKING_TOP_N
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


def run_a_share_return_smoke(
    *,
    group_id: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    hold_days: int = DEFAULT_RETURN_HOLD_DAYS,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    signal_rows = load_a_share_research_dataset(group_id=group_id, start_date=start_date, end_date=end_date)
    if not signal_rows:
        return [], summarize_return_smoke([])

    stock_basic_index = load_knowaction_stock_basic_index(env_path)
    signal_with_codes = [
        {**row, "ts_code": resolve_signal_ts_code(row, stock_basic_index)}
        for row in signal_rows
    ]
    quote_start, quote_end = _quote_range_bounds(signal_with_codes, hold_days)
    quotes = load_knowaction_quotes(
        [row["ts_code"] for row in signal_with_codes],
        quote_start,
        quote_end,
        env_path,
    )
    rows = build_return_smoke_rows(
        signal_with_codes,
        quotes,
        stock_basic_index=stock_basic_index,
        hold_days=hold_days,
    )
    return rows, summarize_return_smoke(rows)


def build_recommendation_pool_memberships(
    daily_mentions: Mapping[str, Mapping[str, int]],
    *,
    group_id: Any = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    windows: Sequence[int] = DEFAULT_POOL_ROTATION_WINDOWS,
    ranking_top_n: int = DEFAULT_POOL_ROTATION_TOP_N,
) -> List[Dict[str, Any]]:
    return _build_recommendation_pool_memberships(
        daily_mentions,
        group_id=group_id,
        start_date=start_date,
        end_date=end_date,
        windows=windows,
        ranking_top_n=ranking_top_n,
    )


def run_recommendation_pool_rotation_backtest(
    *,
    group_id: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    windows: Sequence[int] = DEFAULT_POOL_ROTATION_WINDOWS,
    ranking_top_n: int = DEFAULT_POOL_ROTATION_TOP_N,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    normalized_group_id = normalize_group_id(group_id)
    if not normalized_group_id:
        raise ValueError("group_id 不能为空")

    daily_mentions = read_existing_csv(group_id=normalized_group_id)
    membership_rows = build_recommendation_pool_memberships(
        daily_mentions,
        group_id=normalized_group_id,
        start_date=start_date,
        end_date=end_date,
        windows=windows,
        ranking_top_n=ranking_top_n,
    )
    if not membership_rows:
        empty_summary = summarize_pool_rotation_backtest([])
        return [], [], empty_summary

    stock_basic_index = load_knowaction_stock_basic_index(env_path)
    membership_with_codes = [
        {**row, "ts_code": resolve_signal_ts_code(row, stock_basic_index)}
        for row in membership_rows
    ]
    quote_start, quote_end = _pool_quote_range_bounds(membership_with_codes)
    trade_dates = load_knowaction_trade_dates(quote_start, quote_end, env_path=env_path)
    quotes = load_knowaction_quotes(
        [row["ts_code"] for row in membership_with_codes],
        quote_start,
        quote_end,
        env_path,
    )
    daily_rows = build_pool_rotation_daily_rows(
        membership_with_codes,
        quotes,
        trade_dates=trade_dates,
        stock_basic_index=stock_basic_index,
    )
    period_rows = summarize_pool_rotation_period_returns(daily_rows)
    return daily_rows, period_rows, summarize_pool_rotation_backtest(daily_rows)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_return_smoke_csv(rows: Iterable[Mapping[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DEFAULT_RETURN_SMOKE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in DEFAULT_RETURN_SMOKE_FIELDS})
    return path


def write_pool_rotation_daily_csv(rows: Iterable[Mapping[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DEFAULT_POOL_ROTATION_DAILY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in DEFAULT_POOL_ROTATION_DAILY_FIELDS})
    return path


def write_pool_rotation_period_csv(rows: Iterable[Mapping[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DEFAULT_POOL_ROTATION_PERIOD_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in DEFAULT_POOL_ROTATION_PERIOD_FIELDS})
    return path


__all__ = [
    "DEFAULT_POOL_ROTATION_DAILY_FIELDS",
    "DEFAULT_POOL_ROTATION_PERIOD_FIELDS",
    "DEFAULT_POOL_ROTATION_TOP_N",
    "DEFAULT_POOL_ROTATION_WINDOWS",
    "DEFAULT_RETURN_HOLD_DAYS",
    "DEFAULT_RETURN_SMOKE_FIELDS",
    "DEFAULT_TRADE_CALENDAR_EXCHANGE",
    "build_pool_rotation_daily_rows",
    "build_recommendation_pool_memberships",
    "build_return_smoke_rows",
    "get_knowaction_postgres_dsn",
    "load_knowaction_trade_dates",
    "resolve_signal_ts_code",
    "run_recommendation_pool_rotation_backtest",
    "run_a_share_return_smoke",
    "summarize_pool_rotation_backtest",
    "summarize_pool_rotation_period_returns",
    "summarize_return_smoke",
    "write_pool_rotation_daily_csv",
    "write_pool_rotation_period_csv",
    "write_return_smoke_csv",
]
