from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional, Set

from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_wire_api,
    get_extraction_reasoning_effort,
)
from backend.core.logger_config import log_debug, log_warning
from backend.services.ai_client import (
    extract_response_text,
    is_retryable_ai_error,
)
from backend.services.ai_json_utils import require_json_object
from backend.services.ai_runtime_request import AIRuntimeTextSettings, call_structured_ai_object
from backend.services.stock_concept_taxonomy import normalize_stock_concept_term
from backend.services.stock_extraction_payload import safe_confidence, safe_text_list


DEFAULT_API_BASE = get_default_base_url()
DEFAULT_WIRE_API = get_default_wire_api()
DEFAULT_REASONING_EFFORT = get_extraction_reasoning_effort()
DEFAULT_OPENAI_MAX_RETRIES = max(1, int(os.environ.get("OPENAI_MAX_RETRIES", "1")))
TOPIC_STOCK_EXTRACTION_PROMPT_VERSION = "a-share-topic-stock-extraction-v3"
A_SHARE_COMPANY_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "stock_name": {"type": "string"},
                    "industry_concepts": {"type": "array", "items": {"type": "string"}},
                    "signal_tags": {"type": "array", "items": {"type": "string"}},
                    "raw_terms": {"type": "array", "items": {"type": "string"}},
                    "excerpt": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "stock_name",
                    "industry_concepts",
                    "signal_tags",
                    "raw_terms",
                    "excerpt",
                    "reason",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["stocks"],
    "additionalProperties": False,
}

LogCallback = Optional[Callable[[str], None]]


def _emit_log(
    message: str,
    callback: LogCallback = None,
    level: str = "info",
    debug_logger: Callable[[str], None] = log_debug,
    warning_logger: Callable[[str], None] = log_warning,
):
    if callback:
        callback(message)
    if level == "warning":
        warning_logger(message)
    else:
        debug_logger(message)


def _extract_response_text(response: Any) -> str:
    return extract_response_text(response)


def _extract_json_object(text: str) -> Dict[str, Any]:
    return require_json_object(text, label="AI 公司抽取结果")


def _safe_float(value: Any, default: float = 0.0) -> float:
    return safe_confidence(value, default)


def _safe_text_list(value: Any, *, limit: int = 10) -> List[str]:
    return safe_text_list(value, limit=limit, dedupe_after_truncate=True)


