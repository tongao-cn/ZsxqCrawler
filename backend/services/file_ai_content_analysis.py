"""Content extraction and AI summarization for local group files."""

from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import sysconfig
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_model,
    get_default_wire_api,
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.services.ai_client import call_ai_text, extract_response_text
from backend.services.ai_runtime_request import build_runtime_ai_text_request


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
MAX_DIRECT_PDF_BYTES = 50 * 1024 * 1024
PDF_DIRECT_ANALYSIS_NOTE = "PDF 已作为 input_file 直接传给模型分析，未执行本地文本抽取。"
_WHISPER_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}
_WHISPER_MODEL_LOCK = threading.Lock()


@dataclass(frozen=True)
class FileContentAnalysis:
    summary: str
    extracted_text: str
    extracted_text_preview: str
    content_type: str
    source_size: int


def decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk", "utf-16"):
        try:
            return data.decode(encoding)
        except Exception:
            continue
    return data.decode("utf-8", errors="ignore")


def extract_text_from_docx(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        xml_text = archive.read("word/document.xml")
    decoded = decode_bytes(xml_text)
    fragments = re.findall(r"<w:t[^>]*>(.*?)</w:t>", decoded, flags=re.DOTALL)
    text = "\n".join(fragment.strip() for fragment in fragments if fragment and fragment.strip())
    return text


def extract_text_from_csv(path: Path) -> str:
    raw = path.read_bytes()
    decoded = decode_bytes(raw)
    reader = csv.reader(io.StringIO(decoded))
    lines = []
    for index, row in enumerate(reader):
        if index >= 200:
            break
        lines.append(" | ".join(cell.strip() for cell in row))
    return "\n".join(lines)


def extract_file_text(path: Path) -> Tuple[str, str]:
    suffix = path.suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        if suffix == ".csv":
            return extract_text_from_csv(path), f"text/{suffix.lstrip('.')}"
        if suffix == ".json":
            payload = json.loads(decode_bytes(path.read_bytes()))
            pretty = json.dumps(payload, ensure_ascii=False, indent=2)
            return pretty, "application/json"
        return decode_bytes(path.read_bytes()), f"text/{suffix.lstrip('.') or 'plain'}"

    if suffix == ".docx":
        return extract_text_from_docx(path), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if suffix == ".pdf":
        raise ValueError("PDF 分析不走本地文本抽取，请通过 input_file 直传模型")

    raise ValueError(
        f"暂不支持分析该文件类型: {suffix or '无扩展名'}。"
        "请先使用 txt/md/csv/json/docx/pdf 或 mp3 等可解析文件。"
    )


def response_text(response: Any) -> str:
    return extract_response_text(response)


def build_deep_summary_prompt(file_name: str) -> str:
    return (
        f"请深度阅读并总结文件《{file_name}》。\n\n"
        "要求：\n"
        "- 不要为了简洁省略重要信息，按材料信息量决定篇幅。\n"
        "- 尽量保留关键数据、判断、假设、时间点、公司/行业/标的名称。\n"
        "- 如果是券商研报、会议纪要、投资材料，请重点提取：\n"
        "  1. 核心结论\n"
        "  2. 主要观点和逻辑链条\n"
        "  3. 关键数据、预测、目标价、评级或情景假设\n"
        "  4. 涉及的公司、行业、产业链环节\n"
        "  5. 催化因素\n"
        "  6. 风险点和反方观点\n"
        "  7. 后续值得跟踪的问题\n"
        "- 如果材料内容很长，可以分章节/主题总结。\n"
        "- 如果原文没有的信息，不要编造。"
    )


def summarize_text_with_ai(
    text: str,
    *,
    file_name: str,
    model: str,
    api_base: str,
    wire_api: str,
    reasoning_effort: str,
    get_ai_config: Callable[[], dict[str, Any]] = get_openai_compatible_config,
) -> str:
    clipped_text = text[:MAX_TEXT_CHARS]
    messages = [
        {
            "role": "system",
            "content": (
                "你是文件内容分析助手。"
                "请基于用户提供的文件正文做深入、结构化、可执行的中文总结。"
                "如果内容明显是表格、代码或配置，请按其类型总结重点。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"{build_deep_summary_prompt(file_name)}\n\n"
                f"文件内容如下：\n{clipped_text}"
            ),
        },
    ]

    request = build_runtime_ai_text_request(
        messages,
        get_ai_config=get_ai_config,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        timeout=120,
    )
    return call_ai_text(request).strip()


def summarize_pdf_with_ai(
    path: Path,
    *,
    file_name: str,
    model: str,
    api_base: str,
    wire_api: str,
    reasoning_effort: str,
    get_ai_config: Callable[[], dict[str, Any]] = get_openai_compatible_config,
) -> str:
    if str(wire_api or "").strip().lower() != "responses":
        raise ValueError("PDF 分析默认使用 input_file 直传；当前接口不支持，请切换为 responses 接口")

    source_size = path.stat().st_size
    if source_size > MAX_DIRECT_PDF_BYTES:
        raise ValueError(
            f"PDF 文件超过 input_file 直传上限 {MAX_DIRECT_PDF_BYTES // (1024 * 1024)} MB，无法进行 AI 分析"
        )

    base64_string = base64.b64encode(path.read_bytes()).decode("utf-8")
    request = build_runtime_ai_text_request(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": file_name,
                        "file_data": f"data:application/pdf;base64,{base64_string}",
                    },
                    {
                        "type": "input_text",
                        "text": (
                            f"{build_deep_summary_prompt(file_name)}\n\n"
                            "请直接基于 PDF 页面内容分析；如果 PDF 是扫描件，也请尽量读取页面图像中的文字。"
                        ),
                    },
                ],
            }
        ],
        get_ai_config=get_ai_config,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        timeout=180,
    )
    return call_ai_text(request).strip()


def get_faster_whisper_model():
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


def transcribe_audio_with_faster_whisper(path: Path) -> str:
    model = get_faster_whisper_model()
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


def extract_file_content_for_analysis(
    path: Path,
    *,
    transcribe_audio: Callable[[Path], str] = transcribe_audio_with_faster_whisper,
    extract_text: Callable[[Path], Tuple[str, str]] = extract_file_text,
) -> Tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in AUDIO_EXTENSIONS:
        return transcribe_audio(path), f"audio/{suffix.lstrip('.')}"
    return extract_text(path)


def analyze_file_content(
    path: Path,
    *,
    file_name: str,
    model: str,
    api_base: str,
    wire_api: str,
    reasoning_effort: str,
    extract_content: Callable[[Path], Tuple[str, str]] = extract_file_content_for_analysis,
    summarize_text: Callable[..., str] = summarize_text_with_ai,
    summarize_pdf: Callable[..., str] = summarize_pdf_with_ai,
) -> FileContentAnalysis:
    if path.suffix.lower() == ".pdf":
        summary = summarize_pdf(
            path,
            file_name=file_name,
            model=model,
            api_base=api_base,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
        )
        extracted_text = PDF_DIRECT_ANALYSIS_NOTE
        content_type = "application/pdf"
    else:
        extracted_text, content_type = extract_content(path)
        if not extracted_text.strip():
            raise ValueError("文件内容为空，无法进行 AI 分析")

        summary = summarize_text(
            extracted_text,
            file_name=file_name,
            model=model,
            api_base=api_base,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
        )

    return FileContentAnalysis(
        summary=summary,
        extracted_text=extracted_text,
        extracted_text_preview=extracted_text[:PREVIEW_CHARS],
        content_type=content_type,
        source_size=path.stat().st_size,
    )
