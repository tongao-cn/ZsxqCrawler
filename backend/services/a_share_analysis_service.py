#!/usr/bin/env python3
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from backend.core.ai_provider_config import (
    get_default_model,
    get_openai_compatible_config,
)
from backend.services.a_share_analysis_db_storage import (
    DAILY_MENTIONS_TABLE,
    PROCESSED_STATE_TABLE,
    get_storage_health,
    load_daily_mentions as load_daily_mentions_from_db,
    load_processed_state as load_processed_state_from_db,
    reset_a_share_analysis_range as reset_a_share_analysis_range_to_db,
    save_recommendation_pool_checkpoint,
    save_topic_stock_extractions,
    save_daily_mentions as save_daily_mentions_to_db,
    save_processed_state as save_processed_state_to_db,
)
from backend.services.a_share_analysis_checkpoint import AShareAnalysisCheckpointManager
from backend.services.a_share_analysis_dates import (
    get_date_range_bounds,
    get_last_days_range,
    normalize_date_range as _normalize_date_range,
    select_available_date_range as _select_available_date_range,
    validate_day,  # noqa: F401 - compatibility re-export for scripts
)
from backend.services.a_share_analysis_reset import (
    apply_analysis_reset_range,
    extract_day_from_state_key as _extract_day_from_state_key_impl,
    remove_daily_range as _remove_daily_range_impl,
    remove_state_range as _remove_state_range_impl,
)
from backend.services.a_share_analysis_chart import (
    DEFAULT_RANKING_TOP_N,
    DEFAULT_RANKING_WINDOWS,
)
from backend.services.a_share_analysis_run_plan import (
    build_analysis_run_plan,
    discover_analysis_groups,
    load_analysis_run_items,
)
from backend.services.a_share_analysis_chart_payload import (
    build_chart_payload_from_daily,
    empty_chart_payload as _empty_chart_payload,
)
from backend.services.a_share_analysis_ai import (
    DEFAULT_API_BASE,
    DEFAULT_OPENAI_MAX_RETRIES,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_WIRE_API,
    TOPIC_STOCK_EXTRACTION_PROMPT_VERSION,
    _build_topic_stock_extraction_prompt,  # noqa: F401 - compatibility re-export for tests/tools
    _extract_response_text,  # noqa: F401 - compatibility re-export for tests/tools
    _parse_company_extraction_output,  # noqa: F401 - compatibility re-export for tests/tools
    _parse_topic_stock_extraction_output,  # noqa: F401 - compatibility re-export for tests/tools
    call_openai_extract_companies as _call_openai_extract_companies,
    call_openai_extract_topic_stocks as _call_openai_extract_topic_stocks,
)
from backend.services.a_share_analysis_aggregation import (
    TopicStockExtractionAdapter,
    aggregate_daily as _aggregate_daily,
    format_company_log as _format_company_log_impl,
    format_stock_concepts_log as _format_stock_concepts_log_impl,
    looks_like_attachment_only_topic as _looks_like_attachment_only_topic_impl,
    make_item_key as _make_item_key,
    should_skip_topic_stock_ai_extraction as _should_skip_topic_stock_ai_extraction_impl,
)
from backend.services.a_share_analysis_local_store import (
    DEFAULT_OUTPUT_PATH,
    DEFAULT_STATE_PATH,
    GROUP_ANALYSIS_DIRNAME,  # noqa: F401 - compatibility re-export for local-storage tools
    GROUP_OUTPUT_FILENAME,  # noqa: F401 - compatibility re-export for local-storage tools
    GROUP_STATE_FILENAME,  # noqa: F401 - compatibility re-export for local-storage tools
    get_group_analysis_paths as _get_group_analysis_paths,
    load_state_file as _load_state_file_impl,
    normalize_group_id,
    read_existing_csv_file as _read_existing_csv_file_impl,
    resolve_analysis_paths as _resolve_analysis_paths,
    save_state_file as _save_state_file_impl,
    write_csv_file as _write_csv_file_impl,
)
from backend.services.a_share_analysis_topics import (
    normalize_day as _normalize_day,
    parse_time as _parse_time,
    read_topics_in_time_range as _read_topics_in_time_range,
)
from backend.services.a_share_analysis_source_store import load_source_topics_summary
from backend.services.a_share_recommendation_pool_storage import (
    AShareRecommendationPoolStorage,
    AShareRecommendationPoolStorageAdapters,
)

