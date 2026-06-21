from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import psycopg2

from backend.storage.postgres_core_reader_contract import CORE_SCHEMA, reader_probe_table_name
from backend.storage.postgres_core_schema import quote_identifier


@dataclass(frozen=True)
class ReaderCheck:
    name: str
    passed: bool
    detail: str


def _first_legacy_schema_table(conn) -> tuple[str, str] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema LIKE %s
              AND table_schema <> %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_schema, table_name
            LIMIT 1
            """,
            ("zsxq_%", CORE_SCHEMA),
        )
        row = cur.fetchone()
        return (str(row[0]), str(row[1])) if row else None


def _core_select_allowed(conn) -> ReaderCheck:
    table_name = reader_probe_table_name()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)}")
            count = int(cur.fetchone()[0])
        return ReaderCheck("core select allowed", True, f"{CORE_SCHEMA}.{table_name}: {count} rows")
    except Exception as exc:
        conn.rollback()
        return ReaderCheck("core select allowed", False, exc.__class__.__name__)


def _core_write_blocked(conn) -> ReaderCheck:
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE TABLE {quote_identifier(CORE_SCHEMA)}.{quote_identifier('reader_write_probe')} (id integer)")
        return ReaderCheck("core write blocked", False, "reader unexpectedly created zsxq_core.reader_write_probe")
    except Exception as exc:
        conn.rollback()
        return ReaderCheck("core write blocked", True, exc.__class__.__name__)


def _legacy_read_blocked(conn) -> ReaderCheck:
    legacy = _first_legacy_schema_table(conn)
    if not legacy:
        return ReaderCheck("legacy schema read blocked", True, "no legacy table found")
    schema_name, table_name = legacy
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {quote_identifier(schema_name)}.{quote_identifier(table_name)}")
        return ReaderCheck(
            "legacy schema read blocked",
            False,
            f"reader unexpectedly selected from {schema_name}.{table_name}",
        )
    except Exception as exc:
        conn.rollback()
        return ReaderCheck("legacy schema read blocked", True, exc.__class__.__name__)


def verify_reader_access(dsn: str) -> list[ReaderCheck]:
    conn = psycopg2.connect(dsn)
    try:
        return [
            _core_select_allowed(conn),
            _core_write_blocked(conn),
            _legacy_read_blocked(conn),
        ]
    finally:
        conn.close()


def print_checks(checks: list[ReaderCheck]) -> int:
    for check in checks:
        status = "ok" if check.passed else "fail"
        print(f"[{status}] {check.name}: {check.detail}")
    return 0 if all(check.passed for check in checks) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a PostgreSQL reader DSN can read but not write zsxq_core")
    parser.add_argument("--dsn", default=None, help="Reader DSN. Defaults to ZSXQ_READER_POSTGRES_DSN.")
    args = parser.parse_args()

    dsn = args.dsn or os.getenv("ZSXQ_READER_POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("Reader DSN is not configured. Pass --dsn or set ZSXQ_READER_POSTGRES_DSN.")
    raise SystemExit(print_checks(verify_reader_access(dsn)))


if __name__ == "__main__":
    main()
