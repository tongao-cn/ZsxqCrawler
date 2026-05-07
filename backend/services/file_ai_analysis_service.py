"""AI analysis helpers for downloaded group files."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sysconfig
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from openai import OpenAI
from pypdf import PdfReader

from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_model,
    get_default_wire_api,
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.core.db_path_manager import get_db_path_manager
from backend.storage.zsxq_file_database import ZSXQFileDatabase


_CUDA_DLL_DIRECTORY_HANDLES: list[Any] = []
_CUDA_DLL_DIRECTORIES_ADDED: set[str] = set()


def _add_cuda_dll_directories() -> None:
    if os.name != "nt":
        return

    site_packages = Path(sysconfig.get_paths().get("purelib") or "")
    for directory in (
        site_packages / "nvidia" / "cublas" / "bin",
        site_packages / "nvidia" / "cuda_nvrtc" / "bin",
        site_packages / "ctranslate2",
    ):
        if directory.exists():
            directory_text = str(directory)
            if directory_text not in os.environ.get("PATH", ""):
                os.environ["PATH"] = f"{directory_text}{os.pathsep}{os.environ.get('PATH', '')}"
            if directory_text not in _CUDA_DLL_DIRECTORIES_ADDED:
                _CUDA_DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(directory_text))
                _CUDA_DLL_DIRECTORIES_ADDED.add(directory_text)


def _detect_faster_whisper_device() -> str:
    configured_device = os.environ.get("FASTER_WHISPER_DEVICE", "").strip()
    if configured_device:
        return configured_device

    _add_cuda_dll_directories()
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


DEFAULT_FILE_ANALYSIS_MODEL = get_default_model()
DEFAULT_FILE_ANALYSIS_API_BASE = get_default_base_url()
DEFAULT_FILE_ANALYSIS_WIRE_API = get_default_wire_api()
DEFAULT_FILE_ANALYSIS_REASONING_EFFORT = get_summary_reasoning_effort()
DEFAULT_FASTER_WHISPER_MODEL = os.environ.get("FASTER_WHISPER_MODEL", "medium")
FASTER_WHISPER_DEVICE_CONFIGURED = bool(os.environ.get("FASTER_WHISPER_DEVICE", "").strip())
DEFAULT_FASTER_WHISPER_DEVICE = _detect_faster_whisper_device()
DEFAULT_FASTER_WHISPER_COMPUTE_TYPE = os.environ.get(
    "FASTER_WHISPER_COMPUTE_TYPE",
    "float16" if DEFAULT_FASTER_WHISPER_DEVICE == "cuda" else "int8",
)
DEFAULT_FASTER_WHISPER_RETRIES = max(1, int(os.environ.get("FASTER_WHISPER_RETRIES", "3")))
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".html", ".htm", ".css", ".xml", ".yml", ".yaml", ".ini", ".toml", ".sql",
    ".java", ".go", ".rs", ".c", ".cpp", ".h", ".hpp", ".sh", ".bat",
}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mpeg", ".mpga", ".webm"}
MAX_TEXT_CHARS = 30000
PREVIEW_CHARS = 4000
_WHISPER_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}
_WHISPER_MODEL_LOCK = threading.Lock()


def _safe_filename(file_name: str, fallback_file_id: int) -> str:
    safe_filename = "".join(c for c in str(file_name or "") if c.isalnum() or c in "._-（）()[]{} ")
    safe_filename = safe_filename.strip()
    return safe_filename or f"file_{fallback_file_id}"


def _get_file_db(group_id: str) -> ZSXQFileDatabase:
    return ZSXQFileDatabase(group_id)


def resolve_local_file_path(group_id: str, file_id: int, file_name: str, local_path: Optional[str]) -> Optional[Path]:
    candidates = []
    if local_path:
        candidates.append(Path(local_path))

    path_manager = get_db_path_manager()
    group_dir = Path(path_manager.get_group_dir(group_id))
    candidates.append(group_dir / "downloads" / _safe_filename(file_name, file_id))

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


def _decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk", "utf-16"):
        try:
            return data.decode(encoding)
        except Exception:
            continue
    return data.decode("utf-8", errors="ignore")


def _extract_text_from_docx(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        xml_text = archive.read("word/document.xml")
    decoded = _decode_bytes(xml_text)
    fragments = re.findall(r"<w:t[^>]*>(.*?)</w:t>", decoded, flags=re.DOTALL)
    text = "\n".join(fragment.strip() for fragment in fragments if fragment and fragment.strip())
    return text


def _extract_text_from_csv(path: Path) -> str:
    raw = path.read_bytes()
    decoded = _decode_bytes(raw)
    reader = csv.reader(io.StringIO(decoded))
    lines = []
    for index, row in enumerate(reader):
        if index >= 200:
            break
        lines.append(" | ".join(cell.strip() for cell in row))
    return "\n".join(lines)


def _extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)


def extract_file_text(path: Path) -> Tuple[str, str]:
    suffix = path.suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        if suffix == ".csv":
            return _extract_text_from_csv(path), f"text/{suffix.lstrip('.')}"
        if suffix == ".json":
            payload = json.loads(_decode_bytes(path.read_bytes()))
            pretty = json.dumps(payload, ensure_ascii=False, indent=2)
            return pretty, "application/json"
        return _decode_bytes(path.read_bytes()), f"text/{suffix.lstrip('.') or 'plain'}"

    if suffix == ".docx":
        return _extract_text_from_docx(path), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if suffix == ".pdf":
        return _extract_text_from_pdf(path), "application/pdf"

    raise ValueError(
        f"暂不支持分析该文件类型: {suffix or '无扩展名'}。"
        "请先使用 txt/md/csv/json/docx/pdf 或 mp3 等可解析文件。"
    )


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


def _summarize_text_with_ai(
    text: str,
    *,
    file_name: str,
    model: str,
    api_base: str,
    wire_api: str,
    reasoning_effort: str,
) -> str:
    runtime_ai_config = get_openai_compatible_config()
    api_key = str(runtime_ai_config.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    clipped_text = text[:MAX_TEXT_CHARS]
    messages = [
        {
            "role": "system",
            "content": (
                "你是文件内容分析助手。"
                "请基于用户提供的文件正文做简洁、结构化、可执行的中文总结。"
                "如果内容明显是表格、代码或配置，请按其类型总结重点。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请分析文件《{file_name}》的内容，并输出：\n"
                "1. 一句话结论\n"
                "2. 核心要点（3-8条）\n"
                "3. 如果是研究/资料文件，补充可能值得关注的风险或后续动作\n\n"
                f"文件内容如下：\n{clipped_text}"
            ),
        },
    ]

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=120)
    if str(wire_api or "").strip().lower() == "responses":
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": reasoning_effort},
        )
        return _extract_response_text(response).strip()

    response = client.chat.completions.create(model=model, messages=messages, stream=False)
    return str(response.choices[0].message.content or "").strip()


def _get_faster_whisper_model():
    _add_cuda_dll_directories()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("缺少 faster-whisper 依赖，请先安装后再运行音频分析") from exc

    cache_key = (
        DEFAULT_FASTER_WHISPER_MODEL,
        DEFAULT_FASTER_WHISPER_DEVICE,
        DEFAULT_FASTER_WHISPER_COMPUTE_TYPE,
    )
    cached_model = _WHISPER_MODEL_CACHE.get(cache_key)
    if cached_model is not None:
        return cached_model

    with _WHISPER_MODEL_LOCK:
        cached_model = _WHISPER_MODEL_CACHE.get(cache_key)
        if cached_model is not None:
            return cached_model

        try:
            model = WhisperModel(
                DEFAULT_FASTER_WHISPER_MODEL,
                device=DEFAULT_FASTER_WHISPER_DEVICE,
                compute_type=DEFAULT_FASTER_WHISPER_COMPUTE_TYPE,
            )
        except Exception as exc:
            if DEFAULT_FASTER_WHISPER_DEVICE == "cuda" and not FASTER_WHISPER_DEVICE_CONFIGURED:
                try:
                    fallback_key = (DEFAULT_FASTER_WHISPER_MODEL, "cpu", "int8")
                    model = WhisperModel(DEFAULT_FASTER_WHISPER_MODEL, device="cpu", compute_type="int8")
                    _WHISPER_MODEL_CACHE[fallback_key] = model
                    return model
                except Exception:
                    pass
            raise RuntimeError(
                f"faster-whisper 模型加载失败（model={DEFAULT_FASTER_WHISPER_MODEL}）。"
                f" 如果是首次运行，通常表示本机无法从 HuggingFace 拉取模型；"
                f" 请检查网络或先手动下载模型缓存。原始错误: {exc}"
            ) from exc
        _WHISPER_MODEL_CACHE[cache_key] = model
        return model


def _transcribe_audio_with_faster_whisper(path: Path) -> str:
    model = _get_faster_whisper_model()
    last_error: Optional[Exception] = None
    for attempt in range(1, DEFAULT_FASTER_WHISPER_RETRIES + 1):
        try:
            segments, _info = model.transcribe(str(path), vad_filter=True, beam_size=5)
            text_chunks = []
            for segment in segments:
                segment_text = str(getattr(segment, "text", "") or "").strip()
                if segment_text:
                    text_chunks.append(segment_text)

            transcript = "\n".join(text_chunks).strip()
            if transcript:
                return transcript
            raise RuntimeError("未识别到有效语音内容")
        except Exception as exc:
            last_error = exc
            if attempt < DEFAULT_FASTER_WHISPER_RETRIES:
                time.sleep(min(6, attempt * 2))
                continue

    raise RuntimeError(
        f"音频转录失败（已重试 {DEFAULT_FASTER_WHISPER_RETRIES} 次）: {last_error}. "
        f"请确认音频文件未损坏，且当前机器有足够内存。"
    ) from last_error


def _cached_analysis_result(existing: Optional[Dict[str, Any]], force: bool) -> Optional[Dict[str, Any]]:
    if existing and not force and existing.get("status") == "completed" and existing.get("summary"):
        return {**existing, "cached": True}
    return None


def _extract_file_content_for_analysis(path: Path) -> Tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in AUDIO_EXTENSIONS:
        return _transcribe_audio_with_faster_whisper(path), f"audio/{suffix.lstrip('.')}"
    return extract_file_text(path)


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

        db.cursor.execute(
            """
            SELECT file_id, name, size, download_status, local_path
            FROM files
            WHERE file_id = ?
            """,
            (file_id,),
        )
        row = db.cursor.fetchone()
        if not row:
            raise ValueError("文件不存在，请先收集文件列表")
        file_exists = True

        resolved_path = resolve_local_file_path(group_id, int(row[0]), str(row[1] or ""), row[4])
        if resolved_path is None:
            raise ValueError("本地文件不存在，请先下载该文件后再进行 AI 分析")

        extracted_text, content_type = _extract_file_content_for_analysis(resolved_path)
        if not extracted_text.strip():
            raise ValueError("文件内容为空，无法进行 AI 分析")

        summary = _summarize_text_with_ai(
            extracted_text,
            file_name=str(row[1] or f"file_{file_id}"),
            model=model,
            api_base=api_base,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
        )

        preview = extracted_text[:PREVIEW_CHARS]
        db.upsert_file_ai_analysis(
            file_id,
            status="completed",
            summary=summary,
            extracted_text=extracted_text,
            extracted_text_preview=preview,
            content_type=content_type,
            source_path=str(resolved_path),
            source_size=resolved_path.stat().st_size,
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
