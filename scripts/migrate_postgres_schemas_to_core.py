from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg2
from psycopg2.extras import execute_values

from backend.storage.db_compat import get_postgres_dsn
from backend.storage.postgres_core_schema import (
    CORE_SCHEMA,
    CORE_TABLE_SPEC_BY_NAME,
    LEGACY_SCHEMA_PREFIX,
    PUBLIC_SCHEMA,
    ensure_core_schema,
    quote_identifier,
)


@dataclass
class TableMigrationStats:
    table_name: str
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    conflict: int = 0


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def discover_legacy_schemas(conn) -> list[str]:
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


def _table_columns(conn, schema_name: str, table_name: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, table_name),
        )
        return [str(row[0]) for row in cur.fetchall()]


def _table_count(conn, schema_name: str, table_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {quote_identifier(schema_name)}.{quote_identifier(table_name)}")
        return int(cur.fetchone()[0])


def _core_columns(conn, table_name: str) -> set[str]:
    return set(_table_columns(conn, CORE_SCHEMA, table_name))


def _identity_columns(conn, schema_name: str, table_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND is_identity = 'YES'
            """,
            (schema_name, table_name),
        )
        return {str(row[0]) for row in cur.fetchall()}


def _conflict_target(conn, table_name: str) -> tuple[str, ...]:
    spec = CORE_TABLE_SPEC_BY_NAME.get(table_name)
    if not spec:
        return ()
    core_cols = _core_columns(conn, table_name)
    for unique_key in spec.unique_keys:
        if set(unique_key).issubset(core_cols):
            return unique_key
    if spec.primary_key and set(spec.primary_key).issubset(core_cols):
        identity_cols = _identity_columns(conn, CORE_SCHEMA, table_name)
        if not set(spec.primary_key).issubset(identity_cols):
            return spec.primary_key
    return ()


def _record_key(row: dict[str, object], conflict_target: Iterable[str]) -> str:
    values = [str(row.get(column) or "") for column in conflict_target]
    return "|".join(values)


def _upsert_rows(conn, table_name: str, rows: list[dict[str, object]], conflict_target: tuple[str, ...]) -> tuple[int, int]:
    if not rows:
        return 0, 0
    columns = list(rows[0].keys())
    insert_columns = ", ".join(quote_identifier(column) for column in columns)
    conflict_columns = ", ".join(quote_identifier(column) for column in conflict_target)
    update_columns = [
        column for column in columns
        if column not in conflict_target and column not in {"source_schema", "source_row_id", "migrated_at"}
    ]
    if update_columns:
        assignments = ", ".join(
            f"{quote_identifier(column)} = COALESCE(EXCLUDED.{quote_identifier(column)}, {quote_identifier(table_name)}.{quote_identifier(column)})"
            for column in update_columns
        )
        action = f"DO UPDATE SET {assignments}, migrated_at = CURRENT_TIMESTAMP"
    else:
        action = "DO NOTHING"
    sql = (
        f"INSERT INTO {quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)} ({insert_columns}) "
        f"VALUES %s ON CONFLICT ({conflict_columns}) {action}"
    )
    values = [tuple(row[column] for column in columns) for row in rows]
    with conn.cursor() as cur:
        before = _table_count(conn, CORE_SCHEMA, table_name)
        execute_values(cur, sql, values, page_size=500)
        after = _table_count(conn, CORE_SCHEMA, table_name)
    inserted = max(0, after - before)
    updated = max(0, len(rows) - inserted)
    return inserted, updated


def _insert_record_sources(conn, table_name: str, rows: list[dict[str, object]], conflict_target: tuple[str, ...]) -> None:
    source_rows = []
    for row in rows:
        source_schema = row.get("source_schema")
        source_row_id = row.get("source_row_id")
        if not source_schema or not source_row_id:
            continue
        source_rows.append((table_name, _record_key(row, conflict_target), source_schema, source_row_id))
    if not source_rows:
        return
    sql = (
        f"INSERT INTO {quote_identifier(CORE_SCHEMA)}.record_sources "
        "(record_table, record_key, source_schema, source_row_id) "
        "VALUES %s ON CONFLICT (record_table, record_key, source_schema, source_row_id) DO NOTHING"
    )
    with conn.cursor() as cur:
        execute_values(cur, sql, source_rows, page_size=500)


def migrate_table(conn, schema_name: str, table_name: str, *, apply: bool) -> TableMigrationStats:
    stats = TableMigrationStats(table_name=table_name)
    if table_name not in CORE_TABLE_SPEC_BY_NAME:
        return stats
    source_columns = _table_columns(conn, schema_name, table_name)
    core_columns = _core_columns(conn, table_name)
    identity_columns = _identity_columns(conn, CORE_SCHEMA, table_name)
    common_columns = [
        column for column in source_columns
        if column in core_columns
        and column not in {"migrated_at", "source_schema", "source_row_id"}
        and column not in identity_columns
    ]
    if not common_columns:
        stats.skipped = _table_count(conn, schema_name, table_name)
        return stats
    conflict_target = _conflict_target(conn, table_name)
    if not conflict_target:
        stats.skipped = _table_count(conn, schema_name, table_name)
        return stats
    stats.scanned = _table_count(conn, schema_name, table_name)
    if not apply or stats.scanned == 0:
        return stats

    select_columns = ", ".join(quote_identifier(column) for column in common_columns)
    with conn.cursor() as cur:
        cur.execute(f"SELECT ctid::text AS source_row_id, {select_columns} FROM {quote_identifier(schema_name)}.{quote_identifier(table_name)}")
        source_rows = cur.fetchall()

    rows: list[dict[str, object]] = []
    for source_row in source_rows:
        row = dict(zip(["source_row_id"] + common_columns, source_row))
        row["source_schema"] = schema_name
        row["migrated_at"] = None
        rows.append(row)

    inserted, updated = _upsert_rows(conn, table_name, rows, conflict_target)
    _insert_record_sources(conn, table_name, rows, conflict_target)
    stats.inserted = inserted
    stats.updated = updated
    return stats


def migrate_schemas_to_core(conn, *, apply: bool = False) -> list[TableMigrationStats]:
    ensure_core_schema(conn)
    stats_by_table: dict[str, TableMigrationStats] = {}
    for schema_name in discover_legacy_schemas(conn):
        for table_name in _schema_tables(conn, schema_name):
            stats = migrate_table(conn, schema_name, table_name, apply=apply)
            aggregate = stats_by_table.setdefault(table_name, TableMigrationStats(table_name=table_name))
            aggregate.scanned += stats.scanned
            aggregate.inserted += stats.inserted
            aggregate.updated += stats.updated
            aggregate.skipped += stats.skipped
            aggregate.conflict += stats.conflict
    if apply:
        conn.commit()
    return [stats_by_table[name] for name in sorted(stats_by_table)]


def verify_core(conn) -> list[str]:
    issues: list[str] = []
    for table_name in ("groups", "topics", "comments", "files", "file_ai_analyses", "task_runs", "task_logs"):
        legacy_total = sum(
            _table_count(conn, schema_name, table_name)
            for schema_name in discover_legacy_schemas(conn)
            if table_name in _schema_tables(conn, schema_name)
        )
        if legacy_total == 0:
            continue
        core_total = _table_count(conn, CORE_SCHEMA, table_name)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT count(*)
                FROM {quote_identifier(CORE_SCHEMA)}.record_sources
                WHERE record_table = %s
                """,
                (table_name,),
            )
            source_total = int(cur.fetchone()[0])
        if source_total < legacy_total:
            issues.append(f"{table_name}: record_sources={source_total} legacy={legacy_total}")
        if core_total <= 0:
            issues.append(f"{table_name}: core has no rows after migration")
    return issues


def _write_report(stats: list[TableMigrationStats], issues: list[str]) -> Path:
    report_path = _project_root() / "docs" / "postgres_core_migration_report.md"
    lines = [
        "# PostgreSQL Core Migration Report",
        "",
        "| Table | Scanned | Inserted | Updated | Skipped | Conflicts |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in stats:
        lines.append(
            f"| `{item.table_name}` | {item.scanned} | {item.inserted} | {item.updated} | {item.skipped} | {item.conflict} |"
        )
    lines.extend(["", "## Verification", ""])
    if issues:
        lines.extend(f"- [warn] {issue}" for issue in issues)
    else:
        lines.append("- Core verification passed.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def print_stats(stats: list[TableMigrationStats]) -> None:
    for item in stats:
        print(
            f"{item.table_name}: scanned={item.scanned} inserted={item.inserted} "
            f"updated={item.updated} skipped={item.skipped} conflicts={item.conflict}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy zsxq_* PostgreSQL schemas into zsxq_core")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Inspect source schemas without writing rows.")
    mode.add_argument("--apply", action="store_true", help="Create core schema and migrate rows.")
    mode.add_argument("--verify-only", action="store_true", help="Verify core table counts against legacy schemas.")
    args = parser.parse_args()

    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")
    conn = psycopg2.connect(dsn)
    try:
        if args.verify_only:
            ensure_core_schema(conn)
            issues = verify_core(conn)
            for issue in issues:
                print(f"[warn] {issue}")
            if not issues:
                print("Core verification passed.")
            raise SystemExit(1 if issues else 0)
        stats = migrate_schemas_to_core(conn, apply=args.apply)
        issues = verify_core(conn) if args.apply else []
        print_stats(stats)
        if args.apply:
            report_path = _write_report(stats, issues)
            print(f"Wrote {report_path}")
            if issues:
                raise SystemExit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
