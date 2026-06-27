"""Stock-scoped topic search and AI summary for a group."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Tuple

from backend.core.ai_provider_config import (
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.services.ai_runtime_request import call_runtime_ai_text
from backend.services.stock_topic_analysis_ai_prompts import (
    build_question_analysis_messages,
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
    _parse_json_list,
    _reconcile_processed_topic_ids,
    _stock_analysis_mode,
    parse_stock_names,
)
from backend.services.stock_topic_image_input import (
    MAX_EXTRACT_IMAGE_BYTES,
    SUPPORTED_EXTRACT_IMAGE_TYPES,
    parse_image_data_url as _parse_image_data_url,
)
from backend.services.stock_topic_image_extraction import (
    IMAGE_STOCK_NAME_EXTRACTION_SCHEMA,
    extract_stock_names_from_image,
)
from backend.services.stock_topic_question_keywords import (
    MAX_QUESTION_KEYWORDS,
    QUESTION_KEYWORD_EXTRACTION_SCHEMA,
    extract_question_keywords as _call_question_keyword_ai,
    normalize_question_keywords as _normalize_question_keywords,
)
from backend.services.stock_topic_analysis_payloads import (
    build_analysis_topic_payload,
    build_question_analysis_prompt,
    build_stock_analysis_prompt,
)
from backend.services.stock_topic_search_results import (
    build_empty_stock_topic_search_result,
    build_stock_topic_search_result,
    draft_stock_topic_search_result,
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
from backend.services.stock_topic_batch_runner import run_stock_topic_batch
from backend.services.stock_topic_question_payload import (
    QuestionTopicMaterial,
    build_question_topic_material,
)
from backend.storage.db_compat import connect as connect


MAX_SEARCH_CANDIDATE_TOPICS = 500
MAX_ANALYSIS_TOPICS = 30
MAX_ANALYSIS_TOPICS_PER_CALL = 10
MAX_TRACKED_TOPIC_IDS = 5000
MAX_TOPIC_TEXT_CHARS = 1800
MAX_ANALYSIS_PROMPT_CHARS = 50000
MAX_QUESTION_TOPICS = 60
STOCK_TOPIC_ANALYSIS_TABLE = "stock_topic_analyses"
PROCESSED_TOPIC_STATUSES = {"analyzed", "skipped"}


def _log(log_callback: Callable[[str], None] | None, message: str) -> None:
    if log_callback:
        log_callback(message)


def _empty_latest_result(group_id: str, stock_name: str) -> Dict[str, Any]:
    return {
        **build_empty_stock_topic_search_result(group_id, stock_name),
        "summary_markdown": "",
        "model": "",
        "status": "missing",
        "error": "",
        "created_at": None,
        "updated_at": None,
    }


def _recent_topic_cutoff_text() -> str:
    return (date.today() - timedelta(days=365)).isoformat()


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
    rows = sources.rows
    draft = draft_stock_topic_search_result(
        group_id=group_id_text,
        stock_name=query,
        rows=rows,
        processed_topic_ids=processed_topic_ids,
        alias_terms=alias_terms,
    )
    if not draft.had_rows:
        return build_empty_stock_topic_search_result(group_id_text, query, processed_topic_ids=processed_topic_ids)
    recommendation_count, recommendation_by_date = load_stock_recommendation_counts_for_names(
        group_id_text,
        draft.recommendation_names,
    )
    return build_stock_topic_search_result(
        draft,
        recommendation_count=recommendation_count,
        recommendation_by_date=recommendation_by_date,
        limit=limit,
        max_tracked_topic_ids=MAX_TRACKED_TOPIC_IDS,
    )


def _search_stock_question_material(
    group_id: str,
    question: str,
    *,
    limit: int = MAX_QUESTION_TOPICS,
) -> QuestionTopicMaterial:
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

    return build_question_topic_material(
        group_id=group_id_text,
        question=question_text,
        keywords=keywords,
        keyword_model=keyword_model,
        rows=rows,
        max_analysis_topics=MAX_ANALYSIS_TOPICS,
        max_topic_text_chars=MAX_TOPIC_TEXT_CHARS,
    )


def search_stock_question_topics(group_id: str, question: str, *, limit: int = MAX_QUESTION_TOPICS) -> Dict[str, Any]:
    return _search_stock_question_material(group_id, question, limit=limit).search_result


def _build_analysis_topic_payload(search_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    return build_analysis_topic_payload(search_result)


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
    result = call_runtime_ai_text(
        messages,
        get_ai_config=get_openai_compatible_config,
        wire_api="responses",
        reasoning_effort=get_summary_reasoning_effort(),
    )

    return (
        result.text.strip(),
        result.model,
    )


def _call_question_analysis_ai(question: str, prompt_payload: str) -> Tuple[str, str]:
    messages = build_question_analysis_messages(question, prompt_payload)
    result = call_runtime_ai_text(
        messages,
        get_ai_config=get_openai_compatible_config,
        wire_api="responses",
        reasoning_effort=get_summary_reasoning_effort(),
    )

    return (
        result.text.strip(),
        result.model,
    )


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

    def analyze_one(index: int, stock_name: str) -> Tuple[Dict[str, Any], str]:
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
            return result, status
        except Exception as exc:
            try:
                latest = get_latest_stock_topic_analysis(group_id_text, stock_name) or _empty_latest_result(
                    group_id_text,
                    stock_name,
                )
            except Exception:
                latest = _empty_latest_result(group_id_text, stock_name)
            failed_result = {
                **latest,
                "status": "failed",
                "error": str(exc),
            }
            _log(log_callback, f"{index}/{total} {stock_name}: 失败 - {str(exc)}")
            return failed_result, "failed"

    return run_stock_topic_batch(
        group_id=group_id_text,
        stock_names=names,
        analyze_one=analyze_one,
        log_callback=log_callback,
    )


def _answer_stock_question_impl(
    group_id: str,
    question: str,
    *,
    log_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    _log(log_callback, "🔎 根据问题关键词搜索话题...")
    material = _search_stock_question_material(group_id, question)
    search_result = material.search_result
    _log(
        log_callback,
        f"📚 关键词: {'、'.join(search_result['keywords'])}；命中话题: {search_result['topic_count']}",
    )
    topics = material.analysis_topics
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