try:
    from backend.core.logger_config import (
        ensure_configured,
        log_debug,
        log_error,
        log_exception,
        log_info,
        log_warning,
    )
except Exception:
    def ensure_configured():
        pass

    def log_info(message: str, **kwargs):
        print(f"[INFO] {message}")

    def log_warning(message: str, **kwargs):
        print(f"[WARN] {message}")

    def log_error(message: str, **kwargs):
        print(f"[ERROR] {message}")

    def log_exception(message: str, **kwargs):
        print(f"[EXCEPTION] {message}")

    def log_debug(message: str, **kwargs):
        print(f"[DEBUG] {message}")


DEFAULT_MODEL = get_default_model()
DEFAULT_CONCURRENCY = 10
DEFAULT_CHECKPOINT_BATCH_SIZE = 20

LogCallback = Optional[Callable[[str], None]]
AggregateSuccessCallback = Optional[Callable[[str, str, List[Dict[str, Any]], List[str]], None]]
_db_storage_available: Optional[bool] = None


def _emit_log(message: str, callback: LogCallback = None, level: str = "info"):
    if level == "warning":
        log_warning(message)
    elif level == "error":
        log_error(message)
    elif level == "exception":
        log_exception(message)
    elif level == "debug":
        log_debug(message)
    else:
        log_info(message)

    if callback:
        callback(message)


def _db_storage_enabled(log_callback: LogCallback = None, force_recheck: bool = False) -> bool:
    global _db_storage_available

    if _db_storage_available is True and not force_recheck:
        return _db_storage_available

    try:
        get_storage_health()
        _db_storage_available = True
    except Exception as exc:
        _db_storage_available = False
        _emit_log(f"postgres storage unavailable, fallback to local files: {exc}", log_callback, level="warning")
    return _db_storage_available


def _looks_like_attachment_only_topic(content: str) -> bool:
    return _looks_like_attachment_only_topic_impl(content)


def _should_skip_topic_stock_ai_extraction(content: str) -> Tuple[bool, str]:
    return _should_skip_topic_stock_ai_extraction_impl(content)


def get_group_analysis_paths(group_id: str) -> Dict[str, str]:
    return _get_group_analysis_paths(group_id)


def resolve_analysis_paths(
    output_path: str = DEFAULT_OUTPUT_PATH,
    state_path: str = DEFAULT_STATE_PATH,
    group_id: Optional[str] = None,
) -> Tuple[str, str]:
    return _resolve_analysis_paths(output_path, state_path, group_id)


def should_use_db_storage(group_id: Optional[str] = None) -> bool:
    return _db_storage_enabled()


def parse_time(value: Optional[str]) -> Optional[datetime]:
    return _parse_time(value)


def normalize_day(dt: datetime) -> str:
    return _normalize_day(dt)


def make_item_key(item: Dict[str, Any]) -> str:
    return _make_item_key(item)


def _extract_day_from_state_key(key: str) -> Optional[str]:
    return _extract_day_from_state_key_impl(key)


def read_topics_last_days(group_id: str, days: int, log_callback: LogCallback = None) -> List[Dict[str, Any]]:
    start, end = get_last_days_range(days)
    return read_topics_in_time_range(
        group_id,
        start,
        end,
        f"last {days} days",
        log_callback,
    )


def read_topics_in_date_range(
    group_id: str,
    start_date: str,
    end_date: str,
    log_callback: LogCallback = None,
) -> List[Dict[str, Any]]:
    start, end = get_date_range_bounds(start_date, end_date)
    return read_topics_in_time_range(
        group_id,
        start,
        end,
        f"{start_date} ~ {end_date}",
        log_callback,
    )


