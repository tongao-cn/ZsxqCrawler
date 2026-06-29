from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.storage.topic_file_attachment_writer import sync_topic_file_attachment


def sync_topic_files_to_core_tables(
    file_db: Any,
    topic_data: Dict[str, Any],
    files_data: List[Dict[str, Any]],
) -> int:
    if not files_data:
        return 0

    group_data = topic_data.get("group", {})
    topic_id = topic_data.get("topic_id")
    if not topic_id:
        return 0

    synced_files = 0
    for file_data in files_data:
        file_id = sync_topic_file_attachment(
            file_db,
            group_id=group_data.get("group_id") if group_data else None,
            topic_id=topic_id,
            file_data=file_data,
        )
        if file_id:
            synced_files += 1
    return synced_files


def write_file_response_topic_files(
    file_db: Any,
    *,
    topic_id: Any,
    topic_data: Dict[str, Any],
    file_data: Dict[str, Any],
    topic_files: List[Dict[str, Any]],
) -> Optional[int]:
    group_id_for_file = (topic_data.get("group") or {}).get("group_id")
    file_id = sync_topic_file_attachment(
        file_db,
        group_id=group_id_for_file,
        topic_id=topic_id,
        file_data=file_data,
    )
    if file_id:
        file_db.insert_topic_files(topic_id, [file_data])
    if topic_files:
        file_db.insert_topic_files(topic_id, topic_files)
    return file_id


__all__ = [
    "sync_topic_files_to_core_tables",
    "write_file_response_topic_files",
]
