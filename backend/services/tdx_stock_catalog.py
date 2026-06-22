"""Stock catalog loading and code resolution for TDX exports."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, NamedTuple, Optional, Set, Tuple

import requests

from backend.services.a_share_analysis_db_storage import (
    load_stock_basic_records as load_stock_basic_records_from_db,
)
from backend.services.tdx_a_share_export_plan import dedupe_keep_order


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))
DEFAULT_STOCK_BASIC_CACHE_PATH = PROJECT_ROOT / "output" / "a_share_stock_basic_cache.json"
DEFAULT_TUSHARE_API_URL = os.getenv("TUSHARE_API_URL", "http://api.tushare.pro")
DEFAULT_STOCK_CACHE_TTL = timedelta(days=7)

COMPANY_NAME_ALIASES = {
    "斯菱智驱": ("斯菱股份",),
}


class StockCatalogResolution(NamedTuple):
    records: List[Dict[str, str]]
    stock_basic_source: str
    source_detail: str
    resolved_codes: Dict[str, str]
    unresolved_companies: List[str]
    ambiguous_companies: Dict[str, List[str]]


def load_env_file(path: Path) -> Dict[str, str]:
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


def get_config_value(key: str, env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> str:
    direct_value = (os.getenv(key) or "").strip()
    if direct_value:
        return direct_value
    return (load_env_file(env_path).get(key) or "").strip()


def normalize_company_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "").strip())
    normalized = re.sub(r"[\s\u3000\-\._·・/\\()（）]+", "", normalized)
    return normalized.replace("*", "").upper()


def strip_st_prefix(value: str) -> str:
    stripped = str(value or "").strip()
    upper = stripped.upper().replace(" ", "")
    prefixes = ("S*ST", "*ST", "SST", "ST")
    for prefix in prefixes:
        if upper.startswith(prefix):
            return stripped[len(prefix):].strip()
    return stripped


def strip_a_share_name_markers(value: str) -> str:
    stripped = str(value or "").strip()
    upper = stripped.upper().replace(" ", "")
    for prefix in ("XD", "XR", "DR"):
        if upper.startswith(prefix):
            stripped = stripped[len(prefix):].strip()
            break
    return re.sub(r"(?:[-\s]*(?:U|W|V|B))+$", "", stripped, flags=re.IGNORECASE).strip()


def build_company_name_aliases(name: str) -> Set[str]:
    candidates = {
        name,
        strip_st_prefix(name),
        strip_a_share_name_markers(name),
        strip_a_share_name_markers(strip_st_prefix(name)),
    }
    candidates.update(COMPANY_NAME_ALIASES.get(str(name or "").strip(), ()))
    return {alias for candidate in candidates if (alias := normalize_company_name(candidate))}


def read_stock_basic_cache(cache_path: Path = DEFAULT_STOCK_BASIC_CACHE_PATH) -> Optional[Dict[str, Any]]:
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


def write_stock_basic_cache(records: List[Dict[str, str]], cache_path: Path = DEFAULT_STOCK_BASIC_CACHE_PATH) -> None:
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


def is_stock_basic_cache_fresh(
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


def fetch_stock_basic_from_tushare(
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

    cache_payload = read_stock_basic_cache(cache_path)
    if is_stock_basic_cache_fresh(cache_payload, cache_ttl):
        return list(cache_payload.get("records") or []), "cache", str(cache_path)

    token = get_config_value("TUSHARE_TOKEN", env_path)
    if not token:
        if cache_payload and cache_payload.get("records"):
            return list(cache_payload.get("records") or []), "cache", str(cache_path)
        raise RuntimeError(
            "未找到 TUSHARE_TOKEN，请先设置环境变量，或在 C:\\Dev\\KnowActionSystem\\.env 中配置。"
        )

    records = fetch_stock_basic_from_tushare(token)
    write_stock_basic_cache(records, cache_path)
    return records, "tushare_cache", str(cache_path)


def build_company_name_index(records: List[Dict[str, str]]) -> Dict[str, Set[str]]:
    index: Dict[str, Set[str]] = {}

    for record in records:
        ts_code = str(record.get("ts_code") or "").strip().upper()
        name = str(record.get("name") or "").strip()
        if not ts_code or not name:
            continue

        for alias in build_company_name_aliases(name):
            index.setdefault(alias, set()).add(ts_code)

    return index


def find_prefix_matched_codes(normalized: str, name_index: Mapping[str, Set[str]]) -> List[str]:
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
    name_index = build_company_name_index(records)

    resolved: Dict[str, str] = {}
    unresolved: List[str] = []
    ambiguous: Dict[str, List[str]] = {}

    for company in dedupe_keep_order(company_names):
        normalized = normalize_company_name(company)
        matched_codes = sorted(name_index.get(normalized) or [])
        if not matched_codes:
            matched_codes = find_prefix_matched_codes(normalized, name_index)
        if len(matched_codes) == 1:
            resolved[company] = matched_codes[0]
            continue
        if len(matched_codes) > 1:
            ambiguous[company] = matched_codes
            continue
        unresolved.append(company)

    return resolved, unresolved, ambiguous


def resolve_stock_catalog(
    company_names: Iterable[str],
    *,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
    cache_path: Path = DEFAULT_STOCK_BASIC_CACHE_PATH,
    cache_ttl: timedelta = DEFAULT_STOCK_CACHE_TTL,
) -> StockCatalogResolution:
    records, stock_basic_source, source_detail = load_stock_basic_records(
        cache_path=cache_path,
        cache_ttl=cache_ttl,
        env_path=env_path,
    )
    resolved_codes, unresolved_companies, ambiguous_companies = resolve_company_codes(
        company_names,
        records,
    )
    return StockCatalogResolution(
        records=records,
        stock_basic_source=stock_basic_source,
        source_detail=source_detail,
        resolved_codes=resolved_codes,
        unresolved_companies=unresolved_companies,
        ambiguous_companies=ambiguous_companies,
    )
