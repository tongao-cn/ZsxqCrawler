from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.db_path_manager import get_db_path_manager
from backend.services.a_share_analysis_db_storage import get_storage_health
from backend.services.a_share_analysis_service import (
    DEFAULT_OUTPUT_PATH,
    DEFAULT_STATE_PATH,
    GROUP_ANALYSIS_DIRNAME,
    GROUP_OUTPUT_FILENAME,
    GROUP_STATE_FILENAME,
    normalize_group_id,
)


def _project_root() -> Path:
    return PROJECT_ROOT


def _count_csv_rows(path: Path) -> tuple[int, str | None, str | None]:
    if not path.exists():
        return 0, None, None

    rows = 0
    start_date: str | None = None
    end_date: str | None = None
    with path.open("r", encoding="utf-8", newline="") as file_obj:
        for row in csv.DictReader(file_obj):
            day = str(row.get("date") or "").strip()
            company = str(row.get("company") or "").strip()
            if not day or not company:
                continue
            rows += 1
            start_date = day if start_date is None or day < start_date else start_date
            end_date = day if end_date is None or day > end_date else end_date
    return rows, start_date, end_date


def _count_state_entries(path: Path) -> int:
    if not path.exists():
        return 0

    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    processed = data.get("processed") if isinstance(data, dict) else None
    return len(processed) if isinstance(processed, list) else 0


def _storage_health(group_id: str | None) -> dict[str, Any]:
    try:
        return get_storage_health(group_id=group_id)
    except Exception as exc:
        return {
            "enabled": False,
            "error": str(exc),
            "daily_rows": None,
            "processed_rows": None,
        }


def _candidate(label: str, group_id: str | None, output_path: Path, state_path: Path) -> dict[str, Any]:
    csv_rows, start_date, end_date = _count_csv_rows(output_path)
    state_entries = _count_state_entries(state_path)
    health = _storage_health(group_id)
    return {
        "label": label,
        "group_id": group_id or "GLOBAL",
        "csv_path": str(output_path),
        "csv_exists": output_path.exists(),
        "csv_rows": csv_rows,
        "csv_start_date": start_date,
        "csv_end_date": end_date,
        "state_path": str(state_path),
        "state_exists": state_path.exists(),
        "state_entries": state_entries,
        "db_enabled": bool(health.get("enabled")),
        "db_daily_rows": health.get("daily_rows"),
        "db_processed_rows": health.get("processed_rows"),
        "db_error": health.get("error"),
    }


def audit_candidates(group_id: str | None = None) -> list[dict[str, Any]]:
    root = _project_root()
    normalized_group_id = normalize_group_id(group_id)
    path_manager = get_db_path_manager()
    if normalized_group_id:
        group_dir = Path(path_manager.base_dir) / normalized_group_id
        return [
            _candidate(
                f"group {normalized_group_id}",
                normalized_group_id,
                group_dir / GROUP_ANALYSIS_DIRNAME / GROUP_OUTPUT_FILENAME,
                group_dir / GROUP_ANALYSIS_DIRNAME / GROUP_STATE_FILENAME,
            )
        ]

    candidates = [
        _candidate("global", None, root / DEFAULT_OUTPUT_PATH, root / DEFAULT_STATE_PATH),
    ]
    for group_dir in sorted(Path(path_manager.base_dir).iterdir()):
        if not group_dir.is_dir():
            continue
        analysis_dir = group_dir / GROUP_ANALYSIS_DIRNAME
        output_path = analysis_dir / GROUP_OUTPUT_FILENAME
        state_path = analysis_dir / GROUP_STATE_FILENAME
        if output_path.exists() or state_path.exists():
            candidates.append(_candidate(f"group {group_dir.name}", group_dir.name, output_path, state_path))
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit legacy local A-share analysis CSV/state files without deleting them.")
    parser.add_argument("--group-id", help="Audit one group only. Omit to scan global and all group local files.")
    args = parser.parse_args()

    for item in audit_candidates(args.group_id):
        print(json.dumps(item, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
