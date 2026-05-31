from __future__ import annotations

import json
from typing import Any, Dict


def extract_json_object(text: Any) -> Dict[str, Any]:
    content = str(text or "").strip()
    if not content:
        return {}

    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        payload = json.loads(content)
    except Exception:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            payload = json.loads(content[start : end + 1])
        except Exception:
            return {}

    return payload if isinstance(payload, dict) else {}
