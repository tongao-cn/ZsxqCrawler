from __future__ import annotations

from contextlib import closing
from typing import Any, Dict

from backend.core.account_context import get_account_summary_for_group_auto, is_configured
from backend.core.db_path_manager import get_db_path_manager
from backend.services.group_workflow_service import fetch_official_groups
from backend.storage.zsxq_database import ZSXQDatabase
from backend.storage.zsxq_file_database import ZSXQFileDatabase


def empty_database_stats_response(configured: bool) -> Dict[str, Any]:
    return {
        "configured": configured,
        "topic_database": {
            "stats": {},
            "timestamp_info": {
                "total_topics": 0,
                "oldest_timestamp": "",
                "newest_timestamp": "",
                "has_data": False,
            },
        },
        "file_database": {
            "stats": {},
        },
    }


def coerce_group_id(group_id: str) -> int | str:
    try:
        return int(group_id)
    except Exception:
        return group_id


def count_group_files(group_id: str) -> int:
    try:
        with closing(ZSXQFileDatabase(group_id)) as files_db:
            return files_db.count_files()
    except Exception:
        return 0


def build_group_info_fallback(
    group_id: str,
    account: Any,
    files_count: int,
    source: str = "fallback",
    note: str | None = None,
) -> Dict[str, Any]:
    result = {
        "group_id": coerce_group_id(group_id),
        "name": f"群组 {group_id}",
        "description": "",
        "statistics": {"files": {"count": files_count}},
        "background_url": None,
        "account": account,
        "source": source,
    }
    if note:
        result["note"] = note
    return result


def get_group_info_read_model(group_id: str) -> Dict[str, Any]:
    def build_fallback(source: str = "fallback", note: str | None = None) -> dict:
        return build_group_info_fallback(
            group_id,
            account=get_account_summary_for_group_auto(group_id),
            files_count=count_group_files(group_id),
            source=source,
            note=note,
        )

    try:
        for group_data in fetch_official_groups():
            if str(group_data.get("group_id")) == str(group_id):
                return {
                    "group_id": group_data.get("group_id"),
                    "name": group_data.get("name"),
                    "description": group_data.get("description"),
                    "statistics": group_data.get("statistics", {}),
                    "background_url": group_data.get("background_url"),
                    "account": get_account_summary_for_group_auto(group_id),
                    "source": "official",
                }

        return build_fallback(note="official_group_not_found")
    except Exception:
        return build_fallback(note="exception_fallback")


def get_group_stats_read_model(group_id: int) -> Dict[str, Any]:
    with closing(ZSXQDatabase(str(group_id))) as db:
        return db.get_group_stats_summary()


def get_group_database_info_read_model(group_id: int) -> Dict[str, Any]:
    with closing(ZSXQDatabase(str(group_id))) as topics_db, closing(ZSXQFileDatabase(str(group_id))) as files_db:
        db_info = {
            "group_id": str(group_id),
            "schema": "zsxq_core",
            "group_dir": get_db_path_manager().get_group_dir(str(group_id)),
            "topics": topics_db.get_database_stats(),
            "files": files_db.get_database_stats(),
        }

    return {
        "group_id": group_id,
        "database_info": db_info,
    }


def get_global_database_stats_read_model() -> Dict[str, Any]:
    configured = is_configured()
    if not configured:
        return empty_database_stats_response(False)

    with closing(ZSXQDatabase()) as db:
        aggregated_topic_stats = db.get_database_stats()
        aggregated_timestamp_info = db.get_timestamp_range_info()

    with closing(ZSXQFileDatabase()) as fdb:
        aggregated_file_stats = fdb.get_database_stats()

    return {
        "configured": True,
        "topic_database": {
            "stats": aggregated_topic_stats,
            "timestamp_info": aggregated_timestamp_info,
        },
        "file_database": {
            "stats": aggregated_file_stats,
        },
    }
