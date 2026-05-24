from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

import requests


def _load_mcp_url(server_name: str) -> str:
    completed = subprocess.run(
        ["codex", "mcp", "get", server_name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    for line in completed.stdout.splitlines():
        if line.strip().startswith("url:"):
            return line.split("url:", 1)[1].strip()
    raise RuntimeError(f"MCP server {server_name!r} has no URL in `codex mcp get` output")


def _parse_sse_events(content: bytes) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    data_lines: list[bytes] = []
    for raw_line in content.splitlines():
        line = raw_line.rstrip(b"\r")
        if not line:
            if data_lines:
                events.append(json.loads(b"\n".join(data_lines).decode("utf-8")))
                data_lines = []
            continue
        if line.startswith(b"data:"):
            data_lines.append(line.split(b"data:", 1)[1].lstrip())
    if data_lines:
        events.append(json.loads(b"\n".join(data_lines).decode("utf-8")))
    return events


class McpClient:
    def __init__(self, url: str):
        self.url = url
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._next_id = 1

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        response = requests.post(
            self.url,
            headers=self.headers,
            json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
            timeout=60,
        )
        response.raise_for_status()
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self.headers["Mcp-Session-Id"] = session_id
        events = _parse_sse_events(response.content)
        if not events:
            raise RuntimeError(f"MCP method {method!r} returned no SSE events")
        payload = events[-1]
        if "error" in payload:
            raise RuntimeError(f"MCP method {method!r} failed: {payload['error']}")
        return payload

    def initialize(self) -> dict[str, Any]:
        payload = self.call(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "codex-zsxq-poc", "version": "0.1"},
            },
        )
        requests.post(
            self.url,
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            timeout=30,
        )
        return payload["result"]["serverInfo"]

    def tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = self.call("tools/call", {"name": name, "arguments": arguments})
        content = payload.get("result", {}).get("content") or []
        if not content:
            return {}
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if not text:
            return {}
        return json.loads(text)


def _topic_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("topics_brief", "topics"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _summarize_topic(topic: dict[str, Any]) -> dict[str, Any]:
    counts = topic.get("counts") if isinstance(topic.get("counts"), dict) else {}
    return {
        "topic_id": topic.get("topic_id"),
        "type": topic.get("type"),
        "title": topic.get("title"),
        "create_time": topic.get("create_time"),
        "likes_count": counts.get("likes"),
        "comments_count": counts.get("comments"),
        "reading_count": counts.get("reading"),
        "readers_count": counts.get("readers"),
        "content_chars": len(topic.get("content") or ""),
        "image_count": len(topic.get("images") or []),
        "file_count": len(topic.get("files") or []),
        "raw_keys": sorted(topic.keys()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the configured zsxq-topic MCP server without printing secrets.")
    parser.add_argument("--server", default="zsxq-topic", help="Codex MCP server name.")
    parser.add_argument("--group-id", required=True, help="Knowledge Planet group id.")
    parser.add_argument("--limit", type=int, default=3, help="Topic page size, max 30.")
    parser.add_argument("--comments", action="store_true", help="Fetch comments for the first topic with comments.")
    args = parser.parse_args()

    client = McpClient(_load_mcp_url(args.server))
    server_info = client.initialize()

    tools_payload = client.call("tools/list")
    tools = tools_payload.get("result", {}).get("tools") or []
    tool_names = sorted(tool.get("name") for tool in tools if isinstance(tool, dict) and tool.get("name"))

    topics_payload = client.tool(
        "get_group_topics",
        {"group_id": args.group_id, "limit": max(1, min(args.limit, 30)), "scope": "all"},
    )
    topics = _topic_list(topics_payload)
    topic_summaries = [_summarize_topic(topic) for topic in topics]

    detail_summary: dict[str, Any] | None = None
    if topics:
        first_topic_id = topics[0].get("topic_id")
        detail_payload = client.tool("get_topic_info", {"topic_id": str(first_topic_id)})
        detail_topic = detail_payload.get("topic") if isinstance(detail_payload.get("topic"), dict) else detail_payload
        detail_summary = {
            "topic_id": first_topic_id,
            "success": detail_payload.get("success"),
            "top_level_keys": sorted(detail_payload.keys()),
            "topic_keys": sorted(detail_topic.keys()) if isinstance(detail_topic, dict) else [],
        }

    comments_summary: dict[str, Any] | None = None
    if args.comments:
        comment_topic = next((topic for topic in topics if (topic.get("counts") or {}).get("comments")), None)
        if comment_topic:
            comments_payload = client.tool(
                "get_topic_comments",
                {"topic_id": str(comment_topic.get("topic_id")), "limit": 30},
            )
            comments = comments_payload.get("comments")
            if not isinstance(comments, list):
                comments = comments_payload.get("comments_brief")
            comments_summary = {
                "topic_id": comment_topic.get("topic_id"),
                "success": comments_payload.get("success"),
                "comment_count": len(comments) if isinstance(comments, list) else None,
                "top_level_keys": sorted(comments_payload.keys()),
            }
        else:
            comments_summary = {"blocked": "No returned topic had comments_count > 0."}

    print(
        json.dumps(
            {
                "server": server_info,
                "tool_count": len(tool_names),
                "read_tools_present": {
                    name: name in tool_names
                    for name in ["get_group_topics", "get_topic_info", "get_topic_comments", "call_zsxq_api"]
                },
                "topics": {
                    "success": topics_payload.get("success"),
                    "count": len(topics),
                    "top_level_keys": sorted(topics_payload.keys()),
                    "summaries": topic_summaries,
                },
                "detail": detail_summary,
                "comments": comments_summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
