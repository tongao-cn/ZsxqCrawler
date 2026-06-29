"""PostgreSQL-backed storage for TDX export history."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from psycopg2.extras import Json, execute_values

from backend.services import a_share_analysis_db_storage as analysis_storage
from backend.services.a_share_tdx_export_payload import (
    latest_tdx_export_payload,
    tdx_export_block_payload,
)


DEFAULT_KNOW_ACTION_ENV_PATH = analysis_storage.DEFAULT_KNOW_ACTION_ENV_PATH
TDX_EXPORTS_TABLE = analysis_storage.TDX_EXPORTS_TABLE
TDX_EXPORT_BLOCKS_TABLE = analysis_storage.TDX_EXPORT_BLOCKS_TABLE


def log_tdx_export(
    *,
    start_date: Optional[str],
    end_date: Optional[str],
    tdx_root: str,
    ranking_top_n: int,
    total_written: int,
    unresolved_companies: Sequence[str],
    backup_files: Sequence[str],
    stock_basic_source: str,
    source_detail: Optional[str],
    blocks: Sequence[Dict[str, Any]],
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> int:
    with analysis_storage.get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {analysis_storage._core_table_ref(TDX_EXPORTS_TABLE)} (
                    start_date,
                    end_date,
                    tdx_root,
                    ranking_top_n,
                    total_written,
                    unresolved_count,
                    stock_basic_source,
                    source_detail,
                    backup_files
                )
                VALUES (%s::date, %s::date, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    start_date,
                    end_date,
                    tdx_root,
                    int(ranking_top_n),
                    int(total_written),
                    len(list(unresolved_companies or [])),
                    stock_basic_source,
                    source_detail,
                    Json(list(backup_files or [])),
                ),
            )
            export_id = int(cur.fetchone()[0])

            block_rows: List[Tuple[int, int, str, str, str, int, int, Json]] = []
            for block in blocks:
                block_rows.append(
                    (
                        export_id,
                        int(block.get("window_days") or 0),
                        str(block.get("block_name") or ""),
                        str(block.get("block_code") or ""),
                        str(block.get("block_path") or ""),
                        int(block.get("written_count") or 0),
                        int(block.get("skipped_count") or 0),
                        Json(list(block.get("skipped_companies") or [])),
                    )
                )

            if block_rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {analysis_storage._core_table_ref(TDX_EXPORT_BLOCKS_TABLE)} (
                        export_id,
                        window_days,
                        block_name,
                        block_code,
                        block_path,
                        written_count,
                        skipped_count,
                        skipped_companies
                    )
                    VALUES %s
                    """,
                    block_rows,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s)",
                )
    return export_id


def get_latest_tdx_export(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Optional[Dict[str, Any]]:
    with analysis_storage.get_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    exported_at,
                    start_date::text,
                    end_date::text,
                    tdx_root,
                    ranking_top_n,
                    total_written,
                    unresolved_count,
                    stock_basic_source,
                    source_detail,
                    backup_files
                FROM {analysis_storage._core_table_ref(TDX_EXPORTS_TABLE)}
                ORDER BY exported_at DESC, id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                return None

            export_id = row[0]
            cur.execute(
                f"""
                SELECT
                    window_days,
                    block_name,
                    block_code,
                    block_path,
                    written_count,
                    skipped_count,
                    skipped_companies
                FROM {analysis_storage._core_table_ref(TDX_EXPORT_BLOCKS_TABLE)}
                WHERE export_id = %s
                ORDER BY window_days ASC
                """,
                (export_id,),
            )
            blocks = [
                tdx_export_block_payload(block_row)
                for block_row in cur.fetchall()
            ]

    return latest_tdx_export_payload(row, blocks)


__all__ = [
    "DEFAULT_KNOW_ACTION_ENV_PATH",
    "TDX_EXPORTS_TABLE",
    "TDX_EXPORT_BLOCKS_TABLE",
    "get_latest_tdx_export",
    "log_tdx_export",
]
