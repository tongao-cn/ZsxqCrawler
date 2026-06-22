"""Read assembled topic detail payloads from the local topic store."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.storage.topic_detail_payloads import (
    load_topic_detail_base,
    load_topic_detail_comments,
    load_topic_detail_latest_likes,
    load_topic_detail_likes_detail,
    load_topic_detail_qa,
    load_topic_detail_talk_payload,
)
from backend.storage.zsxq_database_helpers import (
    topic_detail_scope,
)


def read_topic_detail(cursor: Any, topic_id: int, group_id: Optional[str]) -> Optional[Dict[str, Any]]:
    scoped_group_id, topic_scope_sql, topic_scope_params = topic_detail_scope(topic_id, group_id)

    topic_detail = load_topic_detail_base(cursor, topic_scope_sql, topic_scope_params)
    if topic_detail is None:
        return None

    talk_payload = load_topic_detail_talk_payload(cursor, topic_id, scoped_group_id)
    if talk_payload is not None:
        topic_detail["talk"] = talk_payload

    topic_detail["latest_likes"] = load_topic_detail_latest_likes(cursor, topic_id, scoped_group_id)
    topic_detail["show_comments"] = load_topic_detail_comments(cursor, topic_id, scoped_group_id)
    topic_detail["likes_detail"] = load_topic_detail_likes_detail(cursor, topic_id, scoped_group_id)

    if topic_detail["type"] == "q&a":
        topic_detail.update(load_topic_detail_qa(cursor, topic_id, scoped_group_id))

    return topic_detail
