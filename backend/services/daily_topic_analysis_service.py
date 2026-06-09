"""Daily AI reports for group topics."""

from __future__ import annotations

import base64
import json
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from openai import OpenAI

from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_model,
    get_default_wire_api,
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.core.image_cache_manager import get_image_cache_manager
from backend.services.daily_topic_analysis_store import (
    connect_topics_db,
    ensure_report_table,
    get_daily_report_row,
    parse_report_raw_json,
    upsert_report,
    write_report_file,
)
from backend.services.daily_topic_analysis_topics import (
    clip_text,
    date_bounds,
    fetch_topics_for_date,
    image_row_to_payload,
)


MAX_TOPIC_CHARS = 5000
MAX_PROMPT_CHARS = 60000
REPORT_CHUNK_PROMPT_CHARS = 45000
MAX_REPORT_CHUNK_WORKERS = 3
MAX_FINAL_CHUNK_SUMMARY_CHARS = 6000
MAX_FINAL_RETRY_CHUNK_SUMMARY_CHARS = 2500
MAX_IMAGES_PER_REPORT = 12
MAX_IMAGES_PER_TOPIC = 2
MAX_IMAGE_BYTES = 4 * 1024 * 1024
DEFAULT_COMMENTS_PER_TOPIC = 8
PROMPT_VERSION = "daily-topic-report-v1"
BJ_TZ = timezone(timedelta(hours=8))


def _log(log_callback: Optional[Callable[[str], None]], message: str) -> None:
    if log_callback:
        log_callback(message)


def _parse_report_date(value: Optional[str]) -> date:
    if not value:
        return datetime.now(BJ_TZ).date()
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError("date 必须是 YYYY-MM-DD 格式") from exc


def _date_bounds(report_date: date) -> Tuple[str, str]:
    return date_bounds(report_date)


def _clip(text: Any, limit: int) -> str:
    return clip_text(text, limit)


def _image_row_to_payload(row: Any, image_ref: str) -> Dict[str, Any]:
    return image_row_to_payload(row, image_ref)


def _connect_topics_db(group_id: str):
    return connect_topics_db(group_id)


def _ensure_report_table(conn: Any) -> None:
    return ensure_report_table(conn)


def _upsert_report(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    topic_count: int,
    model: str,
    summary_markdown: str,
    raw_json: Dict[str, Any],
    status: str,
    error: str = "",
) -> None:
    upsert_report(
        conn,
        group_id=group_id,
        report_date=report_date,
        topic_count=topic_count,
        model=model,
        prompt_version=PROMPT_VERSION,
        summary_markdown=summary_markdown,
        raw_json=raw_json,
        status=status,
        error=error,
    )


def _fetch_topics_for_date(
    conn: Any,
    *,
    group_id: str,
    report_date: date,
    comments_per_topic: int,
) -> List[Dict[str, Any]]:
    return fetch_topics_for_date(
        conn,
        group_id=group_id,
        report_date=report_date,
        comments_per_topic=comments_per_topic,
        max_topic_chars=MAX_TOPIC_CHARS,
        max_images_per_topic=MAX_IMAGES_PER_TOPIC,
    )


