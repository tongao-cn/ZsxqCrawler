"""Extract PDF text/Markdown with opendataloader-pdf hybrid OCR and cache it."""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, TextIO


DEFAULT_HOST = os.environ.get("PDF_TEXT_EXTRACTOR_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PDF_TEXT_EXTRACTOR_PORT", "5002"))
DEFAULT_OCR_ENGINE = os.environ.get("PDF_TEXT_EXTRACTOR_OCR_ENGINE", "rapidocr")
DEFAULT_OCR_LANG = os.environ.get("PDF_TEXT_EXTRACTOR_OCR_LANG", "chinese")
DEFAULT_DEVICE = os.environ.get("PDF_TEXT_EXTRACTOR_DEVICE", "cpu")
DEFAULT_STARTUP_TIMEOUT_SECONDS = int(os.environ.get("PDF_TEXT_EXTRACTOR_STARTUP_TIMEOUT_SECONDS", "180"))
DEFAULT_CONVERT_TIMEOUT_SECONDS = int(os.environ.get("PDF_TEXT_EXTRACTOR_CONVERT_TIMEOUT_SECONDS", "900"))
DEFAULT_MIN_TEXT_CHARS = int(os.environ.get("PDF_TEXT_EXTRACTOR_MIN_TEXT_CHARS", "50"))
DEFAULT_JAVA_BIN_DIR = Path(
    os.environ.get(
        "PDF_TEXT_EXTRACTOR_JAVA_BIN_DIR",
        r"C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot\bin",
    )
)

_SERVER_LOCK = threading.Lock()
_SERVER_PROCESS: Optional[subprocess.Popen] = None
_SERVER_LOG_PATH: Optional[Path] = None
_SERVER_LOG_HANDLE: Optional[TextIO] = None


@dataclass(frozen=True)
class PdfTextExtractionResult:
    markdown: str
    text: str
    output_dir: Path
    markdown_path: Optional[Path]
    text_path: Optional[Path]
    metadata_path: Path
    cached: bool
    duration_seconds: float
    extractor: str = "opendataloader-pdf"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _safe_stem(path: Path, limit: int = 80) -> str:
    stem = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", path.stem).strip("._-")
    return (stem[:limit].strip("._-") or "pdf")


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_pdf_text_output_dir(path: Path) -> Path:
    file_hash = _sha256_file(path)
    return (
        _project_root()
        / "output"
        / "exports"
        / "file_ai_markdown"
        / "pdf_text_extract"
        / f"{file_hash[:16]}_{_safe_stem(path)}"
    )


