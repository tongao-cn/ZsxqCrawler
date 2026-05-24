from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_ENV_PATH = PROJECT_ROOT / ".env"
MCP_RPC_MAX_ATTEMPTS = 3
MCP_RPC_RETRY_DELAY_SECONDS = 1.0
MCP_RPC_429_RETRY_DELAY_SECONDS = 20.0
MCP_RPC_MAX_RETRY_DELAY_SECONDS = 60.0
MCP_TOOL_MIN_INTERVAL_SECONDS = 0.5
MCP_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
API_KEY_PATTERN = re.compile(r"([?&]api_key=)[^&\s'\"),]+")


def _strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_project_env_file(path: Path = DEFAULT_PROJECT_ENV_PATH) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = _strip_env_value(value)


def sanitize_mcp_error(message: Any) -> str:
    return API_KEY_PATTERN.sub(r"\1***", str(message))


def official_payload_topics(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return payload.get("topics_brief") or payload.get("topics") or []


def official_payload_comments(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return payload.get("comments") or []


def official_payload_topic(payload: Dict[str, Any]) -> Dict[str, Any]:
    topic = payload.get("topic")
    return topic if isinstance(topic, dict) else {}


def official_payload_user(payload: Dict[str, Any]) -> Dict[str, Any]:
    user = payload.get("user")
    return user if isinstance(user, dict) else {}


def official_payload_groups(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return payload.get("groups") or []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_group(group: Dict[str, Any], fallback_group_id: str) -> Dict[str, Any]:
    group_id = group.get("group_id") or fallback_group_id
    return {
        "group_id": _safe_int(group_id) if str(group_id).isdigit() else group_id,
        "name": group.get("name", ""),
        "type": group.get("type", ""),
        "background_url": group.get("background_url", ""),
    }


def _normalize_counts(counts: Dict[str, Any]) -> Dict[str, int]:
    return {
        "likes_count": _safe_int(counts.get("likes")),
        "tourist_likes_count": _safe_int(counts.get("tourist_likes")),
        "rewards_count": _safe_int(counts.get("rewards")),
        "comments_count": _safe_int(counts.get("comments")),
        "reading_count": _safe_int(counts.get("reading")),
        "readers_count": _safe_int(counts.get("readers")),
    }


def normalize_official_topic(
    topic: Dict[str, Any],
    fallback_group_id: str,
    comments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    owner = topic.get("owner") or {}
    normalized = {
        "topic_id": _safe_int(topic.get("topic_id")),
        "group": _normalize_group(topic.get("group") or {}, fallback_group_id),
        "type": topic.get("type") or "talk",
        "title": topic.get("title") or "",
        "create_time": topic.get("create_time") or "",
        "modify_time": topic.get("modify_time") or "",
        "digested": bool(topic.get("digested")),
        "sticky": bool(topic.get("sticky")),
        "answered": bool(topic.get("answered")),
        "silenced": bool(topic.get("silenced")),
        "annotation": topic.get("annotation") or "",
        "user_liked": bool(topic.get("user_liked")),
        "user_subscribed": bool(topic.get("user_subscribed")),
        **_normalize_counts(topic.get("counts") or {}),
    }

    content = topic.get("content") or ""
    topic_type = normalized["type"]
    if topic_type == "q&a":
        normalized["question"] = {
            "text": content,
            "owner": owner,
            "anonymous": False,
        }
        if topic.get("answer"):
            normalized["answer"] = topic["answer"]
    elif topic_type == "article":
        normalized["talk"] = {
            "text": content,
            "owner": owner,
            "images": topic.get("images") or [],
            "files": topic.get("files") or [],
        }
        normalized["article"] = topic.get("article") or {
            "title": topic.get("title") or "",
            "article_id": str(topic.get("topic_id") or ""),
            "article_url": topic.get("article_url") or "",
            "inline_article_url": topic.get("inline_article_url") or "",
        }
    else:
        normalized["talk"] = {
            "text": content,
            "owner": owner,
            "images": topic.get("images") or [],
            "files": topic.get("files") or [],
        }

    if comments is not None:
        normalized["show_comments"] = comments

    return normalized


class OfficialTopicClient:
    def __init__(self, mcp_url: Optional[str] = None, log_callback: Optional[Callable[[str], None]] = None):
        _load_project_env_file()
        self.mcp_url = mcp_url or os.getenv("ZSXQ_TOPIC_MCP_URL")
        self.log_callback = log_callback
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._next_id = 1
        self._initialized = False
        self._last_tool_call_at = 0.0

    def _ensure_url(self) -> str:
        if not self.mcp_url:
            raise RuntimeError("ZSXQ_TOPIC_MCP_URL is required for the official MCP topic flow")
        return self.mcp_url

    def _parse_sse_events(self, content: bytes) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        data_lines: List[bytes] = []
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

    def _log_retry(self, method: str, attempt: int, delay_seconds: float, exc: Exception) -> None:
        if self.log_callback:
            self.log_callback(
                f"⚠️ MCP {method} 请求失败，{delay_seconds:.1f}秒后重试 {attempt}/{MCP_RPC_MAX_ATTEMPTS - 1}: {sanitize_mcp_error(exc)}"
            )

    def _is_retryable_request_error(self, exc: requests.RequestException) -> bool:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            return status_code in MCP_RETRYABLE_STATUS_CODES
        return True

    def _retry_delay_seconds(self, exc: requests.RequestException, attempt: int) -> float:
        response = getattr(exc, "response", None)
        retry_after = getattr(response, "headers", {}).get("Retry-After") if response is not None else None
        if retry_after:
            try:
                return min(float(retry_after), MCP_RPC_MAX_RETRY_DELAY_SECONDS)
            except (TypeError, ValueError):
                pass
        status_code = getattr(response, "status_code", None)
        base_delay = MCP_RPC_429_RETRY_DELAY_SECONDS if status_code == 429 else MCP_RPC_RETRY_DELAY_SECONDS
        return min(base_delay * attempt, MCP_RPC_MAX_RETRY_DELAY_SECONDS)

    def _post_rpc(self, body: Dict[str, Any], method: str) -> requests.Response:
        last_error: Optional[Exception] = None
        for attempt in range(1, MCP_RPC_MAX_ATTEMPTS + 1):
            try:
                response = requests.post(
                    self._ensure_url(),
                    headers=self.headers,
                    json=body,
                    timeout=120,
                )
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                if not self._is_retryable_request_error(exc):
                    raise RuntimeError(f"MCP method {method!r} request failed: {sanitize_mcp_error(exc)}") from exc
                last_error = exc
                if attempt >= MCP_RPC_MAX_ATTEMPTS:
                    break
                delay_seconds = self._retry_delay_seconds(exc, attempt)
                self._log_retry(method, attempt, delay_seconds, exc)
                time.sleep(delay_seconds)

        raise RuntimeError(
            f"MCP method {method!r} request failed after {MCP_RPC_MAX_ATTEMPTS} attempts: {sanitize_mcp_error(last_error)}"
        ) from last_error

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None, expect_response: bool = True) -> Dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        body: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if expect_response:
            body["id"] = request_id

        response = self._post_rpc(body, method)
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self.headers["Mcp-Session-Id"] = session_id
        if not expect_response:
            return {}

        events = self._parse_sse_events(response.content)
        if not events:
            raise RuntimeError(f"MCP method {method!r} returned no SSE events")
        payload = events[-1]
        if "error" in payload:
            raise RuntimeError(f"MCP method {method!r} failed: {payload['error']}")
        return payload

    def _throttle_tool_call(self) -> None:
        elapsed = time.monotonic() - self._last_tool_call_at
        if elapsed < MCP_TOOL_MIN_INTERVAL_SECONDS:
            time.sleep(MCP_TOOL_MIN_INTERVAL_SECONDS - elapsed)
        self._last_tool_call_at = time.monotonic()

    def _initialize(self) -> None:
        if self._initialized:
            return
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "zsxq-crawler", "version": "0.1"},
            },
        )
        self._rpc("notifications/initialized", {}, expect_response=False)
        self._initialized = True

    def _call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._initialize()
        self._throttle_tool_call()
        payload = self._rpc("tools/call", {"name": tool_name, "arguments": params})
        content = payload.get("result", {}).get("content") or []
        if not content:
            return {}
        text = content[0].get("text") if isinstance(content[0], dict) else None
        return json.loads(text) if text else {}

    def get_group_topics(
        self,
        group_id: str,
        limit: int,
        scope: str = "all",
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "group_id": str(group_id),
            "limit": limit,
            "scope": scope,
        }
        if end_time:
            params["end_time"] = end_time
        return self._call_tool("get_group_topics", params)

    def get_topic_info(self, topic_id: int) -> Dict[str, Any]:
        return self._call_tool("get_topic_info", {"topic_id": str(topic_id)})

    def get_self_info(self) -> Dict[str, Any]:
        return self._call_tool("get_self_info", {})

    def get_user_groups(self, user_id: int | str, limit: int = 200, scope: str = "all") -> Dict[str, Any]:
        return self._call_tool("get_user_groups", {"user_id": str(user_id), "limit": limit, "scope": scope})

    def get_topic_comments(self, topic_id: int, limit: int = 30) -> List[Dict[str, Any]]:
        comments: List[Dict[str, Any]] = []
        index = None
        while True:
            params: Dict[str, Any] = {"topic_id": str(topic_id), "limit": limit}
            if index:
                params["index"] = index
            payload = self._call_tool("get_topic_comments", params)
            comments.extend(official_payload_comments(payload))
            index = payload.get("index")
            if not payload.get("has_more") or not index:
                break
        return comments
