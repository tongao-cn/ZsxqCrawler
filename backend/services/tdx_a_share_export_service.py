"""Export A-share rankings into existing Tongdaxin custom blocks."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from backend.services.a_share_analysis_service import (
    build_chart_payload,
    get_group_analysis_paths,
    normalize_group_id,
)
from backend.services.a_share_tdx_export_storage import (
    log_tdx_export,
    get_latest_tdx_export as get_latest_tdx_export_from_db,
)
from backend.services.tdx_stock_catalog import (
    DEFAULT_KNOW_ACTION_ENV_PATH,
    get_config_value as _get_config_value,
    load_stock_basic_records,  # noqa: F401 - compatibility re-export
    resolve_company_codes,  # noqa: F401 - compatibility re-export
    resolve_stock_catalog,
)
from backend.services.tdx_a_share_export_plan import (
    DEFAULT_TDX_EXPORT_SPECS,
    DEFAULT_TDX_EXPORT_WINDOWS,
    RANKING_BLOCK_NAMES,
    TdxBlock,
    build_block_export_result as _build_block_export_result,
    build_export_block_name as _build_export_block_name,  # noqa: F401
    build_pending_block_sync as _build_pending_block_sync,  # noqa: F401
    build_ranking_block_name as _build_ranking_block_name,  # noqa: F401
    build_tdx_export_plan,
    build_tdx_export_ranking_selection,
    collect_ranking_companies as _collect_ranking_companies,  # noqa: F401
    dedupe_keep_order as _dedupe_keep_order,
    ensure_tdx_api_blocks as _ensure_tdx_api_blocks,  # noqa: F401
    export_spec_windows,
    max_export_top_n,
    next_tdx_block_code as _next_tdx_block_code,  # noqa: F401
    normalize_export_specs as _normalize_export_specs,
    normalize_tdx_api_code as _normalize_tdx_api_code,  # noqa: F401
)


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
    max_ranking_top_n = max_export_top_n(export_specs)
    chart_payload = build_chart_payload(
        start_date=start_date,
        end_date=end_date,
        ranking_windows=export_spec_windows(export_specs),
        ranking_top_n=max_ranking_top_n,
        group_id=normalized_group_id,
    )

    rankings = chart_payload.get("rankings") or {}
    selection = build_tdx_export_ranking_selection(rankings, export_specs)

    stock_catalog = resolve_stock_catalog(selection.companies, env_path=env_path)

    resolved_root = _resolve_tdx_root(tdx_root, env_path)
    client = TdxBlockClient(tdx_root=resolved_root)
    client.initialize()
    try:
        existing_blocks = client.list_user_blocks()
        plan = build_tdx_export_plan(
            selection=selection,
            export_specs=export_specs,
            resolved_codes=stock_catalog.resolved_codes,
            existing_blocks=existing_blocks,
            group_name=group_name,
        )

        block_results: List[Dict[str, Any]] = []
        total_written = 0
        aggregate_skipped: List[str] = list(stock_catalog.unresolved_companies)

        for pending in plan.pending_writes:
            client.replace_block_stocks(
                block_name=pending.block_name,
                block_code=pending.block_code,
                ts_codes=pending.converted_codes,
            )
            verified_codes = client.get_block_stocks(pending.block_code)
            total_written += len(pending.converted_codes)
            aggregate_skipped.extend(pending.skipped_companies)
            block_results.append(
                _build_block_export_result(
                    pending.window,
                    pending.block_name,
                    pending.block_code,
                    pending.block_path,
                    pending.converted_codes,
                    pending.skipped_companies,
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
                stock_basic_source=stock_catalog.stock_basic_source,
                source_detail=stock_catalog.source_detail,
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
        stock_basic_source=stock_catalog.stock_basic_source,
        source_detail=stock_catalog.source_detail,
        backup_files=backup_files,
        block_results=block_results,
        total_written=total_written,
        aggregate_skipped=aggregate_skipped,
        ambiguous_companies=stock_catalog.ambiguous_companies,
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
