"""Stock-scoped topic search and AI summary for a group."""

from __future__ import annotations

import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Tuple

from backend.core.ai_provider_config import (
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.services.ai_client import call_ai_text
from backend.services.ai_json_utils import JsonObjectParseError, extract_json_object, require_json_object
from backend.services.ai_runtime_request import build_runtime_ai_text_request
from backend.services.stock_topic_analysis_ai_prompts import (
    build_image_stock_extraction_input,
    build_question_analysis_messages,
    build_question_keyword_messages,
    build_stock_analysis_messages,
)
from backend.services.stock_topic_analysis_helpers import (
    _build_saved_stock_analysis_result,
    _build_stock_alias_terms,
    _build_stock_analysis_result,
    _chunks,
    _merge_topic_ids,
    _normalize_company_name,
    _normalize_text,
    _ordered_unique,
    _parse_json_list,
    _reconcile_processed_topic_ids,
    _safe_float,
    _stock_analysis_mode,
    parse_stock_names,
)
from backend.services.stock_topic_analysis_payloads import (
    build_analysis_topic_payload,
    build_question_analysis_prompt,
    build_stock_analysis_prompt,
    require_topic_excerpt,
)
from backend.services.stock_topic_analysis_store import (
    CHECKPOINT_ANALYZED_BATCH,
    CHECKPOINT_COMPLETED_SNAPSHOT,
    CHECKPOINT_FAILED_BATCH,
    CHECKPOINT_SKIPPED_ONLY,
    load_question_topic_search_rows,
    load_saved_stock_topic_analysis,
    load_stock_recommendation_counts_for_names,
    load_stock_topic_search_sources,
    save_stock_topic_analysis_checkpoint,
)
from backend.services.stock_topic_analysis_runner import (
    AnalyzeStockTopicsBatchRequest,
    AnalyzeStockTopicsRequest,
    AnswerStockQuestionRequest,
    StockTopicAnalysisEngine,
)
from backend.services.daily_topic_analysis_topics import clip_text as _clip
from backend.services.stock_topic_question_payload import build_question_topic_payload_from_rows, load_question_topic_payload
from backend.storage.db_compat import connect as connect


MAX_SEARCH_CANDIDATE_TOPICS = 500
MAX_ANALYSIS_TOPICS = 30
MAX_ANALYSIS_TOPICS_PER_CALL = 10
MAX_TRACKED_TOPIC_IDS = 5000
MAX_TOPIC_TEXT_CHARS = 1800
MAX_ANALYSIS_PROMPT_CHARS = 50000
MAX_BATCH_STOCK_ANALYSIS_WORKERS = 10
MAX_BATCH_TRANSIENT_FAILURES = 5
MAX_QUESTION_KEYWORDS = 8
MAX_QUESTION_TOPICS = 60
MAX_EXTRACT_IMAGE_BYTES = 4 * 1024 * 1024
STOCK_TOPIC_ANALYSIS_TABLE = "stock_topic_analyses"
PROCESSED_TOPIC_STATUSES = {"analyzed", "skipped"}
SUPPORTED_EXTRACT_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
TRANSIENT_BATCH_ERROR_MARKERS = (
    "503",
    "service temporarily unavailable",
    "connection error",
    "timeout",
    "timed out",
)


def _log(log_callback: Callable[[str], None] | None, message: str) -> None:
    if log_callback:
        log_callback(message)


def _is_transient_batch_error(message: str) -> bool:
    normalized = _normalize_text(message).lower()
    return any(marker in normalized for marker in TRANSIENT_BATCH_ERROR_MARKERS)


def _normalize_question_keywords(values: Any, *, limit: int = MAX_QUESTION_KEYWORDS) -> List[str]:
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, Iterable):
        raw_values = list(values)
    else:
        raw_values = []
    return _ordered_unique(
        (_normalize_text(value) for value in raw_values),
        limit=max(1, min(limit, MAX_QUESTION_KEYWORDS)),
    )


