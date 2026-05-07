from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import psycopg2

from backend.storage.db_compat import get_postgres_dsn
from backend.storage.postgres_core_schema import CORE_SCHEMA, ensure_core_schema, quote_identifier


@dataclass(frozen=True)
class BackfillStep:
    name: str
    count_sql: str
    update_sql: str


@dataclass
class BackfillStats:
    name: str
    candidates: int
    updated: int = 0


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _table_ref(table_name: str) -> str:
    return f"{quote_identifier(CORE_SCHEMA)}.{quote_identifier(table_name)}"


def build_group_id_backfill_steps() -> list[BackfillStep]:
    topics = _table_ref("topics")
    comments = _table_ref("comments")
    files = _table_ref("files")
    file_topic_relations = _table_ref("file_topic_relations")
    topic_files = _table_ref("topic_files")
    file_ai_analyses = _table_ref("file_ai_analyses")

    file_group_cte = f"""
        WITH resolved AS (
            SELECT file_id, MIN(group_id) AS group_id
            FROM (
                SELECT f.file_id, t.group_id
                FROM {files} f
                JOIN {topics} t ON t.topic_id = f.topic_id
                WHERE t.group_id IS NOT NULL
                UNION ALL
                SELECT r.file_id, t.group_id
                FROM {file_topic_relations} r
                JOIN {topics} t ON t.topic_id = r.topic_id
                WHERE t.group_id IS NOT NULL
                UNION ALL
                SELECT tf.file_id, t.group_id
                FROM {topic_files} tf
                JOIN {topics} t ON t.topic_id = tf.topic_id
                WHERE t.group_id IS NOT NULL
            ) source
            GROUP BY file_id
            HAVING COUNT(DISTINCT group_id) = 1
        )
    """
    return [
        BackfillStep(
            name="comments.group_id",
            count_sql=f"""
                SELECT COUNT(*)
                FROM {comments} c
                JOIN {topics} t ON t.topic_id = c.topic_id
                WHERE t.group_id IS NOT NULL
                  AND (c.group_id IS NULL OR c.group_id <> t.group_id)
            """,
            update_sql=f"""
                UPDATE {comments} c
                SET group_id = t.group_id,
                    migrated_at = COALESCE(c.migrated_at, CURRENT_TIMESTAMP)
                FROM {topics} t
                WHERE t.topic_id = c.topic_id
                  AND t.group_id IS NOT NULL
                  AND (c.group_id IS NULL OR c.group_id <> t.group_id)
            """,
        ),
        BackfillStep(
            name="files.group_id",
            count_sql=file_group_cte
            + f"""
                SELECT COUNT(*)
                FROM {files} f
                JOIN resolved r ON r.file_id = f.file_id
                WHERE f.group_id IS NULL OR f.group_id <> r.group_id
            """,
            update_sql=file_group_cte
            + f"""
                UPDATE {files} f
                SET group_id = r.group_id,
                    migrated_at = COALESCE(f.migrated_at, CURRENT_TIMESTAMP)
                FROM resolved r
                WHERE r.file_id = f.file_id
                  AND (f.group_id IS NULL OR f.group_id <> r.group_id)
            """,
        ),
        BackfillStep(
            name="file_ai_analyses.group_id",
            count_sql=f"""
                SELECT COUNT(*)
                FROM {file_ai_analyses} a
                JOIN {files} f ON f.file_id = a.file_id
                WHERE f.group_id IS NOT NULL
                  AND (a.group_id IS NULL OR a.group_id <> f.group_id)
            """,
            update_sql=f"""
                UPDATE {file_ai_analyses} a
                SET group_id = f.group_id,
                    migrated_at = COALESCE(a.migrated_at, CURRENT_TIMESTAMP)
                FROM {files} f
                WHERE f.file_id = a.file_id
                  AND f.group_id IS NOT NULL
                  AND (a.group_id IS NULL OR a.group_id <> f.group_id)
            """,
        ),
    ]


def _count(conn, sql: str) -> int:
    with conn.cursor() as cur:
        cur.execute(sql)
        return int(cur.fetchone()[0])


def run_backfill(conn, *, apply: bool) -> list[BackfillStats]:
    ensure_core_schema(conn)
    stats: list[BackfillStats] = []
    for step in build_group_id_backfill_steps():
        candidates = _count(conn, step.count_sql)
        updated = 0
        if apply and candidates:
            with conn.cursor() as cur:
                cur.execute(step.update_sql)
                updated = cur.rowcount
        stats.append(BackfillStats(name=step.name, candidates=candidates, updated=updated))
    if apply:
        conn.commit()
    return stats


def group_id_quality_counts(conn) -> dict[str, int]:
    tables = {
        "comments_null_group_id": "comments",
        "files_null_group_id": "files",
        "file_ai_analyses_null_group_id": "file_ai_analyses",
    }
    counts = {
        name: _count(conn, f"SELECT COUNT(*) FROM {_table_ref(table_name)} WHERE group_id IS NULL")
        for name, table_name in tables.items()
    }
    counts["files_ambiguous_group_id"] = _count(
        conn,
        f"""
        WITH source AS (
            SELECT r.file_id, t.group_id
            FROM {_table_ref('file_topic_relations')} r
            JOIN {_table_ref('topics')} t ON t.topic_id = r.topic_id
            WHERE t.group_id IS NOT NULL
            UNION ALL
            SELECT tf.file_id, t.group_id
            FROM {_table_ref('topic_files')} tf
            JOIN {_table_ref('topics')} t ON t.topic_id = tf.topic_id
            WHERE t.group_id IS NOT NULL
        )
        SELECT COUNT(*)
        FROM (
            SELECT file_id
            FROM source
            GROUP BY file_id
            HAVING COUNT(DISTINCT group_id) > 1
        ) ambiguous
        """,
    )
    return counts


def write_report(stats: list[BackfillStats], quality_counts: dict[str, int]) -> Path:
    report_path = _project_root() / "docs" / "postgres_core_group_id_backfill_report.md"
    lines = [
        "# PostgreSQL Core Group ID Backfill Report",
        "",
        "| Field | Candidates | Updated |",
        "| --- | ---: | ---: |",
    ]
    for item in stats:
        lines.append(f"| `{item.name}` | {item.candidates} | {item.updated} |")
    lines.extend(["", "## Remaining Quality Counts", "", "| Metric | Rows |", "| --- | ---: |"])
    for name, count in quality_counts.items():
        lines.append(f"| `{name}` | {count} |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill zsxq_core group_id fields from topic relations")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Count candidate rows without updating data.")
    mode.add_argument("--apply", action="store_true", help="Backfill group_id fields and write a report.")
    args = parser.parse_args()

    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")
    conn = psycopg2.connect(dsn)
    try:
        stats = run_backfill(conn, apply=args.apply)
        for item in stats:
            print(f"{item.name}: candidates={item.candidates} updated={item.updated}")
        quality_counts = group_id_quality_counts(conn)
        for name, count in quality_counts.items():
            print(f"{name}: rows={count}")
        if args.apply:
            report_path = write_report(stats, quality_counts)
            print(f"Wrote {report_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
