"""Daily topic report generation policy."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.services.daily_topic_analysis_ai import call_report_ai
from backend.services.daily_topic_analysis_prompts import (
    build_chunk_summary_user_prompt,
    build_final_report_user_prompt,
    build_prompt_payload_unclipped,
    build_report_user_prompt,
    clip_chunk_summaries_for_final,
    collect_report_images,
    split_topics_for_report_chunks,
)


MAX_PROMPT_CHARS = 60000
REPORT_CHUNK_PROMPT_CHARS = 45000
MAX_REPORT_CHUNK_WORKERS = 3
MAX_FINAL_CHUNK_SUMMARY_CHARS = 6000
MAX_FINAL_RETRY_CHUNK_SUMMARY_CHARS = 2500
MAX_IMAGES_PER_REPORT = 12
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def _log(log_callback: Optional[Callable[[str], None]], message: str) -> None:
    if log_callback:
        log_callback(message)


def generate_report_with_ai(
    prompt_payload: str,
    report_date: str,
    *,
    group_id: str,
    image_inputs: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    image_refs = [str(image.get("image_ref") or "") for image in image_inputs or [] if image.get("image_ref")]
    return call_report_ai(
        build_report_user_prompt(prompt_payload, report_date, image_refs=image_refs),
        group_id=group_id,
        image_inputs=image_inputs,
        max_image_bytes=MAX_IMAGE_BYTES,
    )


def generate_chunk_summary_with_ai(
    prompt_payload: str,
    report_date: str,
    *,
    group_id: str,
    chunk_index: int,
    chunk_count: int,
) -> Tuple[str, str]:
    return call_report_ai(
        build_chunk_summary_user_prompt(
            prompt_payload,
            report_date,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
        ),
        group_id=group_id,
        image_inputs=[],
        max_image_bytes=MAX_IMAGE_BYTES,
    )


def generate_final_report_from_chunks_with_ai(
    chunk_summaries: List[str],
    report_date: str,
    *,
    group_id: str,
) -> Tuple[str, str]:
    clipped_summaries, _clipped = clip_chunk_summaries_for_final(chunk_summaries, MAX_FINAL_CHUNK_SUMMARY_CHARS)
    return call_report_ai(
        build_final_report_user_prompt(clipped_summaries, report_date),
        group_id=group_id,
        image_inputs=[],
        max_image_bytes=MAX_IMAGE_BYTES,
    )


def generate_final_report_from_chunks_with_retry(
    chunk_summaries: List[str],
    report_date: str,
    *,
    group_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str, bool, bool]:
    clipped_summaries, clipped = clip_chunk_summaries_for_final(chunk_summaries, MAX_FINAL_CHUNK_SUMMARY_CHARS)
    try:
        summary, model = call_report_ai(
            build_final_report_user_prompt(clipped_summaries, report_date),
            group_id=group_id,
            image_inputs=[],
            max_image_bytes=MAX_IMAGE_BYTES,
        )
        return summary, model, clipped, False
    except Exception as exc:
        retry_summaries, retry_clipped = clip_chunk_summaries_for_final(
            chunk_summaries,
            MAX_FINAL_RETRY_CHUNK_SUMMARY_CHARS,
        )
        _log(log_callback, f"⚠️ 合并分块摘要失败，改用更短摘要重试: {exc}")
        summary, model = call_report_ai(
            build_final_report_user_prompt(retry_summaries, report_date),
            group_id=group_id,
            image_inputs=[],
            max_image_bytes=MAX_IMAGE_BYTES,
        )
        return summary, model, clipped or retry_clipped, True


def generate_chunk_summaries_concurrently(
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
        prompt_payload = build_prompt_payload_unclipped(group_id, report_date, chunk_topics)
        chunk_summary, chunk_model = generate_chunk_summary_with_ai(
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


def generate_daily_report_summary(
    *,
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    full_prompt_payload: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    if full_prompt_payload is None:
        full_prompt_payload = build_prompt_payload_unclipped(group_id, report_date, topics)
    if len(full_prompt_payload) <= MAX_PROMPT_CHARS:
        image_inputs = collect_report_images(topics, max_images_per_report=MAX_IMAGES_PER_REPORT)
        if image_inputs:
            _log(log_callback, f"🖼️ 将随日报传入 {len(image_inputs)} 张话题图片附件")
        _log(log_callback, "🤖 正在调用 AI 生成日报...")
        try:
            summary, model = generate_report_with_ai(
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
            summary, model = generate_report_with_ai(
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

    chunks = split_topics_for_report_chunks(
        group_id,
        report_date,
        topics,
        max_chars=REPORT_CHUNK_PROMPT_CHARS,
    )
    _log(log_callback, f"🧩 日报输入较长，拆分为 {len(chunks)} 个分块摘要后汇总")
    _log(log_callback, "🛡️ 最终合并启用短摘要重试保护")
    chunk_summaries, model, chunk_workers = generate_chunk_summaries_concurrently(
        chunks,
        report_date,
        group_id=group_id,
        log_callback=log_callback,
    )

    _log(log_callback, "🤖 正在合并分块摘要生成最终日报...")
    summary, final_model, final_summaries_clipped, final_retry_short = generate_final_report_from_chunks_with_retry(
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
