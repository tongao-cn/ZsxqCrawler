"""AI analysis helpers for downloaded group files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from backend.core.ai_provider_config import get_openai_compatible_config
from backend.services.file_ai_content_analysis import (
    DEFAULT_FILE_ANALYSIS_API_BASE,
    DEFAULT_FILE_ANALYSIS_MODEL,
    DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    DEFAULT_FILE_ANALYSIS_WIRE_API,
    FileContentAnalysis,
    analyze_file_content,
    build_deep_summary_prompt,
    extract_file_text as _content_extract_file_text,
    extract_file_content_for_analysis,
    response_text,
    summarize_pdf_with_ai,
    summarize_text_with_ai,
    transcribe_audio_with_faster_whisper,
)
from backend.services.file_local_paths import resolve_local_file_path
from backend.storage.zsxq_file_database import ZSXQFileDatabase


def _get_file_db(group_id: str) -> ZSXQFileDatabase:
    return ZSXQFileDatabase(group_id)


def extract_file_text(path: Path) -> Tuple[str, str]:
    return _content_extract_file_text(path)


def _extract_response_text(response: Any) -> str:
    return response_text(response)


def _build_deep_summary_prompt(file_name: str) -> str:
    return build_deep_summary_prompt(file_name)


def _summarize_text_with_ai(
    text: str,
    *,
    file_name: str,
    model: str,
    api_base: str,
    wire_api: str,
    reasoning_effort: str,
) -> str:
    return summarize_text_with_ai(
        text,
        file_name=file_name,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        get_ai_config=get_openai_compatible_config,
    )


def _summarize_pdf_with_ai(
    path: Path,
    *,
    file_name: str,
    model: str,
    api_base: str,
    wire_api: str,
    reasoning_effort: str,
) -> str:
    return summarize_pdf_with_ai(
        path,
        file_name=file_name,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        get_ai_config=get_openai_compatible_config,
    )


def _transcribe_audio_with_faster_whisper(path: Path) -> str:
    return transcribe_audio_with_faster_whisper(path)


def _cached_analysis_result(existing: Optional[Dict[str, Any]], force: bool) -> Optional[Dict[str, Any]]:
    if existing and not force and existing.get("status") == "completed" and existing.get("summary"):
        return {**existing, "cached": True}
    return None


def _extract_file_content_for_analysis(path: Path) -> Tuple[str, str]:
    return extract_file_content_for_analysis(
        path,
        transcribe_audio=_transcribe_audio_with_faster_whisper,
        extract_text=extract_file_text,
    )


def _analyze_file_content(
    path: Path,
    *,
    file_name: str,
    model: str,
    api_base: str,
    wire_api: str,
    reasoning_effort: str,
) -> FileContentAnalysis:
    return analyze_file_content(
        path,
        file_name=file_name,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        extract_content=_extract_file_content_for_analysis,
        summarize_text=_summarize_text_with_ai,
        summarize_pdf=_summarize_pdf_with_ai,
    )


def analyze_group_file(
    group_id: str,
    file_id: int,
    *,
    force: bool = False,
    model: str = DEFAULT_FILE_ANALYSIS_MODEL,
    api_base: str = DEFAULT_FILE_ANALYSIS_API_BASE,
    wire_api: str = DEFAULT_FILE_ANALYSIS_WIRE_API,
    reasoning_effort: str = DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
) -> Dict[str, Any]:
    db = _get_file_db(group_id)
    file_exists = False
    try:
        existing = db.get_file_ai_analysis(file_id)
        cached_result = _cached_analysis_result(existing, force)
        if cached_result is not None:
            return cached_result

        source_record = db.get_file_analysis_source_record(file_id)
        if source_record is None:
            raise ValueError("文件不存在，请先收集文件列表")
        file_exists = True

        resolved_path = resolve_local_file_path(
            group_id,
            source_record.file_id,
            source_record.name,
            source_record.local_path,
        )
        if resolved_path is None:
            raise ValueError("本地文件不存在，请先下载该文件后再进行 AI 分析")

        analysis = _analyze_file_content(
            resolved_path,
            file_name=source_record.name,
            model=model,
            api_base=api_base,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
        )

        db.upsert_file_ai_analysis(
            file_id,
            status="completed",
            summary=analysis.summary,
            extracted_text=analysis.extracted_text,
            extracted_text_preview=analysis.extracted_text_preview,
            content_type=analysis.content_type,
            source_path=str(resolved_path),
            source_size=analysis.source_size,
            model=model,
            api_base=api_base,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
            error_message=None,
        )
        result = db.get_file_ai_analysis(file_id) or {}
        return {**result, "cached": False}
    except Exception as exc:
        if file_exists:
            db.upsert_file_ai_analysis(
                file_id,
                status="failed",
                summary=None,
                extracted_text=None,
                extracted_text_preview=None,
                content_type=None,
                source_path=None,
                source_size=None,
                model=model,
                api_base=api_base,
                wire_api=wire_api,
                reasoning_effort=reasoning_effort,
                error_message=str(exc),
            )
        raise
    finally:
        db.close()


def get_group_file_analysis(group_id: str, file_id: int) -> Optional[Dict[str, Any]]:
    db = _get_file_db(group_id)
    try:
        return db.get_file_ai_analysis(file_id)
    finally:
        db.close()
