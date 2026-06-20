import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi import HTTPException

    from backend.core.image_cache_manager import ImageCacheManager
    from backend.core.image_cache_manager import validate_remote_image_url
    from backend.routes.media_routes import (
        _media_bytes_response,
        _media_route_error,
        clear_image_cache,
        get_image_cache_info,
        get_local_image,
        get_local_video,
        proxy_image,
    )
    from backend.services.media_service import (
        MediaServiceError,
        _build_proxy_image_request_headers,
        _cached_image_media,
        _existing_local_media_path,
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

    def test_media_route_error_preserves_status_and_detail_format(self):
        error = _media_route_error("获取图片失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("获取图片失败: boom", error.detail)

    def test_build_cached_image_response_preserves_cache_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "sample.jpg"
            file_path.write_bytes(b"image-data")

            response = _media_bytes_response(_cached_image_media(file_path, "HIT"))

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

            with self.assertRaises(MediaServiceError) as ctx:
                _resolve_safe_child_path(base_dir, "../outside.jpg")

        self.assertEqual(403, ctx.exception.status_code)
        self.assertEqual("禁止访问该路径", ctx.exception.detail)

    def test_existing_local_media_path_returns_existing_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / "images"
            file_path = base_dir / "nested" / "a.jpg"
            file_path.parent.mkdir(parents=True)
            file_path.write_bytes(b"image-data")

            self.assertEqual(
                file_path.resolve(),
                _existing_local_media_path(base_dir, "nested/a.jpg", "图片不存在"),
            )

    def test_existing_local_media_path_raises_custom_missing_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / "videos"

            with self.assertRaises(MediaServiceError) as ctx:
                _existing_local_media_path(base_dir, "missing.mp4", "视频不存在")

        self.assertEqual(404, ctx.exception.status_code)
        self.assertEqual("视频不存在", ctx.exception.detail)

    def test_existing_local_media_path_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / "images"

            with self.assertRaises(MediaServiceError) as ctx:
                _existing_local_media_path(base_dir, "../outside.jpg", "图片不存在")

        self.assertEqual(403, ctx.exception.status_code)
        self.assertEqual("禁止访问该路径", ctx.exception.detail)

    def test_validate_proxy_image_url_rejects_unsafe_schemes(self):
        with self.assertRaises(MediaServiceError) as ctx:
            _validate_proxy_image_url("javascript:alert(1)")

        self.assertEqual(400, ctx.exception.status_code)

    def test_validate_proxy_image_url_rejects_private_ips(self):
        with self.assertRaises(MediaServiceError) as ctx:
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
        from backend.services import media_service

        def fake_cookie(group_id):
            return "zsxq_access_token=secret" if group_id == "123" else None

        with patch.object(media_service, "get_cookie_for_group", side_effect=fake_cookie):
            self.assertEqual(
                {"Cookie": "zsxq_access_token=secret"},
                _build_proxy_image_request_headers("123", "https://images.zsxq.com/a.jpg"),
            )
            self.assertEqual({}, _build_proxy_image_request_headers("123", "https://example.com/a.jpg"))
            self.assertEqual({}, _build_proxy_image_request_headers("456", "https://images.zsxq.com/a.jpg"))
            self.assertEqual({}, _build_proxy_image_request_headers(None, "https://images.zsxq.com/a.jpg"))

    def test_is_blocked_proxy_ip_identifies_private_ranges(self):
        self.assertTrue(_is_blocked_proxy_ip("10.0.0.1"))
        self.assertTrue(_is_blocked_proxy_ip("::1"))
        self.assertFalse(_is_blocked_proxy_ip("8.8.8.8"))

    def test_get_proxy_image_returns_cached_hit_media(self):
        from backend.services.media_service import get_proxy_image

        class FakeCacheManager:
            def __init__(self, cached_path):
                self.cached_path = cached_path

            def is_cached(self, url):
                return True

            def get_cached_path(self, url):
                return self.cached_path

            def download_and_cache(self, url, request_headers=None):
                raise AssertionError("download should not run for cache hit")

        with tempfile.TemporaryDirectory() as tmp:
            cached_path = Path(tmp) / "cached.jpg"
            cached_path.write_bytes(b"cached-image")

            with patch("backend.services.media_service._validate_proxy_image_url", return_value="https://images.zsxq.com/a.jpg"), patch(
                "backend.services.media_service.get_image_cache_manager",
                return_value=FakeCacheManager(cached_path),
            ):
                media = get_proxy_image("https://images.zsxq.com/a.jpg", "123")

        self.assertEqual(b"cached-image", media.content)
        self.assertEqual("image/jpeg", media.media_type)
        self.assertEqual("HIT", media.headers["X-Cache-Status"])

    def test_get_proxy_image_maps_download_failure_to_404(self):
        from backend.services.media_service import get_proxy_image

        class FakeCacheManager:
            def is_cached(self, url):
                return False

            def download_and_cache(self, url, request_headers=None):
                return False, None, "not found"

        with patch("backend.services.media_service._validate_proxy_image_url", return_value="https://images.zsxq.com/a.jpg"), patch(
            "backend.services.media_service.get_image_cache_manager",
            return_value=FakeCacheManager(),
        ):
            with self.assertRaises(MediaServiceError) as ctx:
                get_proxy_image("https://images.zsxq.com/a.jpg", "123")

        self.assertEqual(404, ctx.exception.status_code)
        self.assertEqual("图片加载失败: not found", ctx.exception.detail)

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

    def test_proxy_image_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch("backend.routes.media_routes.get_proxy_image", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(proxy_image("https://images.zsxq.com/a.jpg"))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("代理图片失败: boom", ctx.exception.detail)

    def test_proxy_image_route_preserves_service_error_details(self):
        import asyncio

        with patch(
            "backend.routes.media_routes.get_proxy_image",
            side_effect=MediaServiceError(403, "禁止代理内网或本机图片 URL"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(proxy_image("http://127.0.0.1/a.jpg"))

        self.assertEqual(403, ctx.exception.status_code)
        self.assertEqual("禁止代理内网或本机图片 URL", ctx.exception.detail)

    def test_get_image_cache_info_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch("backend.routes.media_routes.get_image_cache_info_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(get_image_cache_info("123"))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("获取缓存信息失败: boom", ctx.exception.detail)

    def test_clear_image_cache_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch("backend.routes.media_routes.clear_image_cache_response", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(clear_image_cache("123"))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("清空缓存失败: boom", ctx.exception.detail)

    def test_clear_image_cache_route_preserves_service_failure_wrapping(self):
        import asyncio

        with patch(
            "backend.routes.media_routes.clear_image_cache_response",
            side_effect=MediaServiceError(500, "permission denied"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(clear_image_cache("123"))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("清空缓存失败: 500: permission denied", ctx.exception.detail)

    def test_get_local_image_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch("backend.routes.media_routes.get_local_image_media", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(get_local_image("123", "avatar.jpg"))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("获取图片失败: boom", ctx.exception.detail)

    def test_get_local_video_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        with patch("backend.routes.media_routes.get_local_video_file", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(get_local_video("123", "clip.mp4"))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("获取视频失败: boom", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