def _build_prompt_payload(group_id: str, report_date: str, topics: List[Dict[str, Any]]) -> str:
    payload = {
        "group_id": group_id,
        "report_date": report_date,
        "topic_count": len(topics),
        "topics": topics,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return _clip(text, MAX_PROMPT_CHARS)


def _build_prompt_payload_unclipped(group_id: str, report_date: str, topics: List[Dict[str, Any]]) -> str:
    payload = {
        "group_id": group_id,
        "report_date": report_date,
        "topic_count": len(topics),
        "topics": topics,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _split_topics_for_report_chunks(
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    *,
    max_chars: int = REPORT_CHUNK_PROMPT_CHARS,
) -> List[List[Dict[str, Any]]]:
    chunks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    for topic in topics:
        candidate = [*current, topic]
        candidate_text = _build_prompt_payload_unclipped(group_id, report_date, candidate)
        if current and len(candidate_text) > max_chars:
            chunks.append(current)
            current = [topic]
            continue
        current = candidate
    if current:
        chunks.append(current)
    return chunks


def _build_empty_report_summary(report_date: str) -> str:
    return (
        "# 每日话题分析报告\n\n"
        f"日期：{report_date}\n\n"
        "当天没有采集到话题。建议先确认当天最新数据已完成抓取，或检查群组是否确实无新增内容。\n"
    )


def _build_report_metadata(
    *,
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    report_path: str,
) -> Dict[str, Any]:
    return {
        "group_id": group_id,
        "report_date": report_date,
        "topic_count": len(topics),
        "topic_ids": [topic["topic_id"] for topic in topics],
        "image_refs": [image["image_ref"] for image in _collect_report_images(topics)],
        "report_path": report_path,
    }


def _parse_report_raw_json(value: Any) -> Dict[str, Any]:
    return parse_report_raw_json(value)


def _collect_report_images(topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    images: List[Dict[str, Any]] = []
    for topic in topics:
        for image in topic.get("images", []) or []:
            if image.get("url"):
                images.append(image)
                if len(images) >= MAX_IMAGES_PER_REPORT:
                    return images

        for comment in topic.get("comments", []) or []:
            for image in comment.get("images", []) or []:
                if image.get("url"):
                    images.append(image)
                    if len(images) >= MAX_IMAGES_PER_REPORT:
                        return images
    return images


def _build_image_content_parts(group_id: str, images: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    cache_manager = get_image_cache_manager(group_id)
    content_parts: List[Dict[str, str]] = []
    for image in images:
        url = str(image.get("url") or "").strip()
        if not url:
            continue

        success, cache_path, _error = cache_manager.download_and_cache(url, timeout=15)
        if not success or not cache_path or not cache_path.exists():
            continue
        if cache_path.stat().st_size > MAX_IMAGE_BYTES:
            continue

        mime_type = mimetypes.guess_type(str(cache_path))[0] or "image/jpeg"
        encoded = base64.b64encode(cache_path.read_bytes()).decode("ascii")
        content_parts.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{encoded}",
            }
        )
    return content_parts


def _extract_response_text(response: Any) -> str:
    text_value = getattr(response, "output_text", None)
    if text_value:
        return str(text_value)

    outputs = getattr(response, "output", []) or []
    chunks = []
    for output in outputs:
        for content in getattr(output, "content", []) or []:
            chunk_text = getattr(content, "text", None)
            if chunk_text:
                chunks.append(str(chunk_text))
    return "\n".join(chunks)


def _build_report_user_prompt(
    prompt_payload: str,
    report_date: str,
    *,
    image_refs: Optional[List[str]] = None,
) -> str:
    image_note = ""
    if image_refs:
        image_note = (
            "\n- 部分话题图片已作为附件随本请求传入；图片顺序与话题数据中的 image_ref 顺序一致。"
            "\n- 如图片内容影响判断，请在相关话题分析中结合文字与图片，不要臆测图片外的信息。"
        )

    user_prompt = (
        f"请为 {report_date} 的全部话题生成 AI 日报。\n\n"
        "请按以下结构输出：\n"
        "# 每日话题分析报告\n"
        "## 一句话结论\n"
        "## 今日核心洞察\n"
        "## 热点话题 Top 5\n"
        "## 高价值观点与问答\n"
        "## 需要跟进的机会或风险\n"
        "## 明日关注点\n"
        "## 话题索引\n\n"
        "要求：\n"
        "- 每个重点尽量引用 topic_id，方便回溯。\n"
        "- 热点综合阅读、点赞、评论和内容价值判断。\n"
        "- 如果当天话题很少，也要如实说明。"
        f"{image_note}\n"
        "- 不要输出 JSON。\n\n"
        f"话题数据：\n{prompt_payload}"
    )
    return user_prompt


def _build_chunk_summary_user_prompt(
    prompt_payload: str,
    report_date: str,
    *,
    chunk_index: int,
    chunk_count: int,
) -> str:
    return (
        f"请为 {report_date} 的第 {chunk_index}/{chunk_count} 个话题分块生成局部摘要。\n\n"
        "输出中文 Markdown，结构如下：\n"
        "## 分块核心结论\n"
        "## 重要话题与证据\n"
        "## 股票、产业链和概念线索\n"
        "## 风险与待跟进事项\n"
        "## topic_id 索引\n\n"
        "要求：\n"
        "- 只基于本分块输入，不要补充外部信息。\n"
        "- 每个重点尽量引用 topic_id。\n"
        "- 保留能支撑最终日报的高信息密度，不要写寒暄。\n\n"
        f"话题数据：\n{prompt_payload}"
    )


def _clip_chunk_summaries_for_final(chunk_summaries: List[str], limit: int) -> Tuple[List[str], bool]:
    clipped = [_clip(summary, limit) for summary in chunk_summaries]
    return clipped, any(clipped_summary != original for clipped_summary, original in zip(clipped, chunk_summaries))


def _build_final_report_user_prompt(chunk_summaries: List[str], report_date: str) -> str:
    joined = "\n\n".join(
        f"<!-- chunk {index + 1} -->\n{summary}"
        for index, summary in enumerate(chunk_summaries)
    )
    return (
        f"请基于 {report_date} 的多个分块摘要，生成最终 AI 日报。\n\n"
        "请按以下结构输出：\n"
        "# 每日话题分析报告\n"
        "## 一句话结论\n"
        "## 今日核心洞察\n"
        "## 热点话题 Top 5\n"
        "## 高价值观点与问答\n"
        "## 需要跟进的机会或风险\n"
        "## 明日关注点\n"
        "## 话题索引\n\n"
        "要求：\n"
        "- 只能基于分块摘要，不要编造未出现的信息。\n"
        "- 合并重复观点，保留 topic_id 方便回溯。\n"
        "- 不要输出 JSON。\n\n"
        f"分块摘要：\n{joined}"
    )


def _call_report_ai(
    user_prompt: str,
    *,
    group_id: str,
    image_inputs: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    runtime_ai_config = get_openai_compatible_config()
    api_key = str(runtime_ai_config.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = str(runtime_ai_config.get("model") or get_default_model())
    api_base = str(runtime_ai_config.get("base_url") or get_default_base_url())
    wire_api = str(runtime_ai_config.get("wire_api") or get_default_wire_api())
    reasoning_effort = get_summary_reasoning_effort()
    image_inputs = image_inputs or []

    messages = [
        {
            "role": "system",
            "content": (
                "你是知识星球社群日报分析助手。"
                "请只基于输入的话题数据分析，不要编造未出现的信息。"
                "输出中文 Markdown，重点给群主/运营者可执行的信息密度。"
            ),
        },
    ]

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=180)
    if wire_api.strip().lower() == "responses":
        user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
        user_content.extend(_build_image_content_parts(group_id, image_inputs))
        messages.append({"role": "user", "content": user_content})
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": reasoning_effort},
        )
        return _extract_response_text(response).strip(), model

    user_content = [{"type": "text", "text": user_prompt}]
    for image_part in _build_image_content_parts(group_id, image_inputs):
        user_content.append({"type": "image_url", "image_url": {"url": image_part["image_url"]}})
    messages.append({"role": "user", "content": user_content if len(user_content) > 1 else user_prompt})
    response = client.chat.completions.create(model=model, messages=messages, stream=False)
    return str(response.choices[0].message.content or "").strip(), model


def _generate_report_with_ai(
    prompt_payload: str,
    report_date: str,
    *,
    group_id: str,
    image_inputs: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    image_refs = [str(image.get("image_ref") or "") for image in image_inputs or [] if image.get("image_ref")]
    return _call_report_ai(
        _build_report_user_prompt(prompt_payload, report_date, image_refs=image_refs),
        group_id=group_id,
        image_inputs=image_inputs,
    )


def _generate_chunk_summary_with_ai(
    prompt_payload: str,
    report_date: str,
    *,
    group_id: str,
    chunk_index: int,
    chunk_count: int,
) -> Tuple[str, str]:
    return _call_report_ai(
        _build_chunk_summary_user_prompt(
            prompt_payload,
            report_date,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
        ),
        group_id=group_id,
        image_inputs=[],
    )


def _generate_final_report_from_chunks_with_ai(
    chunk_summaries: List[str],
    report_date: str,
    *,
    group_id: str,
) -> Tuple[str, str]:
    clipped_summaries, _clipped = _clip_chunk_summaries_for_final(chunk_summaries, MAX_FINAL_CHUNK_SUMMARY_CHARS)
    return _call_report_ai(
        _build_final_report_user_prompt(clipped_summaries, report_date),
        group_id=group_id,
        image_inputs=[],
    )


def _generate_final_report_from_chunks_with_retry(
    chunk_summaries: List[str],
    report_date: str,
    *,
    group_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str, bool, bool]:
    clipped_summaries, clipped = _clip_chunk_summaries_for_final(chunk_summaries, MAX_FINAL_CHUNK_SUMMARY_CHARS)
    try:
        summary, model = _call_report_ai(
            _build_final_report_user_prompt(clipped_summaries, report_date),
            group_id=group_id,
            image_inputs=[],
        )
        return summary, model, clipped, False
    except Exception as exc:
        retry_summaries, retry_clipped = _clip_chunk_summaries_for_final(
            chunk_summaries,
            MAX_FINAL_RETRY_CHUNK_SUMMARY_CHARS,
        )
        _log(log_callback, f"⚠️ 合并分块摘要失败，改用更短摘要重试: {exc}")
        summary, model = _call_report_ai(
            _build_final_report_user_prompt(retry_summaries, report_date),
            group_id=group_id,
            image_inputs=[],
        )
        return summary, model, clipped or retry_clipped, True


def _generate_chunk_summaries_concurrently(
    chunks: List[List[Dict[str, Any]]],
    report_date: str,
    *,
    group_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[List[str], str, int]:
    chunk_summaries = [""] * len(chunks)
    models = [""] * len(chunks)
    max_workers = min(MAX_REPORT_CHUNK_WORKERS, len(chunks))
    _log(log_callback, f"⚙️ 并发生成分块摘要，并发度 {max_workers}")

    def run_chunk(index: int, chunk_topics: List[Dict[str, Any]]) -> Tuple[int, str, str]:
        prompt_payload = _build_prompt_payload_unclipped(group_id, report_date, chunk_topics)
        chunk_summary, chunk_model = _generate_chunk_summary_with_ai(
            prompt_payload,
            report_date,
            group_id=group_id,
            chunk_index=index + 1,
            chunk_count=len(chunks),
        )
        return index, chunk_summary, chunk_model

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(run_chunk, index, chunk_topics) for index, chunk_topics in enumerate(chunks)]
        for future in as_completed(futures):
            index, chunk_summary, chunk_model = future.result()
            if not chunk_summary:
                raise RuntimeError(f"AI 返回分块摘要为空: {index + 1}/{len(chunks)}")
            chunk_summaries[index] = chunk_summary
            models[index] = chunk_model
            _log(log_callback, f"✅ 日报分块摘要完成 {index + 1}/{len(chunks)}，话题 {len(chunks[index])} 个")

    model = next((item for item in reversed(models) if item), "")
    return chunk_summaries, model, max_workers


def _write_report_file(group_id: str, report_date: str, summary_markdown: str) -> str:
    return write_report_file(group_id, report_date, summary_markdown)


def _generate_daily_report_summary(
    *,
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    full_prompt_payload = _build_prompt_payload_unclipped(group_id, report_date, topics)
    if len(full_prompt_payload) <= MAX_PROMPT_CHARS:
        image_inputs = _collect_report_images(topics)
        if image_inputs:
            _log(log_callback, f"🖼️ 将随日报传入 {len(image_inputs)} 张话题图片附件")
        _log(log_callback, "🤖 正在调用 AI 生成日报...")
        try:
            summary, model = _generate_report_with_ai(
                full_prompt_payload,
                report_date,
                group_id=group_id,
                image_inputs=image_inputs,
            )
            image_retry_without_images = False
        except Exception as exc:
            if not image_inputs:
                raise
            _log(log_callback, f"⚠️ 带图片的 AI 请求失败，改用纯文本重试: {exc}")
            summary, model = _generate_report_with_ai(
                full_prompt_payload,
                report_date,
                group_id=group_id,
                image_inputs=[],
            )
            image_retry_without_images = True
        return summary, model, {
            "generation_mode": "single",
            "prompt_chars": len(full_prompt_payload),
            "chunk_count": 1,
            "image_count": len(image_inputs),
            "image_retry_without_images": image_retry_without_images,
        }

    chunks = _split_topics_for_report_chunks(group_id, report_date, topics)
    _log(log_callback, f"🧩 日报输入较长，拆分为 {len(chunks)} 个分块摘要后汇总")
    _log(log_callback, "🛡️ 最终合并启用短摘要重试保护")
    chunk_summaries, model, chunk_workers = _generate_chunk_summaries_concurrently(
        chunks,
        report_date,
        group_id=group_id,
        log_callback=log_callback,
    )

    _log(log_callback, "🤖 正在合并分块摘要生成最终日报...")
    summary, final_model, final_summaries_clipped, final_retry_short = _generate_final_report_from_chunks_with_retry(
        chunk_summaries,
        report_date,
        group_id=group_id,
        log_callback=log_callback,
    )
    return summary, final_model or model, {
        "generation_mode": "chunked",
        "prompt_chars": len(full_prompt_payload),
        "chunk_count": len(chunks),
        "chunk_topic_counts": [len(chunk) for chunk in chunks],
        "chunk_workers": chunk_workers,
        "final_summaries_clipped": final_summaries_clipped,
        "final_retry_short": final_retry_short,
    }


def analyze_daily_topics(
    group_id: str,
    report_date: Optional[str] = None,
    *,
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Generate and persist one daily AI topic report."""
    parsed_date = _parse_report_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = _connect_topics_db(group_id)

    try:
        _log(log_callback, f"📚 读取 {report_date_text} 的话题数据...")
        topics = _fetch_topics_for_date(
            conn,
            group_id=group_id,
            report_date=parsed_date,
            comments_per_topic=comments_per_topic,
        )
        topic_count = len(topics)
        _log(log_callback, f"📊 当天话题数量: {topic_count}")

        if topic_count == 0:
            summary = _build_empty_report_summary(report_date_text)
            model = ""
            generation_meta = {"generation_mode": "empty", "chunk_count": 0}
        else:
            summary, model, generation_meta = _generate_daily_report_summary(
                group_id=group_id,
                report_date=report_date_text,
                topics=topics,
                log_callback=log_callback,
            )
            if not summary:
                raise RuntimeError("AI 返回内容为空")

        report_path = _write_report_file(group_id, report_date_text, summary)
        raw_json = _build_report_metadata(
            group_id=group_id,
            report_date=report_date_text,
            topics=topics,
            report_path=report_path,
        )
        raw_json.update(generation_meta)
        _upsert_report(
            conn,
            group_id=group_id,
            report_date=report_date_text,
            topic_count=topic_count,
            model=model,
            summary_markdown=summary,
            raw_json=raw_json,
            status="completed",
        )
        _log(log_callback, f"✅ 日报已生成: {report_path}")
        return {
            "group_id": group_id,
            "report_date": report_date_text,
            "topic_count": topic_count,
            "model": model,
            "summary_markdown": summary,
            "report_path": report_path,
        }
    except Exception as exc:
        _upsert_report(
            conn,
            group_id=group_id,
            report_date=report_date_text,
            topic_count=0,
            model=str(get_openai_compatible_config().get("model") or ""),
            summary_markdown="",
            raw_json={"group_id": group_id, "report_date": report_date_text},
            status="failed",
            error=str(exc),
        )
        raise
    finally:
        conn.close()


def get_daily_report(group_id: str, report_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    parsed_date = _parse_report_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = _connect_topics_db(group_id)
    try:
        return get_daily_report_row(conn, group_id=group_id, report_date=report_date_text)
    finally:
        conn.close()
