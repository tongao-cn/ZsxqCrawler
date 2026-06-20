from __future__ import annotations

import json
from typing import Any, Dict, Optional


class JsonObjectParseError(ValueError):
    def __init__(self, label: str, text: Any):
        preview = str(text or "").strip().replace("\n", " ")[:200]
        super().__init__(f"{label} is not a valid JSON object: {preview}")


def _strip_json_fence(content: str) -> str:
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _load_json_object(content: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(content)
    except Exception:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(content[start : end + 1])
        except Exception:
            return None

    return payload if isinstance(payload, dict) else None


def extract_json_object(text: Any) -> Dict[str, Any]:
    content = str(text or "").strip()
    if not content:
        return {}

    return _load_json_object(_strip_json_fence(content)) or {}


def require_json_object(text: Any, *, label: str = "AI response") -> Dict[str, Any]:
    content = str(text or "").strip()
    if not content:
        raise JsonObjectParseError(label, text)

    payload = _load_json_object(_strip_json_fence(content))
    if payload is None:
        raise JsonObjectParseError(label, text)
    return payload
