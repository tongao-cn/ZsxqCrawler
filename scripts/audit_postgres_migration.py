from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg2

from backend.storage.db_compat import get_database_backend, get_postgres_dsn, schema_name_for_path
from scripts.manage_postgres_public_schema import PUBLIC_VIEW_SPECS, quote_identifier
from scripts.migrate_sqlite_to_postgres import _iter_sqlite_files, _sqlite_tables


@dataclass(frozen=True)
class AuditIssue:
    level: str
    message: str


@dataclass(frozen=True)
class SqliteTableStats:
    rows: int
    columns: frozenset[str]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sqlite_table_stats(db_path: Path) -> dict[str, SqliteTableStats]:
    conn = sqlite3.connect(db_path)
    try:
        stats: dict[str, SqliteTableStats] = {}
        for table_name, _sql in _sqlite_tables(conn):
            count = conn.execute(f"SELECT count(*) FROM {quote_identifier(table_name)}").fetchone()[0]
            columns = frozenset(str(row[1]) for row in conn.execute(f"PRAGMA table_info({quote_identifier(table_name)})"))
            stats[table_name] = SqliteTableStats(rows=int(count), columns=columns)
        return stats
    finally:
        conn.close()


def _postgres_table_count(conn, schema_name: str, table_name: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
            """,
            (schema_name, table_name),
        )
        if cur.fetchone() is None:
            return None
        cur.execute(f"SELECT count(*) FROM {quote_identifier(schema_name)}.{quote_identifier(table_name)}")
        return int(cur.fetchone()[0])


def _public_view_count(conn, view_name: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.views
            WHERE table_schema = 'zsxq_public'
              AND table_name = %s
            """,
            (view_name,),
        )
        if cur.fetchone() is None:
            return None
        cur.execute(f"SELECT count(*) FROM {quote_identifier('zsxq_public')}.{quote_identifier(view_name)}")
        return int(cur.fetchone()[0])


def _expected_public_counts(sqlite_stats_by_schema: dict[str, dict[str, SqliteTableStats]]) -> dict[str, int]:
    expected: dict[str, int] = {}
    for spec in PUBLIC_VIEW_SPECS:
        count = 0
        for table_stats in sqlite_stats_by_schema.values():
            stats = table_stats.get(spec.table)
            if stats and set(spec.required_columns).issubset(stats.columns):
                count += stats.rows
        expected[spec.name] = count
    return expected


def audit_migration(root: Path, conn) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    sqlite_files = list(_iter_sqlite_files(root))
    if not sqlite_files:
        return [AuditIssue("warn", f"No .db files found under {root}")]

    sqlite_stats_by_schema: dict[str, dict[str, SqliteTableStats]] = {}
    for db_path in sqlite_files:
        schema_name = schema_name_for_path(db_path)
        sqlite_stats = _sqlite_table_stats(db_path)
        sqlite_stats_by_schema[schema_name] = sqlite_stats
        for table_name, stats in sqlite_stats.items():
            pg_count = _postgres_table_count(conn, schema_name, table_name)
            if pg_count is None:
                issues.append(AuditIssue("error", f"{schema_name}.{table_name} missing in PostgreSQL"))
            elif pg_count != stats.rows:
                issues.append(
                    AuditIssue(
                        "error",
                        f"{schema_name}.{table_name} row mismatch: sqlite={stats.rows}, postgres={pg_count}",
                    )
                )

    for view_name, expected_count in _expected_public_counts(sqlite_stats_by_schema).items():
        actual_count = _public_view_count(conn, view_name)
        if actual_count is None:
            issues.append(AuditIssue("error", f"zsxq_public.{view_name} view missing"))
        elif actual_count != expected_count:
            issues.append(
                AuditIssue(
                    "error",
                    f"zsxq_public.{view_name} row mismatch: expected={expected_count}, actual={actual_count}",
                )
            )

    return issues


def print_audit_report(issues: Iterable[AuditIssue]) -> int:
    issue_list = list(issues)
    if not issue_list:
        print("PostgreSQL migration audit passed.")
        return 0
    for issue in issue_list:
        print(f"[{issue.level}] {issue.message}")
    return 1 if any(issue.level == "error" for issue in issue_list) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit SQLite to PostgreSQL migration row counts")
    parser.add_argument("--root", default=None, help="Directory containing .db files. Defaults to output/databases.")
    args = parser.parse_args()

    if get_database_backend() != "postgres":
        raise RuntimeError("Set ZSXQ_DATABASE_BACKEND=postgres or config.toml [database].backend = 'postgres'")
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")

    root = Path(args.root) if args.root else _project_root() / "output" / "databases"
    if not root.exists():
        raise FileNotFoundError(f"SQLite database root not found: {root}")

    conn = psycopg2.connect(dsn)
    try:
        raise SystemExit(print_audit_report(audit_migration(root, conn)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