def _read_text(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _first_file(output_dir: Path, suffix: str) -> Optional[Path]:
    files = sorted(path for path in output_dir.rglob(f"*{suffix}") if path.is_file())
    return files[0] if files else None


def _load_cached(output_dir: Path, *, min_text_chars: int) -> Optional[PdfTextExtractionResult]:
    metadata_path = output_dir / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if metadata.get("status") != "completed":
        return None

    markdown_path = output_dir / str(metadata.get("markdown_file") or "document.md")
    text_path = output_dir / str(metadata.get("text_file") or "document.txt")
    markdown = _read_text(markdown_path if markdown_path.exists() else _first_file(output_dir, ".md"))
    text = _read_text(text_path if text_path.exists() else _first_file(output_dir, ".txt"))
    if max(len(markdown), len(text)) < min_text_chars:
        return None
    return PdfTextExtractionResult(
        markdown=markdown,
        text=text,
        output_dir=output_dir,
        markdown_path=markdown_path if markdown_path.exists() else _first_file(output_dir, ".md"),
        text_path=text_path if text_path.exists() else _first_file(output_dir, ".txt"),
        metadata_path=metadata_path,
        cached=True,
        duration_seconds=0.0,
    )


def _java_env() -> dict[str, str]:
    env = os.environ.copy()
    if DEFAULT_JAVA_BIN_DIR.exists() and str(DEFAULT_JAVA_BIN_DIR) not in env.get("PATH", ""):
        env["PATH"] = f"{DEFAULT_JAVA_BIN_DIR}{os.pathsep}{env.get('PATH', '')}"
    return env


def _uv_command(*args: str) -> list[str]:
    return ["uv", "run", *args]


def _health_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/health"


def _server_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _is_server_ready(host: str, port: int, *, timeout_seconds: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(_health_url(host, port), timeout=timeout_seconds) as response:
            return response.status == 200
    except Exception:
        return False


def _wait_for_server(
    process: subprocess.Popen,
    *,
    host: str,
    port: int,
    timeout_seconds: int,
    log_path: Path,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"opendataloader-pdf hybrid 服务启动失败，退出码 {process.returncode}，日志: {log_path}"
            )
        if _is_server_ready(host, port):
            return
        time.sleep(1)
    raise TimeoutError(f"等待 opendataloader-pdf hybrid 服务启动超时，日志: {log_path}")


def _server_log_dir() -> Path:
    log_dir = _project_root() / "output" / "exports" / "file_ai_markdown" / "pdf_text_extract_server"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def ensure_hybrid_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    ocr_engine: str = DEFAULT_OCR_ENGINE,
    ocr_lang: str = DEFAULT_OCR_LANG,
    device: str = DEFAULT_DEVICE,
    startup_timeout_seconds: int = DEFAULT_STARTUP_TIMEOUT_SECONDS,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> str:
    global _SERVER_LOG_HANDLE, _SERVER_LOG_PATH, _SERVER_PROCESS

    with _SERVER_LOCK:
        if _is_server_ready(host, port):
            return _server_url(host, port)
        if _SERVER_PROCESS is not None and _SERVER_PROCESS.poll() is None:
            _wait_for_server(
                _SERVER_PROCESS,
                host=host,
                port=port,
                timeout_seconds=startup_timeout_seconds,
                log_path=_SERVER_LOG_PATH or _server_log_dir() / "server.log",
            )
            return _server_url(host, port)

        log_path = _server_log_dir() / f"server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_file = log_path.open("w", encoding="utf-8", errors="replace")
        _SERVER_LOG_HANDLE = log_file
        command = _uv_command(
            "--with",
            "opendataloader-pdf[hybrid]",
            "opendataloader-pdf-hybrid",
            "--host",
            host,
            "--port",
            str(port),
            "--ocr-engine",
            ocr_engine,
            "--ocr-lang",
            ocr_lang,
            "--no-enrich-formula",
            "--no-enrich-picture-description",
            "--device",
            device,
        )
        _SERVER_PROCESS = popen(
            command,
            cwd=_project_root(),
            env=_java_env(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _SERVER_LOG_PATH = log_path
        _wait_for_server(
            _SERVER_PROCESS,
            host=host,
            port=port,
            timeout_seconds=startup_timeout_seconds,
            log_path=log_path,
        )
        return _server_url(host, port)


def stop_hybrid_server() -> None:
    global _SERVER_LOG_HANDLE, _SERVER_PROCESS
    with _SERVER_LOCK:
        process = _SERVER_PROCESS
        log_handle = _SERVER_LOG_HANDLE
        _SERVER_PROCESS = None
        _SERVER_LOG_HANDLE = None
    if process is not None and process.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
            )
            if log_handle is not None:
                log_handle.close()
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    if log_handle is not None:
        log_handle.close()


atexit.register(stop_hybrid_server)


def _write_metadata(metadata_path: Path, payload: dict[str, object]) -> None:
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_opendataloader_convert(
    pdf_path: Path,
    output_dir: Path,
    *,
    server_url: str,
    timeout_seconds: int,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> subprocess.CompletedProcess:
    command = _uv_command(
        "--with",
        "opendataloader-pdf",
        "opendataloader-pdf",
        "--format",
        "markdown,text,json",
        "--output-dir",
        str(output_dir),
        "--quiet",
        "--image-output",
        "off",
        "--hybrid",
        "docling-fast",
        "--hybrid-mode",
        "full",
        "--hybrid-url",
        server_url,
        str(pdf_path),
    )
    return runner(
        command,
        cwd=_project_root(),
        env=_java_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )


def extract_pdf_text_with_opendataloader(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    force: bool = False,
    min_text_chars: int = DEFAULT_MIN_TEXT_CHARS,
    convert_timeout_seconds: int = DEFAULT_CONVERT_TIMEOUT_SECONDS,
    ensure_server: Callable[[], str] = ensure_hybrid_server,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> PdfTextExtractionResult:
    source_path = Path(pdf_path)
    target_dir = Path(output_dir) if output_dir is not None else default_pdf_text_output_dir(source_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = target_dir / "metadata.json"

    if not force:
        cached = _load_cached(target_dir, min_text_chars=min_text_chars)
        if cached is not None:
            return cached

    start = time.perf_counter()
    file_hash = _sha256_file(source_path)
    try:
        server_url = ensure_server()
        completed = _run_opendataloader_convert(
            source_path,
            target_dir,
            server_url=server_url,
            timeout_seconds=convert_timeout_seconds,
            runner=runner,
        )
        duration_seconds = round(time.perf_counter() - start, 3)
        markdown_path = _first_file(target_dir, ".md")
        text_path = _first_file(target_dir, ".txt")
        json_path = _first_file(target_dir, ".json")
        markdown = _read_text(markdown_path)
        text = _read_text(text_path)
        content_chars = max(len(markdown), len(text))
        status = "completed" if completed.returncode == 0 and content_chars >= min_text_chars else "failed"
        metadata = {
            "status": status,
            "file_hash": file_hash,
            "source_path": str(source_path),
            "source_size": source_path.stat().st_size,
            "extractor": "opendataloader-pdf",
            "hybrid": "docling-fast",
            "hybrid_mode": "full",
            "ocr_engine": DEFAULT_OCR_ENGINE,
            "ocr_lang": DEFAULT_OCR_LANG,
            "duration_seconds": duration_seconds,
            "text_chars": len(text),
            "markdown_chars": len(markdown),
            "markdown_file": markdown_path.name if markdown_path else None,
            "text_file": text_path.name if text_path else None,
            "json_file": json_path.name if json_path else None,
            "created_at": _utc_now_text(),
            "returncode": completed.returncode,
            "stdout_tail": (completed.stdout or "")[-2000:],
            "stderr_tail": (completed.stderr or "")[-2000:],
        }
        _write_metadata(metadata_path, metadata)
        if status != "completed":
            detail = (completed.stderr or completed.stdout or "未生成有效文本").strip()
            raise RuntimeError(f"opendataloader-pdf 提取失败或结果过短: {detail[-1000:]}")
        return PdfTextExtractionResult(
            markdown=markdown,
            text=text,
            output_dir=target_dir,
            markdown_path=markdown_path,
            text_path=text_path,
            metadata_path=metadata_path,
            cached=False,
            duration_seconds=duration_seconds,
        )
    except Exception as exc:
        duration_seconds = round(time.perf_counter() - start, 3)
        _write_metadata(
            metadata_path,
            {
                "status": "failed",
                "file_hash": file_hash,
                "source_path": str(source_path),
                "source_size": source_path.stat().st_size if source_path.exists() else None,
                "extractor": "opendataloader-pdf",
                "hybrid": "docling-fast",
                "hybrid_mode": "full",
                "ocr_engine": DEFAULT_OCR_ENGINE,
                "ocr_lang": DEFAULT_OCR_LANG,
                "duration_seconds": duration_seconds,
                "error": str(exc),
                "created_at": _utc_now_text(),
            },
        )
        raise