def _parse_image_data_url(image_data_url: str) -> Tuple[str, str, bytes]:
    value = _normalize_text(image_data_url)
    match = re.fullmatch(r"data:([^;,]+);base64,(.+)", value, flags=re.DOTALL)
    if not match:
        raise ValueError("图片数据格式不正确")

    mime_type = match.group(1).strip().lower()
    if mime_type not in SUPPORTED_EXTRACT_IMAGE_TYPES:
        raise ValueError("仅支持 JPG、PNG 或 WebP 图片")

    import base64
    import binascii

    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except binascii.Error as exc:
        raise ValueError("图片 base64 数据不正确") from exc
    if not image_bytes:
        raise ValueError("图片内容为空")
    if len(image_bytes) > MAX_EXTRACT_IMAGE_BYTES:
        raise ValueError("图片不能超过 4MB")
    return mime_type, value, image_bytes


def _topic_content(row: Any) -> str:
    return "\n".join(
        part
        for part in (
            _normalize_text(row["title"]),
            _normalize_text(row["talk_text"]),
            _normalize_text(row["question_text"]),
            _normalize_text(row["answer_text"]),
        )
        if part
    )


def _empty_search_result(group_id: str, stock_name: str) -> Dict[str, Any]:
    return {
        "group_id": group_id,
        "stock_name": stock_name,
        "stock_code": "",
        "market": "",
        "topics": [],
        "concepts": [],
        "topic_count": 0,
        "recommendation_count": 0,
        "processed_topic_ids": [],
        "analyzed_topic_ids": [],
        "skipped_topic_ids": [],
    }


def _empty_latest_result(group_id: str, stock_name: str) -> Dict[str, Any]:
    return {
        **_empty_search_result(group_id, stock_name),
        "summary_markdown": "",
        "model": "",
        "status": "missing",
        "error": "",
        "created_at": None,
        "updated_at": None,
    }


def _recent_topic_cutoff_text() -> str:
    return (date.today() - timedelta(days=365)).isoformat()


def _require_topic_excerpt(value: Any, *, topic_id: Any, stock_name: Any) -> str:
    return require_topic_excerpt(value, topic_id=topic_id, stock_name=stock_name)


def _score_relevant_topic(extracted_content: str, mode: str, matched_terms: Iterable[str], topic_row: Dict[str, Any]) -> int:
    if not extracted_content:
        return 0
    score = 100 if mode in {"full", "title_full"} else 70
    score += min(len(_ordered_unique(matched_terms, limit=10)) * 5, 15)
    confidence = _safe_float(topic_row.get("confidence"))
    if confidence > 0:
        score += min(int(confidence * 10), 10)
    return score


def get_latest_stock_topic_analysis(group_id: str, stock_name: str) -> Dict[str, Any] | None:
    query = _normalize_text(stock_name)
    if not query:
        raise ValueError("stock_name 不能为空")

    return load_saved_stock_topic_analysis(group_id, query)


def get_latest_stock_topic_analyses(group_id: str, stock_names: Any) -> Dict[str, Any]:
    names = parse_stock_names(stock_names)
    if not names:
        raise ValueError("stock_names 不能为空")

    group_id_text = _normalize_text(group_id)
    return {
        "group_id": group_id_text,
        "stocks": [
            get_latest_stock_topic_analysis(group_id_text, stock_name) or _empty_latest_result(group_id_text, stock_name)
            for stock_name in names
        ],
    }


