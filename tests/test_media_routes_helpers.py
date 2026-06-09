import tempfile
import unittest
from pathlib import Path

try:
    from fastapi import HTTPException

    from backend.core.image_cache_manager import ImageCacheManager
    from backend.core.image_cache_manager import validate_remote_image_url
    from backend.routes.media_routes import (
        _build_cached_image_response,
        _build_proxy_image_request_headers,
        _guess_content_type,
        _is_blocked_proxy_ip,
        _read_file_bytes,
        _resolve_safe_child_path,
        _validate_proxy_image_url,
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

    def test_validate_proxy_image_url_rejects_unsafe_schemes(self):
        with self.assertRaises(HTTPException) as ctx:
            _validate_proxy_image_url("javascript:alert(1)")

        self.assertEqual(400, ctx.exception.status_code)

    def test_validate_proxy_image_url_rejects_private_ips(self):
        with self.assertRaises(HTTPException) as ctx:
            _validate_proxy_image_url("http://127.0.0.1/avatar.png")

        self.assertEqual(403, ctx.exception.status_code)

    def test_validate_remote_image_url_allows_trusted_zsxq_proxy_address(self):
        import backend.core.image_cache_manager as image_cache_manager

        original_getaddrinfo = image_cache_manager.socket.getaddrinfo
        try:
            image_cache_manager.socket.getaddrinfo = lambda *args, **kwargs: [
                (None, None, None, None, ("198.18.0.80", 443))
            ]

            self.assertEqual(
                "https://images.zsxq.com/a.jpg",
                validate_remote_image_url("https://images.zsxq.com/a.jpg"),
            )
            with self.assertRaises(ValueError):
                validate_remote_image_url("https://example.com/a.jpg")
        finally:
            image_cache_manager.socket.getaddrinfo = original_getaddrinfo

    def test_build_proxy_image_request_headers_uses_group_cookie(self):
        from backend.routes import media_routes

        original = media_routes.get_cookie_for_group
        try:
            media_routes.get_cookie_for_group = lambda group_id: "zsxq_access_token=secret" if group_id == "123" else None

            self.assertEqual(
                {"Cookie": "zsxq_access_token=secret"},
                _build_proxy_image_request_headers("123", "https://images.zsxq.com/a.jpg"),
            )
            self.assertEqual({}, _build_proxy_image_request_headers("123", "https://example.com/a.jpg"))
            self.assertEqual({}, _build_proxy_image_request_headers("456", "https://images.zsxq.com/a.jpg"))
            self.assertEqual({}, _build_proxy_image_request_headers(None, "https://images.zsxq.com/a.jpg"))
        finally:
            media_routes.get_cookie_for_group = original

    def test_is_blocked_proxy_ip_identifies_private_ranges(self):
        self.assertTrue(_is_blocked_proxy_ip("10.0.0.1"))
        self.assertTrue(_is_blocked_proxy_ip("::1"))
        self.assertFalse(_is_blocked_proxy_ip("8.8.8.8"))

    def test_download_and_cache_rejects_large_content_length(self):
        class FakeResponse:
            headers = {"content-type": "image/png", "content-length": "11"}

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size=8192):
                yield b"x"

        with tempfile.TemporaryDirectory() as tmp:
            manager = ImageCacheManager(tmp)
            import backend.core.image_cache_manager as image_cache_manager

            original_get = __import__("requests").get
            original_validate = image_cache_manager.validate_remote_image_url
            try:
                image_cache_manager.validate_remote_image_url = lambda url: url
                __import__("requests").get = lambda *args, **kwargs: FakeResponse()
                ok, path, error = manager.download_and_cache("https://images.zsxq.com/a.png", max_bytes=10)
            finally:
                __import__("requests").get = original_get
                image_cache_manager.validate_remote_image_url = original_validate

        self.assertFalse(ok)
        self.assertIsNone(path)
        self.assertIn("图片过大", error)


if __name__ == "__main__":
    unittest.main()
