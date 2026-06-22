"""Official topic page import helpers for crawl workflows."""

from __future__ import annotations

from typing import Any, Callable, NamedTuple

from backend.crawlers.official_topic_client import OfficialTopicClient, normalize_official_topic
from backend.storage.zsxq_database import ZSXQDatabase


TaskLogWriter = Callable[[str, str], None]


class OfficialTopicImportPlan(NamedTuple):
    topics_to_import: list[dict[str, Any]]
    should_stop: bool


def import_official_topic(db: ZSXQDatabase, _group_id: str, topic_data: dict[str, Any]) -> str:
    result = db.import_topic_data_with_result(topic_data)
    if not result.succeeded:
        return "error"
    return "updated" if result.status == "existing" else "new"


def official_topic_exists(db: ZSXQDatabase, _group_id: str, topic_id: Any) -> bool:
    return db.topic_exists(topic_id)


def official_topic_id(topic: dict[str, Any]) -> int:
    return int(topic.get("topic_id") or 0)


def official_topic_comments_count(topic: dict[str, Any]) -> int:
    return int((topic.get("counts") or {}).get("comments") or 0)


def add_official_import_result(stats: dict[str, int], imported: str) -> None:
    if imported == "new":
        stats["new_topics"] += 1
    elif imported == "updated":
        stats["updated_topics"] += 1
    else:
        stats["errors"] += 1


def new_official_topics(
    db: ZSXQDatabase,
    group_id: str,
    topics: list[dict[str, Any]],
    *,
    topic_exists: Callable[[ZSXQDatabase, str, Any], bool] = official_topic_exists,
    topic_id: Callable[[dict[str, Any]], int] = official_topic_id,
) -> list[dict[str, Any]]:
    return [
        topic
        for topic in topics
        if not topic_exists(db, group_id, topic_id(topic))
    ]


def official_topics_to_import_for_mode(
    db: ZSXQDatabase,
    group_id: str,
    mode: str,
    unique_topics: list[dict[str, Any]],
    task_id: str,
    add_task_log: TaskLogWriter,
    *,
    find_new_topics: Callable[[ZSXQDatabase, str, list[dict[str, Any]]], list[dict[str, Any]]] = new_official_topics,
) -> OfficialTopicImportPlan:
    if mode != "latest":
        add_task_log(task_id, f"📄 官方本页获取 {len(unique_topics)} 个话题")
        return OfficialTopicImportPlan(unique_topics, False)

    new_topics = find_new_topics(db, group_id, unique_topics)
    add_task_log(task_id, f"📊 官方页面分析: {len(unique_topics)} 个话题，{len(new_topics)} 个新话题")
    if not new_topics:
        add_task_log(task_id, "✅ 本页话题均已存在，最新采集完成")
        return OfficialTopicImportPlan([], True)
    return OfficialTopicImportPlan(new_topics, False)


def fetch_official_comments(
    client: OfficialTopicClient,
    topic_id: int,
    comments_count: int,
    task_id: str,
    add_task_log: TaskLogWriter,
) -> list[dict[str, Any]]:
    if comments_count <= 0:
        return []
    try:
        comments = client.get_topic_comments(topic_id)
        add_task_log(task_id, f"📝 话题 {topic_id} 官方评论拉取 {len(comments)}/{comments_count} 条")
        return comments
    except Exception as exc:
        add_task_log(task_id, f"⚠️ 话题 {topic_id} 官方评论拉取失败: {exc}")
        return []


def import_official_topics(
    db: ZSXQDatabase,
    client: OfficialTopicClient,
    group_id: str,
    topics: list[dict[str, Any]],
    task_id: str,
    add_task_log: TaskLogWriter,
    *,
    topic_id: Callable[[dict[str, Any]], int] = official_topic_id,
    comments_count_for_topic: Callable[[dict[str, Any]], int] = official_topic_comments_count,
    fetch_comments: Callable[[OfficialTopicClient, int, int, str], list[dict[str, Any]]] | None = None,
    normalize_topic: Callable[..., dict[str, Any]] = normalize_official_topic,
    import_topic: Callable[[ZSXQDatabase, str, dict[str, Any]], str] = import_official_topic,
    add_import_result: Callable[[dict[str, int], str], None] = add_official_import_result,
) -> dict[str, int]:
    stats = {"new_topics": 0, "updated_topics": 0, "errors": 0}
    for topic in topics:
        current_topic_id = topic_id(topic)
        comments_count = comments_count_for_topic(topic)
        if fetch_comments is None:
            comments = fetch_official_comments(client, current_topic_id, comments_count, task_id, add_task_log)
        else:
            comments = fetch_comments(client, current_topic_id, comments_count, task_id)
        normalized = normalize_topic(topic, group_id, comments=comments if comments_count else None)
        imported = import_topic(db, group_id, normalized)
        add_import_result(stats, imported)
    db.conn.commit()
    return stats


def import_official_page_topics(
    total_stats: dict[str, Any],
    db: ZSXQDatabase,
    client: OfficialTopicClient,
    group_id: str,
    topics: list[dict[str, Any]],
    task_id: str,
    add_task_log: TaskLogWriter,
    add_page_stats: Callable[[dict[str, Any], dict[str, int]], None],
    *,
    import_topics: Callable[
        [ZSXQDatabase, OfficialTopicClient, str, list[dict[str, Any]], str],
        dict[str, int],
    ] | None = None,
) -> dict[str, int]:
    if import_topics is None:
        page_stats = import_official_topics(db, client, group_id, topics, task_id, add_task_log)
    else:
        page_stats = import_topics(db, client, group_id, topics, task_id)
    add_page_stats(total_stats, page_stats)
    return page_stats
