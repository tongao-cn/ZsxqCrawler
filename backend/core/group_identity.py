from __future__ import annotations

from typing import Optional


def normalize_group_id(group_id: Optional[str]) -> Optional[str]:
    if group_id is None:
        return None
    normalized = str(group_id).strip()
    return normalized or None
