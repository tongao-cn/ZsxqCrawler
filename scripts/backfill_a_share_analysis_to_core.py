from __future__ import annotations

import argparse

import psycopg2

from backend.services.a_share_analysis_db_storage import (
    DAILY_MENTIONS_TABLE,
    PROCESSED_STATE_TABLE,
    TDX_EXPORTS_TABLE,
    TDX_EXPORT_BLOCKS_TABLE,
)
from backend.storage.db_compat import get_postgres_dsn
from backend.storage.postgres_core_schema import CORE_SCHEMA, ensure_core_schema, quote_identifier


def _table_ref(schema: str, table_name: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(table_name)}"


def build_backfill_sql() -> list[str]:
    public_daily = _table_ref("public", DAILY_MENTIONS_TABLE)
    public_state = _table_ref("public", PROCESSED_STATE_TABLE)
    public_exports = _table_ref("public", TDX_EXPORTS_TABLE)
    public_blocks = _table_ref("public", TDX_EXPORT_BLOCKS_TABLE)
    core_daily = _table_ref(CORE_SCHEMA, DAILY_MENTIONS_TABLE)
    core_state = _table_ref(CORE_SCHEMA, PROCESSED_STATE_TABLE)
    core_exports = _table_ref(CORE_SCHEMA, TDX_EXPORTS_TABLE)
    core_blocks = _table_ref(CORE_SCHEMA, TDX_EXPORT_BLOCKS_TABLE)
    return [
        f"""
DO $$
BEGIN
    IF to_regclass('public.{DAILY_MENTIONS_TABLE}') IS NOT NULL THEN
        INSERT INTO {core_daily} (group_id, mention_date, company, mentions_count, updated_at)
        SELECT COALESCE(group_id, ''), mention_date, company, mentions_count, updated_at
        FROM {public_daily}
        ON CONFLICT (group_id, mention_date, company) DO UPDATE SET
            mentions_count = EXCLUDED.mentions_count,
            updated_at = GREATEST({core_daily}.updated_at, EXCLUDED.updated_at);
    END IF;
END $$""".strip(),
        f"""
DO $$
BEGIN
    IF to_regclass('public.{PROCESSED_STATE_TABLE}') IS NOT NULL THEN
        INSERT INTO {core_state} (group_id, source, topic_id, day, processed_at)
        SELECT COALESCE(group_id, ''), source, topic_id, day, processed_at
        FROM {public_state}
        ON CONFLICT (group_id, source, topic_id, day) DO UPDATE SET
            processed_at = GREATEST({core_state}.processed_at, EXCLUDED.processed_at);
    END IF;
END $$""".strip(),
        f"""
DO $$
BEGIN
    IF to_regclass('public.{TDX_EXPORTS_TABLE}') IS NOT NULL THEN
        INSERT INTO {core_exports} (
            id, exported_at, start_date, end_date, tdx_root, ranking_top_n,
            total_written, unresolved_count, stock_basic_source, source_detail, backup_files
        )
        SELECT
            id, exported_at, start_date, end_date, tdx_root, ranking_top_n,
            total_written, unresolved_count, stock_basic_source, source_detail, backup_files
        FROM {public_exports}
        ON CONFLICT (id) DO UPDATE SET
            exported_at = EXCLUDED.exported_at,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            tdx_root = EXCLUDED.tdx_root,
            ranking_top_n = EXCLUDED.ranking_top_n,
            total_written = EXCLUDED.total_written,
            unresolved_count = EXCLUDED.unresolved_count,
            stock_basic_source = EXCLUDED.stock_basic_source,
            source_detail = EXCLUDED.source_detail,
            backup_files = EXCLUDED.backup_files;
    END IF;
END $$""".strip(),
        f"""
DO $$
BEGIN
    IF to_regclass('public.{TDX_EXPORT_BLOCKS_TABLE}') IS NOT NULL THEN
        INSERT INTO {core_blocks} (
            id, export_id, window_days, block_name, block_code, block_path,
            written_count, skipped_count, skipped_companies
        )
        SELECT
            id, export_id, window_days, block_name, block_code, block_path,
            written_count, skipped_count, skipped_companies
        FROM {public_blocks}
        ON CONFLICT (id) DO UPDATE SET
            export_id = EXCLUDED.export_id,
            window_days = EXCLUDED.window_days,
            block_name = EXCLUDED.block_name,
            block_code = EXCLUDED.block_code,
            block_path = EXCLUDED.block_path,
            written_count = EXCLUDED.written_count,
            skipped_count = EXCLUDED.skipped_count,
            skipped_companies = EXCLUDED.skipped_companies;
    END IF;
END $$""".strip(),
        f"""
SELECT setval(
    pg_get_serial_sequence('{CORE_SCHEMA}.{TDX_EXPORTS_TABLE}', 'id'),
    GREATEST(COALESCE((SELECT MAX(id) FROM {core_exports}), 0), 1),
    true
)""".strip(),
        f"""
SELECT setval(
    pg_get_serial_sequence('{CORE_SCHEMA}.{TDX_EXPORT_BLOCKS_TABLE}', 'id'),
    GREATEST(COALESCE((SELECT MAX(id) FROM {core_blocks}), 0), 1),
    true
)""".strip(),
    ]


def backfill_a_share_analysis_to_core(*, apply: bool = False) -> list[str]:
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")

    statements = build_backfill_sql()
    if apply:
        conn = psycopg2.connect(dsn)
        try:
            ensure_core_schema(conn)
            with conn.cursor() as cur:
                for statement in statements:
                    cur.execute(statement)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return statements


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill ZSXQ A-share analysis tables into zsxq_core")
    parser.add_argument("--apply", action="store_true", help="Execute the backfill. Omit to print SQL only.")
    args = parser.parse_args()

    statements = backfill_a_share_analysis_to_core(apply=args.apply)
    if not args.apply:
        for statement in statements:
            print(statement.rstrip(";") + ";")


if __name__ == "__main__":
    main()
