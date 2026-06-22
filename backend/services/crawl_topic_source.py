"""Topic source selection policy for crawl workflows."""

from __future__ import annotations

import os
from typing import Any, Optional


# official means the MCP HTTP flow; "cli" is accepted only as an old spelling
# and does not shell out to zsxq-cli.
OFFICIAL_TOPIC_SOURCE_ALIASES = {"official", "cli", "mcp"}
# legacy means the cookie-based ZSXQTopicCrawler fallback.
LEGACY_TOPIC_SOURCE_ALIASES = {"legacy", "crawler", "cookie"}


def normalize_topic_source(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip().lower()
    if not text:
        return None
    if text in OFFICIAL_TOPIC_SOURCE_ALIASES:
        return "official"
    if text in LEGACY_TOPIC_SOURCE_ALIASES:
        return "legacy"
    return None


def resolve_topic_source(request: Any) -> str:
    return (
        normalize_topic_source(getattr(request, "topicSource", None))
        or normalize_topic_source(os.getenv("ZSXQ_TOPIC_SOURCE"))
        or "official"
    )


def uses_official_topic_source(request: Any) -> bool:
    return resolve_topic_source(request) == "official"