def read_topics_in_time_range(
    group_id: str,
    start: datetime,
    end: datetime,
    range_label: str,
    log_callback: LogCallback = None,
) -> List[Dict[str, Any]]:
    return _read_topics_in_time_range(
        group_id,
        start,
        end,
        range_label,
        debug_logger=log_debug,
        emit_log=_emit_log,
        log_callback=log_callback,
    )


def _format_company_log(companies: Sequence[str], max_chars: int = 160) -> str:
    return _format_company_log_impl(companies, max_chars)


def _format_stock_concepts_log(stocks: Sequence[Dict[str, Any]], max_chars: int = 220) -> str:
    return _format_stock_concepts_log_impl(stocks, max_chars)


def call_openai_extract_topic_stocks(
    text: str,
    api_key: Optional[str],
    model: str,
    api_base: Optional[str] = None,
    wire_api: str = DEFAULT_WIRE_API,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    max_retries: int = DEFAULT_OPENAI_MAX_RETRIES,
    item_context: Optional[str] = None,
    log_callback: LogCallback = None,
) -> List[Dict[str, Any]]:
    return _call_openai_extract_topic_stocks(
        text,
        api_key,
        model,
        api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        max_retries=max_retries,
        item_context=item_context,
        log_callback=log_callback,
        debug_logger=log_debug,
        warning_logger=log_warning,
    )


def call_openai_extract_companies(
    text: str,
    api_key: Optional[str],
    model: str,
    api_base: Optional[str] = None,
    wire_api: str = DEFAULT_WIRE_API,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    max_retries: int = DEFAULT_OPENAI_MAX_RETRIES,
    item_context: Optional[str] = None,
    log_callback: LogCallback = None,
) -> List[str]:
    return _call_openai_extract_companies(
        text,
        api_key,
        model,
        api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        max_retries=max_retries,
        item_context=item_context,
        log_callback=log_callback,
        debug_logger=log_debug,
        warning_logger=log_warning,
    )