def search_stock_topics(group_id: str, stock_name: str, *, limit: int | None = None) -> Dict[str, Any]:
    query = _normalize_text(stock_name)
    if not query:
        raise ValueError("stock_name 不能为空")

    group_id_text = _normalize_text(group_id)
    alias_terms = _build_stock_alias_terms(stock_name)
    search_term = alias_terms[0] if alias_terms else query
    recent_cutoff = _recent_topic_cutoff_text()
    sources = load_stock_topic_search_sources(
        group_id_text,
        query,
        search_term,
        recent_cutoff=recent_cutoff,
        processed_topic_statuses=PROCESSED_TOPIC_STATUSES,
        max_tracked_topic_ids=MAX_TRACKED_TOPIC_IDS,
        max_candidate_topics=MAX_SEARCH_CANDIDATE_TOPICS,
    )
    processed_topic_ids = sources.processed_topic_ids
    processed_topic_id_set = set(processed_topic_ids)
    rows = sources.rows
    if not rows:
        empty_result = _empty_search_result(group_id_text, query)
        empty_result["processed_topic_ids"] = processed_topic_ids
        empty_result["analyzed_topic_ids"] = processed_topic_ids
        return empty_result

    topics_by_id: Dict[str, Dict[str, Any]] = {}
    stock_names: List[str] = []
    stock_codes: List[str] = []
    markets: List[str] = []

    for row in rows:
        topic_id = str(row["topic_id"])
        if topic_id in processed_topic_id_set:
            continue
        stored_excerpt = _require_topic_excerpt(row["excerpt"], topic_id=topic_id, stock_name=query)
        extracted_content = stored_excerpt
        mode = "stored_excerpt"
        matched_terms = _ordered_unique([_normalize_text(row["stock_name"]), *alias_terms], limit=10)
        topic = topics_by_id.setdefault(
            topic_id,
            {
                "topic_id": topic_id,
                "title": row["title"] or "",
                "create_time": row["create_time"] or "",
                "likes_count": int(row["likes_count"] or 0),
                "comments_count": int(row["comments_count"] or 0),
                "reading_count": int(row["reading_count"] or 0),
                "content_preview": _clip(extracted_content, 260),
                "concepts": [],
                "reasons": [],
                "excerpt": stored_excerpt,
                "confidence": 0.0,
                "recommendation_count": 0,
                "extract_mode": mode,
                "relevance_score": 0,
                "analysis_content": extracted_content,
            },
        )
        stock_names.append(row["stock_name"] or query)
        stock_codes.append(row["stock_code"] or "")
        markets.append(row["market"] or "")
        topic["concepts"] = _ordered_unique([*topic["concepts"], *_parse_json_list(row["concepts_json"])], limit=12)
        topic["reasons"] = _ordered_unique([*topic["reasons"], row["reason"]], limit=6)
        topic["confidence"] = max(_safe_float(topic["confidence"]), _safe_float(row["confidence"]))
        topic["relevance_score"] = max(
            int(topic["relevance_score"]),
            _score_relevant_topic(extracted_content, mode, matched_terms, topic),
        )
        topic["extract_mode"] = mode if topic.get("extract_mode") != "full" else topic["extract_mode"]
        if len(extracted_content) > len(str(topic.get("analysis_content") or "")):
            topic["analysis_content"] = extracted_content

    recommendation_count, recommendation_by_date = load_stock_recommendation_counts_for_names(
        group_id_text,
        _ordered_unique([query, *stock_names], limit=10),
    )
    for topic in topics_by_id.values():
        topic_day = str(topic["create_time"] or "")[:10]
        topic["recommendation_count"] = recommendation_by_date.get(topic_day, 0)

    topics = sorted(
        topics_by_id.values(),
        key=lambda item: (
            int(item.get("relevance_score") or 0),
            str(item["create_time"] or ""),
        ),
        reverse=True,
    )
    if limit is not None:
        topics = topics[: max(1, int(limit))]
    concepts = _ordered_unique(
        concept
        for topic in topics
        for concept in topic.get("concepts", [])
    )
    stock_code_values = _ordered_unique(stock_codes, limit=1)
    market_values = _ordered_unique(markets, limit=1)
    return {
        "group_id": group_id_text,
        "stock_name": query,
        "stock_code": stock_code_values[0] if stock_code_values else "",
        "market": market_values[0] if market_values else "",
        "topics": topics,
        "concepts": concepts,
        "topic_count": len(topics),
        "recommendation_count": recommendation_count,
        "processed_topic_ids": _ordered_unique(processed_topic_ids, limit=MAX_TRACKED_TOPIC_IDS),
        "analyzed_topic_ids": _ordered_unique(processed_topic_ids, limit=MAX_TRACKED_TOPIC_IDS),
        "skipped_topic_ids": [],
    }


