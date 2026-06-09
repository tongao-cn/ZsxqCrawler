from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple


LogCallback = Optional[Callable[[str], None]]
AggregateSuccessCallback = Optional[Callable[[str, str, List[Dict[str, Any]], List[str]], None]]
StockExtractor = Callable[..., List[Dict[str, Any]]]


def looks_like_attachment_only_topic(content: str) -> bool:
    normalized = str(content or "").strip()
    return normalized in {"「图片」", "「文件」", "[图片]", "[文件]", "图片", "文件"}


def should_skip_topic_stock_ai_extraction(content: str) -> Tuple[bool, str]:
    text = str(content or "").strip()
    if looks_like_attachment_only_topic(text):
        return True, "content only contains attachment placeholder"
    if len(text) < 20:
        return True, "content is empty or shorter than 20 chars"
    return False, ""


def make_item_key(item: Dict[str, Any]) -> str:
    return f"{item.get('source', '')}:{item.get('topic_id', '')}:{item.get('day', '')}"


def format_company_log(companies: Sequence[str], max_chars: int = 160) -> str:
    normalized = [str(company).strip() for company in companies if str(company).strip()]
    if not normalized:
        return "无"

    joined = ", ".join(normalized)
    if len(joined) <= max_chars:
        return joined

    current_length = 0
    visible: List[str] = []
    for company in normalized:
        addition = len(company) if not visible else len(company) + 2
        if current_length + addition > max_chars:
            break
        visible.append(company)
        current_length += addition

    remaining = len(normalized) - len(visible)
    suffix = f" ... (+{remaining})" if remaining > 0 else ""
    return ", ".join(visible) + suffix


def format_stock_concepts_log(stocks: Sequence[Dict[str, Any]], max_chars: int = 220) -> str:
    entries: List[str] = []
    for stock in stocks:
        stock_name = str(stock.get("stock_name") or "").strip()
        concepts = [
            str(concept).strip()
            for concept in stock.get("concepts") or []
            if str(concept).strip()
        ]
        if not stock_name or not concepts:
            continue
        entries.append(f"{stock_name}: {'/'.join(concepts[:3])}")

    if not entries:
        return "无"

    joined = "; ".join(entries)
    if len(joined) <= max_chars:
        return joined

    current_length = 0
    visible: List[str] = []
    for entry in entries:
        addition = len(entry) if not visible else len(entry) + 2
        if current_length + addition > max_chars:
            break
        visible.append(entry)
        current_length += addition

    remaining = len(entries) - len(visible)
    suffix = f" ... (+{remaining})" if remaining > 0 else ""
    return "; ".join(visible) + suffix


def aggregate_daily(
    items: List[Dict[str, Any]],
    api_key: Optional[str],
    model: str,
    api_base: Optional[str],
    *,
    wire_api: str,
    reasoning_effort: str,
    concurrency: int,
    log_callback: LogCallback,
    success_callback: AggregateSuccessCallback,
    stock_extractor: StockExtractor,
    debug_logger: Callable[[str], None],
    emit_log: Callable[..., None],
    prompt_version: str,
) -> Tuple[Dict[str, Dict[str, int]], Set[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    daily: Dict[str, Dict[str, int]] = {}
    succeeded_item_keys: Set[str] = set()
    failed_items: List[Dict[str, Any]] = []
    topic_stock_extractions: List[Dict[str, Any]] = []
    prefilter_skipped = 0

    def _work(item: Dict[str, Any]):
        debug_logger(f"process item topic_id={item.get('topic_id')} day={item.get('day')}")
        item_key = make_item_key(item)
        content = str(item.get("text") or "").strip()
        should_skip, skip_reason = should_skip_topic_stock_ai_extraction(content)
        if should_skip:
            debug_logger(f"skip topic_id={item.get('topic_id')} because {skip_reason}")
            return item.get("day"), [], item.get("topic_id"), item_key
        stocks = stock_extractor(
            content,
            api_key,
            model,
            api_base,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
            item_context=f"topic_id={item.get('topic_id')} day={item.get('day')} key={item_key}",
            log_callback=log_callback,
        )
        unique_stocks: Dict[str, Dict[str, Any]] = {}
        for stock in stocks:
            stock_name = str(stock.get("stock_name") or "").strip()
            if not stock_name or stock_name in unique_stocks:
                continue
            unique_stocks[stock_name] = {
                "group_id": str(item.get("group_id") or ""),
                "topic_id": str(item.get("topic_id") or ""),
                "topic_date": str(item.get("day") or ""),
                "stock_name": stock_name,
                "stock_code": "",
                "market": "",
                "concepts": list(stock.get("concepts") or []),
                "excerpt": str(stock.get("excerpt") or ""),
                "reason": str(stock.get("reason") or ""),
                "confidence": float(stock.get("confidence") or 0),
                "model": model,
                "prompt_version": prompt_version,
            }
        return item.get("day"), list(unique_stocks.values()), item.get("topic_id"), item_key

    max_workers = max(1, int(concurrency or 1))
    items_to_submit: List[Dict[str, Any]] = []
    for item in items:
        item_key = make_item_key(item)
        should_skip, skip_reason = should_skip_topic_stock_ai_extraction(str(item.get("text") or ""))
        if should_skip:
            prefilter_skipped += 1
            succeeded_item_keys.add(item_key)
            if success_callback:
                success_callback(item_key, str(item.get("day") or ""), [], [])
            emit_log(
                f"skipped topic_id={item.get('topic_id')} before AI extraction: {skip_reason}",
                log_callback,
                level="debug",
            )
            continue
        items_to_submit.append(item)
    if prefilter_skipped:
        emit_log(f"prefilter skipped {prefilter_skipped} topics before AI extraction", log_callback)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {executor.submit(_work, item): item for item in items_to_submit}
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            item_key = make_item_key(item)
            try:
                day, stocks, topic_id, result_item_key = future.result()
            except Exception as exc:
                failed_items.append(
                    {
                        "topic_id": str(item.get("topic_id") or ""),
                        "day": str(item.get("day") or ""),
                        "group_id": str(item.get("group_id") or ""),
                        "item_key": item_key,
                        "error": str(exc),
                    }
                )
                emit_log(
                    f"worker failed for topic_id={item.get('topic_id')} day={item.get('day')} key={item_key}: {exc}",
                    log_callback,
                    level="exception",
                )
                continue

            companies = sorted(stock["stock_name"] for stock in stocks if stock.get("stock_name"))
            if companies:
                day_bucket = daily.setdefault(day, {})
                for company in companies:
                    day_bucket[company] = day_bucket.get(company, 0) + 1
                topic_stock_extractions.extend(stocks)
            succeeded_item_keys.add(result_item_key)
            if success_callback:
                success_callback(result_item_key, str(day or ""), stocks, companies)
            emit_log(
                f"extracted {len(companies)} companies for topic_id={topic_id}: "
                f"{format_company_log(companies)}; concepts: {format_stock_concepts_log(stocks)}",
                log_callback,
            )
    return daily, succeeded_item_keys, failed_items, topic_stock_extractions
