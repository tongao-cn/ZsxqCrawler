"""Daily AI reports for group topics."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.core.ai_provider_config import get_openai_compatible_config
from backend.services.daily_topic_analysis_ai import (
    build_image_content_parts,
    call_report_ai,
    extract_response_text,
)
from backend.services.daily_topic_analysis_prompts import (
    build_chunk_summary_user_prompt,
    build_empty_report_summary,
    build_final_report_user_prompt,
    build_prompt_payload_unclipped,
    build_report_metadata,
    build_report_user_prompt,
    clip_chunk_summaries_for_final,
    collect_report_images,
    split_topics_for_report_chunks,
)
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
    image_row_to_payload,
)
from backend.services.daily_topic_report_generation import (
    MAX_FINAL_CHUNK_SUMMARY_CHARS,
    MAX_FINAL_RETRY_CHUNK_SUMMARY_CHARS,
    MAX_IMAGE_BYTES,
    MAX_IMAGES_PER_REPORT,
    MAX_PROMPT_CHARS,
    MAX_REPORT_CHUNK_WORKERS,
    REPORT_CHUNK_PROMPT_CHARS,
    generate_chunk_summaries_concurrently as _generate_chunk_summaries_concurrently_impl,
    generate_chunk_summary_with_ai as _generate_chunk_summary_with_ai_impl,
    generate_daily_report_summary as _generate_daily_report_summary_impl,
    generate_final_report_from_chunks_with_ai as _generate_final_report_from_chunks_with_ai_impl,
    generate_final_report_from_chunks_with_retry as _generate_final_report_from_chunks_with_retry_impl,
    generate_report_with_ai as _generate_report_with_ai_impl,
)
from backend.services.topic_material import (
    DailyTopicMaterialSnapshot,
    load_daily_topic_material,
    parse_topic_material_date,
)


MAX_TOPIC_CHARS = 5000
MAX_IMAGES_PER_TOPIC = 2
DEFAULT_COMMENTS_PER_TOPIC = 8
PROMPT_VERSION = "daily-topic-report-v1"


def _log(log_callback: Optional[Callable[[str], None]], message: str) -> None:
    if log_callback:
        log_callback(message)


def _parse_report_date(value: Optional[str]) -> date:
    return parse_topic_material_date(value)


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


def _load_daily_topic_material(
    group_id: str,
    *,
    report_date: date,
    comments_per_topic: int,
) -> DailyTopicMaterialSnapshot:
    return load_daily_topic_material(
        group_id,
        report_date=report_date,
        comments_per_topic=comments_per_topic,
        max_topic_chars=MAX_TOPIC_CHARS,
        max_images_per_topic=MAX_IMAGES_PER_TOPIC,
        max_prompt_chars=MAX_PROMPT_CHARS,
    )


def _build_prompt_payload_unclipped(group_id: str, report_date: str, topics: List[Dict[str, Any]]) -> str:
    return build_prompt_payload_unclipped(group_id, report_date, topics)


def _split_topics_for_report_chunks(
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    *,
    max_chars: int = REPORT_CHUNK_PROMPT_CHARS,
) -> List[List[Dict[str, Any]]]:
    return split_topics_for_report_chunks(group_id, report_date, topics, max_chars=max_chars)


def _build_empty_report_summary(report_date: str) -> str:
    return build_empty_report_summary(report_date)


def _build_report_metadata(
    *,
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    report_path: str,
) -> Dict[str, Any]:
    return build_report_metadata(
        group_id=group_id,
        report_date=report_date,
        topics=topics,
        report_path=report_path,
        max_images_per_report=MAX_IMAGES_PER_REPORT,
    )


def _parse_report_raw_json(value: Any) -> Dict[str, Any]:
    return parse_report_raw_json(value)


def _collect_report_images(topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return collect_report_images(topics, max_images_per_report=MAX_IMAGES_PER_REPORT)


def _build_image_content_parts(group_id: str, images: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return build_image_content_parts(group_id, images, max_image_bytes=MAX_IMAGE_BYTES)


def _extract_response_text(response: Any) -> str:
    return extract_response_text(response)


def _build_report_user_prompt(
    prompt_payload: str,
    report_date: str,
    *,
    image_refs: Optional[List[str]] = None,
) -> str:
    return build_report_user_prompt(prompt_payload, report_date, image_refs=image_refs)


def _build_chunk_summary_user_prompt(
    prompt_payload: str,
    report_date: str,
    *,
    chunk_index: int,
    chunk_count: int,
) -> str:
    return build_chunk_summary_user_prompt(
        prompt_payload,
        report_date,
        chunk_index=chunk_index,
        chunk_count=chunk_count,
    )


def _clip_chunk_summaries_for_final(chunk_summaries: List[str], limit: int) -> Tuple[List[str], bool]:
    return clip_chunk_summaries_for_final(chunk_summaries, limit)


def _build_final_report_user_prompt(chunk_summaries: List[str], report_date: str) -> str:
    return build_final_report_user_prompt(chunk_summaries, report_date)


def _call_report_ai(
    user_prompt: str,
    *,
    group_id: str,
    image_inputs: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    return call_report_ai(
        user_prompt,
        group_id=group_id,
        image_inputs=image_inputs,
        max_image_bytes=MAX_IMAGE_BYTES,
    )


def _generate_report_with_ai(
    prompt_payload: str,
    report_date: str,
    *,
    group_id: str,
    image_inputs: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    return _generate_report_with_ai_impl(
        prompt_payload,
        report_date,
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
    return _generate_chunk_summary_with_ai_impl(
        prompt_payload,
        report_date,
        group_id=group_id,
        chunk_index=chunk_index,
        chunk_count=chunk_count,
    )


def _generate_final_report_from_chunks_with_ai(
    chunk_summaries: List[str],
    report_date: str,
    *,
    group_id: str,
) -> Tuple[str, str]:
    return _generate_final_report_from_chunks_with_ai_impl(
        chunk_summaries,
        report_date,
        group_id=group_id,
    )


def _generate_final_report_from_chunks_with_retry(
    chunk_summaries: List[str],
    report_date: str,
    *,
    group_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str, bool, bool]:
    return _generate_final_report_from_chunks_with_retry_impl(
        chunk_summaries,
        report_date,
        group_id=group_id,
        log_callback=log_callback,
    )


def _generate_chunk_summaries_concurrently(
    chunks: List[List[Dict[str, Any]]],
    report_date: str,
    *,
    group_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[List[str], str, int]:
    return _generate_chunk_summaries_concurrently_impl(
        chunks,
        report_date,
        group_id=group_id,
        log_callback=log_callback,
    )


def _write_report_file(group_id: str, report_date: str, summary_markdown: str) -> str:
    return write_report_file(group_id, report_date, summary_markdown)


def _generate_daily_report_summary(
    *,
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    full_prompt_payload: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    return _generate_daily_report_summary_impl(
        group_id=group_id,
        report_date=report_date,
        topics=topics,
        full_prompt_payload=full_prompt_payload,
        log_callback=log_callback,
    )


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
        material = _load_daily_topic_material(
            group_id,
            report_date=parsed_date,
            comments_per_topic=comments_per_topic,
        )
        topics = material.topics
        topic_count = material.topic_count
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
                full_prompt_payload=material.prompt_payload_unclipped,
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