def _build_stock_question_search_result(
    *,
    group_id: str,
    question: str,
    keywords: List[str],
    keyword_model: str,
    rows: List[Any],
) -> Dict[str, Any]:
    topics_by_id: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        topic_id = str(row["topic_id"])
        content = _topic_content(row)
        matched_keywords = [keyword for keyword in keywords if keyword.lower() in content.lower()]
        topics_by_id[topic_id] = {
            "topic_id": topic_id,
            "title": row["title"] or "",
            "create_time": row["create_time"] or "",
            "likes_count": int(row["likes_count"] or 0),
            "comments_count": int(row["comments_count"] or 0),
            "reading_count": int(row["reading_count"] or 0),
            "content_preview": _clip(content, 300),
            "matched_keywords": matched_keywords,
        }

    topics = sorted(topics_by_id.values(), key=lambda item: str(item["create_time"] or ""), reverse=True)
    return {
        "group_id": group_id,
        "question": question,
        "keywords": keywords,
        "keyword_model": keyword_model,
        "topics": topics,
        "topic_count": len(topics),
    }


def _search_stock_question_topics_with_rows(
    group_id: str,
    question: str,
    *,
    limit: int = MAX_QUESTION_TOPICS,
) -> tuple[Dict[str, Any], List[Any]]:
    question_text = _normalize_text(question)
    if not question_text:
        raise ValueError("question 不能为空")
    keywords, keyword_model = _call_question_keyword_ai(question_text)
    if not keywords:
        raise ValueError("无法从问题中提取关键词")

    group_id_text = _normalize_text(group_id)
    recent_cutoff = _recent_topic_cutoff_text()
    rows = load_question_topic_search_rows(
        group_id_text,
        keywords,
        recent_cutoff=recent_cutoff,
        limit=max(1, min(int(limit), MAX_QUESTION_TOPICS)),
    )

    return (
        _build_stock_question_search_result(
            group_id=group_id_text,
            question=question_text,
            keywords=keywords,
            keyword_model=keyword_model,
            rows=rows,
        ),
        rows,
    )


def search_stock_question_topics(group_id: str, question: str, *, limit: int = MAX_QUESTION_TOPICS) -> Dict[str, Any]:
    search_result, _rows = _search_stock_question_topics_with_rows(group_id, question, limit=limit)
    return search_result


