from __future__ import annotations

from typing import Any, Dict, Optional

from backend.storage.zsxq_database_helpers import replace_file_topic_relation, upsert_core_file


def sync_topic_file_attachment(
    file_db: Any,
    *,
    group_id: Optional[Any],
    topic_id: Any,
    file_data: Dict[str, Any],
) -> Optional[int]:
    file_id = upsert_core_file(file_db.cursor, group_id, topic_id, file_data)
    if not file_id:
        return None

    replace_file_topic_relation(file_db, file_id, topic_id)
    return file_id
