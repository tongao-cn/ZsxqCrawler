import asyncio
import unittest

from backend.services.columns_remote_service import fetch_column_file_download_url, fetch_column_video_m3u8_url


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self.payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.payload


class ColumnsRemoteServiceTests(unittest.TestCase):
    def test_fetch_column_file_download_url_retries_1059_then_returns_url(self):
        responses = [
            FakeResponse({"succeeded": False, "code": 1059, "error_message": "limited"}),
            FakeResponse({"succeeded": True, "resp_data": {"download_url": "https://example.test/file"}}),
        ]
        calls = []
        sleeps = []

        def request_get(url, **kwargs):
            calls.append((url, kwargs))
            return responses.pop(0)

        async def sleep(seconds):
            sleeps.append(seconds)

        result = asyncio.run(
            fetch_column_file_download_url(
                file_id=12,
                file_name="report.pdf",
                headers={"Cookie": "redacted"},
                request_get=request_get,
                sleep=sleep,
            )
        )

        self.assertEqual("https://example.test/file", result)
        self.assertEqual([2], sleeps)
        self.assertEqual(
            [
                "https://api.zsxq.com/v2/files/12/download_url",
                "https://api.zsxq.com/v2/files/12/download_url",
            ],
            [call[0] for call in calls],
        )
        self.assertEqual({"Cookie": "redacted"}, calls[0][1]["headers"])
        self.assertEqual(30, calls[0][1]["timeout"])

    def test_fetch_column_video_m3u8_url_preserves_http_failure_message(self):
        log_errors = []
        sleeps = []

        def request_get(*args, **kwargs):
            return FakeResponse(status_code=503, text="service unavailable")

        async def sleep(seconds):
            sleeps.append(seconds)

        with self.assertRaisesRegex(Exception, "获取视频链接失败: HTTP 503") as raised:
            asyncio.run(
                fetch_column_video_m3u8_url(
                    video_id=99,
                    topic_id=88,
                    headers={},
                    request_get=request_get,
                    log_error=log_errors.append,
                    sleep=sleep,
                )
            )

        self.assertIn("https://api.zsxq.com/v2/videos/99/url", str(raised.exception))
        self.assertEqual(9, len(sleeps))
        self.assertEqual(str(raised.exception), log_errors[-1])

    def test_fetch_column_file_download_url_logs_non_retry_api_failure_context(self):
        log_errors = []

        def request_get(*args, **kwargs):
            return FakeResponse({"succeeded": False, "code": 403, "error_message": "denied"})

        with self.assertRaisesRegex(Exception, "获取下载链接失败: denied \\(code=403\\)"):
            asyncio.run(
                fetch_column_file_download_url(
                    file_id=12,
                    file_name="secret.pdf",
                    headers={},
                    request_get=request_get,
                    log_error=log_errors.append,
                )
            )

        self.assertEqual(
            ["获取下载链接失败: code=403, message=denied, file_id=12, file_name=secret.pdf"],
            log_errors,
        )


if __name__ == "__main__":
    unittest.main()
