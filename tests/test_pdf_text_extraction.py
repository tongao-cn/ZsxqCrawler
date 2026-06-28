import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class PdfTextExtractionTests(unittest.TestCase):
    def test_extract_pdf_text_uses_completed_cache_without_starting_server(self):
        from backend.services.pdf_text_extraction import extract_pdf_text_with_opendataloader

        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "cache"
            output_dir.mkdir()
            cached_markdown = "# Cached Markdown\n\n" + ("正文内容" * 20)
            cached_text = "Cached text " * 20
            (output_dir / "report.md").write_text(cached_markdown, encoding="utf-8")
            (output_dir / "report.txt").write_text(cached_text, encoding="utf-8")
            (output_dir / "metadata.json").write_text(
                """
                {
                  "status": "completed",
                  "markdown_file": "report.md",
                  "text_file": "report.txt"
                }
                """,
                encoding="utf-8",
            )
            pdf_path = Path(temp_dir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfake")

            def fail_server():
                raise AssertionError("server should not start for completed cache")

            result = extract_pdf_text_with_opendataloader(
                pdf_path,
                output_dir,
                ensure_server=fail_server,
            )

        self.assertTrue(result.cached)
        self.assertEqual(cached_markdown, result.markdown)
        self.assertEqual(cached_text.strip(), result.text)

    def test_extract_pdf_text_runs_hybrid_full_and_writes_metadata(self):
        from backend.services.pdf_text_extraction import extract_pdf_text_with_opendataloader

        captured = {}

        def fake_runner(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            output_dir = Path(command[command.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "report.md").write_text("# OCR Markdown\n\n正文" * 20, encoding="utf-8")
            (output_dir / "report.txt").write_text("OCR text " * 20, encoding="utf-8")
            (output_dir / "report.json").write_text("{}", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfake")
            output_dir = Path(temp_dir) / "out"

            result = extract_pdf_text_with_opendataloader(
                pdf_path,
                output_dir,
                ensure_server=lambda: "http://127.0.0.1:5002",
                runner=fake_runner,
            )

            metadata = (output_dir / "metadata.json").read_text(encoding="utf-8")

        command = captured["command"]
        self.assertFalse(result.cached)
        self.assertIn("--hybrid-mode", command)
        self.assertEqual("full", command[command.index("--hybrid-mode") + 1])
        self.assertIn("--image-output", command)
        self.assertEqual("off", command[command.index("--image-output") + 1])
        self.assertIn("http://127.0.0.1:5002", command)
        self.assertIn('"status": "completed"', metadata)
        self.assertIn('"hybrid_mode": "full"', metadata)
        self.assertIn('"extraction_mode": "hybrid-full"', metadata)

    def test_extract_pdf_text_falls_back_to_java_only_when_hybrid_fails(self):
        from backend.services.pdf_text_extraction import extract_pdf_text_with_opendataloader

        commands = []

        def fake_runner(command, **kwargs):
            commands.append(command)
            output_dir = Path(command[command.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            if "--hybrid" in command:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="hybrid failed")
            (output_dir / "report.md").write_text("# Java Markdown\n\n正文" * 20, encoding="utf-8")
            (output_dir / "report.txt").write_text("Java text " * 20, encoding="utf-8")
            (output_dir / "report.json").write_text("{}", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfake")
            output_dir = Path(temp_dir) / "out"

            result = extract_pdf_text_with_opendataloader(
                pdf_path,
                output_dir,
                ensure_server=lambda: "http://127.0.0.1:5002",
                runner=fake_runner,
            )

            metadata = (output_dir / "metadata.json").read_text(encoding="utf-8")

        self.assertEqual(2, len(commands))
        self.assertIn("--hybrid", commands[0])
        self.assertNotIn("--hybrid", commands[1])
        self.assertFalse(result.cached)
        self.assertEqual("# Java Markdown\n\n正文" * 20, result.markdown)
        self.assertIn('"status": "completed"', metadata)
        self.assertIn('"extraction_mode": "java-only-fallback"', metadata)
        self.assertIn('"fallback_reason": "hybrid failed"', metadata)

    def test_extract_pdf_markdown_for_analysis_uses_opendataloader_text_extractor(self):
        from backend.services.file_ai_content_analysis import extract_pdf_markdown_for_analysis

        class FakeResult:
            markdown = "# Extracted\n\n正文"
            text = "fallback text"

        captured = {}

        def fake_extract_pdf_text(path, output_dir):
            captured["path"] = path
            captured["output_dir"] = output_dir
            return FakeResult()

        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfake")

            markdown = extract_pdf_markdown_for_analysis(
                pdf_path,
                file_name="report.pdf",
                model="gpt-5.5",
                api_base="https://api.openai.com/v1",
                wire_api="chat",
                reasoning_effort="medium",
                extract_pdf_text=fake_extract_pdf_text,
            )

        self.assertEqual("# Extracted\n\n正文", markdown)
        self.assertEqual(pdf_path, captured["path"])
        self.assertIn("pdf_text_extract", str(captured["output_dir"]))


if __name__ == "__main__":
    unittest.main()
