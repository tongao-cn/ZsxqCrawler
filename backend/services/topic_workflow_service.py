from __future__ import annotations

from backend.storage.zsxq_database import ZSXQDatabase


def _clear_group_topic_data(group_id: str) -> dict:
    db = ZSXQDatabase(group_id)
    try:
        deleted_counts = db.delete_group_topic_records()
        db.conn.commit()
        return deleted_counts
    finally:
        db.close()
