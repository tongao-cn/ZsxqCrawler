from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from backend.storage.db_compat import connect
from scripts.probe_zsxq_mcp_topics import McpClient, _load_mcp_url, _topic_list


DIRECT_TOPIC_FIELDS = {
    "topic_id": "topic_id",
    "type": "type",
    "title": "title",
    "create_time": "create_time",
    "modify_time": "modify_time",
    "digested": "digested",
    "annotation": "annotation",
}

COUNT_FIELDS = {
    "likes_count": "likes",
    "comments_count": "comments",
    "reading_count": "reading",
    "readers_count": "readers",
    "rewards_count": "rewards",
}

EXPECTED_RAW_IMPORT_KEYS = [
    "topic_id",
    "group",
    "type",
    "title",
    "create_time",
    "modify_time",
    "digested",
    "sticky",
    "answered",
    "silenced",
    "annotation",
    "likes_count",
    "tourist_likes_count",
    "rewards_count",
    "comments_count",
    "reading_count",
    "readers_count",
    "user_liked",
    "user_subscribed",
    "talk",
    "question",
    "answer",
    "show_comments",
    "latest_likes",
    "likes_detail",
    "user_specific",
]


def _group_id_value(group_id: str) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def _fetch_sample_topic_ids(group_id: str, per_category: int) -> dict[str, list[str]]:
    conn = connect()
    cur = conn.cursor()
    group_value = _group_id_value(group_id)

    queries = {
        "comments": """
            SELECT topic_id::text
            FROM topics
            WHERE group_id = ? AND comments_count > 0
            ORDER BY create_time DESC
            LIMIT ?
        """,
        "qa": """
            SELECT topic_id::text
            FROM topics
            WHERE group_id = ? AND type = 'q&a'
            ORDER BY create_time DESC
            LIMIT ?
        """,
        "article": """
            SELECT topic_id::text
            FROM topics
            WHERE group_id = ? AND type = 'article'
            ORDER BY create_time DESC
            LIMIT ?
        """,
        "images": """
            SELECT DISTINCT t.topic_id::text
            FROM topics t
            JOIN images i ON i.topic_id = t.topic_id
            WHERE t.group_id = ? AND i.comment_id IS NULL
            ORDER BY t.topic_id::text DESC
            LIMIT ?
        """,
        "tags": """
            SELECT DISTINCT t.topic_id::text
            FROM topics t
            JOIN topic_tags tt ON tt.topic_id = t.topic_id
            WHERE t.group_id = ?
            ORDER BY t.topic_id::text DESC
            LIMIT ?
        """,
        "files": """
            SELECT DISTINCT t.topic_id::text
            FROM topics t
            JOIN topic_files tf ON tf.topic_id = t.topic_id
            WHERE t.group_id = ?
            ORDER BY t.topic_id::text DESC
            LIMIT ?
        """,
    }
    samples: dict[str, list[str]] = {}
    try:
        for name, sql in queries.items():
            cur.execute(sql, (group_value, per_category))
            samples[name] = [str(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()
    return samples


def _normalize_mcp_topic(topic: dict[str, Any], comments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    counts = topic.get("counts") if isinstance(topic.get("counts"), dict) else {}
    owner = topic.get("owner") if isinstance(topic.get("owner"), dict) else {}
    files = topic.get("files") if isinstance(topic.get("files"), list) else []
    images = topic.get("images") if isinstance(topic.get("images"), list) else []
    normalized: dict[str, Any] = {
        "topic_id": topic.get("topic_id"),
        "group": topic.get("group") if isinstance(topic.get("group"), dict) else {},
        "type": topic.get("type"),
        "title": topic.get("title"),
        "create_time": topic.get("create_time"),
        "modify_time": topic.get("modify_time"),
        "digested": topic.get("digested", False),
        "annotation": topic.get("annotation"),
        "likes_count": counts.get("likes", 0),
        "rewards_count": counts.get("rewards", 0),
        "comments_count": counts.get("comments", 0),
        "reading_count": counts.get("reading", 0),
        "readers_count": counts.get("readers", 0),
    }
    if topic.get("type") == "q&a":
        normalized["question"] = {"text": topic.get("content") or "", "owner": owner}
    else:
        normalized["talk"] = {"text": topic.get("content") or "", "owner": owner, "images": images, "files": files}
    if comments is not None:
        normalized["show_comments"] = comments
    return normalized


def _coverage(normalized: dict[str, Any]) -> dict[str, Any]:
    present = sorted(key for key in EXPECTED_RAW_IMPORT_KEYS if key in normalized and normalized.get(key) is not None)
    missing = sorted(key for key in EXPECTED_RAW_IMPORT_KEYS if key not in normalized or normalized.get(key) is None)
    return {
        "present": present,
        "missing": missing,
        "present_count": len(present),
        "expected_count": len(EXPECTED_RAW_IMPORT_KEYS),
    }


def _summarize_mcp_topic(topic: dict[str, Any], comments_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    comments = None
    if comments_payload:
        raw_comments = comments_payload.get("comments")
        if not isinstance(raw_comments, list):
            raw_comments = comments_payload.get("comments_brief")
        comments = raw_comments if isinstance(raw_comments, list) else []
    normalized = _normalize_mcp_topic(topic, comments)
    counts = topic.get("counts") if isinstance(topic.get("counts"), dict) else {}
    return {
        "topic_id": topic.get("topic_id"),
        "type": topic.get("type"),
        "source_keys": sorted(topic.keys()),
        "counts": counts,
        "file_count": len(topic.get("files") or []),
        "image_count": len(topic.get("images") or []),
        "comment_payload": None
        if comments_payload is None
        else {
            "success": comments_payload.get("success"),
            "top_level_keys": sorted(comments_payload.keys()),
            "comment_count": len(comments or []),
            "first_comment_keys": sorted(comments[0].keys()) if comments else [],
        },
        "normalized_keys": sorted(normalized.keys()),
        "import_key_coverage": _coverage(normalized),
        "directly_supported_tables": {
            "groups": bool(normalized.get("group")),
            "users": bool((normalized.get("talk") or normalized.get("question") or {}).get("owner")),
            "topics": True,
            "talks": "talk" in normalized,
            "questions": "question" in normalized,
            "answers": "answer" in normalized,
            "comments": "show_comments" in normalized,
            "images": bool((normalized.get("talk") or {}).get("images")),
            "topic_files": bool((normalized.get("talk") or {}).get("files")),
            "files": bool((normalized.get("talk") or {}).get("files")),
            "tags": False,
            "likes": False,
            "like_emojis": False,
            "user_liked_emojis": False,
        },
    }


def _topic_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    topic = payload.get("topic")
    return topic if isinstance(topic, dict) else payload


def _call_raw_topics(client: McpClient, group_id: str, begin_time: str | None, end_time: str | None) -> dict[str, Any]:
    query: dict[str, Any] = {"scope": "all", "count": 3}
    if begin_time:
        query["begin_time"] = begin_time
    if end_time:
        query["end_time"] = end_time
    return client.tool(
        "call_zsxq_api",
        {"method": "GET", "path": f"/v2/groups/{group_id}/topics", "query": query},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run MCP topic payload coverage against current import expectations.")
    parser.add_argument("--server", default="zsxq-topic")
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--per-category", type=int, default=2)
    parser.add_argument("--latest-limit", type=int, default=5)
    parser.add_argument("--begin-time", help="Optional raw API begin_time probe.")
    parser.add_argument("--end-time", help="Optional raw API end_time probe.")
    args = parser.parse_args()

    client = McpClient(_load_mcp_url(args.server))
    server_info = client.initialize()
    local_samples = _fetch_sample_topic_ids(args.group_id, max(1, args.per_category))

    latest_payload = client.tool(
        "get_group_topics",
        {"group_id": args.group_id, "limit": max(1, min(args.latest_limit, 30)), "scope": "all"},
    )
    latest_topics = _topic_list(latest_payload)

    selected_ids: list[str] = []
    for topic in latest_topics:
        topic_id = topic.get("topic_id")
        if topic_id:
            selected_ids.append(str(topic_id))
    for ids in local_samples.values():
        for topic_id in ids:
            if topic_id not in selected_ids:
                selected_ids.append(topic_id)

    detail_results = []
    for topic_id in selected_ids:
        detail_payload = client.tool("get_topic_info", {"topic_id": topic_id})
        topic = _topic_from_payload(detail_payload)
        counts = topic.get("counts") if isinstance(topic.get("counts"), dict) else {}
        comments_payload = None
        if counts.get("comments"):
            comments_payload = client.tool("get_topic_comments", {"topic_id": topic_id, "limit": 30})
        detail_results.append(_summarize_mcp_topic(topic, comments_payload))

    raw_range_probe = None
    if args.begin_time or args.end_time:
        raw = _call_raw_topics(client, args.group_id, args.begin_time, args.end_time)
        body = raw.get("body") if isinstance(raw.get("body"), dict) else {}
        resp_data = body.get("resp_data") if isinstance(body.get("resp_data"), dict) else {}
        raw_range_probe = {
            "success": raw.get("success"),
            "status_code": raw.get("status_code"),
            "body_keys": sorted(body.keys()) if isinstance(body, dict) else [],
            "topic_count": len(resp_data.get("topics") or []),
            "has_more": resp_data.get("has_more"),
        }

    table_counts: dict[str, int] = {}
    for result in detail_results:
        for table, supported in result["directly_supported_tables"].items():
            if supported:
                table_counts[table] = table_counts.get(table, 0) + 1

    print(
        json.dumps(
            {
                "server": server_info,
                "local_sample_ids": local_samples,
                "latest_topic_count": len(latest_topics),
                "detail_topic_count": len(detail_results),
                "table_support_counts": table_counts,
                "details": detail_results,
                "raw_range_probe": raw_range_probe,
                "still_unverified": [
                    "article payload mapping" if not table_counts.get("articles") else None,
                    "answer payload mapping" if not table_counts.get("answers") else None,
                    "tag extraction from MCP payload" if not table_counts.get("tags") else None,
                    "likes/latest_likes/emoji payloads" if not table_counts.get("likes") else None,
                    "file download URL or file bytes",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
