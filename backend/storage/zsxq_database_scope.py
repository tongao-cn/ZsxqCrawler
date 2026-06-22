from __future__ import annotations

from typing import Any, Optional


def group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def nullable_group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    if not value:
        return None
    return int(value) if value.isdigit() else value
