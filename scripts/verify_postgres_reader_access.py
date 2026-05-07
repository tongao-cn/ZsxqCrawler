from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import psycopg2

from backend.storage.postgres_core_schema import CORE_SCHEMA
from scripts.manage_postgres_public_schema import PUBLIC_SCHEMA, PUBLIC_VIEW_SPECS, quote_identifier


@dataclass(frozen=True)
class ReaderCheck:
    name: str
    passed: bool
    detail: str


def _view_count(conn, view_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {quote_identifier(PUBLIC_SCHEMA)}.{quote_identifier(view_name)}")
        return int(cur.fetchone()[0])


def _first_internal_schema(conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE (schema_name = %s OR schema_name LIKE %s)
              AND schema_name <> %s
            ORDER BY schema_name
            LIMIT 1
            """,
            (CORE_SCHEMA, "zsxq_%", PUBLIC_SCHEMA),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None


def _select_internal_schema_is_blocked(conn) -> ReaderCheck:
    schema_name = _first_internal_schema(conn)
    if not schema_name:
        return ReaderCheck("internal schema select blocked", True, "no internal schema found")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                LIMIT 1
                """,
                (schema_name,),
            )
            row = cur.fetchone()
            if not row:
                return ReaderCheck("internal schema select blocked", True, f"{schema_name} has no base table")
            table_name = str(row[0])
            cur.execute(f"SELECT count(*) FROM {quote_identifier(schema_name)}.{quote_identifier(table_name)}")
        return ReaderCheck(
            "internal schema select blocked",
            False,
            f"reader unexpectedly selected from {schema_name}.{table_name}",
        )
    except Exception as exc:
        conn.rollback()
        return ReaderCheck("internal schema select blocked", True, exc.__class__.__name__)


def _public_write_is_blocked(conn) -> ReaderCheck:
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE TABLE {quote_identifier(PUBLIC_SCHEMA)}.{quote_identifier('reader_write_probe')} (id integer)")
        return ReaderCheck("public schema write blocked", False, "reader unexpectedly created zsxq_public.reader_write_probe")
    except Exception as exc:
        conn.rollback()
        return ReaderCheck("public schema write blocked", True, exc.__class__.__name__)


def verify_reader_access(dsn: str) -> list[ReaderCheck]:
    conn = psycopg2.connect(dsn)
    try:
        checks: list[ReaderCheck] = []
        for spec in PUBLIC_VIEW_SPECS:
            try:
                count = _view_count(conn, spec.name)
                checks.append(ReaderCheck(f"select {PUBLIC_SCHEMA}.{spec.name}", True, f"{count} rows"))
            except Exception as exc:
                conn.rollback()
                checks.append(ReaderCheck(f"select {PUBLIC_SCHEMA}.{spec.name}", False, exc.__class__.__name__))
        checks.append(_select_internal_schema_is_blocked(conn))
        checks.append(_public_write_is_blocked(conn))
        return checks
    finally:
        conn.close()


def print_checks(checks: list[ReaderCheck]) -> int:
    for check in checks:
        status = "ok" if check.passed else "fail"
        print(f"[{status}] {check.name}: {check.detail}")
    return 0 if all(check.passed for check in checks) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a PostgreSQL reader DSN can only read zsxq_public views")
    parser.add_argument("--dsn", default=None, help="Reader DSN. Defaults to ZSXQ_READER_POSTGRES_DSN.")
    args = parser.parse_args()

    dsn = args.dsn or os.getenv("ZSXQ_READER_POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("Reader DSN is not configured. Pass --dsn or set ZSXQ_READER_POSTGRES_DSN.")
    raise SystemExit(print_checks(verify_reader_access(dsn)))


if __name__ == "__main__":
    main()