def _build_analysis_topic_payload(search_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    return build_analysis_topic_payload(search_result)


def _build_question_topic_payload(search_result: Dict[str, Any], rows: List[Any] | None = None) -> List[Dict[str, Any]]:
    if rows is not None:
        return build_question_topic_payload_from_rows(
            search_result,
            rows,
            max_analysis_topics=MAX_ANALYSIS_TOPICS,
            max_topic_text_chars=MAX_TOPIC_TEXT_CHARS,
        )
    return load_question_topic_payload(
        search_result,
        max_analysis_topics=MAX_ANALYSIS_TOPICS,
        max_topic_text_chars=MAX_TOPIC_TEXT_CHARS,
    )


def _build_stock_analysis_prompt(
    search_result: Dict[str, Any],
    topics: List[Dict[str, Any]],
    *,
    existing_summary: str = "",
) -> str:
    return build_stock_analysis_prompt(
        search_result,
        topics,
        existing_summary=existing_summary,
        max_analysis_prompt_chars=MAX_ANALYSIS_PROMPT_CHARS,
    )


def _build_question_analysis_prompt(search_result: Dict[str, Any], topics: List[Dict[str, Any]]) -> str:
    return build_question_analysis_prompt(
        search_result,
        topics,
        max_analysis_prompt_chars=MAX_ANALYSIS_PROMPT_CHARS,
    )


def _call_stock_analysis_ai(prompt_payload: str, *, incremental: bool = False) -> Tuple[str, str]:
    messages = build_stock_analysis_messages(prompt_payload)
    request = build_runtime_ai_text_request(
        messages,
        get_ai_config=get_openai_compatible_config,
        wire_api="responses",
        reasoning_effort=get_summary_reasoning_effort(),
        timeout=180,
    )

    return (
        call_ai_text(request).strip(),
        request.model,
    )


def _extract_json_object(text: str) -> Dict[str, Any]:
    return extract_json_object(text)


def _call_question_keyword_ai(question: str) -> Tuple[List[str], str]:
    messages = build_question_keyword_messages(question)
    request = build_runtime_ai_text_request(
        messages,
        get_ai_config=get_openai_compatible_config,
        wire_api="responses",
        reasoning_effort=get_summary_reasoning_effort(),
        timeout=120,
    )
    text = call_ai_text(request)

    try:
        parsed = require_json_object(text, label="AI 问题关键词抽取结果")
    except JsonObjectParseError as exc:
        raise ValueError("AI 问题关键词抽取结果不是合法 JSON") from exc
    keywords = _normalize_question_keywords(parsed.get("keywords") or parsed.get("keyword") or [])
    if not keywords:
        raise ValueError("AI 未能从问题中提取检索关键词")
    return keywords, request.model


def _call_question_analysis_ai(question: str, prompt_payload: str) -> Tuple[str, str]:
    messages = build_question_analysis_messages(question, prompt_payload)
    request = build_runtime_ai_text_request(
        messages,
        get_ai_config=get_openai_compatible_config,
        wire_api="responses",
        reasoning_effort=get_summary_reasoning_effort(),
        timeout=180,
    )

    return (
        call_ai_text(request).strip(),
        request.model,
    )


def extract_stock_names_from_image(image_data_url: str) -> Dict[str, Any]:
    mime_type, normalized_data_url, image_bytes = _parse_image_data_url(image_data_url)
    prompt = (
        "请从这张图片中提取出现的 A 股股票名称。"
        "只输出 JSON，不要 Markdown，不要解释。"
        "如果识别到股票，JSON 结构为 {\"stockNames\": [\"股票名1\", \"股票名2\"]}。"
        "如果图片中没有明确股票名称，JSON 结构为 {\"error\": \"NO_STOCKS\"}。"
        "要求：保留图片里的股票中文简称，去重，最多 50 个。"
    )

    request = build_runtime_ai_text_request(
        build_image_stock_extraction_input(prompt, normalized_data_url),
        get_ai_config=get_openai_compatible_config,
        wire_api="responses",
        reasoning_effort=get_summary_reasoning_effort(),
        timeout=120,
    )
    text = call_ai_text(request)

    parsed = _extract_json_object(text)
    if parsed:
        stock_names = parse_stock_names(parsed.get("stockNames") or parsed.get("stock_names") or [])
    else:
        stock_names = parse_stock_names(text)
    if not stock_names:
        raise ValueError("图片里没有识别到明确股票名称")
    return {
        "stockNames": stock_names,
        "model": request.model,
        "mime_type": mime_type,
        "image_bytes": len(image_bytes),
    }


def _analyze_stock_topics_impl(
    group_id: str,
    stock_name: str,
    *,
    limit: int | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    _log(log_callback, "📚 搜索股票相关话题...")
    search_result = search_stock_topics(group_id, stock_name, limit=limit)
    _log(log_callback, f"📊 命中话题: {search_result['topic_count']}，推荐次数: {search_result['recommendation_count']}")
    latest = get_latest_stock_topic_analysis(group_id, stock_name)
    topic_progress = _reconcile_processed_topic_ids(latest, search_result)
    has_existing_summary = bool((latest or {}).get("summary_markdown"))

    if has_existing_summary and not topic_progress.has_new_topics:
        result = _build_saved_stock_analysis_result(
            search_result,
            latest,
            processed_topic_ids=topic_progress.processed_topic_ids,
            analyzed_topic_ids=topic_progress.saved_topic_ids,
        )
        if topic_progress.has_new_processed_topic_ids:
            save_stock_topic_analysis_checkpoint(
                result=result,
                phase=CHECKPOINT_SKIPPED_ONLY,
                max_tracked_topic_ids=MAX_TRACKED_TOPIC_IDS,
                analyzed_topic_ids=topic_progress.processed_topic_ids,
                processed_state_topic_ids=topic_progress.new_skipped_topic_ids,
            )
        _log(log_callback, "✅ 没有新话题，沿用已保存的个股分析结果")
        return result

    topics = topic_progress.topics_to_analyze(_build_analysis_topic_payload(search_result))

    if not topics:
        processed_topic_ids = topic_progress.with_current_topics_processed()
        result = _build_stock_analysis_result(
            search_result,
            summary_markdown=(latest or {}).get("summary_markdown") or "没有找到可分析的话题内容。",
            model=(latest or {}).get("model", ""),
            status="completed",
            processed_topic_ids=processed_topic_ids,
            analyzed_topic_ids=topic_progress.saved_topic_ids,
            new_topic_count=0,
            analysis_mode=_stock_analysis_mode(
                has_existing_summary=has_existing_summary,
                has_topics_to_analyze=False,
            ),
        )
        save_stock_topic_analysis_checkpoint(
            result=result,
            phase=CHECKPOINT_SKIPPED_ONLY,
            max_tracked_topic_ids=MAX_TRACKED_TOPIC_IDS,
            analyzed_topic_ids=processed_topic_ids,
            processed_state_topic_ids=topic_progress.new_skipped_topic_ids,
        )
        return result

    analysis_mode = _stock_analysis_mode(
        has_existing_summary=has_existing_summary,
        has_topics_to_analyze=True,
    )
    topic_batches = _chunks(topics, MAX_ANALYSIS_TOPICS_PER_CALL)
    _log(
        log_callback,
        f"🤖 调用 AI {'增量更新' if analysis_mode == 'incremental' else '初始化分析'} {len(topics)} 条话题，分 {len(topic_batches)} 批...",
    )
    try:
        summary = (latest or {}).get("summary_markdown") or ""
        model = (latest or {}).get("model") or ""
        processed_topic_ids = list(topic_progress.processed_topic_ids)
        current_batch_topic_ids: List[str] = []
        for batch_index, topic_batch in enumerate(topic_batches, start=1):
            _log(log_callback, f"🤖 AI 分析批次 {batch_index}/{len(topic_batches)}，话题 {len(topic_batch)} 条")
            current_batch_topic_ids = [str(topic.get("topic_id") or "") for topic in topic_batch]
            summary, model = _call_stock_analysis_ai(
                _build_stock_analysis_prompt(
                    search_result,
                    topic_batch,
                    existing_summary=summary,
                ),
                incremental=bool(summary),
            )
            processed_topic_ids = _merge_topic_ids(processed_topic_ids, current_batch_topic_ids)
            checkpoint_result = _build_stock_analysis_result(
                search_result,
                summary_markdown=summary or "",
                model=model,
                status="running" if batch_index < len(topic_batches) else "completed",
                processed_topic_ids=processed_topic_ids,
                new_topic_count=len(topics),
                analysis_mode=analysis_mode,
            )
            save_stock_topic_analysis_checkpoint(
                result=checkpoint_result,
                phase=CHECKPOINT_ANALYZED_BATCH,
                max_tracked_topic_ids=MAX_TRACKED_TOPIC_IDS,
                analyzed_topic_ids=processed_topic_ids,
                processed_state_topic_ids=current_batch_topic_ids,
            )
    except Exception as exc:
        failed_topic_ids = current_batch_topic_ids or topic_progress.new_topic_ids
        failed_result = _build_stock_analysis_result(
            search_result,
            topics=search_result["topics"][: len(topics)],
            summary_markdown=summary or "",
            model=model or "",
            status=None,
            processed_topic_ids=processed_topic_ids,
            new_topic_count=len(topics),
            analysis_mode=analysis_mode,
        )
        save_stock_topic_analysis_checkpoint(
            result=failed_result,
            phase=CHECKPOINT_FAILED_BATCH,
            max_tracked_topic_ids=MAX_TRACKED_TOPIC_IDS,
            error=str(exc),
            analyzed_topic_ids=processed_topic_ids,
            processed_state_topic_ids=failed_topic_ids,
        )
        raise
    processed_topic_ids = _merge_topic_ids(processed_topic_ids, (topic.get("topic_id") for topic in topics))
    result = _build_stock_analysis_result(
        search_result,
        topics=search_result["topics"],
        summary_markdown=summary or "AI 返回内容为空。",
        model=model,
        status="completed",
        processed_topic_ids=processed_topic_ids,
        new_topic_count=len(topics),
        analysis_mode=analysis_mode,
    )
    save_stock_topic_analysis_checkpoint(
        result=result,
        phase=CHECKPOINT_COMPLETED_SNAPSHOT,
        max_tracked_topic_ids=MAX_TRACKED_TOPIC_IDS,
        analyzed_topic_ids=processed_topic_ids,
    )
    _log(log_callback, "✅ 个股分析结果已保存")
    return result


def _analyze_stock_topics_batch_impl(
    group_id: str,
    stock_names: Any,
    *,
    log_callback: Callable[[str], None] | None = None,
    max_stocks: int | None = None,
) -> Dict[str, Any]:
    names = parse_stock_names(stock_names, limit=max_stocks)
    if not names:
        raise ValueError("stock_names 不能为空")

    group_id_text = _normalize_text(group_id)
    total = len(names)
    results: List[Dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    no_topic_count = 0
    skipped_count = 0
    consecutive_transient_failures = 0
    abort_reason = ""
    max_workers = min(MAX_BATCH_STOCK_ANALYSIS_WORKERS, total)
    _log(log_callback, f"开始批量分析，共 {total} 只股票，并发 {max_workers}")

    def analyze_one(index: int, stock_name: str) -> Tuple[int, Dict[str, Any], str]:
        try:
            preview = search_stock_topics(group_id_text, stock_name)
            if preview["topic_count"] <= 0:
                _log(log_callback, f"{index}/{total} {stock_name}: 未命中话题，保存空结果")
            else:
                _log(log_callback, f"{index}/{total} {stock_name}: 命中 {preview['topic_count']} 个话题，开始 AI 分析")

            result = analyze_stock_topics(
                group_id_text,
                stock_name,
                log_callback=log_callback,
            )
            _log(log_callback, f"{index}/{total} {result.get('stock_name') or stock_name}: 完成并保存")
            status = "no_topics" if result.get("topic_count", 0) <= 0 else "success"
            return index, result, status
        except Exception as exc:
            try:
                latest = get_latest_stock_topic_analysis(group_id_text, stock_name) or _empty_latest_result(group_id_text, stock_name)
            except Exception:
                latest = _empty_latest_result(group_id_text, stock_name)
            failed_result = {
                **latest,
                "status": "failed",
                "error": str(exc),
            }
            _log(log_callback, f"{index}/{total} {stock_name}: 失败 - {str(exc)}")
            return index, failed_result, "failed"

    def record_result(index: int, result: Dict[str, Any], status: str) -> None:
        nonlocal success_count, failed_count, no_topic_count, consecutive_transient_failures, abort_reason
        ordered_results[index - 1] = result
        if status == "no_topics":
            no_topic_count += 1
            consecutive_transient_failures = 0
        elif status == "failed":
            failed_count += 1
            if _is_transient_batch_error(str(result.get("error") or "")):
                consecutive_transient_failures += 1
            else:
                consecutive_transient_failures = 0
        else:
            success_count += 1
            consecutive_transient_failures = 0

        if consecutive_transient_failures >= MAX_BATCH_TRANSIENT_FAILURES and not abort_reason:
            abort_reason = f"连续 {consecutive_transient_failures} 个临时错误，停止提交后续股票"
            _log(log_callback, f"⚠️ {abort_reason}")

    ordered_results: List[Dict[str, Any] | None] = [None] * total
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        next_position = 1

        def submit_next() -> None:
            nonlocal next_position
            if next_position > total:
                return
            futures[executor.submit(analyze_one, next_position, names[next_position - 1])] = next_position
            next_position += 1

        for _ in range(max_workers):
            submit_next()

        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future, None)
                index, result, status = future.result()
                record_result(index, result, status)
                if not abort_reason:
                    submit_next()

    results = [result for result in ordered_results if result is not None]
    skipped_count = total - len(results)
    if abort_reason:
        _log(log_callback, f"批量分析中止：成功 {success_count}，失败 {failed_count}，无话题 {no_topic_count}，未提交 {skipped_count}")
    else:
        _log(log_callback, f"批量分析完成：成功 {success_count}，失败 {failed_count}，无话题 {no_topic_count}")
    return {
        "group_id": group_id_text,
        "stocks": results,
        "summary": {
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "no_topics": no_topic_count,
            "skipped": skipped_count,
            "aborted": bool(abort_reason),
            "abort_reason": abort_reason,
        },
    }


def _answer_stock_question_impl(
    group_id: str,
    question: str,
    *,
    log_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    _log(log_callback, "🔎 根据问题关键词搜索话题...")
    search_result, search_rows = _search_stock_question_topics_with_rows(group_id, question)
    _log(
        log_callback,
        f"📚 关键词: {'、'.join(search_result['keywords'])}；命中话题: {search_result['topic_count']}",
    )
    topics = _build_question_topic_payload(search_result, search_rows)
    if not topics:
        return {
            **search_result,
            "summary_markdown": "没有找到可回答该问题的话题内容。",
            "model": "",
            "status": "completed",
        }

    _log(log_callback, f"🤖 调用 AI 总结前 {len(topics)} 条话题...")
    summary, model = _call_question_analysis_ai(
        search_result["question"],
        _build_question_analysis_prompt(search_result, topics),
    )
    _log(log_callback, "✅ A股问答总结完成")
    return {
        **search_result,
        "topics": search_result["topics"][: len(topics)],
        "summary_markdown": summary or "AI 返回内容为空。",
        "model": model,
        "status": "completed",
    }


class _StockTopicAnalysisOperations:
    def analyze_stock_topics(self, request: AnalyzeStockTopicsRequest) -> Dict[str, Any]:
        return _analyze_stock_topics_impl(
            request.group_id,
            request.stock_name,
            limit=request.limit,
            log_callback=request.log_callback,
        )

    def analyze_stock_topics_batch(self, request: AnalyzeStockTopicsBatchRequest) -> Dict[str, Any]:
        return _analyze_stock_topics_batch_impl(
            request.group_id,
            request.stock_names,
            log_callback=request.log_callback,
            max_stocks=request.max_stocks,
        )

    def answer_stock_question(self, request: AnswerStockQuestionRequest) -> Dict[str, Any]:
        return _answer_stock_question_impl(
            request.group_id,
            request.question,
            log_callback=request.log_callback,
        )


_STOCK_TOPIC_ANALYSIS_OPERATIONS = _StockTopicAnalysisOperations()
_STOCK_TOPIC_ANALYSIS_ENGINE = StockTopicAnalysisEngine(_STOCK_TOPIC_ANALYSIS_OPERATIONS)


def analyze_stock_topics(
    group_id: str,
    stock_name: str,
    *,
    limit: int | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    return _STOCK_TOPIC_ANALYSIS_ENGINE.analyze_stock_topics(
        group_id,
        stock_name,
        limit=limit,
        log_callback=log_callback,
    )


def analyze_stock_topics_batch(
    group_id: str,
    stock_names: Any,
    *,
    log_callback: Callable[[str], None] | None = None,
    max_stocks: int | None = None,
) -> Dict[str, Any]:
    return _STOCK_TOPIC_ANALYSIS_ENGINE.analyze_stock_topics_batch(
        group_id,
        stock_names,
        log_callback=log_callback,
        max_stocks=max_stocks,
    )


def answer_stock_question(
    group_id: str,
    question: str,
    *,
    log_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    return _STOCK_TOPIC_ANALYSIS_ENGINE.answer_stock_question(
        group_id,
        question,
        log_callback=log_callback,
    )


__all__ = [
    "answer_stock_question",
    "analyze_stock_topics",
    "analyze_stock_topics_batch",
    "extract_stock_names_from_image",
    "get_latest_stock_topic_analysis",
    "get_latest_stock_topic_analyses",
    "parse_stock_names",
    "search_stock_question_topics",
    "search_stock_topics",
    "_call_question_keyword_ai",
    "_parse_image_data_url",
    "_normalize_company_name",
    "_normalize_question_keywords",
    "_parse_json_list",
]
