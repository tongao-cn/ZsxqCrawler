from __future__ import annotations

from contextlib import closing
from typing import Any, Dict

from backend.core.account_context import is_configured
from backend.core.db_path_manager import get_db_path_manager
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
