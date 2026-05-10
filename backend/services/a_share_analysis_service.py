#!/usr/bin/env python3
import csv
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from backend.core.db_path_manager import get_db_path_manager
from backend.core.local_group_runtime import get_cached_local_group_ids
from backend.storage.db_compat import connect
from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_model,
    get_default_wire_api,
    get_extraction_reasoning_effort,
    get_openai_compatible_config,
)
from backend.services.a_share_analysis_db_storage import (
    DAILY_MENTIONS_TABLE,
    PROCESSED_STATE_TABLE,
    get_storage_health,
    load_daily_mentions as load_daily_mentions_from_db,
    load_processed_state as load_processed_state_from_db,
    save_recommendation_pool_checkpoint,
    save_topic_stock_extractions,
    save_daily_mentions as save_daily_mentions_to_db,
    save_processed_state as save_processed_state_to_db,
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


DEFAULT_OUTPUT_PATH = "output/company_mentions_last_month.csv"
DEFAULT_STATE_PATH = "output/company_mentions_state.json"
DEFAULT_MODEL = get_default_model()
DEFAULT_API_BASE = get_default_base_url()
DEFAULT_WIRE_API = get_default_wire_api()
DEFAULT_REASONING_EFFORT = get_extraction_reasoning_effort()
DEFAULT_CONCURRENCY = 10
DEFAULT_RANKING_WINDOWS = (3, 7, 14, 21)
DEFAULT_RANKING_TOP_N = 35
DEFAULT_CHECKPOINT_BATCH_SIZE = 20
DEFAULT_OPENAI_MAX_RETRIES = max(1, int(os.environ.get("OPENAI_MAX_RETRIES", "4")))
GROUP_ANALYSIS_DIRNAME = "a_share_analysis"
GROUP_OUTPUT_FILENAME = "company_mentions.csv"
GROUP_STATE_FILENAME = "company_mentions_state.json"
TOPIC_STOCK_EXTRACTION_PROMPT_VERSION = "a-share-topic-stock-extraction-v1"
A_SHARE_COMPANY_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "stock_name": {"type": "string"},
                    "concepts": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["stock_name", "concepts", "reason", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["stocks"],
    "additionalProperties": False,
}

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

    if _db_storage_available is not None and not force_recheck:
        return _db_storage_available

    try:
        get_storage_health()
        _db_storage_available = True
    except Exception as exc:
        _db_storage_available = False
        _emit_log(f"postgres storage unavailable, fallback to local files: {exc}", log_callback, level="warning")
    return _db_storage_available


def normalize_group_id(group_id: Optional[str]) -> Optional[str]:
    if group_id is None:
        return None
    normalized = str(group_id).strip()
    return normalized or None


def get_group_analysis_paths(group_id: str) -> Dict[str, str]:
    normalized_group_id = normalize_group_id(group_id)
    if not normalized_group_id:
        raise ValueError("group_id 不能为空")

    path_manager = get_db_path_manager()
    analysis_dir = os.path.join(path_manager.get_group_dir(normalized_group_id), GROUP_ANALYSIS_DIRNAME)
    return {
        "group_id": normalized_group_id,
        "analysis_dir": analysis_dir,
        "output_path": os.path.join(analysis_dir, GROUP_OUTPUT_FILENAME),
        "state_path": os.path.join(analysis_dir, GROUP_STATE_FILENAME),
    }


def resolve_analysis_paths(
    output_path: str = DEFAULT_OUTPUT_PATH,
    state_path: str = DEFAULT_STATE_PATH,
    group_id: Optional[str] = None,
) -> Tuple[str, str]:
    normalized_group_id = normalize_group_id(group_id)
    if normalized_group_id and output_path == DEFAULT_OUTPUT_PATH and state_path == DEFAULT_STATE_PATH:
        group_paths = get_group_analysis_paths(normalized_group_id)
        return group_paths["output_path"], group_paths["state_path"]
    return output_path, state_path


def should_use_db_storage(group_id: Optional[str] = None) -> bool:
    return _db_storage_enabled()


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    formats = (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo:
                return dt.astimezone().replace(tzinfo=None)
            return dt.replace(tzinfo=None)
        except Exception:
            continue
    try:
        if value.endswith("+0800"):
            base = value[:-5]
            return datetime.strptime(base, "%Y-%m-%dT%H:%M:%S.%f")
    except Exception:
        pass
    return None


def normalize_day(dt: datetime) -> str:
    if dt.tzinfo:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d")


def validate_day(day: Optional[str], field_name: str = "date") -> Optional[str]:
    if day is None or str(day).strip() == "":
        return None
    try:
        return datetime.strptime(str(day).strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD 格式") from exc


def _normalize_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    start_field_name: str = "start_date",
    end_field_name: str = "end_date",
    reverse_error: str = "start_date 不能晚于 end_date",
) -> Tuple[str, str]:
    start_day = validate_day(start_date, start_field_name) or ""
    end_day = validate_day(end_date, end_field_name) or ""
    if start_day > end_day:
        raise ValueError(reverse_error)
    return start_day, end_day


def get_last_days_range(days: int) -> Tuple[datetime, datetime]:
    now = datetime.now()
    return now - timedelta(days=days), now


def get_required_days_for_start_date(start_date: str) -> int:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    delta = datetime.now().date() - start_dt.date()
    return max(1, delta.days + 2)


def make_item_key(item: Dict[str, Any]) -> str:
    return f"{item.get('source', '')}:{item.get('topic_id', '')}:{item.get('day', '')}"


def _extract_day_from_state_key(key: str) -> Optional[str]:
    if not key:
        return None
    parts = key.split(":")
    if len(parts) < 3:
        return None
    day = parts[-1].strip()
    if len(day) != 10:
        return None
    return day


def read_topics_last_days(group_id: str, days: int, log_callback: LogCallback = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    normalized_group_id = str(group_id or "").strip()
    query_group_id: Any = int(normalized_group_id) if normalized_group_id.isdigit() else normalized_group_id

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT t.topic_id, t.title, t.create_time FROM topics t WHERE t.group_id = ?",
            (query_group_id,),
        )
        rows = cur.fetchall()
        log_debug(f"loaded topics rows: {len(rows)} from zsxq_core for group {normalized_group_id}")

        start, end = get_last_days_range(days)
        filtered_rows = []
        for topic_id, title, create_time in rows:
            dt = parse_time(create_time)
            if not dt or dt < start or dt > end:
                continue
            filtered_rows.append((topic_id, title, create_time, dt))

        talk_texts: Dict[Any, str] = {}
        topic_ids = [topic_id for topic_id, _, _, _ in filtered_rows]
        if topic_ids:
            try:
                placeholders = ", ".join("?" for _ in topic_ids)
                cur.execute(
                    f"SELECT topic_id, text FROM talks WHERE topic_id IN ({placeholders})",
                    tuple(topic_ids),
                )
                for topic_id, text in cur.fetchall():
                    talk_texts[topic_id] = text or ""
            except Exception:
                pass
        log_debug(f"loaded talks texts: {len(talk_texts)} for group {normalized_group_id}")

        for topic_id, title, create_time, dt in filtered_rows:
            text = talk_texts.get(topic_id) or (title or "")
            if not text:
                continue
            items.append(
                {
                    "topic_id": topic_id,
                    "title": title or "",
                    "text": text,
                    "create_time": create_time,
                    "day": normalize_day(dt),
                    "source": "topics",
                    "group_id": normalized_group_id,
                }
            )
    finally:
        conn.close()

    _emit_log(
        f"filtered topics items: {len(items)} for last {days} days in group {normalized_group_id}",
        log_callback,
    )
    return items


def _extract_response_text(response: Any) -> str:
    text_value = getattr(response, "output_text", None)
    if text_value:
        return str(text_value)

    try:
        outputs = getattr(response, "output", []) or []
        chunks: List[str] = []
        for output in outputs:
            for content in getattr(output, "content", []) or []:
                chunk_text = getattr(content, "text", None)
                if chunk_text:
                    chunks.append(str(chunk_text))
        if chunks:
            return "\n".join(chunks)
    except Exception:
        pass

    return ""


def _format_company_log(companies: Sequence[str], max_chars: int = 160) -> str:
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


def _format_stock_concepts_log(stocks: Sequence[Dict[str, Any]], max_chars: int = 220) -> str:
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


def _extract_json_object(text: str) -> Dict[str, Any]:
    content = str(text or "").strip()
    if not content:
        return {}

    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return {}
        payload = json.loads(content[start : end + 1])

    return payload if isinstance(payload, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(0.0, min(1.0, parsed))


def _safe_text_list(value: Any, *, limit: int = 10) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned: List[str] = []
    seen: Set[str] = set()
    for raw in value:
        text = str(raw or "").strip()[:80]
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
        if len(cleaned) >= limit:
            break
    return cleaned


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
            concepts = _safe_text_list(raw.get("concepts"), limit=10)
            reason = str(raw.get("reason") or "").strip()[:1000]
            confidence = _safe_float(raw.get("confidence"))
        else:
            company = _clean_company_name(raw)
            concepts = []
            reason = ""
            confidence = 0.7

        if not _is_valid_company_name(company) or company in seen:
            continue
        cleaned.append(
            {
                "stock_name": company,
                "concepts": concepts,
                "reason": reason,
                "confidence": confidence,
            }
        )
        seen.add(company)
    return cleaned


def _parse_company_extraction_output(message: str) -> List[str]:
    return [stock["stock_name"] for stock in _parse_topic_stock_extraction_output(message)]


def _get_chat_json_schema_response_format() -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "a_share_company_extraction",
            "strict": True,
            "schema": A_SHARE_COMPANY_EXTRACTION_SCHEMA,
        },
    }


def _get_responses_json_schema_text_format() -> Dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "name": "a_share_company_extraction",
            "strict": True,
            "schema": A_SHARE_COMPANY_EXTRACTION_SCHEMA,
        },
    }


