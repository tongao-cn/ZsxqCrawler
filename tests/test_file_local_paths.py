import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class FileLocalPathTests(unittest.TestCase):
    def test_safe_download_filename_keeps_downloader_contract(self):
        from backend.services.file_local_paths import safe_download_filename

        self.assertEqual("memo（）[v1].pdf", safe_download_filename("memo（）[v1].pdf", 101))
        self.assertEqual("..memo.pdf", safe_download_filename("../memo?.pdf", 101))
        self.assertEqual("file_101", safe_download_filename("///", 101))

    def test_download_target_path_uses_safe_filename(self):
        from backend.services.file_local_paths import download_target_path

        self.assertEqual(
            ("..memo.pdf", str(Path("downloads") / "..memo.pdf")),
            download_target_path("downloads", "../memo?.pdf", 101),
        )

    def test_resolve_local_file_path_prefers_existing_stored_path(self):
        from backend.services.file_local_paths import resolve_local_file_path

        with TemporaryDirectory() as temp_dir:
            stored_path = Path(temp_dir) / "stored name.pdf"
            expected_dir = Path(temp_dir) / "downloads"
            expected_dir.mkdir()
            expected_path = expected_dir / "Report2026.pdf"
            stored_path.write_bytes(b"stored")
            expected_path.write_bytes(b"expected")

            with patch("backend.services.file_local_paths.group_download_dir", return_value=str(expected_dir)):
                resolved = resolve_local_file_path("group-1", 101, "Report / 2026.pdf", str(stored_path))

        self.assertEqual(stored_path.resolve(), resolved)

    def test_resolve_local_file_path_falls_back_to_expected_download_path(self):
        from backend.services.file_local_paths import resolve_local_file_path

        with TemporaryDirectory() as temp_dir:
            expected_dir = Path(temp_dir) / "downloads"
            expected_dir.mkdir()
            expected_path = expected_dir / "Report2026.pdf"
            expected_path.write_bytes(b"expected")

            with patch("backend.services.file_local_paths.group_download_dir", return_value=str(expected_dir)):
                resolved = resolve_local_file_path("group-1", 101, "Report / 2026.pdf", None)

        self.assertEqual(expected_path.resolve(), resolved)


if __name__ == "__main__":
    unittest.main()
