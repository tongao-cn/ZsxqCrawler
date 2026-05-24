from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _find_cli(explicit_path: str | None = None) -> str | None:
    if explicit_path:
        return explicit_path

    for name in ("zsxq-cli", "zsxq-cli.exe"):
        found = shutil.which(name)
        if found:
            return found

    npx_root = Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"
    if npx_root.exists():
        candidates = sorted(
            npx_root.glob(r"*\node_modules\@zsxq\cli-win32-x64\bin\zsxq-cli.exe"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return str(candidates[0])

    return None


def _run_json(cli_path: str, args: list[str]) -> tuple[int, Any, str]:
    completed = subprocess.run(
        [cli_path, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    raw = (completed.stdout or completed.stderr or "").strip()
    if not raw:
        return completed.returncode, None, raw
    try:
        return completed.returncode, json.loads(raw), raw
    except json.JSONDecodeError:
        return completed.returncode, None, raw


def _topic_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    candidates = [
        payload.get("topics_brief"),
        payload.get("topics"),
        payload.get("data"),
        payload.get("resp_data", {}).get("topics") if isinstance(payload.get("resp_data"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
        if isinstance(candidate, dict) and isinstance(candidate.get("topics"), list):
            return [item for item in candidate["topics"] if isinstance(item, dict)]
    return []


def _summarize_topic(topic: dict[str, Any]) -> dict[str, Any]:
    counts = topic.get("counts") if isinstance(topic.get("counts"), dict) else {}
    return {
        "topic_id": topic.get("topic_id") or topic.get("id"),
        "type": topic.get("type"),
        "title": topic.get("title"),
        "create_time": topic.get("create_time") or topic.get("created_at"),
        "has_content": bool(topic.get("content") or topic.get("text") or topic.get("talk")),
        "likes_count": topic.get("likes_count") or counts.get("likes"),
        "comments_count": topic.get("comments_count") or counts.get("comments"),
        "raw_keys": sorted(topic.keys()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe official zsxq-cli read APIs without touching ZsxqCrawler runtime.")
    parser.add_argument("--group-id", help="Group id to probe. If omitted, only auth and CLI availability are checked.")
    parser.add_argument("--limit", type=int, default=3, help="Topic page size for group +topics, max 30.")
    parser.add_argument("--cli-path", help="Explicit zsxq-cli binary path.")
    parser.add_argument("--detail", action="store_true", help="Fetch topic +detail for the first returned topic.")
    args = parser.parse_args()

    cli_path = _find_cli(args.cli_path)
    result: dict[str, Any] = {
        "cli_found": bool(cli_path),
        "cli_path": cli_path,
        "auth": None,
        "topics": None,
        "detail": None,
    }
    if not cli_path:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    code, auth_payload, auth_raw = _run_json(cli_path, ["auth", "status", "--json"])
    result["auth"] = {
        "exit_code": code,
        "json": auth_payload,
        "raw": auth_raw if auth_payload is None else None,
    }
    logged_in = bool(
        isinstance(auth_payload, dict)
        and auth_payload.get("ok") is True
        and isinstance(auth_payload.get("data"), dict)
        and auth_payload["data"].get("loggedIn") is True
    )
    if not logged_in:
        result["blocked"] = "zsxq-cli is available, but the local OAuth account is not logged in."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3

    if not args.group_id:
        result["blocked"] = "logged in, but --group-id was not provided."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 4

    limit = max(1, min(args.limit, 30))
    code, topics_payload, topics_raw = _run_json(
        cli_path,
        ["group", "+topics", "--group-id", args.group_id, "--limit", str(limit), "--json"],
    )
    topics = _topic_items(topics_payload)
    result["topics"] = {
        "exit_code": code,
        "count": len(topics),
        "summaries": [_summarize_topic(topic) for topic in topics],
        "top_level_keys": sorted(topics_payload.keys()) if isinstance(topics_payload, dict) else None,
        "raw": topics_raw if topics_payload is None else None,
    }

    first_topic_id = result["topics"]["summaries"][0]["topic_id"] if topics else None
    if args.detail and first_topic_id:
        code, detail_payload, detail_raw = _run_json(
            cli_path,
            ["topic", "+detail", "--topic-id", str(first_topic_id), "--json"],
        )
        result["detail"] = {
            "exit_code": code,
            "top_level_keys": sorted(detail_payload.keys()) if isinstance(detail_payload, dict) else None,
            "raw": detail_raw if detail_payload is None else None,
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if code == 0 else 5


if __name__ == "__main__":
    sys.exit(main())
