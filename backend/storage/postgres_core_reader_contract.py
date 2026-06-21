from __future__ import annotations

from backend.storage.postgres_core_schema import CORE_SCHEMA


SUPPORTED_READER_TABLES = (
    "groups",
    "topics",
    "comments",
    "files",
    "file_ai_analyses",
    "daily_ai_reports",
    "zsxq_a_share_daily_mentions",
    "zsxq_a_share_topic_stock_extractions",
    "daily_stock_concepts",
    "stock_topic_analyses",
    "accounts",
    "group_account_map",
)

STATUS_REPORT_CORE_TABLES = (
    "groups",
    "topics",
    "files",
    "comments",
    "daily_ai_reports",
    "file_ai_analyses",
    "zsxq_a_share_daily_mentions",
    "zsxq_a_share_processed_state",
    "zsxq_a_share_tdx_exports",
    "zsxq_a_share_tdx_export_blocks",
)

READER_PROBE_TABLE = "groups"


def supported_reader_table_names() -> tuple[str, ...]:
    return SUPPORTED_READER_TABLES


def status_report_table_names() -> tuple[str, ...]:
    return STATUS_REPORT_CORE_TABLES


def reader_probe_table_name() -> str:
    return READER_PROBE_TABLE
