import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class PdfMarkdownConversionTests(unittest.TestCase):
    def test_normalize_page_range_defaults_to_all_pages(self):
        from backend.services.pdf_markdown_conversion import normalize_page_range

        self.assertEqual((1, 8), normalize_page_range(8, start_page=1, end_page=None))
        self.assertEqual((3, 8), normalize_page_range(8, start_page=3, end_page=0))

    def test_normalize_page_range_rejects_invalid_ranges(self):
        from backend.services.pdf_markdown_conversion import normalize_page_range

        with self.assertRaises(ValueError):
            normalize_page_range(0, start_page=1, end_page=None)
        with self.assertRaises(ValueError):
            normalize_page_range(8, start_page=0, end_page=None)
        with self.assertRaises(ValueError):
            normalize_page_range(8, start_page=6, end_page=5)
        with self.assertRaises(ValueError):
            normalize_page_range(8, start_page=1, end_page=9)

    def test_read_pdf_page_count_uses_pymupdf(self):
        import fitz

        from backend.services.pdf_markdown_conversion import read_pdf_page_count

        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "report.pdf"
            doc = fitz.open()
            doc.new_page()
            doc.new_page()
            doc.save(pdf_path)
            doc.close()

            self.assertEqual(2, read_pdf_page_count(pdf_path))

    def test_convert_pdf_to_markdown_caches_pages_and_combines_successes(self):
        from backend.services.pdf_markdown_conversion import convert_pdf_to_markdown

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pdf_path = temp_path / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4")
            output_dir = temp_path / "out"
            rendered = []
            transcribed = []

            def fake_page_count(_pdf_path):
                return 2

            def fake_render(_pdf_path, page_number, image_path, **_kwargs):
                rendered.append(page_number)
                image_path.write_bytes(f"image:{page_number}".encode("utf-8"))
                return image_path

            def fake_transcribe(image_path, *, page_number, **_kwargs):
                transcribed.append((page_number, image_path.name))
                return f"markdown page {page_number}"

            first = convert_pdf_to_markdown(
                pdf_path,
                output_dir,
                page_count_reader=fake_page_count,
                page_renderer=fake_render,
                image_to_markdown=fake_transcribe,
            )
            second = convert_pdf_to_markdown(
                pdf_path,
                output_dir,
                page_count_reader=fake_page_count,
                page_renderer=fake_render,
                image_to_markdown=fake_transcribe,
            )

            self.assertEqual([1, 2], rendered)
            self.assertEqual([(1, "page_0001.jpg"), (2, "page_0002.jpg")], transcribed)
            self.assertEqual(
                "## Page 1\n\nmarkdown page 1\n\n## Page 2\n\nmarkdown page 2",
                first.markdown,
            )
            self.assertEqual(first.markdown, second.markdown)
            self.assertTrue((output_dir / "index.md").exists())
            self.assertEqual(
                ["completed", "completed"], [page.status for page in second.pages]
            )
            self.assertTrue(all(page.cached for page in second.pages))

    def test_convert_pdf_to_markdown_records_failed_pages(self):
        from backend.services.pdf_markdown_conversion import convert_pdf_to_markdown

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pdf_path = temp_path / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4")

            def fake_page_count(_pdf_path):
                return 3

            def fake_render(_pdf_path, page_number, image_path, **_kwargs):
                image_path.write_bytes(f"image:{page_number}".encode("utf-8"))
                return image_path

            def fake_transcribe(_image_path, *, page_number, **_kwargs):
                if page_number == 2:
                    raise RuntimeError("model timeout")
                return f"markdown page {page_number}"

            result = convert_pdf_to_markdown(
                pdf_path,
                temp_path / "out",
                page_count_reader=fake_page_count,
                page_renderer=fake_render,
                image_to_markdown=fake_transcribe,
            )

            self.assertEqual(
                ["completed", "failed", "completed"],
                [page.status for page in result.pages],
            )
            self.assertEqual("model timeout", result.pages[1].error)
            self.assertNotIn("markdown page 2", result.markdown)
            self.assertIn("markdown page 1", result.markdown)
            self.assertIn("markdown page 3", result.markdown)
            self.assertIn(
                "- `failed` page 2: model timeout",
                result.index_path.read_text(encoding="utf-8"),
            )

    def test_transcribe_page_image_with_responses_uses_responses_image_input(self):
        from unittest.mock import patch

        from backend.services.pdf_markdown_conversion import (
            transcribe_page_image_with_responses,
        )

        captured = {}

        class FakeResponses:
            def create(self, **kwargs):
                captured["kwargs"] = kwargs

                class FakeResponse:
                    output_text = " page markdown "

                return FakeResponse()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured["client"] = kwargs
                self.responses = FakeResponses()

        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "page.jpg"
            image_path.write_bytes(b"fake image")

            with patch("openai.OpenAI", FakeOpenAI):
                markdown = transcribe_page_image_with_responses(
                    image_path,
                    page_number=7,
                    model="gpt-5.4-mini",
                    api_base="https://example.test/v1",
                    timeout_seconds=45,
                    get_ai_config=lambda: {"api_key": "sk-test"},
                )

        self.assertEqual("page markdown", markdown)
        self.assertEqual("sk-test", captured["client"]["api_key"])
        self.assertEqual("https://example.test/v1", captured["client"]["base_url"])
        self.assertEqual(45, captured["client"]["timeout"])
        self.assertEqual("gpt-5.4-mini", captured["kwargs"]["model"])
        self.assertEqual({"effort": "low"}, captured["kwargs"]["reasoning"])
        content = captured["kwargs"]["input"][0]["content"]
        self.assertEqual("input_text", content[0]["type"])
        self.assertIn("Page number: 7", content[0]["text"])
        self.assertEqual("input_image", content[1]["type"])
        self.assertTrue(content[1]["image_url"].startswith("data:image/jpeg;base64,"))

    def test_convert_pdf_to_markdown_passes_reasoning_effort_to_image_transcriber(self):
        from backend.services.pdf_markdown_conversion import convert_pdf_to_markdown

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pdf_path = temp_path / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4")
            captured = {}

            def fake_render(_pdf_path, _page_number, image_path, **_kwargs):
                image_path.write_bytes(b"image")
                return image_path

            def fake_transcribe(_image_path, **kwargs):
                captured["kwargs"] = kwargs
                return "markdown"

            convert_pdf_to_markdown(
                pdf_path,
                temp_path / "out",
                reasoning_effort="low",
                page_count_reader=lambda _path: 1,
                page_renderer=fake_render,
                image_to_markdown=fake_transcribe,
            )

        self.assertEqual("low", captured["kwargs"]["reasoning_effort"])


if __name__ == "__main__":
    unittest.main()
