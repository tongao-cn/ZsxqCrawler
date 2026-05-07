from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from backend.storage.db_compat import get_postgres_dsn
from backend.storage.postgres_core_schema import CORE_SCHEMA, LEGACY_SCHEMA_PREFIX, PUBLIC_SCHEMA, quote_identifier


@dataclass(frozen=True)
class LegacySchemaSummary:
    schema_name: str
    table_count: int
    row_count: int
    tracked_row_count: int = 0
    untracked_row_count: int = 0

    @property
    def drop_status(self) -> str:
        if self.row_count == 0:
            return "ready_to_drop_empty"
        if self.untracked_row_count == 0:
            return "ready_to_drop_tracked"
        return "hold_untracked_rows"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def discover_legacy_archive_schemas(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE %s
              AND schema_name <> %s
              AND schema_name <> %s
            ORDER BY schema_name
            """,
            (f"{LEGACY_SCHEMA_PREFIX}%", PUBLIC_SCHEMA, CORE_SCHEMA),
        )
        return [str(row[0]) for row in cur.fetchall()]


def _schema_tables(conn, schema_name: str) -> list[str]:
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
        cur.execute(f"SELECT COUNT(*) FROM {quote_identifier(schema_name)}.{quote_identifier(table_name)}")
        return int(cur.fetchone()[0])


def _tracked_row_count(conn, schema_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM {quote_identifier(CORE_SCHEMA)}.{quote_identifier('record_sources')}
            WHERE source_schema = %s
            """,
            (schema_name,),
        )
        return int(cur.fetchone()[0])


def summarize_legacy_schemas(conn) -> list[LegacySchemaSummary]:
    rows: list[LegacySchemaSummary] = []
    for schema_name in discover_legacy_archive_schemas(conn):
        tables = _schema_tables(conn, schema_name)
        row_count = sum(_table_count(conn, schema_name, table_name) for table_name in tables)
        tracked_row_count = _tracked_row_count(conn, schema_name)
        rows.append(
            LegacySchemaSummary(
                schema_name=schema_name,
                table_count=len(tables),
                row_count=row_count,
                tracked_row_count=tracked_row_count,
                untracked_row_count=max(0, row_count - tracked_row_count),
            )
        )
    return rows


def build_drop_sql(summaries: list[LegacySchemaSummary]) -> list[str]:
    return [
        f"DROP SCHEMA IF EXISTS {quote_identifier(item.schema_name)} CASCADE;"
        for item in summaries
        if item.drop_status.startswith("ready_to_drop")
    ]


def build_report(summaries: list[LegacySchemaSummary], *, include_drop_sql: bool = True) -> str:
    total_rows = sum(item.row_count for item in summaries)
    tracked_rows = sum(item.tracked_row_count for item in summaries)
    untracked_rows = sum(item.untracked_row_count for item in summaries)
    ready = [item for item in summaries if item.drop_status.startswith("ready_to_drop")]
    held = [item for item in summaries if item.drop_status == "hold_untracked_rows"]
    lines = [
        "# PostgreSQL Legacy Schema Archive Report",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- Legacy schema count: {len(summaries)}",
        f"- Legacy row count: {total_rows}",
        f"- `record_sources` tracked row count: {tracked_rows}",
        f"- Untracked legacy row count: {untracked_rows}",
        f"- Ready-to-drop schema count: {len(ready)}",
        f"- Held schema count: {len(held)}",
        "- This report does not delete data.",
        "- `ready_to_drop_*` means this report can generate future drop SQL; it still does not execute deletion.",
        "",
        "## Drop Readiness",
        "",
        "| Status | Schemas | Rows | Untracked Rows |",
        "| --- | ---: | ---: | ---: |",
    ]
    for status in ("ready_to_drop_empty", "ready_to_drop_tracked", "hold_untracked_rows"):
        items = [item for item in summaries if item.drop_status == status]
        lines.append(
            f"| `{status}` | {len(items)} | {sum(item.row_count for item in items)} | {sum(item.untracked_row_count for item in items)} |"
        )

    lines.extend(
        [
            "",
            "## Largest Schemas",
            "",
            "| Schema | Tables | Rows | Tracked Rows | Untracked Rows | Status |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in sorted(summaries, key=lambda row: row.row_count, reverse=True)[:50]:
        lines.append(
            f"| `{item.schema_name}` | {item.table_count} | {item.row_count} | "
            f"{item.tracked_row_count} | {item.untracked_row_count} | `{item.drop_status}` |"
        )

    held_rows = sorted(held, key=lambda row: row.untracked_row_count, reverse=True)[:50]
    lines.extend(
        [
            "",
            "## Held Schemas",
            "",
            "| Schema | Tables | Rows | Tracked Rows | Untracked Rows |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    if held_rows:
        for item in held_rows:
            lines.append(
                f"| `{item.schema_name}` | {item.table_count} | {item.row_count} | "
                f"{item.tracked_row_count} | {item.untracked_row_count} |"
            )
    else:
        lines.append("| none | 0 | 0 | 0 | 0 |")

    lines.extend(
        [
            "",
            "## Ready-To-Drop Schemas",
            "",
            "| Schema | Tables | Rows | Status |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for item in sorted(ready, key=lambda row: row.schema_name)[:100]:
        lines.append(f"| `{item.schema_name}` | {item.table_count} | {item.row_count} | `{item.drop_status}` |")

    if include_drop_sql:
        lines.extend(
            [
                "",
                "## Generated Drop SQL",
                "",
                "The SQL below includes only `ready_to_drop_*` schemas and is for a future archive/delete task. Do not run it until core migration has been independently accepted and backed up.",
                "",
                "```sql",
            ]
        )
        drop_sql = build_drop_sql(summaries)
        lines.extend(drop_sql if drop_sql else ["-- No schemas are ready to drop."])
        lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a PostgreSQL legacy zsxq_* archive report")
    parser.add_argument("--output", default="docs/postgres_legacy_archive_report.md", help="Markdown report path.")
    parser.add_argument("--no-drop-sql", action="store_true", help="Do not include generated DROP SCHEMA SQL.")
    args = parser.parse_args()

    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")

    conn = psycopg2.connect(dsn)
    try:
        report = build_report(summarize_legacy_schemas(conn), include_drop_sql=not args.no_drop_sql)
    finally:
        conn.close()

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = _project_root() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
