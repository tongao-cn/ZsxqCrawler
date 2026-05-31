from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional


def extract_topic_data(topic_detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    resp_data = topic_detail.get("resp_data", {}) or {}
    topic_data = resp_data.get("topic", {}) or {}
    return topic_data or None


def save_topic_detail(
    *,
    db: Any,
    group_id: str,
    topic_detail: Dict[str, Any],
) -> bool:
    topic_data = extract_topic_data(topic_detail)
    if not topic_data:
        return False

    db.insert_topic_detail(int(group_id), topic_data, json.dumps(topic_detail, ensure_ascii=False))
    return True


def prepare_column_topic(
    *,
    add_task_log: Callable[[str, str], None],
    column_id: int,
    db: Any,
    group_id: str,
    incremental_mode: bool,
    task_id: str,
    topic: Dict[str, Any],
    topic_idx: int,
    total_topics: int,
) -> tuple[Optional[int], str, bool]:
    topic_id = topic.get("topic_id")
    topic_title = topic.get("title", "无标题")[:30]
    db.insert_column_topic(column_id, int(group_id), topic)

    if incremental_mode and db.topic_detail_exists(topic_id):
        add_task_log(task_id, f"   📄 [{topic_idx}/{total_topics}] {topic_title}... ⏭️ 跳过（已存在）")
        return topic_id, topic_title, True

    add_task_log(task_id, f"   📄 [{topic_idx}/{total_topics}] {topic_title}...")
    return topic_id, topic_title, False