def aggregate_daily(
    items: List[Dict[str, Any]],
    api_key: Optional[str],
    model: str,
    api_base: Optional[str],
    wire_api: str = DEFAULT_WIRE_API,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    concurrency: int = DEFAULT_CONCURRENCY,
    log_callback: LogCallback = None,
    success_callback: AggregateSuccessCallback = None,
) -> Tuple[Dict[str, Dict[str, int]], Set[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    def extract_topic_stocks(content: str, item_context: str) -> List[Dict[str, Any]]:
        return call_openai_extract_topic_stocks(
            content,
            api_key,
            model,
            api_base,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
            item_context=item_context,
            log_callback=log_callback,
        )

    return _aggregate_daily(
        items,
        concurrency=concurrency,
        log_callback=log_callback,
        success_callback=success_callback,
        extraction_adapter=TopicStockExtractionAdapter(
            extract=extract_topic_stocks,
            model=model,
            prompt_version=TOPIC_STOCK_EXTRACTION_PROMPT_VERSION,
        ),
        debug_logger=log_debug,
        emit_log=_emit_log,
    )


def _read_existing_csv_file(output_path: str = DEFAULT_OUTPUT_PATH) -> Dict[str, Dict[str, int]]:
    return _read_existing_csv_file_impl(output_path, log_info)


def read_existing_csv(
    output_path: str = DEFAULT_OUTPUT_PATH,
    group_id: Optional[str] = None,
) -> Dict[str, Dict[str, int]]:
    return _recommendation_pool_storage().read_daily(output_path, DEFAULT_STATE_PATH, group_id=group_id)


def _write_csv_file(daily: Dict[str, Dict[str, int]], output_path: str = DEFAULT_OUTPUT_PATH):
    _write_csv_file_impl(daily, output_path, log_info)


def write_csv(
    daily: Dict[str, Dict[str, int]],
    output_path: str = DEFAULT_OUTPUT_PATH,
    group_id: Optional[str] = None,
):
    _recommendation_pool_storage().save_daily(daily, output_path, DEFAULT_STATE_PATH, group_id=group_id)


def _load_state_file(state_path: str = DEFAULT_STATE_PATH) -> set:
    return _load_state_file_impl(state_path, log_info)


def _recommendation_pool_storage() -> AShareRecommendationPoolStorage:
    return AShareRecommendationPoolStorage(
        AShareRecommendationPoolStorageAdapters(
            should_use_db_storage=should_use_db_storage,
            resolve_analysis_paths=resolve_analysis_paths,
            read_daily_file=_read_existing_csv_file,
            write_daily_file=_write_csv_file,
            load_state_file=_load_state_file,
            save_state_file=_save_state_file,
            load_daily_mentions_from_db=load_daily_mentions_from_db,
            save_daily_mentions_to_db=save_daily_mentions_to_db,
            load_processed_state_from_db=load_processed_state_from_db,
            save_processed_state_to_db=save_processed_state_to_db,
            normalize_group_id=normalize_group_id,
            log_info=log_info,
        )
    )


def load_state(
    state_path: str = DEFAULT_STATE_PATH,
    group_id: Optional[str] = None,
) -> set:
    return _recommendation_pool_storage().load_processed(DEFAULT_OUTPUT_PATH, state_path, group_id=group_id)


def _save_state_file(state_path: str = DEFAULT_STATE_PATH, processed_keys: Optional[Iterable[str]] = None):
    _save_state_file_impl(state_path, processed_keys, log_info)


def save_state(
    state_path: str = DEFAULT_STATE_PATH,
    processed_keys: Optional[Iterable[str]] = None,
    group_id: Optional[str] = None,
):
    _recommendation_pool_storage().save_processed(
        DEFAULT_OUTPUT_PATH,
        state_path,
        processed_keys,
        group_id=group_id,
    )


def remove_daily_range(
    daily: Dict[str, Dict[str, int]],
    start_date: str,
    end_date: str,
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int]]:
    return _remove_daily_range_impl(daily, start_date, end_date)


def remove_state_range(processed_keys: set, start_date: str, end_date: str) -> Tuple[set, int]:
    return _remove_state_range_impl(processed_keys, start_date, end_date)


def reset_analysis_range(
    start_date: str,
    end_date: str,
    output_path: str = DEFAULT_OUTPUT_PATH,
    state_path: str = DEFAULT_STATE_PATH,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    start_date, end_date = _normalize_date_range(start_date, end_date)

    resolved_output_path, resolved_state_path = resolve_analysis_paths(output_path, state_path, group_id)
    daily = read_existing_csv(resolved_output_path, group_id=group_id)
    processed_keys = load_state(resolved_state_path, group_id=group_id)

    if should_use_db_storage(group_id):
        removed = reset_a_share_analysis_range_to_db(start_date, end_date, group_id=group_id)
        summary = get_analysis_summary(resolved_output_path, resolved_state_path, group_id=group_id)
        return {
            "group_id": normalize_group_id(group_id),
            "start_date": start_date,
            "end_date": end_date,
            "removed_days": 0,
            "removed_rows": removed.get("daily_mentions", 0),
            "removed_mentions": 0,
            "removed_state_keys": removed.get("processed_state", 0),
            "removed_topic_stock_extractions": removed.get("topic_stock_extractions", 0),
            "removed_stock_topic_processed_states": removed.get("stock_topic_processed_states", 0),
            "removed_stock_topic_analyses": removed.get("stock_topic_analyses", 0),
            "removed_stock_topic_analysis_versions": removed.get("stock_topic_analysis_versions", 0),
            "summary": summary,
        }

    daily, removed_daily = remove_daily_range(daily, start_date, end_date)
    processed_keys, removed_state_keys = remove_state_range(processed_keys, start_date, end_date)

    write_csv(daily, resolved_output_path, group_id=group_id)
    save_state(resolved_state_path, processed_keys, group_id=group_id)

    summary = get_analysis_summary(resolved_output_path, resolved_state_path, group_id=group_id)
    return {
        "group_id": normalize_group_id(group_id),
        "start_date": start_date,
        "end_date": end_date,
        **removed_daily,
        "removed_state_keys": removed_state_keys,
        "summary": summary,
    }


def backfill_topic_stock_extractions(
    *,
    group_id: Optional[str],
    days: int = 7,
    model: str = DEFAULT_MODEL,
    api_base: str = DEFAULT_API_BASE,
    wire_api: str = DEFAULT_WIRE_API,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    concurrency: int = DEFAULT_CONCURRENCY,
    log_callback: LogCallback = None,
) -> Dict[str, Any]:
    bounded_days = max(1, int(days))
    end_day = datetime.now().strftime("%Y-%m-%d")
    start_day = (datetime.now() - timedelta(days=bounded_days - 1)).strftime("%Y-%m-%d")
    return run_analysis(
        days=bounded_days,
        group_id=group_id,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        concurrency=concurrency,
        reset_start_date=start_day,
        reset_end_date=end_day,
        log_callback=log_callback,
    )


def get_source_topics_summary(group_id: Optional[str] = None) -> Dict[str, Any]:
    normalized_group_id = normalize_group_id(group_id)
    if not normalized_group_id:
        return {
            "topics_db_exists": None,
            "topics_count": None,
            "oldest_topic_time": None,
            "latest_topic_time": None,
        }

    return load_source_topics_summary(normalized_group_id)


def get_analysis_summary(
    output_path: str = DEFAULT_OUTPUT_PATH,
    state_path: str = DEFAULT_STATE_PATH,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_group_id = normalize_group_id(group_id)
    resolved_output_path, resolved_state_path = resolve_analysis_paths(output_path, state_path, normalized_group_id)
    daily = read_existing_csv(resolved_output_path, group_id=normalized_group_id)
    processed_keys = load_state(resolved_state_path, group_id=normalized_group_id)
    storage_health = get_storage_health(group_id=normalized_group_id) if should_use_db_storage(normalized_group_id) else None
    has_db_data = bool(storage_health and (
        int(storage_health.get("daily_rows") or 0) > 0 or int(storage_health.get("processed_rows") or 0) > 0
    ))
    source_topics_summary = get_source_topics_summary(normalized_group_id)
    available_dates = sorted(daily.keys())

    unique_companies = set()
    rows_count = 0
    total_mentions = 0
    for company_counts in daily.values():
        rows_count += len(company_counts)
        total_mentions += sum(company_counts.values())
        unique_companies.update(company_counts.keys())

    if storage_health and (normalized_group_id is None or has_db_data):
        output_exists = True
        state_exists = True
        updated_at = storage_health.get("latest_updated_at")
        database_name = storage_health.get("database_name") or "postgres"
        output_path_value = f"{database_name}.public.{DAILY_MENTIONS_TABLE}"
        state_path_value = f"{database_name}.public.{PROCESSED_STATE_TABLE}"
    else:
        output_exists = os.path.exists(resolved_output_path)
        state_exists = os.path.exists(resolved_state_path)
        updated_at = None
        if output_exists:
            updated_at = datetime.fromtimestamp(os.path.getmtime(resolved_output_path)).isoformat()
        output_path_value = resolved_output_path
        state_path_value = resolved_state_path

    return {
        "group_id": normalized_group_id,
        "output_path": output_path_value,
        "state_path": state_path_value,
        "output_exists": output_exists,
        "state_exists": state_exists,
        "available_dates": available_dates,
        "available_start_date": available_dates[0] if available_dates else None,
        "available_end_date": available_dates[-1] if available_dates else None,
        "date_count": len(available_dates),
        "rows_count": rows_count,
        "total_mentions": total_mentions,
        "unique_companies": len(unique_companies),
        "processed_items": len(processed_keys),
        "updated_at": updated_at,
        "source_topics_db_exists": source_topics_summary.get("topics_db_exists"),
        "source_topics_count": source_topics_summary.get("topics_count"),
        "source_oldest_topic_time": source_topics_summary.get("oldest_topic_time"),
        "source_latest_topic_time": source_topics_summary.get("latest_topic_time"),
    }


def build_chart_payload(
    output_path: str = DEFAULT_OUTPUT_PATH,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    top_n: int = 20,
    ranking_windows: Sequence[int] = DEFAULT_RANKING_WINDOWS,
    ranking_top_n: int = DEFAULT_RANKING_TOP_N,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_output_path, _resolved_state_path = resolve_analysis_paths(output_path, DEFAULT_STATE_PATH, group_id)
    daily = read_existing_csv(resolved_output_path, group_id=group_id)
    return build_chart_payload_from_daily(
        daily,
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        ranking_windows=ranking_windows,
        ranking_top_n=ranking_top_n,
        group_id=group_id,
    )


def run_analysis(
    days: int = 21,
    output_path: str = DEFAULT_OUTPUT_PATH,
    state_path: str = DEFAULT_STATE_PATH,
    group_id: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    api_base: str = DEFAULT_API_BASE,
    wire_api: str = DEFAULT_WIRE_API,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    concurrency: int = DEFAULT_CONCURRENCY,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    reset_start_date: Optional[str] = None,
    reset_end_date: Optional[str] = None,
    log_callback: LogCallback = None,
) -> Dict[str, Any]:
    ensure_configured()
    run_plan = build_analysis_run_plan(
        days=days,
        concurrency=concurrency,
        output_path=output_path,
        state_path=state_path,
        group_id=group_id,
        start_date=start_date,
        end_date=end_date,
    )
    normalized_group_id = run_plan.normalized_group_id
    days = run_plan.days
    concurrency = run_plan.concurrency
    resolved_output_path = run_plan.output_path
    resolved_state_path = run_plan.state_path
    run_date_range = run_plan.run_date_range
    existing_daily = read_existing_csv(resolved_output_path, group_id=normalized_group_id)
    processed_keys = load_state(resolved_state_path, group_id=normalized_group_id)

    reset_summary = None
    if reset_start_date or reset_end_date:
        if not reset_start_date or not reset_end_date:
            raise ValueError("reset_start_date 和 reset_end_date 需要同时提供")
        start_day, end_day = _normalize_date_range(
            reset_start_date,
            reset_end_date,
            "reset_start_date",
            "reset_end_date",
            "reset_start_date 不能晚于 reset_end_date",
        )

        reset_result = apply_analysis_reset_range(
            existing_daily,
            processed_keys,
            start_day,
            end_day,
            days,
        )
        existing_daily = reset_result.daily
        processed_keys = reset_result.processed_keys
        reset_summary = reset_result.reset_summary
        _emit_log(
            f"reset range finished: {start_day} ~ {end_day}, "
            f"removed_rows={reset_summary['removed_rows']}, "
            f"removed_mentions={reset_summary['removed_mentions']}, "
            f"removed_state_keys={reset_summary['removed_state_keys']}",
            log_callback,
        )
        write_csv(existing_daily, resolved_output_path, group_id=normalized_group_id)
        save_state(resolved_state_path, processed_keys, group_id=normalized_group_id)

        if reset_result.days > days:
            _emit_log(
                f"scan days auto adjusted: requested={days}, required={reset_result.days} to cover reset range",
                log_callback,
            )
            days = reset_result.days

    runtime_ai_config = get_openai_compatible_config()
    api_key = str(runtime_ai_config.get("api_key") or "").strip()
    if not api_key:
        write_csv(existing_daily, resolved_output_path, group_id=normalized_group_id)
        save_state(resolved_state_path, processed_keys, group_id=normalized_group_id)
        _emit_log("OPENAI_API_KEY not set and config.toml [ai].api_key is empty", log_callback, level="error")
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    groups = discover_analysis_groups(normalized_group_id)
    _emit_log(f"discovered groups: {len(groups)}", log_callback)

    all_items = load_analysis_run_items(
        groups,
        days=days,
        run_date_range=run_date_range,
        read_topics_last_days=read_topics_last_days,
        read_topics_in_date_range=read_topics_in_date_range,
        log_callback=log_callback,
    )
    _emit_log(f"discovered items total={len(all_items)}", log_callback)
    items_to_process = [item for item in all_items if make_item_key(item) not in processed_keys]
    _emit_log(
        f"items to process={len(items_to_process)} skipped={len(all_items) - len(items_to_process)}",
        log_callback,
    )

    checkpoint_enabled = bool(normalized_group_id and should_use_db_storage(normalized_group_id))
    checkpoint_manager = AShareAnalysisCheckpointManager(
        enabled=checkpoint_enabled,
        group_id=normalized_group_id,
        processed_keys=processed_keys,
        save_checkpoint=save_recommendation_pool_checkpoint,
        emit_log=lambda message: _emit_log(message, log_callback),
        batch_size=DEFAULT_CHECKPOINT_BATCH_SIZE,
    )

    new_daily, succeeded_item_keys, failed_items, topic_stock_extractions = aggregate_daily(
        items_to_process,
        api_key=api_key,
        model=model,
        api_base=api_base,
        wire_api=wire_api or str(runtime_ai_config.get("wire_api") or DEFAULT_WIRE_API),
        reasoning_effort=reasoning_effort or str(runtime_ai_config.get("reasoning_effort") or DEFAULT_REASONING_EFFORT),
        concurrency=concurrency,
        log_callback=log_callback,
        success_callback=checkpoint_manager.success_callback(),
    )
    checkpoint_manager.flush(force=True)

    added_mentions = 0
    for day, company_counts in new_daily.items():
        day_bucket = existing_daily.setdefault(day, {})
        for company, added_count in company_counts.items():
            day_bucket[company] = day_bucket.get(company, 0) + added_count
            added_mentions += added_count

    saved_topic_stock_extractions = 0
    if topic_stock_extractions and normalized_group_id and should_use_db_storage(normalized_group_id):
        if checkpoint_enabled:
            saved_topic_stock_extractions = checkpoint_manager.saved_topic_stock_extractions
        else:
            saved_topic_stock_extractions = save_topic_stock_extractions(
                topic_stock_extractions,
                group_id=normalized_group_id,
            )
            _emit_log(
                f"db topic stock extractions saved at {datetime.now().isoformat(timespec='seconds')}: "
                f"group_id={normalized_group_id}, topic_stock_extractions={saved_topic_stock_extractions}",
                log_callback,
            )

    write_csv(existing_daily, resolved_output_path, group_id=normalized_group_id)
    processed_keys.update(succeeded_item_keys)
    save_state(resolved_state_path, processed_keys, group_id=normalized_group_id)

    summary = get_analysis_summary(resolved_output_path, resolved_state_path, group_id=normalized_group_id)
    result = {
        "group_id": normalized_group_id,
        "days": days,
        "groups_count": len(groups),
        "items_discovered": len(all_items),
        "items_processed": len(items_to_process),
        "items_succeeded": len(succeeded_item_keys),
        "items_failed": len(failed_items),
        "new_days": len(new_daily),
        "added_mentions": added_mentions,
        "topic_stock_extractions": saved_topic_stock_extractions,
        "failed_items": failed_items[:100],
        "reset_summary": reset_summary,
        "summary": summary,
        "output_path": summary["output_path"],
        "state_path": summary["state_path"],
    }
    _emit_log(
        f"analysis finished: processed={len(items_to_process)}, succeeded={len(succeeded_item_keys)}, "
        f"failed={len(failed_items)}, added_mentions={added_mentions}, "
        f"topic_stock_extractions={saved_topic_stock_extractions}, date_count={summary['date_count']}",
        log_callback,
    )
    return result