def _normalize_extracted_concepts(raw: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    industry_concepts = _safe_text_list(raw.get("industry_concepts"), limit=5)
    signal_tags = _safe_text_list(raw.get("signal_tags"), limit=6)

    if industry_concepts or signal_tags:
        candidates.extend(industry_concepts)
        candidates.extend(signal_tags)
    else:
        candidates.extend(_safe_text_list(raw.get("concepts"), limit=10))

    concepts: List[str] = []
    for candidate in candidates:
        class_name, normalized = normalize_stock_concept_term(candidate)
        if class_name == "empty" or not normalized or normalized in concepts:
            continue
        concepts.append(normalized)
        if len(concepts) >= 10:
            break
    return concepts


def _clean_company_name(raw: Any) -> str:
    company = str(raw or "").strip()
    company = (
        company.replace("•", "")
        .replace("-", "")
        .replace("1.", "")
        .replace("2.", "")
        .replace("3.", "")
        .strip()
    )
    if "、" in company and company.split("、", 1)[0].isdigit():
        company = company.split("、", 1)[1].strip()
    return company


def _is_valid_company_name(company: str) -> bool:
    return (
        bool(company)
        and 2 <= len(company) <= 12
        and "证券" not in company
        and "指数" not in company
        and "ETF" not in company.upper()
    )


def _parse_topic_stock_extraction_output(message: str) -> List[Dict[str, Any]]:
    payload = _extract_json_object(message)
    return _parse_topic_stock_extraction_payload(payload)


def _parse_topic_stock_extraction_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_stocks = payload.get("stocks")
    if raw_stocks is None:
        raw_stocks = payload.get("companies")
    if raw_stocks is None:
        raw_stocks = payload.get("a_share_companies")
    if not isinstance(raw_stocks, list):
        return []

    cleaned: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for raw in raw_stocks:
        if isinstance(raw, dict):
            company = _clean_company_name(raw.get("stock_name") or raw.get("company") or raw.get("name"))
            concepts = _normalize_extracted_concepts(raw)
            raw_terms = _safe_text_list(raw.get("raw_terms"), limit=10)
            excerpt = str(raw.get("excerpt") or "").strip()[:2000]
            reason = str(raw.get("reason") or "").strip()[:1000]
            confidence = _safe_float(raw.get("confidence"))
        else:
            company = _clean_company_name(raw)
            concepts = []
            raw_terms = []
            excerpt = ""
            reason = ""
            confidence = 0.7

        if not _is_valid_company_name(company) or company in seen:
            continue
        item = {
            "stock_name": company,
            "concepts": concepts,
            "excerpt": excerpt,
            "reason": reason,
            "confidence": confidence,
        }
        if raw_terms:
            item["raw_terms"] = raw_terms
        cleaned.append(item)
        seen.add(company)
    return cleaned


def _parse_company_extraction_output(message: str) -> List[str]:
    return [stock["stock_name"] for stock in _parse_topic_stock_extraction_output(message)]


def _is_retryable_openai_error(exc: Exception) -> bool:
    return is_retryable_ai_error(exc)


def _build_topic_stock_extraction_prompt() -> str:
    return (
        "请从下面内容中提取明确具有正向推荐或受益语义的中国A股上市公司，并给出上下文中的投资概念。\n"
        "这里的推荐池只收录被看好、被推荐、可能受益、作为投资主线或机会提及的股票；"
        "不要仅因为公司名称出现就输出。\n"
        "你必须同时输出每只股票对应的 excerpt，excerpt 是从原文中直接摘出的证据片段，不要改写成摘要。\n"
        "要求：\n"
        "1. 只保留可以明确判断为A股上市公司的公司名称。\n"
        "2. 只有当上下文对该股票是正向推荐、重点关注、买入/增持、受益、催化、业绩改善、困境反转、弹性向上等语义时才输出。\n"
        "3. 如果公司只是风险、暴雷、利空、业绩下修、利润重算下滑、处罚、减持、踩雷、避雷、跌幅归因、表现平平、净卖出、负面案例或需要规避的对象，不要输出。\n"
        "4. 港股、美股、ETF、指数、板块、行业、产品、基金、机构、人物都不要输出。\n"
        "5. 如果只是业务、产品、子公司、老板姓名，且无法唯一映射到A股上市公司，不要猜。\n"
        "6. 同一家公司如果同时出现全称和简称，只输出一个更常见的A股证券简称。\n"
        "7. industry_concepts 填中粒度产业概念，每只股票最多 3-5 个，例如机器人、PCB、CCL、铜箔、储能、锂电/电池、光通信/CPO、AI算力/数据中心、半导体设备/先进封装；不要把涨价、国产替代、订单、出海这类催化属性放进这里。\n"
        "8. signal_tags 填催化或属性信号，例如涨价/供需、国产替代/自主可控、出海/出口、订单/扩产、估值/分红；没有明确证据可给空数组。\n"
        "9. raw_terms 可保留原文中的细分词或精确说法，例如 PCB钻针、CPU涨价、固态电池量产；没有可给空数组。raw_terms 用于回溯，不要为了凑数输出。\n"
        "10. excerpt 规则：\n"
        "   - 如果全文都在讲一个股票，返回全文。\n"
        "   - 如果分段讲多个股票，只返回当前股票对应的那一段。\n"
        "   - 如果一段里同时讲多个股票，这一段要对每个相关股票都返回同一段 excerpt。\n"
        "   - 如果同一股票在全文多处出现，只保留最能说明其被推荐或受益的那一段，尽量保留原文，不要改写。\n"
        "11. reason 简要说明该股票被推荐或受益的原因；如果只有负面或风险语义，应直接不输出，而不是降低 confidence。"
    )


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
    timeout: int = 200,
    debug_logger: Callable[[str], None] = log_debug,
    warning_logger: Callable[[str], None] = log_warning,
) -> List[Dict[str, Any]]:
    if not api_key:
        warning_logger("openai-compatible api key missing")
        return []

    content = str(text or "").strip()
    if len(content) < 20:
        debug_logger("skip topic stock extraction because content is empty or shorter than 20 chars")
        return []

    prompt = _build_topic_stock_extraction_prompt()
    content = content if len(content) <= 8000 else content[:8000]
    messages = [
        {
            "role": "system",
            "content": (
                "你是A股推荐池抽取助手。"
                "你的任务是从中文投资内容中抽取明确被正向推荐或明确受益的中国A股上市公司、关联概念和理由。"
                "如果无法确认是A股上市公司，或上下文只是负面风险、暴雷、利空、避雷、跌幅归因，就不要输出。"
            ),
        },
        {"role": "user", "content": prompt + "\n\n" + content},
    ]

    normalized_wire_api = str(wire_api or DEFAULT_WIRE_API).strip().lower()
    runtime_settings = AIRuntimeTextSettings(
        api_key=str(api_key or ""),
        model=model,
        api_base=api_base or DEFAULT_API_BASE,
        wire_api=normalized_wire_api,
    )

    last_error: Optional[Exception] = None
    attempts = max(1, int(max_retries or 1))
    payload: Dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        try:
            result = call_structured_ai_object(
                messages,
                schema_name="a_share_company_extraction",
                schema=A_SHARE_COMPANY_EXTRACTION_SCHEMA,
                label="AI 公司抽取结果",
                settings=runtime_settings,
                reasoning_effort=str(reasoning_effort or DEFAULT_REASONING_EFFORT).strip() or DEFAULT_REASONING_EFFORT,
                timeout=timeout,
            )
            payload = result.payload
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            retryable = _is_retryable_openai_error(exc)
            if attempt >= attempts or not retryable:
                raise

            wait_seconds = min(20, 2 ** (attempt - 1))
            context_text = f" {item_context}" if item_context else ""
            _emit_log(
                f"openai request retry {attempt}/{attempts - 1}{context_text}: {exc} (sleep {wait_seconds}s)",
                log_callback,
                level="warning",
                debug_logger=debug_logger,
                warning_logger=warning_logger,
            )
            time.sleep(wait_seconds)

    if last_error is not None:
        raise last_error

    cleaned = _parse_topic_stock_extraction_payload(payload)
    debug_logger(f"openai-compatible model extracted topic stocks: {len(cleaned)}")
    return cleaned


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
    timeout: int = 200,
    debug_logger: Callable[[str], None] = log_debug,
    warning_logger: Callable[[str], None] = log_warning,
) -> List[str]:
    return [
        stock["stock_name"]
        for stock in call_openai_extract_topic_stocks(
            text,
            api_key,
            model,
            api_base,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
            max_retries=max_retries,
            item_context=item_context,
            log_callback=log_callback,
            timeout=timeout,
            debug_logger=debug_logger,
            warning_logger=warning_logger,
        )
    ]
