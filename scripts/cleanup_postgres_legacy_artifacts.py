from __future__ import annotations

import argparse
from dataclasses import dataclass

import psycopg2

from backend.storage.db_compat import get_postgres_dsn
from backend.storage.postgres_core_schema import CORE_SCHEMA, CORE_TABLE_SPECS, quote_identifier


PUBLIC_SCHEMA = "zsxq_public"
LEGACY_SCHEMA_PREFIX = "zsxq_"
TRACKING_COLUMNS = ("source_schema", "source_row_id", "migrated_at")


@dataclass(frozen=True)
class CleanupPlan:
    statements: list[str]
    legacy_schema_count: int
    tracked_rows: int
    untracked_rows: int
    active_writers: int

    def text(self) -> str:
        header = [
            f"-- legacy_schema_count: {self.legacy_schema_count}",
            f"-- tracked_rows: {self.tracked_rows}",
            f"-- untracked_rows: {self.untracked_rows}",
            f"-- active_writers: {self.active_writers}",
        ]
        return "\n".join(header + self.statements) + "\n"


def _schema_exists(conn, schema_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (schema_name,))
        return cur.fetchone() is not None


def _legacy_schemas(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE %s
              AND schema_name NOT IN (%s, %s)
            ORDER BY schema_name
            """,
            (f"{LEGACY_SCHEMA_PREFIX}%", CORE_SCHEMA, PUBLIC_SCHEMA),
        )
        return [str(row[0]) for row in cur.fetchall()]


def _table_names(conn, schema_name: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (schema_name,),
        )
        return [str(row[0]) for row in cur.fetchall()]


def _table_count(conn, schema_name: str, table_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {quote_identifier(schema_name)}.{quote_identifier(table_name)}")
        return int(cur.fetchone()[0])


def _legacy_row_count(conn, schema_name: str) -> int:
    return sum(_table_count(conn, schema_name, table_name) for table_name in _table_names(conn, schema_name))


def _tracked_rows(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = 'record_sources'
            """,
            (CORE_SCHEMA,),
        )
        if cur.fetchone() is None:
            return 0
        cur.execute(f"SELECT count(*) FROM {quote_identifier(CORE_SCHEMA)}.{quote_identifier('record_sources')}")
        return int(cur.fetchone()[0])


def _active_writers(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid()
              AND state IN ('active', 'idle in transaction')
              AND (
                query ~* '\\m(insert|update|delete|alter|drop|create|truncate)\\M'
                OR state = 'idle in transaction'
              )
            """
        )
        return int(cur.fetchone()[0])


def build_cleanup_plan(conn) -> CleanupPlan:
    legacy_schemas = _legacy_schemas(conn)
    legacy_rows = sum(_legacy_row_count(conn, schema_name) for schema_name in legacy_schemas)
    tracked = _tracked_rows(conn)
    untracked = max(0, legacy_rows - tracked)
    active_writers = _active_writers(conn)
    statements: list[str] = []
    if _schema_exists(conn, PUBLIC_SCHEMA):
        statements.append(f"DROP SCHEMA IF EXISTS {quote_identifier(PUBLIC_SCHEMA)} CASCADE;")
    statements.extend(f"DROP SCHEMA IF EXISTS {quote_identifier(schema_name)} CASCADE;" for schema_name in legacy_schemas)
    statements.append(f"DROP TABLE IF EXISTS {quote_identifier(CORE_SCHEMA)}.{quote_identifier('record_sources')} CASCADE;")
    core_tables = {spec.name for spec in CORE_TABLE_SPECS if spec.name != "record_sources"}
    existing_tables = set(_table_names(conn, CORE_SCHEMA))
    for table_name in sorted(core_tables & existing_tables):
        for column_name in TRACKING_COLUMNS:
            statements.append(
                f"ALTER TABLE {quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)} "
                f"DROP COLUMN IF EXISTS {quote_identifier(column_name)};"
            )
    return CleanupPlan(statements, len(legacy_schemas), tracked, untracked, active_writers)


def apply_cleanup_plan(conn, plan: CleanupPlan) -> None:
    if plan.untracked_rows != 0:
        raise RuntimeError(f"Refusing cleanup: untracked legacy rows = {plan.untracked_rows}")
    if plan.active_writers != 0:
        raise RuntimeError(f"Refusing cleanup: active writer sessions = {plan.active_writers}")
    with conn.cursor() as cur:
        for statement in plan.statements:
            cur.execute(statement)
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup zsxq_public, legacy zsxq_* schemas, and source tracking columns")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print cleanup SQL without executing it.")
    mode.add_argument("--apply", action="store_true", help="Execute cleanup SQL after safety checks.")
    args = parser.parse_args()

    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")
    conn = psycopg2.connect(dsn)
    try:
        plan = build_cleanup_plan(conn)
        if args.apply:
            apply_cleanup_plan(conn, plan)
        else:
            print(plan.text(), end="")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
