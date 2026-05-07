from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import psycopg2

from backend.storage.postgres_core_schema import CORE_SCHEMA
from scripts.manage_postgres_public_schema import PUBLIC_SCHEMA, quote_identifier


@dataclass(frozen=True)
class WriterCheck:
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
              AND table_schema NOT IN (%s, %s)
              AND table_type = 'BASE TABLE'
            ORDER BY table_schema, table_name
            LIMIT 1
            """,
            ("zsxq_%", CORE_SCHEMA, PUBLIC_SCHEMA),
        )
        row = cur.fetchone()
        return (str(row[0]), str(row[1])) if row else None


def _core_write_allowed(conn) -> WriterCheck:
    table_name = "writer_access_probe"
    table_ref = f"{quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)}"
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE TABLE IF NOT EXISTS {table_ref} (id integer PRIMARY KEY, note text)")
            cur.execute(f"INSERT INTO {table_ref} (id, note) VALUES (1, 'ok') ON CONFLICT (id) DO UPDATE SET note = EXCLUDED.note")
            cur.execute(f"UPDATE {table_ref} SET note = 'updated' WHERE id = 1")
            cur.execute(f"DELETE FROM {table_ref} WHERE id = 1")
            cur.execute(f"DROP TABLE {table_ref}")
        conn.commit()
        return WriterCheck("core write allowed", True, f"{CORE_SCHEMA}.{table_name}")
    except Exception as exc:
        conn.rollback()
        return WriterCheck("core write allowed", False, exc.__class__.__name__)


def _public_maintenance_allowed(conn) -> WriterCheck:
    view_name = "writer_access_probe_view"
    view_ref = f"{quote_identifier(PUBLIC_SCHEMA)}.{quote_identifier(view_name)}"
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE OR REPLACE VIEW {view_ref} AS SELECT 1 AS id")
            cur.execute(f"SELECT count(*) FROM {view_ref}")
            cur.execute(f"DROP VIEW {view_ref}")
        conn.commit()
        return WriterCheck("public maintenance allowed", True, f"{PUBLIC_SCHEMA}.{view_name}")
    except Exception as exc:
        conn.rollback()
        return WriterCheck("public maintenance allowed", False, exc.__class__.__name__)


def _legacy_read_blocked(conn) -> WriterCheck:
    legacy = _first_legacy_schema_table(conn)
    if not legacy:
        return WriterCheck("legacy schema read blocked", True, "no legacy table found")
    schema_name, table_name = legacy
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {quote_identifier(schema_name)}.{quote_identifier(table_name)}")
        return WriterCheck(
            "legacy schema read blocked",
            False,
            f"writer unexpectedly selected from {schema_name}.{table_name}",
        )
    except Exception as exc:
        conn.rollback()
        return WriterCheck("legacy schema read blocked", True, exc.__class__.__name__)


def verify_writer_access(dsn: str) -> list[WriterCheck]:
    conn = psycopg2.connect(dsn)
    try:
        return [
            _core_write_allowed(conn),
            _public_maintenance_allowed(conn),
            _legacy_read_blocked(conn),
        ]
    finally:
        conn.close()


def print_checks(checks: list[WriterCheck]) -> int:
    for check in checks:
        status = "ok" if check.passed else "fail"
        print(f"[{status}] {check.name}: {check.detail}")
    return 0 if all(check.passed for check in checks) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a PostgreSQL writer DSN can write core and maintain public views")
    parser.add_argument("--dsn", default=None, help="Writer DSN. Defaults to ZSXQ_WRITER_POSTGRES_DSN.")
    args = parser.parse_args()

    dsn = args.dsn or os.getenv("ZSXQ_WRITER_POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("Writer DSN is not configured. Pass --dsn or set ZSXQ_WRITER_POSTGRES_DSN.")
    raise SystemExit(print_checks(verify_writer_access(dsn)))


if __name__ == "__main__":
    main()
