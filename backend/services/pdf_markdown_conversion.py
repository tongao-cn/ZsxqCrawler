"""Convert PDF pages to Markdown through rendered page images."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from backend.core.ai_provider_config import get_openai_compatible_config
from backend.services.ai_client import extract_response_text


DEFAULT_PDF_MARKDOWN_MODEL = "gpt-5.4-mini"
DEFAULT_RENDER_DPI = 300
DEFAULT_IMAGE_FORMAT = "jpg"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_PDF_MARKDOWN_REASONING_EFFORT = "low"


@dataclass(frozen=True)
class PdfMarkdownPageResult:
    page_number: int
    status: str
    markdown: str = ""
    error: str = ""
    image_path: Optional[Path] = None
    markdown_path: Optional[Path] = None
    cached: bool = False


@dataclass(frozen=True)
class PdfMarkdownConversionResult:
    markdown: str
    pages: list[PdfMarkdownPageResult]
    output_dir: Path
    combined_path: Path
    index_path: Path


def normalize_page_range(
    total_pages: int, *, start_page: int = 1, end_page: Optional[int] = None
) -> tuple[int, int]:
    if total_pages < 1:
        raise ValueError("PDF must contain at least one page")
    if start_page < 1:
        raise ValueError("start_page must be >= 1")

    normalized_end = total_pages if end_page is None or end_page == 0 else int(end_page)
    if normalized_end > total_pages:
        raise ValueError("end_page cannot exceed total page count")
    if normalized_end < start_page:
        raise ValueError("end_page must be >= start_page")
    return int(start_page), normalized_end


def read_pdf_page_count(pdf_path: Path) -> int:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("缺少 PyMuPDF 依赖，无法读取 PDF 页数") from exc

    with fitz.open(pdf_path) as doc:
        return doc.page_count


def render_pdf_page_image(
    pdf_path: Path,
    page_number: int,
    image_path: Path,
    *,
    dpi: int = DEFAULT_RENDER_DPI,
    image_format: str = DEFAULT_IMAGE_FORMAT,
) -> Path:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("缺少 PyMuPDF 依赖，无法渲染 PDF 页面") from exc

    image_path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as doc:
        page = doc.load_page(page_number - 1)
        pixmap = page.get_pixmap(dpi=dpi)
        pixmap.save(str(image_path))
    return image_path


def transcribe_page_image_with_responses(
    image_path: Path,
    *,
    page_number: int,
    model: str = DEFAULT_PDF_MARKDOWN_MODEL,
    api_base: Optional[str] = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    reasoning_effort: str = DEFAULT_PDF_MARKDOWN_REASONING_EFFORT,
    get_ai_config: Callable[[], dict[str, Any]] = get_openai_compatible_config,
) -> str:
    config = get_ai_config()
    api_key = str(config.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set and config.toml [ai].api_key is empty"
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai 依赖，无法调用 Responses API") from exc

    base_url = (
        str(api_base or config.get("base_url") or config.get("api_base") or "").strip()
        or None
    )
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    prompt = (
        "Below is one rendered page from a PDF document. "
        "Transcribe it into clean Markdown. Preserve headings, lists, tables, formulas, numbers, and footnotes. "
        "Output Markdown only, without wrapping fences or commentary."
    )

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)
    kwargs: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{prompt}\n\nPage number: {page_number}",
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{encoded_image}",
                    },
                ],
            }
        ],
    }
    normalized_reasoning_effort = str(reasoning_effort or "").strip()
    if normalized_reasoning_effort:
        kwargs["reasoning"] = {"effort": normalized_reasoning_effort}
    response = client.responses.create(**kwargs)
    return extract_response_text(response).strip()


def _page_markdown_entry(page: PdfMarkdownPageResult) -> str:
    return f"## Page {page.page_number}\n\n{page.markdown.strip()}"


def _write_index(
    index_path: Path, pages: list[PdfMarkdownPageResult], combined_path: Path
) -> None:
    lines = [
        "# PDF Markdown Conversion",
        "",
        f"- combined_markdown: `{combined_path}`",
        f"- total_pages: `{len(pages)}`",
        "",
    ]
    for page in pages:
        if page.status == "completed":
            cached = " cached" if page.cached else ""
            lines.append(
                f"- `completed{cached}` page {page.page_number}: `{page.markdown_path}`"
            )
        else:
            lines.append(f"- `failed` page {page.page_number}: {page.error}")
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_pdf_to_markdown(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    start_page: int = 1,
    end_page: Optional[int] = None,
    model: str = DEFAULT_PDF_MARKDOWN_MODEL,
    api_base: Optional[str] = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    reasoning_effort: str = DEFAULT_PDF_MARKDOWN_REASONING_EFFORT,
    dpi: int = DEFAULT_RENDER_DPI,
    image_format: str = DEFAULT_IMAGE_FORMAT,
    force: bool = False,
    page_count_reader: Callable[[Path], int] = read_pdf_page_count,
    page_renderer: Callable[..., Path] = render_pdf_page_image,
    image_to_markdown: Callable[..., str] = transcribe_page_image_with_responses,
) -> PdfMarkdownConversionResult:
    source_path = Path(pdf_path)
    target_dir = Path(output_dir)
    pages_dir = target_dir / "pages"
    images_dir = target_dir / "images"
    target_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    first_page, last_page = normalize_page_range(
        page_count_reader(source_path),
        start_page=start_page,
        end_page=end_page,
    )

    page_results: list[PdfMarkdownPageResult] = []
    for page_number in range(first_page, last_page + 1):
        markdown_path = pages_dir / f"page_{page_number:04d}.md"
        image_path = images_dir / f"page_{page_number:04d}.{image_format}"
        if markdown_path.exists() and not force:
            cached_markdown = markdown_path.read_text(encoding="utf-8").strip()
            if cached_markdown:
                page_results.append(
                    PdfMarkdownPageResult(
                        page_number=page_number,
                        status="completed",
                        markdown=cached_markdown,
                        image_path=image_path,
                        markdown_path=markdown_path,
                        cached=True,
                    )
                )
                continue

        try:
            rendered_image = page_renderer(
                source_path,
                page_number,
                image_path,
                dpi=dpi,
                image_format=image_format,
            )
            markdown = image_to_markdown(
                rendered_image,
                page_number=page_number,
                model=model,
                api_base=api_base,
                timeout_seconds=timeout_seconds,
                reasoning_effort=reasoning_effort,
            ).strip()
            if not markdown:
                raise RuntimeError("empty markdown returned")
            markdown_path.write_text(markdown, encoding="utf-8")
            page_results.append(
                PdfMarkdownPageResult(
                    page_number=page_number,
                    status="completed",
                    markdown=markdown,
                    image_path=rendered_image,
                    markdown_path=markdown_path,
                )
            )
        except Exception as exc:
            page_results.append(
                PdfMarkdownPageResult(
                    page_number=page_number,
                    status="failed",
                    error=str(exc),
                    image_path=image_path,
                    markdown_path=markdown_path,
                )
            )

    combined_markdown = "\n\n".join(
        _page_markdown_entry(page)
        for page in page_results
        if page.status == "completed" and page.markdown.strip()
    )
    combined_path = target_dir / "combined.md"
    index_path = target_dir / "index.md"
    combined_path.write_text(combined_markdown, encoding="utf-8")
    _write_index(index_path, page_results, combined_path)
    return PdfMarkdownConversionResult(
        markdown=combined_markdown,
        pages=page_results,
        output_dir=target_dir,
        combined_path=combined_path,
        index_path=index_path,
    )
