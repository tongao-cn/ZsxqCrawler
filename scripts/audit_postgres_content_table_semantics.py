from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import psycopg2

from backend.storage.db_compat import get_postgres_dsn
from backend.storage.postgres_core_schema import CORE_SCHEMA, quote_identifier


@dataclass(frozen=True)
class DedupSpec:
    table: str
    key_columns: tuple[str, ...]
    mode: str = "dedup"


@dataclass
class DedupStats:
    table: str
    key_columns: tuple[str, ...]
    duplicate_groups: int
    duplicate_rows: int
    rows_to_delete: int
    deleted: int = 0


DEDUP_SPECS: tuple[DedupSpec, ...] = (
    DedupSpec("talks", ("topic_id",)),
    DedupSpec("questions", ("topic_id",)),
    DedupSpec("answers", ("topic_id",)),
    DedupSpec("articles", ("topic_id",)),
    DedupSpec("latest_likes", ("topic_id", "owner_user_id", "create_time")),
    DedupSpec("like_emojis", ("topic_id", "emoji_key")),
    DedupSpec("user_liked_emojis", ("topic_id", "emoji_key")),
)

READ_ONLY_SPECS: tuple[DedupSpec, ...] = (
    DedupSpec("likes", ("topic_id", "user_id", "create_time"), mode="read-only"),
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _table_ref(table_name: str) -> str:
    return f"{quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)}"


def _quoted_columns(columns: Sequence[str]) -> str:
    return ", ".join(quote_identifier(column) for column in columns)


def _partition_columns(columns: Sequence[str]) -> str:
    return ", ".join(quote_identifier(column) for column in columns)


def _duplicate_stats_sql(spec: DedupSpec) -> str:
    table_ref = _table_ref(spec.table)
    key_cols = _quoted_columns(spec.key_columns)
    return f"""
        SELECT COUNT(*) AS duplicate_groups,
               COALESCE(SUM(cnt), 0) AS duplicate_rows,
               COALESCE(SUM(cnt - 1), 0) AS rows_to_delete
        FROM (
            SELECT {key_cols}, COUNT(*) AS cnt
            FROM {table_ref}
            GROUP BY {key_cols}
            HAVING COUNT(*) > 1
        ) duplicates
    """


def _sample_sql(spec: DedupSpec, limit: int) -> str:
    table_ref = _table_ref(spec.table)
    key_cols = _quoted_columns(spec.key_columns)
    return f"""
        SELECT {key_cols}, COUNT(*) AS cnt, MIN(id) AS min_id, MAX(id) AS keep_id
        FROM {table_ref}
        GROUP BY {key_cols}
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC, keep_id DESC
        LIMIT {int(limit)}
    """


def _delete_sql(spec: DedupSpec) -> str:
    table_ref = _table_ref(spec.table)
    partition_cols = _partition_columns(spec.key_columns)
    return f"""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY {partition_cols}
                       ORDER BY id DESC
                   ) AS row_number
            FROM {table_ref}
        )
        DELETE FROM {table_ref} target
        USING ranked
        WHERE target.id = ranked.id
          AND ranked.row_number > 1
    """


def collect_stats(conn, spec: DedupSpec) -> DedupStats:
    with conn.cursor() as cur:
        cur.execute(_duplicate_stats_sql(spec))
        duplicate_groups, duplicate_rows, rows_to_delete = cur.fetchone()
    return DedupStats(
        table=spec.table,
        key_columns=spec.key_columns,
        duplicate_groups=int(duplicate_groups),
        duplicate_rows=int(duplicate_rows),
        rows_to_delete=int(rows_to_delete),
    )


def collect_samples(conn, spec: DedupSpec, *, limit: int) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(_sample_sql(spec, limit))
        return list(cur.fetchall())


def apply_dedup(conn, spec: DedupSpec) -> int:
    with conn.cursor() as cur:
        cur.execute(_delete_sql(spec))
        return int(cur.rowcount)


def run_audit(conn, *, apply: bool) -> list[DedupStats]:
    stats: list[DedupStats] = []
    for spec in DEDUP_SPECS + READ_ONLY_SPECS:
        item = collect_stats(conn, spec)
        if apply and spec.mode == "dedup" and item.rows_to_delete:
            item.deleted = apply_dedup(conn, spec)
        stats.append(item)
    if apply:
        conn.commit()
    else:
        conn.rollback()
    return stats


def write_report(conn, stats: list[DedupStats], *, sample_limit: int, apply: bool) -> Path:
    report_path = _project_root() / "docs" / "postgres_content_table_semantics_audit.md"
    lines = [
        "# PostgreSQL Content Table Semantics Audit",
        "",
        "## Latest Dedup Run",
        "",
        f"- mode: {'apply' if apply else 'dry-run'}",
        "- strategy: keep the maximum identity `id` in each logical duplicate group",
        "",
        "| Table | Key | Duplicate Groups | Duplicate Rows | Rows To Delete | Deleted |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in stats:
        key = ", ".join(item.key_columns)
        lines.append(
            f"| `{item.table}` | `{key}` | {item.duplicate_groups} | "
            f"{item.duplicate_rows} | {item.rows_to_delete} | {item.deleted} |"
        )

    lines.extend(["", "## Top Duplicate Samples", ""])
    for spec in DEDUP_SPECS + READ_ONLY_SPECS:
        samples = collect_samples(conn, spec, limit=sample_limit)
        lines.append(f"### {spec.table}")
        if not samples:
            lines.append("")
            lines.append("No duplicate groups.")
            lines.append("")
            continue
        header = [*spec.key_columns, "cnt", "min_id", "keep_id"]
        lines.append("")
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for row in samples:
            lines.append("| " + " | ".join(str(value) for value in row) + " |")
        lines.append("")

    lines.extend(
        [
            "## Intended Semantics",
            "",
            "- `talks`, `questions`, `answers`, and `articles` have one logical row per `topic_id`.",
            "- `latest_likes` is the current latest-like snapshot keyed by `(topic_id, owner_user_id, create_time)`.",
            "- `like_emojis` and `user_liked_emojis` are keyed by `(topic_id, emoji_key)`.",
            "- `likes` remains an append/history table and is audited read-only by `(topic_id, user_id, create_time)`.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and optionally deduplicate content child tables.")
    parser.add_argument("--apply", action="store_true", help="Delete duplicate rows, keeping the maximum id per key.")
    parser.add_argument("--write-report", action="store_true", help="Write docs/postgres_content_table_semantics_audit.md.")
    parser.add_argument("--sample-limit", type=int, default=10, help="Duplicate sample rows per table in reports.")
    args = parser.parse_args()

    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")

    conn = psycopg2.connect(dsn)
    try:
        stats = run_audit(conn, apply=args.apply)
        for item in stats:
            key = ", ".join(item.key_columns)
            mode = next((spec.mode for spec in DEDUP_SPECS + READ_ONLY_SPECS if spec.table == item.table), "dedup")
            print(
                f"{item.table}({key})[{mode}]: duplicate_groups={item.duplicate_groups} "
                f"duplicate_rows={item.duplicate_rows} rows_to_delete={item.rows_to_delete} "
                f"deleted={item.deleted}"
            )
        if args.write_report:
            report_path = write_report(conn, stats, sample_limit=args.sample_limit, apply=args.apply)
            print(f"Wrote {report_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