def _is_retryable_openai_error(exc: Exception) -> bool:
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, RateLimitError
    except Exception:
        return False

    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)):
        return True

    if isinstance(exc, APIStatusError):
        status_code = int(getattr(exc, "status_code", 0) or 0)
        return status_code == 408 or status_code == 409 or status_code == 429 or status_code >= 500

    return False


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
    timeout: int = 120,
) -> List[Dict[str, Any]]:
    if not api_key:
        log_warning("openai-compatible api key missing")
        return []

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai 依赖，请先安装后再运行分析") from exc

    prompt = (
        "请从下面内容中提取明确提到的中国A股上市公司，并给出上下文中的投资概念。\n"
        "要求：\n"
        "1. 只保留可以明确判断为A股上市公司的公司名称。\n"
        "2. 港股、美股、ETF、指数、板块、行业、产品、基金、机构、人物都不要输出。\n"
        "3. 如果只是业务、产品、子公司、老板姓名，且无法唯一映射到A股上市公司，不要猜。\n"
        "4. 同一家公司如果同时出现全称和简称，只输出一个更常见的A股证券简称。\n"
        "5. concepts 必须来自上下文，例如固态电池、机器人、算力、低空经济等；没有明确概念可给空数组。\n"
        "6. reason 简要说明该股票为什么被提到；不确定时降低 confidence。"
    )
    content = text if len(text) <= 8000 else text[:8000]
    messages = [
        {
            "role": "system",
            "content": (
                "你是A股上市公司名称抽取助手。"
                "你的任务是从中文投资内容中抽取明确提及的中国A股上市公司、关联概念和理由。"
                "如果无法确认是A股上市公司，就不要输出。"
            ),
        },
        {"role": "user", "content": prompt + "\n\n" + content},
    ]

    client = OpenAI(api_key=api_key, base_url=(api_base or DEFAULT_API_BASE), timeout=timeout)
    normalized_wire_api = str(wire_api or DEFAULT_WIRE_API).strip().lower()

    last_error: Optional[Exception] = None
    attempts = max(1, int(max_retries or 1))
    message = ""
    for attempt in range(1, attempts + 1):
        try:
            if normalized_wire_api == "responses":
                response = client.responses.create(
                    model=model,
                    input=messages,
                    reasoning={"effort": str(reasoning_effort or DEFAULT_REASONING_EFFORT).strip() or DEFAULT_REASONING_EFFORT},
                    text=_get_responses_json_schema_text_format(),
                )
                message = _extract_response_text(response)
            else:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=False,
                    response_format=_get_chat_json_schema_response_format(),
                )
                message = response.choices[0].message.content or ""
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
            )
            time.sleep(wait_seconds)

    if last_error is not None:
        raise last_error

    try:
        cleaned = _parse_topic_stock_extraction_output(message)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI 公司抽取结果不是合法 JSON: {message[:200]}") from exc

    log_debug(f"openai-compatible model extracted topic stocks: {len(cleaned)}")
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
    timeout: int = 120,
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
        )
    ]


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
    from concurrent.futures import ThreadPoolExecutor, as_completed

    daily: Dict[str, Dict[str, int]] = {}
    succeeded_item_keys: Set[str] = set()
    failed_items: List[Dict[str, Any]] = []
    topic_stock_extractions: List[Dict[str, Any]] = []

    def _work(item: Dict[str, Any]):
        log_debug(f"process item topic_id={item.get('topic_id')} day={item.get('day')}")
        item_key = make_item_key(item)
        stocks = call_openai_extract_topic_stocks(
            item["text"],
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
                "reason": str(stock.get("reason") or ""),
                "confidence": float(stock.get("confidence") or 0),
                "model": model,
                "prompt_version": TOPIC_STOCK_EXTRACTION_PROMPT_VERSION,
            }
        return item.get("day"), list(unique_stocks.values()), item.get("topic_id"), item_key

    max_workers = max(1, int(concurrency or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {executor.submit(_work, item): item for item in items}
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
                _emit_log(
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
            _emit_log(
                f"extracted {len(companies)} companies for topic_id={topic_id}: "
                f"{_format_company_log(companies)}; concepts: {_format_stock_concepts_log(stocks)}",
                log_callback,
            )
    return daily, succeeded_item_keys, failed_items, topic_stock_extractions


def _read_existing_csv_file(output_path: str = DEFAULT_OUTPUT_PATH) -> Dict[str, Dict[str, int]]:
    daily: Dict[str, Dict[str, int]] = {}
    if not os.path.exists(output_path):
        return daily
    try:
        with open(output_path, "r", encoding="utf-8", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            for row in reader:
                day = (row.get("date") or "").strip()
                company = (row.get("company") or "").strip()
                if not day or not company:
                    continue
                try:
                    count = int(str(row.get("articles_count") or "0").strip())
                except Exception:
                    continue
                daily.setdefault(day, {})[company] = count
    except Exception:
        return {}

    total_entries = sum(sum(company_counts.values()) for company_counts in daily.values())
    log_info(f"loaded existing csv days={len(daily)} total_entries={total_entries}")
    return daily


def read_existing_csv(
    output_path: str = DEFAULT_OUTPUT_PATH,
    group_id: Optional[str] = None,
) -> Dict[str, Dict[str, int]]:
    resolved_output_path, _resolved_state_path = resolve_analysis_paths(output_path, DEFAULT_STATE_PATH, group_id)
    if should_use_db_storage(group_id):
        try:
            return load_daily_mentions_from_db(group_id=group_id)
        except Exception as exc:
            raise RuntimeError(f"read daily mentions from PostgreSQL failed: {exc}") from exc
    return _read_existing_csv_file(resolved_output_path)


def _write_csv_file(daily: Dict[str, Dict[str, int]], output_path: str = DEFAULT_OUTPUT_PATH):
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(["date", "company", "articles_count"])
        for day in sorted(daily.keys()):
            for company, count in sorted(daily[day].items(), key=lambda item: (-item[1], item[0])):
                writer.writerow([day, company, count])
    log_info(f"legacy local csv fallback written: {output_path}")


def write_csv(
    daily: Dict[str, Dict[str, int]],
    output_path: str = DEFAULT_OUTPUT_PATH,
    group_id: Optional[str] = None,
):
    resolved_output_path, _resolved_state_path = resolve_analysis_paths(output_path, DEFAULT_STATE_PATH, group_id)
    if should_use_db_storage(group_id):
        try:
            save_daily_mentions_to_db(daily, group_id=group_id)
            total_rows = sum(len(company_counts) for company_counts in daily.values())
            total_mentions = _compute_total_mentions(daily)
            log_info(
                f"db daily mentions saved: group_id={normalize_group_id(group_id) or 'GLOBAL'}, "
                f"days={len(daily)}, rows={total_rows}, mentions={total_mentions}"
            )
            return
        except Exception as exc:
            raise RuntimeError(f"save daily mentions to PostgreSQL failed: {exc}") from exc
    _write_csv_file(daily, resolved_output_path)


def _load_state_file(state_path: str = DEFAULT_STATE_PATH) -> set:
    if not os.path.exists(state_path):
        log_info("state file not found, start fresh")
        return set()
    try:
        with open(state_path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
            processed = set(data.get("processed", []))
            log_info(f"loaded state entries={len(processed)}")
            return processed
    except Exception:
        return set()


def load_state(
    state_path: str = DEFAULT_STATE_PATH,
    group_id: Optional[str] = None,
) -> set:
    _resolved_output_path, resolved_state_path = resolve_analysis_paths(DEFAULT_OUTPUT_PATH, state_path, group_id)
    if should_use_db_storage(group_id):
        try:
            return load_processed_state_from_db(group_id=group_id)
        except Exception as exc:
            raise RuntimeError(f"read processed state from PostgreSQL failed: {exc}") from exc
    return _load_state_file(resolved_state_path)


def _save_state_file(state_path: str = DEFAULT_STATE_PATH, processed_keys: Optional[Iterable[str]] = None):
    directory = os.path.dirname(state_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    payload = {"processed": sorted(list(processed_keys or set()))}
    with open(state_path, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)
    log_info(f"saved state entries={len(payload['processed'])} to {state_path}")


def save_state(
    state_path: str = DEFAULT_STATE_PATH,
    processed_keys: Optional[Iterable[str]] = None,
    group_id: Optional[str] = None,
):
    normalized_keys = set(processed_keys or set())
    _resolved_output_path, resolved_state_path = resolve_analysis_paths(DEFAULT_OUTPUT_PATH, state_path, group_id)
    if should_use_db_storage(group_id):
        try:
            save_processed_state_to_db(normalized_keys, group_id=group_id)
            return
        except Exception as exc:
            raise RuntimeError(f"save processed state to PostgreSQL failed: {exc}") from exc
    _save_state_file(resolved_state_path, normalized_keys)


def remove_daily_range(
    daily: Dict[str, Dict[str, int]],
    start_date: str,
    end_date: str,
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int]]:
    kept: Dict[str, Dict[str, int]] = {}
    removed_days = 0
    removed_rows = 0
    removed_mentions = 0
    for day, company_counts in daily.items():
        if start_date <= day <= end_date:
            removed_days += 1
            removed_rows += len(company_counts)
            removed_mentions += sum(company_counts.values())
            continue
        kept[day] = company_counts
    return kept, {
        "removed_days": removed_days,
        "removed_rows": removed_rows,
        "removed_mentions": removed_mentions,
    }


def remove_state_range(processed_keys: set, start_date: str, end_date: str) -> Tuple[set, int]:
    kept = set()
    removed = 0
    for key in processed_keys:
        day = _extract_day_from_state_key(key)
        if day and start_date <= day <= end_date:
            removed += 1
            continue
        kept.add(key)
    return kept, removed


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


def _compute_total_mentions(daily: Dict[str, Dict[str, int]]) -> int:
    return sum(sum(company_counts.values()) for company_counts in daily.values())


def get_source_topics_summary(group_id: Optional[str] = None) -> Dict[str, Any]:
    normalized_group_id = normalize_group_id(group_id)
    if not normalized_group_id:
        return {
            "topics_db_exists": None,
            "topics_count": None,
            "oldest_topic_time": None,
            "latest_topic_time": None,
        }

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), MIN(create_time), MAX(create_time) FROM topics WHERE group_id = ?",
            (int(normalized_group_id) if normalized_group_id.isdigit() else normalized_group_id,),
        )
        topics_count, oldest_topic_time, latest_topic_time = cur.fetchone()
        return {
            "topics_db_exists": True,
            "topics_count": int(topics_count or 0),
            "oldest_topic_time": oldest_topic_time,
            "latest_topic_time": latest_topic_time,
        }
    finally:
        conn.close()


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


def _color_for_name(name: str) -> str:
    seed = sum((index + 1) * ord(char) for index, char in enumerate(name))
    hue = seed % 360
    saturation = 58 + (seed % 17)
    lightness = 45 + (seed % 10)
    return f"hsl({hue}, {saturation}%, {lightness}%)"


def _select_available_date_range(
    available_dates: Sequence[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[str, str, List[str]]:
    selected_start = validate_day(start_date, "start_date") or available_dates[0]
    selected_end = validate_day(end_date, "end_date") or available_dates[-1]
    if selected_start > selected_end:
        selected_start, selected_end = selected_end, selected_start
    range_dates = [day for day in available_dates if selected_start <= day <= selected_end]
    return selected_start, selected_end, range_dates


def _empty_chart_payload(
    group_id: Optional[str],
    available_dates: Sequence[str],
    selected_start_date: Optional[str],
    selected_end_date: Optional[str],
    top_n: int,
    ranking_top_n: int,
) -> Dict[str, Any]:
    return {
        "group_id": normalize_group_id(group_id),
        "available_dates": list(available_dates),
        "selected_start_date": selected_start_date,
        "selected_end_date": selected_end_date,
        "chart_data": [],
        "series": [],
        "rankings": {},
        "date_count": 0,
        "company_count": 0,
        "total_companies_in_range": 0,
        "top_n": top_n,
        "ranking_top_n": ranking_top_n,
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
    available_dates = sorted(daily.keys())
    if not available_dates:
        return _empty_chart_payload(
            normalize_group_id(group_id),
            [],
            None,
            None,
            top_n,
            ranking_top_n,
        )

    selected_start, selected_end, range_dates = _select_available_date_range(available_dates, start_date, end_date)
    if not range_dates:
        return _empty_chart_payload(
            group_id,
            available_dates,
            selected_start,
            selected_end,
            top_n,
            ranking_top_n,
        )

    company_totals: Dict[str, int] = defaultdict(int)
    for day in range_dates:
        for company, count in daily.get(day, {}).items():
            company_totals[company] += count

    top_companies = sorted(company_totals.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    selected_companies = [company for company, _count in top_companies]
    cumulative = {company: 0 for company in selected_companies}
    chart_data: List[Dict[str, Any]] = []
    for day in range_dates:
        row: Dict[str, Any] = {"date": day}
        for company in selected_companies:
            cumulative[company] += daily.get(day, {}).get(company, 0)
            row[company] = cumulative[company]
        chart_data.append(row)

    series = [
        {
            "key": company,
            "label": company,
            "total": total,
            "color": _color_for_name(company),
        }
        for company, total in top_companies
    ]

    rankings: Dict[str, List[Dict[str, Any]]] = {}
    start_index = available_dates.index(range_dates[0])
    end_index = available_dates.index(range_dates[-1])
    for window in ranking_windows:
        from_index = max(start_index, end_index - int(window) + 1)
        totals: Dict[str, int] = defaultdict(int)
        for index in range(from_index, end_index + 1):
            day = available_dates[index]
            for company, count in daily.get(day, {}).items():
                totals[company] += count
        rankings[str(window)] = [
            {"company": company, "count": count}
            for company, count in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:ranking_top_n]
        ]

    return {
        "group_id": normalize_group_id(group_id),
        "available_dates": available_dates,
        "selected_start_date": range_dates[0],
        "selected_end_date": range_dates[-1],
        "chart_data": chart_data,
        "series": series,
        "rankings": rankings,
        "date_count": len(range_dates),
        "company_count": len(selected_companies),
        "total_companies_in_range": len(company_totals),
        "top_n": top_n,
        "ranking_top_n": ranking_top_n,
    }


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
    reset_start_date: Optional[str] = None,
    reset_end_date: Optional[str] = None,
    log_callback: LogCallback = None,
) -> Dict[str, Any]:
    ensure_configured()
    normalized_group_id = normalize_group_id(group_id)
    days = max(1, int(days))
    concurrency = max(1, int(concurrency))

    resolved_output_path, resolved_state_path = resolve_analysis_paths(output_path, state_path, normalized_group_id)
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

        existing_daily, removed_daily = remove_daily_range(existing_daily, start_day, end_day)
        processed_keys, removed_state_in_range = remove_state_range(processed_keys, start_day, end_day)
        reset_summary = {
            "start_date": start_day,
            "end_date": end_day,
            **removed_daily,
            "removed_state_keys": removed_state_in_range,
        }
        _emit_log(
            f"reset range finished: {start_day} ~ {end_day}, "
            f"removed_rows={removed_daily['removed_rows']}, "
            f"removed_mentions={removed_daily['removed_mentions']}, "
            f"removed_state_keys={removed_state_in_range}",
            log_callback,
        )
        write_csv(existing_daily, resolved_output_path, group_id=normalized_group_id)
        save_state(resolved_state_path, processed_keys, group_id=normalized_group_id)

        required_days = get_required_days_for_start_date(start_day)
        if required_days > days:
            _emit_log(
                f"scan days auto adjusted: requested={days}, required={required_days} to cover reset range",
                log_callback,
            )
            days = required_days

    runtime_ai_config = get_openai_compatible_config()
    api_key = str(runtime_ai_config.get("api_key") or "").strip()
    if not api_key:
        write_csv(existing_daily, resolved_output_path, group_id=normalized_group_id)
        save_state(resolved_state_path, processed_keys, group_id=normalized_group_id)
        _emit_log("OPENAI_API_KEY not set and config.toml [ai].api_key is empty", log_callback, level="error")
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    if normalized_group_id:
        groups = [normalized_group_id]
    else:
        groups = [str(group_id) for group_id in sorted(get_cached_local_group_ids(force_refresh=True))]
    _emit_log(f"discovered groups: {len(groups)}", log_callback)

    all_items: List[Dict[str, Any]] = []
    for group_id in groups:
        all_items.extend(read_topics_last_days(group_id, days, log_callback))

    _emit_log(f"discovered items total={len(all_items)}", log_callback)
    items_to_process = [item for item in all_items if make_item_key(item) not in processed_keys]
    _emit_log(
        f"items to process={len(items_to_process)} skipped={len(all_items) - len(items_to_process)}",
        log_callback,
    )

    checkpoint_enabled = bool(normalized_group_id and should_use_db_storage(normalized_group_id))
    checkpoint_batch_size = DEFAULT_CHECKPOINT_BATCH_SIZE
    checkpoint_daily: Dict[str, Dict[str, int]] = {}
    checkpoint_keys: Set[str] = set()
    checkpoint_extractions: List[Dict[str, Any]] = []
    checkpoint_saved_topic_stock_extractions = 0

    def flush_checkpoint(force: bool = False) -> None:
        nonlocal checkpoint_daily
        nonlocal checkpoint_keys
        nonlocal checkpoint_extractions
        nonlocal checkpoint_saved_topic_stock_extractions

        if not checkpoint_enabled or not checkpoint_keys:
            return
        if not force and len(checkpoint_keys) < checkpoint_batch_size:
            return

        result = save_recommendation_pool_checkpoint(
            daily_delta=checkpoint_daily,
            processed_keys=checkpoint_keys,
            topic_stock_extractions=checkpoint_extractions,
            group_id=normalized_group_id,
        )
        processed_keys.update(checkpoint_keys)
        checkpoint_saved_topic_stock_extractions += int(result.get("topic_stock_extractions") or 0)
        _emit_log(
            f"db checkpoint saved at {datetime.now().isoformat(timespec='seconds')}: "
            f"group_id={normalized_group_id}, daily_mentions={result.get('daily_mentions', 0)}, "
            f"topic_stock_extractions={result.get('topic_stock_extractions', 0)}, "
            f"processed_state={result.get('processed_state', 0)}",
            log_callback,
        )
        checkpoint_daily = {}
        checkpoint_keys = set()
        checkpoint_extractions = []

    def on_success(item_key: str, day: str, stocks: List[Dict[str, Any]], companies: List[str]) -> None:
        if not checkpoint_enabled:
            return
        if companies:
            day_bucket = checkpoint_daily.setdefault(day, {})
            for company in companies:
                day_bucket[company] = day_bucket.get(company, 0) + 1
        checkpoint_keys.add(item_key)
        checkpoint_extractions.extend(stocks)
        flush_checkpoint()

    new_daily, succeeded_item_keys, failed_items, topic_stock_extractions = aggregate_daily(
        items_to_process,
        api_key=api_key,
        model=model,
        api_base=api_base,
        wire_api=wire_api or str(runtime_ai_config.get("wire_api") or DEFAULT_WIRE_API),
        reasoning_effort=reasoning_effort or str(runtime_ai_config.get("reasoning_effort") or DEFAULT_REASONING_EFFORT),
        concurrency=concurrency,
        log_callback=log_callback,
        success_callback=on_success,
    )
    flush_checkpoint(force=True)

    added_mentions = 0
    for day, company_counts in new_daily.items():
        day_bucket = existing_daily.setdefault(day, {})
        for company, added_count in company_counts.items():
            day_bucket[company] = day_bucket.get(company, 0) + added_count
            added_mentions += added_count

    saved_topic_stock_extractions = 0
    if topic_stock_extractions and normalized_group_id and should_use_db_storage(normalized_group_id):
        if checkpoint_enabled:
            saved_topic_stock_extractions = checkpoint_saved_topic_stock_extractions
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
