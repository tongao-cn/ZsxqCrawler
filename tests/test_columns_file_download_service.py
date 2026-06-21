import asyncio
import os
import tempfile
import unittest

from backend.services.columns_file_download_service import download_column_file


class FakeColumnsDb:
    def __init__(self):
        self.status_updates = []

    def update_file_download_status(self, file_id, status, local_path=None):
        self.status_updates.append((file_id, status, local_path))


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text="", chunks=None):
        self.payload = payload or {}
        self.status_code = status_code
        self.text = text
        self.chunks = chunks or []

    def json(self):
        return self.payload

    def iter_content(self, chunk_size=8192):
        yield from self.chunks


class ColumnsFileDownloadServiceTests(unittest.TestCase):
    def test_download_column_file_skips_existing_complete_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            downloads_dir = os.path.join(tmp_dir, "column_downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            local_path = os.path.join(downloads_dir, "report.pdf")
            with open(local_path, "wb") as file_obj:
                file_obj.write(b"abc")

            db = FakeColumnsDb()
            result = asyncio.run(
                download_column_file(
                    db=db,
                    file_id=1,
                    file_name="report.pdf",
                    file_size=3,
                    group_dir=tmp_dir,
                    headers={},
                    request_get=lambda *args, **kwargs: self.fail("request_get should not be called"),
                )
            )

        self.assertEqual("skipped", result)
        self.assertEqual([(1, "completed", local_path)], db.status_updates)

    def test_download_column_file_writes_downloaded_bytes(self):
        responses = [
            FakeResponse({"succeeded": True, "resp_data": {"download_url": "https://example.test/file"}}),
            FakeResponse(status_code=200, chunks=[b"hello", b"", b" world"]),
        ]

        def request_get(*args, **kwargs):
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            db = FakeColumnsDb()
            result = asyncio.run(
                download_column_file(
                    db=db,
                    file_id=2,
                    file_name="note.txt",
                    file_size=11,
                    group_dir=tmp_dir,
                    headers={"Cookie": "redacted"},
                    request_get=request_get,
                )
            )
            local_path = os.path.join(tmp_dir, "column_downloads", "note.txt")
            with open(local_path, "rb") as file_obj:
                content = file_obj.read()

        self.assertEqual("downloaded", result)
        self.assertEqual(b"hello world", content)
        self.assertEqual([(2, "completed", local_path)], db.status_updates)

    def test_download_column_file_writes_to_sanitized_column_path(self):
        responses = [
            FakeResponse({"succeeded": True, "resp_data": {"download_url": "https://example.test/file"}}),
            FakeResponse(status_code=200, chunks=[b"safe"]),
        ]

        def request_get(*args, **kwargs):
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            db = FakeColumnsDb()
            result = asyncio.run(
                download_column_file(
                    db=db,
                    file_id=3,
                    file_name="../note?.txt",
                    file_size=4,
                    group_dir=tmp_dir,
                    headers={},
                    request_get=request_get,
                )
            )
            local_path = os.path.join(tmp_dir, "column_downloads", "..note.txt")
            with open(local_path, "rb") as file_obj:
                content = file_obj.read()

        self.assertEqual("downloaded", result)
        self.assertEqual(b"safe", content)
        self.assertEqual([(3, "completed", local_path)], db.status_updates)


if __name__ == "__main__":
    unittest.main()
