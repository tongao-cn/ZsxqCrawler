from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Sequence


def normalize_json_value(value: Any, default: Any):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return default


def tdx_export_block_payload(row: Sequence[Any]) -> Dict[str, Any]:
    (
        window_days,
        block_name,
        block_code,
        block_path,
        written_count,
        skipped_count,
        skipped_companies,
    ) = row
    return {
        "window_days": int(window_days or 0),
        "block_name": str(block_name or ""),
        "block_code": str(block_code or ""),
        "block_path": str(block_path or ""),
        "written_count": int(written_count or 0),
        "skipped_count": int(skipped_count or 0),
        "skipped_companies": normalize_json_value(skipped_companies, []),
    }


def dedupe_company_names(values: Iterable[Any]) -> List[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def latest_tdx_export_payload(row: Sequence[Any], blocks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    (
        export_id,
        exported_at,
        start_date,
        end_date,
        tdx_root,
        ranking_top_n,
        total_written,
        unresolved_count,
        stock_basic_source,
        source_detail,
        backup_files,
    ) = row

    unresolved_companies: List[Any] = []
    for block in blocks:
        unresolved_companies.extend(list(block.get("skipped_companies") or []))

    return {
        "export_id": int(export_id),
        "exported_at": exported_at.isoformat() if hasattr(exported_at, "isoformat") else str(exported_at),
        "start_date": start_date,
        "end_date": end_date,
        "tdx_root": str(tdx_root or ""),
        "ranking_top_n": int(ranking_top_n or 0),
        "total_written": int(total_written or 0),
        "unresolved_count": int(unresolved_count or 0),
        "unresolved_companies": dedupe_company_names(unresolved_companies),
        "stock_basic_source": str(stock_basic_source or ""),
        "source_detail": str(source_detail or ""),
        "backup_files": normalize_json_value(backup_files, []),
        "blocks": list(blocks),
    }
