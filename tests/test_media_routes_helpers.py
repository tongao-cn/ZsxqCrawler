import tempfile
import unittest
from pathlib import Path

try:
    from fastapi import HTTPException

    from backend.routes.media_routes import (
        _build_cached_image_response,
        _guess_content_type,
        _read_file_bytes,
        _resolve_safe_child_path,
    )

    HAS_MEDIA_ROUTE_DEPS = True
except Exception:
    HAS_MEDIA_ROUTE_DEPS = False


@unittest.skipUnless(HAS_MEDIA_ROUTE_DEPS, "media route dependencies are not installed")
class MediaRoutesHelperTests(unittest.TestCase):
    def test_guess_content_type_uses_mimetype_then_default(self):
        self.assertEqual("image/png", _guess_content_type(Path("avatar.png"), "image/jpeg"))
        self.assertEqual("fallback/type", _guess_content_type(Path("file.unknownext"), "fallback/type"))

    def test_read_file_bytes_returns_binary_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "sample.bin"
            file_path.write_bytes(b"\x00media-bytes")

            self.assertEqual(b"\x00media-bytes", _read_file_bytes(file_path))

    def test_build_cached_image_response_preserves_cache_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "sample.jpg"
            file_path.write_bytes(b"image-data")

            response = _build_cached_image_response(file_path, "HIT")

        self.assertEqual(b"image-data", response.body)
        self.assertEqual("image/jpeg", response.media_type)
        self.assertEqual("public, max-age=86400", response.headers["cache-control"])
        self.assertEqual("*", response.headers["access-control-allow-origin"])
        self.assertEqual("HIT", response.headers["x-cache-status"])

    def test_resolve_safe_child_path_allows_nested_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / "images"
            expected = base_dir / "nested" / "a.jpg"

            self.assertEqual(expected.resolve(), _resolve_safe_child_path(base_dir, "nested/a.jpg"))

    def test_resolve_safe_child_path_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / "images"

            with self.assertRaises(HTTPException) as ctx:
                _resolve_safe_child_path(base_dir, "../outside.jpg")

        self.assertEqual(403, ctx.exception.status_code)
        self.assertEqual("禁止访问该路径", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
