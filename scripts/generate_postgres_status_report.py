from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from backend.storage.db_compat import get_database_backend, get_postgres_dsn
from backend.storage.postgres_core_schema import CORE_SCHEMA
from scripts.manage_postgres_public_schema import PUBLIC_SCHEMA, PUBLIC_VIEW_SPECS, discover_internal_schemas, quote_identifier


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


def _schema_summary(conn, schema_names: list[str]) -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    for schema_name in schema_names:
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


def _legacy_schema_count(conn) -> int:
    return len([schema for schema in discover_internal_schemas(conn) if schema != CORE_SCHEMA])


def build_report(conn) -> str:
    core_rows = _schema_summary(conn, [CORE_SCHEMA])
    legacy_count = _legacy_schema_count(conn)

    lines = [
        "# PostgreSQL Status Report",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## PostgreSQL Core Schema",
        "",
    ]
    if core_rows:
        lines.extend(["| Schema | Tables | Rows |", "| --- | ---: | ---: |"])
        lines.extend(f"| `{schema}` | {table_count} | {row_count} |" for schema, table_count, row_count in core_rows)
    else:
        lines.append("- `zsxq_core` has not been created.")

    lines.extend(["", "## Public Views", "", "| View | Rows |", "| --- | ---: |"])
    for spec in PUBLIC_VIEW_SPECS:
        count = _view_count(conn, spec.name)
        count_text = "missing" if count is None else str(count)
        lines.append(f"| `{PUBLIC_SCHEMA}.{spec.name}` | {count_text} |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Other projects should read from `zsxq_public` with the reader DSN.",
            f"- Legacy archived `zsxq_*` schema count: {legacy_count}.",
            "- `files.group_id` and `file_ai_analyses.group_id` may remain `NULL` when no reliable group relation exists.",
            "- Re-run this report after any PostgreSQL public view or data refresh.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a PostgreSQL status report")
    parser.add_argument(
        "--output",
        default="docs/postgres_status_report.md",
        help="Markdown report path.",
    )
    args = parser.parse_args()

    if get_database_backend() != "postgres":
        raise RuntimeError("Set ZSXQ_DATABASE_BACKEND=postgres or config.toml [database].backend = 'postgres'")
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = _project_root() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(dsn)
    try:
        report = build_report(conn)
    finally:
        conn.close()

    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
