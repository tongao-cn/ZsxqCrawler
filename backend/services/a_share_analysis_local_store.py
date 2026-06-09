from __future__ import annotations

import csv
import json
import os
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from backend.core.db_path_manager import get_db_path_manager


DEFAULT_OUTPUT_PATH = "output/company_mentions_last_month.csv"
DEFAULT_STATE_PATH = "output/company_mentions_state.json"
GROUP_ANALYSIS_DIRNAME = "a_share_analysis"
GROUP_OUTPUT_FILENAME = "company_mentions.csv"
GROUP_STATE_FILENAME = "company_mentions_state.json"


def normalize_group_id(group_id: Optional[str]) -> Optional[str]:
    if group_id is None:
        return None
    normalized = str(group_id).strip()
    return normalized or None


def get_group_analysis_paths(group_id: str) -> Dict[str, str]:
    normalized_group_id = normalize_group_id(group_id)
    if not normalized_group_id:
        raise ValueError("group_id 不能为空")

    path_manager = get_db_path_manager()
    analysis_dir = os.path.join(path_manager.get_group_dir(normalized_group_id), GROUP_ANALYSIS_DIRNAME)
    return {
        "group_id": normalized_group_id,
        "analysis_dir": analysis_dir,
        "output_path": os.path.join(analysis_dir, GROUP_OUTPUT_FILENAME),
        "state_path": os.path.join(analysis_dir, GROUP_STATE_FILENAME),
    }


def resolve_analysis_paths(
    output_path: str = DEFAULT_OUTPUT_PATH,
    state_path: str = DEFAULT_STATE_PATH,
    group_id: Optional[str] = None,
) -> Tuple[str, str]:
    normalized_group_id = normalize_group_id(group_id)
    if normalized_group_id and output_path == DEFAULT_OUTPUT_PATH and state_path == DEFAULT_STATE_PATH:
        group_paths = get_group_analysis_paths(normalized_group_id)
        return group_paths["output_path"], group_paths["state_path"]
    return output_path, state_path


def read_existing_csv_file(
    output_path: str = DEFAULT_OUTPUT_PATH,
    log_info: Optional[Callable[[str], None]] = None,
) -> Dict[str, Dict[str, int]]:
    daily: Dict[str, Dict[str, int]] = {}
    if not os.path.exists(output_path):
        return daily
    try:
        with open(output_path, "r", encoding="utf-8", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            for row in reader:
                day = (row.get("date") or "").strip()
                company = (row.get("company") or "").strip()
                if not day or not company:
                    continue
                try:
                    count = int(str(row.get("articles_count") or "0").strip())
                except Exception:
                    continue
                daily.setdefault(day, {})[company] = count
    except Exception:
        return {}

    if log_info:
        total_entries = sum(sum(company_counts.values()) for company_counts in daily.values())
        log_info(f"loaded existing csv days={len(daily)} total_entries={total_entries}")
    return daily


def write_csv_file(
    daily: Dict[str, Dict[str, int]],
    output_path: str = DEFAULT_OUTPUT_PATH,
    log_info: Optional[Callable[[str], None]] = None,
) -> None:
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(["date", "company", "articles_count"])
        for day in sorted(daily.keys()):
            for company, count in sorted(daily[day].items(), key=lambda item: (-item[1], item[0])):
                writer.writerow([day, company, count])
    if log_info:
        log_info(f"legacy local csv fallback written: {output_path}")


def load_state_file(
    state_path: str = DEFAULT_STATE_PATH,
    log_info: Optional[Callable[[str], None]] = None,
) -> set:
    if not os.path.exists(state_path):
        if log_info:
            log_info("state file not found, start fresh")
        return set()
    try:
        with open(state_path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
            processed = set(data.get("processed", []))
            if log_info:
                log_info(f"loaded state entries={len(processed)}")
            return processed
    except Exception:
        return set()


def save_state_file(
    state_path: str = DEFAULT_STATE_PATH,
    processed_keys: Optional[Iterable[str]] = None,
    log_info: Optional[Callable[[str], None]] = None,
) -> None:
    directory = os.path.dirname(state_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    payload = {"processed": sorted(list(processed_keys or set()))}
    with open(state_path, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)
    if log_info:
        log_info(f"saved state entries={len(payload['processed'])} to {state_path}")
