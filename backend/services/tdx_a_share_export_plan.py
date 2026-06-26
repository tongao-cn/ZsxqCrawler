"""Pure planning helpers for exporting A-share rankings into TDX blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


RANKING_BLOCK_NAMES = {
    3: "3日推荐池",
    7: "7日推荐池",
    14: "14日推荐池",
    21: "21日推荐池",
    30: "30日推荐池",
}
DEFAULT_TDX_EXPORT_SPECS = ((30, 300), (14, 150), (7, 100))
DEFAULT_TDX_EXPORT_WINDOWS = tuple(window for window, _top_n in DEFAULT_TDX_EXPORT_SPECS)
TDX_BLOCK_CODE_PATTERN = re.compile(r"^ZX(?P<number>\d+)$", re.IGNORECASE)
TS_CODE_PATTERN = re.compile(r"^(?P<code>\d{6})\.(?P<market>SH|SZ|BJ)$", re.IGNORECASE)


@dataclass(frozen=True)
class TdxBlock:
    code: str
    name: str


@dataclass(frozen=True)
class TdxExportRankingSelection:
    sliced_rankings: Mapping[str, Sequence[Mapping[str, Any]]]
    companies: Tuple[str, ...]


@dataclass(frozen=True)
class TdxPendingBlockSync:
    window: int
    block_name: str
    block_code: str
    block_path: str
    converted_codes: Tuple[str, ...]
    skipped_companies: Tuple[str, ...]


@dataclass(frozen=True)
class TdxExportPlan:
    expected_block_names: Tuple[str, ...]
    cfg_by_name: Mapping[str, Mapping[str, str]]
    created_cfg_records: Tuple[Mapping[str, str], ...]
    pending_writes: Tuple[TdxPendingBlockSync, ...]


def normalize_export_specs(
    ranking_windows: Sequence[int],
    ranking_top_n: Optional[int],
) -> Tuple[Tuple[int, int], ...]:
    if ranking_top_n is None:
        requested_windows = {int(item) for item in ranking_windows}
        return tuple(
            (int(window), top_n)
            for window, top_n in DEFAULT_TDX_EXPORT_SPECS
            if int(window) in requested_windows
        )
    return tuple((int(window), int(ranking_top_n)) for window in ranking_windows)


def export_spec_windows(export_specs: Sequence[Tuple[int, int]]) -> Tuple[int, ...]:
    return tuple(int(window) for window, _top_n in export_specs)


def max_export_top_n(export_specs: Sequence[Tuple[int, int]]) -> int:
    return max((int(top_n) for _window, top_n in export_specs), default=0)


def build_tdx_export_ranking_selection(
    rankings: Mapping[str, Any],
    export_specs: Sequence[Tuple[int, int]],
) -> TdxExportRankingSelection:
    sliced_rankings = {
        str(window): list(rankings.get(str(window)) or [])[:top_n]
        for window, top_n in export_specs
    }
    return TdxExportRankingSelection(
        sliced_rankings=sliced_rankings,
        companies=tuple(collect_ranking_companies(sliced_rankings, export_spec_windows(export_specs))),
    )


def build_tdx_export_plan(
    *,
    selection: TdxExportRankingSelection,
    export_specs: Sequence[Tuple[int, int]],
    resolved_codes: Mapping[str, str],
    existing_blocks: Sequence[TdxBlock],
    group_name: Optional[str] = None,
) -> TdxExportPlan:
    expected_block_names = tuple(
        build_export_block_name(window, top_n, group_name)
        for window, top_n in export_specs
    )
    cfg_by_name, created_cfg_records = ensure_tdx_api_blocks(existing_blocks, expected_block_names)
    pending_writes = tuple(
        build_pending_block_sync(
            window,
            top_n,
            selection.sliced_rankings,
            resolved_codes,
            cfg_by_name,
            group_name,
        )
        for window, top_n in export_specs
    )
    return TdxExportPlan(
        expected_block_names=expected_block_names,
        cfg_by_name=cfg_by_name,
        created_cfg_records=tuple(created_cfg_records),
        pending_writes=pending_writes,
    )


def dedupe_keep_order(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_ranking_block_name(window: int, group_name: Optional[str] = None) -> str:
    normalized_group_name = _normalize_tdx_group_name(group_name)
    if normalized_group_name:
        return f"{normalized_group_name}-{int(window)}日"
    return RANKING_BLOCK_NAMES.get(int(window), f"{int(window)}日推荐池")


def build_export_block_name(window: int, top_n: int, group_name: Optional[str] = None) -> str:
    return f"{int(window)}日Top{int(top_n)}"


def next_tdx_block_code(records: Sequence[Mapping[str, str]]) -> str:
    used_codes = {str(record.get("code") or "").strip().upper() for record in records}
    max_number = 0
    for code in used_codes:
        match = TDX_BLOCK_CODE_PATTERN.fullmatch(code)
        if match is not None:
            max_number = max(max_number, int(match.group("number")))

    next_number = max_number + 1
    while f"ZX{next_number:03d}" in used_codes:
        next_number += 1
    return f"ZX{next_number:03d}"


def ensure_tdx_api_blocks(
    existing_blocks: Sequence[TdxBlock],
    block_names: Sequence[str],
) -> Tuple[Dict[str, Dict[str, str]], List[Dict[str, str]]]:
    records = [{"name": block.name, "code": block.code} for block in existing_blocks]
    cfg_by_name = {
        block.name: {"name": block.name, "code": block.code}
        for block in existing_blocks
        if block.name and block.code
    }
    created_records: List[Dict[str, str]] = []

    for block_name in block_names:
        if block_name in cfg_by_name:
            continue
        record = {
            "name": block_name,
            "code": next_tdx_block_code(records),
        }
        records.append(record)
        cfg_by_name[block_name] = record
        created_records.append(record)

    return cfg_by_name, created_records


def normalize_tdx_api_code(ts_code: str) -> Optional[str]:
    match = TS_CODE_PATTERN.fullmatch(str(ts_code or "").strip())
    if match is None:
        return None
    return f"{match.group('code')}.{match.group('market').upper()}"


def collect_ranking_companies(rankings: Mapping[str, Any], ranking_windows: Sequence[int]) -> List[str]:
    all_companies: List[str] = []
    for window in ranking_windows:
        window_rows = rankings.get(str(window)) or []
        all_companies.extend(
            str(item.get("company") or "").strip()
            for item in window_rows
            if str(item.get("company") or "").strip()
        )
    return all_companies


def build_pending_block_sync(
    window: int,
    top_n: int,
    rankings: Mapping[str, Any],
    resolved_codes: Mapping[str, str],
    cfg_by_name: Mapping[str, Mapping[str, str]],
    group_name: Optional[str] = None,
) -> TdxPendingBlockSync:
    block_name = build_export_block_name(window, top_n, group_name)
    cfg_record = cfg_by_name[block_name]
    block_code = str(cfg_record.get("code") or "").strip().upper()
    if not block_code:
        raise RuntimeError(f"板块 {block_name} 没有有效代码")

    ranking_rows = rankings.get(str(window)) or []
    converted_codes: List[str] = []
    skipped_companies: List[str] = []

    for item in ranking_rows:
        company = str(item.get("company") or "").strip()
        if not company:
            continue

        ts_code = resolved_codes.get(company)
        if not ts_code:
            skipped_companies.append(company)
            continue

        tdx_api_code = normalize_tdx_api_code(ts_code)
        if not tdx_api_code:
            skipped_companies.append(company)
            continue
        converted_codes.append(tdx_api_code)

    return TdxPendingBlockSync(
        window=int(window),
        block_name=block_name,
        block_code=block_code,
        block_path=f"tdx-api://{block_code}",
        converted_codes=tuple(dedupe_keep_order(converted_codes)),
        skipped_companies=tuple(dedupe_keep_order(skipped_companies)),
    )


def build_block_export_result(
    window: int,
    block_name: str,
    block_code: str,
    blk_path: Path | str,
    converted_codes: Sequence[str],
    skipped_companies: Sequence[str],
    verified_count: Optional[int] = None,
) -> Dict[str, Any]:
    result = {
        "window_days": window,
        "block_name": block_name,
        "block_code": block_code,
        "block_path": str(blk_path),
        "written_count": len(converted_codes),
        "skipped_count": len(skipped_companies),
        "skipped_companies": list(skipped_companies),
    }
    if verified_count is not None:
        result["verified_count"] = int(verified_count)
    return result


def _normalize_tdx_group_name(group_name: Optional[str]) -> Optional[str]:
    normalized = str(group_name or "").strip()
    return normalized or None
