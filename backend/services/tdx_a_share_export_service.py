"""Export A-share rankings into existing Tongdaxin custom blocks."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import requests

from backend.services.a_share_analysis_service import (
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

TDXQUANT_RELATIVE_PATH = Path("PYPlugins") / "user"
TS_CODE_PATTERN = re.compile(r"^(?P<code>\d{6})\.(?P<market>SH|SZ|BJ)$", re.IGNORECASE)

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


@dataclass(frozen=True)
class TdxBlock:
    code: str
    name: str


class TdxBlockApiError(RuntimeError):
    """Raised when the official TdxQuant block API cannot satisfy a request."""


class TdxBlockClient:
    """Thin official TdxQuant adapter for custom block operations."""

    def __init__(
        self,
        *,
        tdx_root: str | Path | None = None,
        tdxquant_path: str | Path | None = None,
        tq: Any | None = None,
        initialize_path: str | Path | None = None,
    ) -> None:
        self.tdx_root = Path(tdx_root) if tdx_root is not None else DEFAULT_TDX_ROOT
        self.tdxquant_path = (
            Path(tdxquant_path)
            if tdxquant_path is not None
            else self.tdx_root / TDXQUANT_RELATIVE_PATH
        )
        self._tq = tq
        self._initialize_path = Path(initialize_path) if initialize_path is not None else Path(__file__)

    @property
    def tq(self) -> Any:
        if self._tq is None:
            self._tq = self._load_tq()
        return self._tq

    def _load_tq(self) -> Any:
        tqcenter_path = self.tdxquant_path / "tqcenter.py"
        client_dll_path = self.tdx_root / "PYPlugins" / "TPythClient.dll"
        if not tqcenter_path.exists():
            raise TdxBlockApiError(f"tqcenter.py not found: {tqcenter_path}")
        if not client_dll_path.exists():
            raise TdxBlockApiError(f"TPythClient.dll not found: {client_dll_path}")
        if str(self.tdxquant_path) not in sys.path:
            sys.path.insert(0, str(self.tdxquant_path))
        try:
            from tqcenter import tq  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on local TDX install
            raise TdxBlockApiError(f"failed to import tqcenter: {exc}") from exc
        return tq

    def initialize(self) -> None:
        self.tq.initialize(str(self._initialize_path))

    def close(self) -> None:
        close = getattr(self.tq, "close", None)
        if callable(close):
            close()

    def list_user_blocks(self) -> List[TdxBlock]:
        payload = self.tq.get_user_sector()
        if not isinstance(payload, list):
            raise TdxBlockApiError("TdxQuant get_user_sector response is not a list")
        blocks: List[TdxBlock] = []
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            code = str(item.get("Code") or item.get("code") or "").strip().upper()
            name = str(item.get("Name") or item.get("name") or "").strip()
            if code and name:
                blocks.append(TdxBlock(code=code, name=name))
        return blocks

    def get_block_stocks(self, block_code: str) -> List[Any]:
        payload = self.tq.get_stock_list_in_sector(
            str(block_code).strip().upper(),
            block_type=1,
            list_type=0,
        )
        if not isinstance(payload, list):
            raise TdxBlockApiError("TdxQuant get_stock_list_in_sector response is not a list")
        return payload

    def ensure_block(self, *, block_code: str, block_name: str) -> Dict[str, Any] | None:
        normalized_code = str(block_code or "").strip().upper()
        normalized_name = str(block_name or "").strip()
        if not normalized_code:
            raise ValueError("block_code is required")
        if not normalized_name:
            raise ValueError("block_name is required")

        existing = {block.code: block for block in self.list_user_blocks()}
        current = existing.get(normalized_code)
        if current is None:
            return _require_tdx_api_success(
                self.tq.create_sector(block_code=normalized_code, block_name=normalized_name),
                "create_sector",
            )
        if current.name != normalized_name:
            return _require_tdx_api_success(
                self.tq.rename_sector(block_code=normalized_code, block_name=normalized_name),
                "rename_sector",
            )
        return None

    def replace_block_stocks(
        self,
        *,
        block_code: str,
        block_name: str,
        ts_codes: Iterable[str],
    ) -> Dict[str, Any]:
        normalized_code = str(block_code or "").strip().upper()
        self.ensure_block(block_code=normalized_code, block_name=block_name)
        clear_result = _require_tdx_api_success(
            self.tq.clear_sector(block_code=normalized_code),
            "clear_sector",
        )
        codes = _dedupe_keep_order(ts_codes)
        if not codes:
            return {"clear_result": clear_result, "send_result": None}
        send_result = _require_tdx_api_success(
            self.tq.send_user_block(block_code=normalized_code, stocks=codes, show=False),
            "send_user_block",
        )
        return {"clear_result": clear_result, "send_result": send_result}


def _normalize_tdx_group_name(group_name: Optional[str]) -> Optional[str]:
    normalized = str(group_name or "").strip()
    return normalized or None


def _build_ranking_block_name(window: int, group_name: Optional[str] = None) -> str:
    normalized_group_name = _normalize_tdx_group_name(group_name)
    if normalized_group_name:
        return f"{normalized_group_name}-{int(window)}日"
    return RANKING_BLOCK_NAMES.get(int(window), f"{int(window)}日推荐池")


def _build_export_block_name(window: int, top_n: int, group_name: Optional[str] = None) -> str:
    normalized_group_name = _normalize_tdx_group_name(group_name)
    prefix = normalized_group_name or RANKING_BLOCK_NAMES.get(int(window), f"{int(window)}日推荐池")
    return f"{prefix}-{int(window)}日Top{int(top_n)}" if normalized_group_name else f"{int(window)}日Top{int(top_n)}"


def _normalize_export_specs(
    ranking_windows: Sequence[int],
    ranking_top_n: Optional[int],
) -> Tuple[Tuple[int, int], ...]:
    if ranking_top_n is None:
        return tuple((int(window), top_n) for window, top_n in DEFAULT_TDX_EXPORT_SPECS if int(window) in {int(item) for item in ranking_windows})
    return tuple((int(window), int(ranking_top_n)) for window in ranking_windows)


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


def _parse_tdx_api_result(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str) and payload.strip():
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise TdxBlockApiError(f"TdxQuant block API returned invalid JSON: {payload}") from exc
        if isinstance(parsed, dict):
            return parsed
    if payload in (None, ""):
        return {}
    raise TdxBlockApiError(f"TdxQuant block API returned unsupported payload: {payload!r}")


def _require_tdx_api_success(payload: Any, action: str) -> Dict[str, Any]:
    parsed = _parse_tdx_api_result(payload)
    error_id = str(parsed.get("ErrorId", "0"))
    if error_id != "0":
        message = parsed.get("Error") or parsed.get("Msg") or error_id
        raise TdxBlockApiError(f"TdxQuant {action} failed: {message}")
    return parsed


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


def _strip_a_share_name_markers(value: str) -> str:
    stripped = str(value or "").strip()
    upper = stripped.upper().replace(" ", "")
    for prefix in ("XD", "XR", "DR"):
        if upper.startswith(prefix):
            stripped = stripped[len(prefix):].strip()
            break
    return re.sub(r"(?:[-\s]*(?:U|W|V|B))+$", "", stripped, flags=re.IGNORECASE).strip()


def _build_company_name_aliases(name: str) -> Set[str]:
    candidates = {
        name,
        _strip_st_prefix(name),
        _strip_a_share_name_markers(name),
        _strip_a_share_name_markers(_strip_st_prefix(name)),
    }
    return {alias for candidate in candidates if (alias := _normalize_company_name(candidate))}


def _normalize_tdx_api_code(ts_code: str) -> Optional[str]:
    match = TS_CODE_PATTERN.fullmatch(str(ts_code or "").strip())
    if match is None:
        return None
    return f"{match.group('code')}.{match.group('market').upper()}"


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


def _ensure_tdx_api_blocks(
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
            "code": _next_tdx_block_code(records),
        }
        records.append(record)
        cfg_by_name[block_name] = record
        created_records.append(record)

    return cfg_by_name, created_records


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

        for alias in _build_company_name_aliases(name):
            index.setdefault(alias, set()).add(ts_code)

    return index


def _find_prefix_matched_codes(normalized: str, name_index: Mapping[str, Set[str]]) -> List[str]:
    if len(normalized) < 4:
        return []

    matched_codes: Set[str] = set()
    for alias, codes in name_index.items():
        common_length = min(len(normalized), len(alias))
        if common_length < 3:
            continue
        if normalized[:common_length] == alias[:common_length]:
            matched_codes.update(codes)
    return sorted(matched_codes)


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
        if not matched_codes:
            matched_codes = _find_prefix_matched_codes(normalized, name_index)
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


def _build_pending_block_sync(
    window: int,
    top_n: int,
    rankings: Mapping[str, Any],
    resolved_codes: Mapping[str, str],
    cfg_by_name: Mapping[str, Mapping[str, str]],
    group_name: Optional[str] = None,
) -> Tuple[int, str, str, str, List[str], List[str]]:
    block_name = _build_export_block_name(window, top_n, group_name)
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

        tdx_api_code = _normalize_tdx_api_code(ts_code)
        if not tdx_api_code:
            skipped_companies.append(company)
            continue
        converted_codes.append(tdx_api_code)

    return (
        int(window),
        block_name,
        block_code,
        f"tdx-api://{block_code}",
        _dedupe_keep_order(converted_codes),
        _dedupe_keep_order(skipped_companies),
    )


def _build_block_export_result(
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
        tdxquant_path = candidate / TDXQUANT_RELATIVE_PATH / "tqcenter.py"
        client_dll_path = candidate / "PYPlugins" / "TPythClient.dll"
        if tdxquant_path.exists() or client_dll_path.exists():
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
    ranking_top_n: Optional[int] = None,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> Dict[str, Any]:
    normalized_group_id = normalize_group_id(group_id)
    export_specs = _normalize_export_specs(ranking_windows, ranking_top_n)
    max_ranking_top_n = max((top_n for _window, top_n in export_specs), default=0)
    chart_payload = build_chart_payload(
        start_date=start_date,
        end_date=end_date,
        ranking_windows=tuple(window for window, _top_n in export_specs),
        ranking_top_n=max_ranking_top_n,
        group_id=normalized_group_id,
    )

    rankings = chart_payload.get("rankings") or {}
    sliced_rankings = {
        str(window): list(rankings.get(str(window)) or [])[:top_n]
        for window, top_n in export_specs
    }
    all_companies = _collect_ranking_companies(sliced_rankings, [window for window, _top_n in export_specs])

    stock_records, stock_basic_source, source_detail = load_stock_basic_records(env_path=env_path)
    resolved_codes, unresolved_companies, ambiguous_companies = resolve_company_codes(all_companies, stock_records)

    resolved_root = _resolve_tdx_root(tdx_root, env_path)
    expected_block_names = [
        _build_export_block_name(window, top_n, group_name)
        for window, top_n in export_specs
    ]
    client = TdxBlockClient(tdx_root=resolved_root)
    client.initialize()
    try:
        existing_blocks = client.list_user_blocks()
        cfg_by_name, _created_cfg_records = _ensure_tdx_api_blocks(existing_blocks, expected_block_names)
        pending_writes = [
            _build_pending_block_sync(window, top_n, sliced_rankings, resolved_codes, cfg_by_name, group_name)
            for window, top_n in export_specs
        ]

        block_results: List[Dict[str, Any]] = []
        total_written = 0
        aggregate_skipped: List[str] = list(unresolved_companies)

        for window, block_name, block_code, block_path, converted_codes, skipped_companies in pending_writes:
            client.replace_block_stocks(
                block_name=block_name,
                block_code=block_code,
                ts_codes=converted_codes,
            )
            verified_codes = client.get_block_stocks(block_code)
            total_written += len(converted_codes)
            aggregate_skipped.extend(skipped_companies)
            block_results.append(
                _build_block_export_result(
                    window,
                    block_name,
                    block_code,
                    block_path,
                    converted_codes,
                    skipped_companies,
                    verified_count=len(verified_codes),
                )
            )
    finally:
        client.close()

    backup_files: List[str] = []

    export_id: Optional[int] = None
    if normalized_group_id is None:
        try:
            export_id = log_tdx_export(
                start_date=chart_payload.get("selected_start_date"),
                end_date=chart_payload.get("selected_end_date"),
                tdx_root=str(resolved_root),
                ranking_top_n=max_ranking_top_n,
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
        ranking_top_n=max_ranking_top_n,
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
    "DEFAULT_TDX_EXPORT_SPECS",
    "DEFAULT_TDX_EXPORT_WINDOWS",
    "export_a_share_rankings_to_tdx",
    "get_latest_tdx_export",
]
