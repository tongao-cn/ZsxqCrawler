"""Export A-share rankings into existing Tongdaxin custom blocks."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import requests

from backend.services.a_share_analysis_service import (
    DEFAULT_RANKING_TOP_N,
    build_chart_payload,
    get_group_analysis_paths,
    normalize_group_id,
)
from backend.services.a_share_analysis_db_storage import (
    load_stock_basic_records as load_stock_basic_records_from_db,
    log_tdx_export,
    get_latest_tdx_export as get_latest_tdx_export_from_db,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))
DEFAULT_STOCK_BASIC_CACHE_PATH = PROJECT_ROOT / "output" / "a_share_stock_basic_cache.json"
DEFAULT_TUSHARE_API_URL = os.getenv("TUSHARE_API_URL", "http://api.tushare.pro")
DEFAULT_STOCK_CACHE_TTL = timedelta(days=7)
DEFAULT_TDX_ROOT = Path(os.getenv("TDX_ROOT", r"C:\new_tdx"))
COMMON_TDX_ROOTS = (
    Path(r"C:\new_tdx"),
    Path(r"D:\new_tdx"),
    Path(r"E:\new_tdx"),
    Path(r"C:\TdxW_HuaTai"),
    Path(r"D:\TdxW_HuaTai"),
    Path(r"C:\通达信"),
    Path(r"D:\通达信"),
)

TDX_BLOCK_DIR_REL = Path("T0002") / "blocknew"
TDX_CFG_NAME = "blocknew.cfg"
TDX_RECORD_SIZE = 120
TDX_NAME_SIZE = 50
TDX_CODE_SIZE = 64
TS_CODE_PATTERN = re.compile(r"^(?P<code>\d{6})\.(?P<market>SH|SZ)$", re.IGNORECASE)
MARKET_PREFIX_MAP = {
    "SH": "1",
    "SZ": "0",
}

RANKING_BLOCK_NAMES = {
    3: "3日推荐池",
    7: "7日推荐池",
    14: "14日推荐池",
    21: "21日推荐池",
    30: "30日推荐池",
}
DEFAULT_TDX_EXPORT_WINDOWS = (30,)
TDX_BLOCK_CODE_PATTERN = re.compile(r"^ZX(?P<number>\d+)$", re.IGNORECASE)


def _normalize_tdx_group_name(group_name: Optional[str]) -> Optional[str]:
    normalized = str(group_name or "").strip()
    return normalized or None


def _build_ranking_block_name(window: int, group_name: Optional[str] = None) -> str:
    normalized_group_name = _normalize_tdx_group_name(group_name)
    if normalized_group_name:
        return f"{normalized_group_name}-{int(window)}日"
    return RANKING_BLOCK_NAMES.get(int(window), f"{int(window)}日推荐池")


def _get_group_latest_export_path(group_id: str) -> Path:
    group_paths = get_group_analysis_paths(group_id)
    return Path(group_paths["analysis_dir"]) / "latest_tdx_export.json"


def _write_group_latest_export(group_id: str, payload: Dict[str, Any]) -> None:
    latest_export_path = _get_group_latest_export_path(group_id)
    latest_export_path.parent.mkdir(parents=True, exist_ok=True)
    latest_export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_latest_tdx_export(group_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    normalized_group_id = normalize_group_id(group_id)
    if normalized_group_id is None:
        return get_latest_tdx_export_from_db()

    latest_export_path = _get_group_latest_export_path(normalized_group_id)
    if not latest_export_path.exists():
        return None

    try:
        payload = json.loads(latest_export_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def _dedupe_keep_order(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _load_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _get_config_value(key: str, env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> str:
    direct_value = (os.getenv(key) or "").strip()
    if direct_value:
        return direct_value
    return (_load_env_file(env_path).get(key) or "").strip()


def _normalize_company_name(value: str) -> str:
    normalized = re.sub(r"[\s\u3000\-\._·・/\\()（）]+", "", str(value or "").strip())
    return normalized.replace("*", "").upper()


def _strip_st_prefix(value: str) -> str:
    stripped = str(value or "").strip()
    upper = stripped.upper().replace(" ", "")
    prefixes = ("S*ST", "*ST", "SST", "ST")
    for prefix in prefixes:
        if upper.startswith(prefix):
            return stripped[len(prefix):].strip()
    return stripped


def _normalize_tdx_code(ts_code: str) -> Optional[str]:
    match = TS_CODE_PATTERN.fullmatch(str(ts_code or "").strip())
    if match is None:
        return None
    code = match.group("code")
    market = match.group("market").upper()
    prefix = MARKET_PREFIX_MAP.get(market)
    if prefix is None:
        return None
    return f"{prefix}{code}"


def _encode_gbk_fixed(text: str, size: int) -> bytes:
    raw = str(text or "").encode("gbk", errors="ignore")
    if len(raw) > size:
        raw = raw[:size]
        while raw and len(raw) == size and (raw[-1] & 0x80):
            raw = raw[:-1]
    return raw.ljust(size, b"\x00")


def _encode_ascii_fixed(text: str, size: int) -> bytes:
    raw = str(text or "").encode("ascii", errors="ignore")
    return raw[:size].ljust(size, b"\x00")


def read_tdx_cfg(cfg_path: Path) -> List[Dict[str, str]]:
    if not cfg_path.exists():
        return []

    data = cfg_path.read_bytes()
    if len(data) % TDX_RECORD_SIZE != 0:
        raise ValueError(f"{cfg_path} 不是 {TDX_RECORD_SIZE} 字节的整数倍")

    records: List[Dict[str, str]] = []
    for offset in range(0, len(data), TDX_RECORD_SIZE):
        chunk = data[offset : offset + TDX_RECORD_SIZE]
        name = chunk[:TDX_NAME_SIZE].split(b"\x00", 1)[0].decode("gbk", errors="ignore").strip()
        code = chunk[
            TDX_NAME_SIZE : TDX_NAME_SIZE + TDX_CODE_SIZE
        ].split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        if not name and not code:
            continue
        records.append({"name": name, "code": code})
    return records


def write_tdx_cfg(cfg_path: Path, records: List[Dict[str, str]]) -> None:
    payload = bytearray()
    for record in records:
        payload.extend(_encode_gbk_fixed(record["name"], TDX_NAME_SIZE))
        payload.extend(_encode_ascii_fixed(record["code"], TDX_CODE_SIZE))
        payload.extend(b"\x00" * (TDX_RECORD_SIZE - TDX_NAME_SIZE - TDX_CODE_SIZE))
    cfg_path.write_bytes(bytes(payload))


def _next_tdx_block_code(records: Sequence[Mapping[str, str]]) -> str:
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


def _ensure_tdx_cfg_records(
    records: List[Dict[str, str]],
    block_names: Sequence[str],
) -> Tuple[Dict[str, Dict[str, str]], List[Dict[str, str]]]:
    cfg_by_name = {
        str(record.get("name") or "").strip(): record
        for record in records
        if str(record.get("name") or "").strip()
    }
    created_records: List[Dict[str, str]] = []

    for block_name in block_names:
        if block_name in cfg_by_name:
            continue
        record = {
            "name": block_name,
            "code": _next_tdx_block_code(records),
        }
        records.append(record)
        cfg_by_name[block_name] = record
        created_records.append(record)

    return cfg_by_name, created_records


def _write_blk(path: Path, codes: List[str]) -> None:
    text = "\n".join(codes)
    if text:
        text += "\n"
    path.write_text(text, encoding="ascii", newline="")


def _backup_targets(backup_dir: Path, targets: List[Path]) -> List[str]:
    existing_targets = [target for target in targets if target.exists()]
    if not existing_targets:
        return []

    backup_dir.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    for target in existing_targets:
        destination = backup_dir / target.name
        shutil.copy2(target, destination)
        copied.append(str(destination))
    return copied


def _read_stock_basic_cache(cache_path: Path = DEFAULT_STOCK_BASIC_CACHE_PATH) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    records = payload.get("records")
    if not isinstance(records, list):
        return None
    return payload


def _write_stock_basic_cache(records: List[Dict[str, str]], cache_path: Path = DEFAULT_STOCK_BASIC_CACHE_PATH) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": datetime.now().isoformat(),
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _is_stock_basic_cache_fresh(
    payload: Optional[Dict[str, Any]],
    cache_ttl: timedelta = DEFAULT_STOCK_CACHE_TTL,
) -> bool:
    if not payload:
        return False

    updated_at = str(payload.get("updated_at") or "").strip()
    if not updated_at:
        return False

    try:
        updated_dt = datetime.fromisoformat(updated_at)
    except Exception:
        return False

    return datetime.now() - updated_dt <= cache_ttl


def _fetch_stock_basic_from_tushare(
    token: str,
    api_url: str = DEFAULT_TUSHARE_API_URL,
) -> List[Dict[str, str]]:
    response = requests.post(
        api_url,
        json={
            "api_name": "stock_basic",
            "token": token,
            "params": {
                "exchange": "",
                "list_status": "L",
            },
            "fields": "ts_code,symbol,name",
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()

    if payload.get("code") not in (0, "0", None):
        raise RuntimeError(payload.get("msg") or "Tushare stock_basic 接口调用失败")

    data = payload.get("data") or {}
    fields = data.get("fields") or []
    items = data.get("items") or []
    if not fields:
        raise RuntimeError("Tushare stock_basic 未返回字段定义")

    records: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, list):
            continue
        record = dict(zip(fields, item))
        ts_code = str(record.get("ts_code") or "").strip()
        name = str(record.get("name") or "").strip()
        if not ts_code or not name:
            continue
        records.append(
            {
                "ts_code": ts_code,
                "symbol": str(record.get("symbol") or "").strip(),
                "name": name,
            }
        )

    if not records:
        raise RuntimeError("Tushare stock_basic 返回为空")

    return records


def load_stock_basic_records(
    cache_path: Path = DEFAULT_STOCK_BASIC_CACHE_PATH,
    cache_ttl: timedelta = DEFAULT_STOCK_CACHE_TTL,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> Tuple[List[Dict[str, str]], str, str]:
    try:
        records = load_stock_basic_records_from_db(env_path)
        if records:
            return records, "knowaction_db", "stock_basic"
    except Exception:
        pass

    cache_payload = _read_stock_basic_cache(cache_path)
    if _is_stock_basic_cache_fresh(cache_payload, cache_ttl):
        return list(cache_payload.get("records") or []), "cache", str(cache_path)

    token = _get_config_value("TUSHARE_TOKEN", env_path)
    if not token:
        if cache_payload and cache_payload.get("records"):
            return list(cache_payload.get("records") or []), "cache", str(cache_path)
        raise RuntimeError(
            "未找到 TUSHARE_TOKEN，请先设置环境变量，或在 C:\\Dev\\KnowActionSystem\\.env 中配置。"
        )

    records = _fetch_stock_basic_from_tushare(token)
    _write_stock_basic_cache(records, cache_path)
    return records, "tushare_cache", str(cache_path)


def _build_company_name_index(records: List[Dict[str, str]]) -> Dict[str, Set[str]]:
    index: Dict[str, Set[str]] = {}

    for record in records:
        ts_code = str(record.get("ts_code") or "").strip().upper()
        name = str(record.get("name") or "").strip()
        if not ts_code or not name:
            continue

        aliases = {
            _normalize_company_name(name),
            _normalize_company_name(_strip_st_prefix(name)),
        }

        for alias in aliases:
            if not alias:
                continue
            index.setdefault(alias, set()).add(ts_code)

    return index


def resolve_company_codes(
    company_names: Iterable[str],
    records: List[Dict[str, str]],
) -> Tuple[Dict[str, str], List[str], Dict[str, List[str]]]:
    name_index = _build_company_name_index(records)

    resolved: Dict[str, str] = {}
    unresolved: List[str] = []
    ambiguous: Dict[str, List[str]] = {}

    for company in _dedupe_keep_order(company_names):
        normalized = _normalize_company_name(company)
        matched_codes = sorted(name_index.get(normalized) or [])
        if len(matched_codes) == 1:
            resolved[company] = matched_codes[0]
            continue
        if len(matched_codes) > 1:
            ambiguous[company] = matched_codes
            continue
        unresolved.append(company)

    return resolved, unresolved, ambiguous


def _collect_ranking_companies(rankings: Mapping[str, Any], ranking_windows: Sequence[int]) -> List[str]:
    all_companies: List[str] = []
    for window in ranking_windows:
        window_rows = rankings.get(str(window)) or []
        all_companies.extend(
            str(item.get("company") or "").strip()
            for item in window_rows
            if str(item.get("company") or "").strip()
        )
    return all_companies


def _build_pending_block_write(
    window: int,
    rankings: Mapping[str, Any],
    resolved_codes: Mapping[str, str],
    cfg_by_name: Mapping[str, Mapping[str, str]],
    block_dir: Path,
    group_name: Optional[str] = None,
) -> Tuple[int, str, str, Path, List[str], List[str]]:
    block_name = _build_ranking_block_name(window, group_name)
    cfg_record = cfg_by_name[block_name]
    block_code = str(cfg_record.get("code") or "").strip()
    if not block_code:
        raise RuntimeError(f"板块 {block_name} 在 blocknew.cfg 中没有有效代码")

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

        tdx_code = _normalize_tdx_code(ts_code)
        if not tdx_code:
            skipped_companies.append(company)
            continue
        converted_codes.append(tdx_code)

    return (
        int(window),
        block_name,
        block_code,
        block_dir / f"{block_code}.blk",
        _dedupe_keep_order(converted_codes),
        _dedupe_keep_order(skipped_companies),
    )


def _build_block_export_result(
    window: int,
    block_name: str,
    block_code: str,
    blk_path: Path,
    converted_codes: Sequence[str],
    skipped_companies: Sequence[str],
) -> Dict[str, Any]:
    return {
        "window_days": window,
        "block_name": block_name,
        "block_code": block_code,
        "block_path": str(blk_path),
        "written_count": len(converted_codes),
        "skipped_count": len(skipped_companies),
        "skipped_companies": list(skipped_companies),
    }


def _build_export_result(
    *,
    normalized_group_id: Optional[str],
    resolved_root: Path,
    chart_payload: Mapping[str, Any],
    ranking_top_n: int,
    stock_basic_source: str,
    source_detail: str,
    backup_files: List[str],
    block_results: List[Dict[str, Any]],
    total_written: int,
    aggregate_skipped: List[str],
    ambiguous_companies: Dict[str, List[str]],
    effective_export_id: Optional[int],
) -> Dict[str, Any]:
    return {
        "group_id": normalized_group_id,
        "exported_at": datetime.now().isoformat(),
        "tdx_root": str(resolved_root),
        "selected_start_date": chart_payload.get("selected_start_date"),
        "selected_end_date": chart_payload.get("selected_end_date"),
        "ranking_top_n": ranking_top_n,
        "used_stock_cache": stock_basic_source == "cache",
        "stock_basic_source": stock_basic_source,
        "stock_cache_path": source_detail,
        "backup_files": backup_files,
        "blocks": block_results,
        "total_written": total_written,
        "unresolved_companies": _dedupe_keep_order(aggregate_skipped),
        "ambiguous_companies": ambiguous_companies,
        "export_id": effective_export_id,
    }


def _resolve_tdx_root(
    explicit_root: Optional[str] = None,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> Path:
    raw_candidates: List[Path] = []

    if explicit_root:
        raw_candidates.append(Path(explicit_root))

    configured_root = _get_config_value("TDX_ROOT", env_path)
    if configured_root:
        raw_candidates.append(Path(configured_root))

    raw_candidates.append(DEFAULT_TDX_ROOT)
    raw_candidates.extend(COMMON_TDX_ROOTS)

    seen: Set[str] = set()
    candidates: List[Path] = []
    for candidate in raw_candidates:
        normalized = str(candidate).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(Path(normalized))

    for candidate in candidates:
        block_dir = candidate / TDX_BLOCK_DIR_REL
        cfg_path = block_dir / TDX_CFG_NAME
        if cfg_path.exists() or block_dir.exists():
            return candidate.resolve()

    return candidates[0].resolve()


def export_a_share_rankings_to_tdx(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    *,
    group_id: Optional[str] = None,
    group_name: Optional[str] = None,
    tdx_root: Optional[str] = None,
    ranking_windows: Sequence[int] = DEFAULT_TDX_EXPORT_WINDOWS,
    ranking_top_n: int = DEFAULT_RANKING_TOP_N,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> Dict[str, Any]:
    normalized_group_id = normalize_group_id(group_id)
    chart_payload = build_chart_payload(
        start_date=start_date,
        end_date=end_date,
        ranking_windows=ranking_windows,
        ranking_top_n=ranking_top_n,
        group_id=normalized_group_id,
    )

    rankings = chart_payload.get("rankings") or {}
    all_companies = _collect_ranking_companies(rankings, ranking_windows)

    stock_records, stock_basic_source, source_detail = load_stock_basic_records(env_path=env_path)
    resolved_codes, unresolved_companies, ambiguous_companies = resolve_company_codes(all_companies, stock_records)

    resolved_root = _resolve_tdx_root(tdx_root, env_path)
    block_dir = resolved_root / TDX_BLOCK_DIR_REL
    cfg_path = block_dir / TDX_CFG_NAME
    if not cfg_path.exists():
        raise RuntimeError(f"未找到通达信板块配置文件: {cfg_path}")

    expected_block_names = [
        _build_ranking_block_name(int(window), group_name)
        for window in ranking_windows
    ]
    cfg_records = read_tdx_cfg(cfg_path)
    cfg_by_name, created_cfg_records = _ensure_tdx_cfg_records(cfg_records, expected_block_names)

    pending_writes = [
        _build_pending_block_write(int(window), rankings, resolved_codes, cfg_by_name, block_dir, group_name)
        for window in ranking_windows
    ]

    backup_dir = block_dir / f"backup_a_share_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_files = _backup_targets(
        backup_dir,
        ([cfg_path] if created_cfg_records else [])
        + [blk_path for _, _, _, blk_path, _, _ in pending_writes],
    )

    block_results: List[Dict[str, Any]] = []
    total_written = 0
    aggregate_skipped: List[str] = list(unresolved_companies)

    if created_cfg_records:
        write_tdx_cfg(cfg_path, cfg_records)

    for window, block_name, block_code, blk_path, converted_codes, skipped_companies in pending_writes:
        _write_blk(blk_path, converted_codes)
        total_written += len(converted_codes)
        aggregate_skipped.extend(skipped_companies)
        block_results.append(
            _build_block_export_result(
                window,
                block_name,
                block_code,
                blk_path,
                converted_codes,
                skipped_companies,
            )
        )

    export_id: Optional[int] = None
    if normalized_group_id is None:
        try:
            export_id = log_tdx_export(
                start_date=chart_payload.get("selected_start_date"),
                end_date=chart_payload.get("selected_end_date"),
                tdx_root=str(resolved_root),
                ranking_top_n=ranking_top_n,
                total_written=total_written,
                unresolved_companies=_dedupe_keep_order(aggregate_skipped),
                backup_files=backup_files,
                stock_basic_source=stock_basic_source,
                source_detail=source_detail,
                blocks=block_results,
            )
        except Exception:
            export_id = None

    effective_export_id = export_id
    if normalized_group_id is not None and effective_export_id is None:
        effective_export_id = int(datetime.now().timestamp())

    result = _build_export_result(
        normalized_group_id=normalized_group_id,
        resolved_root=resolved_root,
        chart_payload=chart_payload,
        ranking_top_n=ranking_top_n,
        stock_basic_source=stock_basic_source,
        source_detail=source_detail,
        backup_files=backup_files,
        block_results=block_results,
        total_written=total_written,
        aggregate_skipped=aggregate_skipped,
        ambiguous_companies=ambiguous_companies,
        effective_export_id=effective_export_id,
    )

    if normalized_group_id is not None:
        _write_group_latest_export(normalized_group_id, result)

    return result


__all__ = [
    "DEFAULT_TDX_ROOT",
    "RANKING_BLOCK_NAMES",
    "DEFAULT_TDX_EXPORT_WINDOWS",
    "TDX_BLOCK_DIR_REL",
    "TDX_CFG_NAME",
    "export_a_share_rankings_to_tdx",
    "get_latest_tdx_export",
    "read_tdx_cfg",
    "write_tdx_cfg",
]
