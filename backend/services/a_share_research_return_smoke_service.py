"""A-share research return smoke backed by KnowActionSystem quotes."""

from __future__ import annotations

import csv
import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import psycopg2

from backend.services.a_share_research_export_service import load_a_share_research_dataset


DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))
DEFAULT_RETURN_HOLD_DAYS = 5
DEFAULT_RETURN_SMOKE_FIELDS = [
    "group_id",
    "signal_date",
    "stock_name",
    "stock_code",
    "market",
    "ts_code",
    "mention_count",
    "topic_count",
    "concepts",
    "avg_confidence",
    "max_confidence",
    "hold_days",
    "entry_date",
    "exit_date",
    "entry_open",
    "exit_close",
    "gross_return",
    "status",
]


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _parse_day(value: Any, field_name: str) -> date:
    try:
        return datetime.strptime(_normalize_text(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD 格式") from exc


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


def _company_key(value: Any) -> str:
    return (
        _normalize_text(value)
        .replace(" ", "")
        .replace("*", "")
        .replace("股份有限公司", "")
        .replace("有限责任公司", "")
        .replace("有限公司", "")
        .replace("集团", "")
    )


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

    lookup: Dict[str, str] = {}
    duplicates = set()
    for ts_code, symbol, name in rows:
        normalized_ts_code = _normalize_text(ts_code).upper()
        if not normalized_ts_code:
            continue
        keys = {_company_key(name), _normalize_text(symbol)}
        for key in keys:
            if not key:
                continue
            if key in lookup and lookup[key] != normalized_ts_code:
                duplicates.add(key)
                continue
            lookup[key] = normalized_ts_code
    for key in duplicates:
        lookup.pop(key, None)
    return lookup


def _infer_market_from_symbol(symbol: str) -> str:
    if symbol.startswith("6"):
        return "SH"
    if symbol.startswith(("0", "3")):
        return "SZ"
    if symbol.startswith(("4", "8", "9")):
        return "BJ"
    return ""


def resolve_signal_ts_code(signal: Mapping[str, Any], stock_basic_index: Mapping[str, str] | None = None) -> str:
    raw_ts_code = _normalize_text(signal.get("ts_code")).upper()
    if "." in raw_ts_code:
        return raw_ts_code

    stock_code = _normalize_text(signal.get("stock_code") or signal.get("symbol")).upper()
    if "." in stock_code:
        return stock_code
    market = _normalize_text(signal.get("market")).upper()
    if stock_code and not market:
        market = _infer_market_from_symbol(stock_code)
    if stock_code and market:
        return f"{stock_code}.{market}"

    lookup = stock_basic_index or {}
    return lookup.get(_company_key(signal.get("stock_name")), "")


def _quote_range_bounds(signal_rows: Sequence[Mapping[str, Any]], hold_days: int) -> Tuple[date, date]:
    signal_dates = [_parse_day(row.get("signal_date"), "signal_date") for row in signal_rows if row.get("signal_date")]
    if not signal_dates:
        raise ValueError("没有可用于收益 smoke 的 signal_date")
    start_date = min(signal_dates)
    end_date = max(signal_dates) + timedelta(days=max(hold_days, 1) * 3 + 10)
    return start_date, end_date


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


def _is_tradable_quote(quote: Mapping[str, Any]) -> bool:
    return _safe_float(quote.get("close")) > 0 and (_safe_float(quote.get("amount")) > 0 or _safe_float(quote.get("vol")) > 0)


def _is_tradable_entry_quote(quote: Mapping[str, Any]) -> bool:
    return _is_tradable_quote(quote) and _safe_float(quote.get("open")) > 0


def _quotes_by_ts_code(quote_rows: Iterable[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for raw in quote_rows:
        ts_code = _normalize_text(raw.get("ts_code")).upper()
        trade_date = _normalize_text(raw.get("trade_date"))
        if not ts_code or not trade_date:
            continue
        grouped.setdefault(ts_code, []).append(
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "open": _safe_float(raw.get("open")),
                "close": _safe_float(raw.get("close")),
                "vol": _safe_float(raw.get("vol")),
                "amount": _safe_float(raw.get("amount")),
            }
        )
    for rows in grouped.values():
        rows.sort(key=lambda item: item["trade_date"])
    return grouped


def build_return_smoke_rows(
    signal_rows: Iterable[Mapping[str, Any]],
    quote_rows: Iterable[Mapping[str, Any]],
    *,
    stock_basic_index: Mapping[str, str] | None = None,
    hold_days: int = DEFAULT_RETURN_HOLD_DAYS,
) -> List[Dict[str, Any]]:
    normalized_hold_days = max(1, int(hold_days))
    grouped_quotes = _quotes_by_ts_code(quote_rows)
    results: List[Dict[str, Any]] = []

    for signal in signal_rows:
        ts_code = resolve_signal_ts_code(signal, stock_basic_index)
        signal_date_text = _normalize_text(signal.get("signal_date"))
        base = {
            "group_id": _normalize_text(signal.get("group_id")),
            "signal_date": signal_date_text,
            "stock_name": _normalize_text(signal.get("stock_name")),
            "stock_code": _normalize_text(signal.get("stock_code")),
            "market": _normalize_text(signal.get("market")).upper(),
            "ts_code": ts_code,
            "mention_count": _safe_int(signal.get("mention_count")),
            "topic_count": _safe_int(signal.get("topic_count")),
            "concepts": signal.get("concepts") or [],
            "avg_confidence": _safe_float(signal.get("avg_confidence")),
            "max_confidence": _safe_float(signal.get("max_confidence")),
            "hold_days": normalized_hold_days,
            "entry_date": "",
            "exit_date": "",
            "entry_open": "",
            "exit_close": "",
            "gross_return": "",
            "status": "",
        }
        if not ts_code:
            results.append({**base, "status": "skipped_unresolved_ts_code"})
            continue
        try:
            signal_date = _parse_day(signal_date_text, "signal_date")
        except ValueError:
            results.append({**base, "status": "skipped_invalid_signal_date"})
            continue

        stock_quotes = grouped_quotes.get(ts_code, [])
        future_quotes = [
            quote
            for quote in stock_quotes
            if _parse_day(quote["trade_date"], "trade_date") > signal_date and _is_tradable_entry_quote(quote)
        ]
        if not future_quotes:
            results.append({**base, "status": "skipped_no_tradable_entry"})
            continue

        entry_quote = future_quotes[0]
        entry_date = _parse_day(entry_quote["trade_date"], "trade_date")
        exit_candidates = [
            quote
            for quote in stock_quotes
            if _parse_day(quote["trade_date"], "trade_date") >= entry_date and _is_tradable_quote(quote)
        ]
        if not exit_candidates:
            results.append({**base, "entry_date": entry_quote["trade_date"], "entry_open": entry_quote["open"], "status": "skipped_no_tradable_exit"})
            continue

        forced_exit = len(exit_candidates) < normalized_hold_days
        exit_quote = exit_candidates[min(normalized_hold_days, len(exit_candidates)) - 1]
        entry_open = _safe_float(entry_quote["open"])
        exit_close = _safe_float(exit_quote["close"])
        gross_return = exit_close / entry_open - 1 if entry_open > 0 else 0.0
        results.append(
            {
                **base,
                "entry_date": entry_quote["trade_date"],
                "exit_date": exit_quote["trade_date"],
                "entry_open": round(entry_open, 6),
                "exit_close": round(exit_close, 6),
                "gross_return": round(gross_return, 6),
                "status": "completed_forced_end_of_sample" if forced_exit else "completed",
            }
        )

    return results


def summarize_return_smoke(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    row_list = list(rows)
    completed_returns = [
        _safe_float(row.get("gross_return"))
        for row in row_list
        if _normalize_text(row.get("status")).startswith("completed") and _normalize_text(row.get("gross_return")) != ""
    ]
    status_counts: Dict[str, int] = {}
    for row in row_list:
        status = _normalize_text(row.get("status")) or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "rows": len(row_list),
        "completed": len(completed_returns),
        "skipped": len(row_list) - len(completed_returns),
        "status_counts": status_counts,
        "mean_return": round(sum(completed_returns) / len(completed_returns), 6) if completed_returns else None,
        "median_return": round(median(completed_returns), 6) if completed_returns else None,
        "win_rate": round(sum(1 for value in completed_returns if value > 0) / len(completed_returns), 6) if completed_returns else None,
    }


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


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
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


__all__ = [
    "DEFAULT_RETURN_HOLD_DAYS",
    "DEFAULT_RETURN_SMOKE_FIELDS",
    "build_return_smoke_rows",
    "get_knowaction_postgres_dsn",
    "resolve_signal_ts_code",
    "run_a_share_return_smoke",
    "summarize_return_smoke",
    "write_return_smoke_csv",
]
