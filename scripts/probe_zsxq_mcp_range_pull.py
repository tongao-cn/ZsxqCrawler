from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from scripts.probe_zsxq_mcp_topics import McpClient, _load_mcp_url, _topic_list


BJ_TZ = timezone(timedelta(hours=8))


def _parse_zsxq_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("+0800", "+08:00"))


def _format_zsxq_time(value: datetime) -> str:
    value = value.astimezone(BJ_TZ)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"


def _default_begin_end(days: int) -> tuple[datetime, datetime]:
    now = datetime.now(BJ_TZ)
    end = now
    begin = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    return begin, end


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only range pull probe using zsxq-topic MCP end_time pagination.")
    parser.add_argument("--server", default="zsxq-topic")
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--begin-time")
    parser.add_argument("--end-time")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--max-pages", type=int, default=10000)
    args = parser.parse_args()

    if args.begin_time:
        begin = _parse_zsxq_time(args.begin_time)
    else:
        begin, _ = _default_begin_end(args.days)
    if args.end_time:
        end = _parse_zsxq_time(args.end_time)
    else:
        _, end = _default_begin_end(args.days)

    client = McpClient(_load_mcp_url(args.server))
    server_info = client.initialize()

    cursor = _format_zsxq_time(end)
    limit = max(1, min(args.limit, 30))
    pages: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    matched: list[dict[str, Any]] = []
    matched_seen: set[str] = set()
    matched_duplicate_count = 0
    scanned_count = 0
    stop_reason = "unknown"

    for page_no in range(1, args.max_pages + 1):
        payload = client.tool(
            "get_group_topics",
            {"group_id": args.group_id, "limit": limit, "scope": "all", "end_time": cursor},
        )
        topics = _topic_list(payload)
        page_info: dict[str, Any] = {
            "page": page_no,
            "success": payload.get("success"),
            "count": len(topics),
            "has_more": payload.get("has_more"),
            "next_end_time": payload.get("next_end_time"),
        }
        if topics:
            page_info["first_time"] = topics[0].get("create_time")
            page_info["last_time"] = topics[-1].get("create_time")
        pages.append(page_info)

        if not payload.get("success"):
            stop_reason = "api_unsuccessful"
            break
        if not topics:
            stop_reason = "empty_page"
            break

        scanned_count += len(topics)
        oldest = None
        for topic in topics:
            topic_id = str(topic.get("topic_id") or "")
            if topic_id in seen:
                duplicates.append(topic_id)
            elif topic_id:
                seen.add(topic_id)
            create_time = topic.get("create_time")
            if not create_time:
                continue
            created_at = _parse_zsxq_time(create_time)
            oldest = created_at if oldest is None or created_at < oldest else oldest
            if begin <= created_at <= end:
                if topic_id in matched_seen:
                    matched_duplicate_count += 1
                else:
                    matched_seen.add(topic_id)
                    matched.append(
                        {
                            "topic_id": topic_id,
                            "type": topic.get("type"),
                            "title": topic.get("title"),
                            "create_time": create_time,
                            "comments_count": (topic.get("counts") or {}).get("comments"),
                            "file_count": len(topic.get("files") or []),
                            "image_count": len(topic.get("images") or []),
                        }
                    )

        if oldest and oldest < begin:
            stop_reason = "oldest_before_begin_time"
            break
        if not payload.get("has_more"):
            stop_reason = "has_more_false"
            break
        next_end_time = payload.get("next_end_time")
        if not next_end_time or next_end_time == cursor:
            stop_reason = "cursor_not_advancing"
            break
        cursor = str(next_end_time)
    else:
        stop_reason = "max_pages_reached"

    matched_times = [item["create_time"] for item in matched if item.get("create_time")]
    result = {
        "server": server_info,
        "group_id": args.group_id,
        "begin_time": _format_zsxq_time(begin),
        "end_time": _format_zsxq_time(end),
        "limit": limit,
        "pages_scanned": len(pages),
        "topics_scanned": scanned_count,
        "topics_matched_unique": len(matched),
        "topics_matched_duplicate_count": matched_duplicate_count,
        "unique_topics_seen": len(seen),
        "duplicate_count": len(duplicates),
        "duplicate_topic_ids_sample": duplicates[:10],
        "stop_reason": stop_reason,
        "matched_newest": max(matched_times) if matched_times else None,
        "matched_oldest": min(matched_times) if matched_times else None,
        "page_samples": pages[:5] + ([{"omitted_pages": max(0, len(pages) - 10)}] if len(pages) > 10 else []) + pages[-5:],
        "matched_samples": matched[:3] + ([{"omitted_topics": max(0, len(matched) - 6)}] if len(matched) > 6 else []) + matched[-3:],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
