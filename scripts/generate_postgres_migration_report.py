from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from backend.storage.db_compat import get_database_backend, get_postgres_dsn
from scripts.audit_postgres_migration import AuditIssue, audit_migration
from scripts.manage_postgres_public_schema import PUBLIC_SCHEMA, PUBLIC_VIEW_SPECS, discover_internal_schemas, quote_identifier
from scripts.migrate_sqlite_to_postgres import _iter_sqlite_files, _sqlite_tables


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _table_count(conn, schema_name: str, table_name: str) -> int | None:
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


def _view_count(conn, view_name: str) -> int | None:
    return _table_count(conn, PUBLIC_SCHEMA, view_name)


def _internal_schema_summary(conn) -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    for schema_name in discover_internal_schemas(conn):
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
            tables = [str(row[0]) for row in cur.fetchall()]
        total_rows = 0
        for table_name in tables:
            count = _table_count(conn, schema_name, table_name)
            total_rows += count or 0
        rows.append((schema_name, len(tables), total_rows))
    return rows


def _sqlite_summary(root: Path) -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    for db_path in _iter_sqlite_files(root):
        import sqlite3

        conn = sqlite3.connect(db_path)
        try:
            tables = _sqlite_tables(conn)
            total_rows = 0
            for table_name, _sql in tables:
                count = conn.execute(f"SELECT count(*) FROM {quote_identifier(table_name)}").fetchone()[0]
                total_rows += int(count)
            rows.append((str(db_path), len(tables), total_rows))
        finally:
            conn.close()
    return rows


def _issues_to_markdown(issues: list[AuditIssue]) -> list[str]:
    if not issues:
        return ["- PostgreSQL migration audit passed."]
    return [f"- [{issue.level}] {issue.message}" for issue in issues]


def build_report(root: Path, conn) -> str:
    sqlite_rows = _sqlite_summary(root) if root.exists() else []
    internal_rows = _internal_schema_summary(conn)
    audit_issues = audit_migration(root, conn) if root.exists() else [AuditIssue("warn", f"SQLite root not found: {root}")]
    if sqlite_rows and len(audit_issues) == 1 and audit_issues[0].level == "warn":
        audit_issues = []

    lines = [
        "# PostgreSQL Real Migration Report",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"SQLite root: `{root}`",
        "",
        "## SQLite Sources",
        "",
    ]
    if sqlite_rows:
        lines.extend(["| Database | Tables | Rows |", "| --- | ---: | ---: |"])
        lines.extend(f"| `{path}` | {table_count} | {row_count} |" for path, table_count, row_count in sqlite_rows)
    else:
        lines.append("- No SQLite `.db` files found under the configured root.")

    lines.extend(["", "## PostgreSQL Internal Schemas", ""])
    if internal_rows:
        lines.extend(["| Schema | Tables | Rows |", "| --- | ---: | ---: |"])
        lines.extend(f"| `{schema}` | {table_count} | {row_count} |" for schema, table_count, row_count in internal_rows)
    else:
        lines.append("- No internal `zsxq_*` schemas found.")

    lines.extend(["", "## Public Views", "", "| View | Rows |", "| --- | ---: |"])
    for spec in PUBLIC_VIEW_SPECS:
        count = _view_count(conn, spec.name)
        count_text = "missing" if count is None else str(count)
        lines.append(f"| `{PUBLIC_SCHEMA}.{spec.name}` | {count_text} |")

    lines.extend(["", "## Audit", ""])
    lines.extend(_issues_to_markdown(audit_issues))

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Other projects should read from `zsxq_public` with the reader DSN.",
            "- `files.group_id` and `file_ai_analyses.group_id` may remain `NULL` when no reliable group relation exists.",
            "- Re-run this report after any production migration or public view change.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a PostgreSQL migration status report")
    parser.add_argument("--root", default=None, help="Directory containing .db files. Defaults to output/databases.")
    parser.add_argument(
        "--output",
        default="docs/postgres_real_migration_report.md",
        help="Markdown report path.",
    )
    args = parser.parse_args()

    if get_database_backend() != "postgres":
        raise RuntimeError("Set ZSXQ_DATABASE_BACKEND=postgres or config.toml [database].backend = 'postgres'")
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")

    root = Path(args.root) if args.root else _project_root() / "output" / "databases"
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = _project_root() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(dsn)
    try:
        report = build_report(root, conn)
    finally:
        conn.close()

    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
