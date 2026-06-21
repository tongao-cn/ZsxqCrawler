import asyncio
import unittest

from backend.services.columns_remote_service import (
    fetch_column_file_download_url,
    fetch_column_topics,
    fetch_column_video_m3u8_url,
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self.payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
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

    def test_fetch_column_topics_returns_topics_and_request_count(self):
        task_logs = []

        def request_get(url, **kwargs):
            self.assertEqual("https://example.test/topics", url)
            self.assertEqual({"Cookie": "redacted"}, kwargs["headers"])
            self.assertEqual(30, kwargs["timeout"])
            return FakeResponse({"succeeded": True, "resp_data": {"topics": [{"topic_id": 1}]}})

        topics, request_count = fetch_column_topics(
            "task-1",
            3,
            "https://example.test/topics",
            {"Cookie": "redacted"},
            request_get=request_get,
            add_task_log=lambda task_id, message: task_logs.append((task_id, message)),
        )

        self.assertEqual([{"topic_id": 1}], topics)
        self.assertEqual(1, request_count)
        self.assertEqual([("task-1", "   📝 获取到 1 篇文章")], task_logs)

    def test_fetch_column_topics_preserves_http_failure_logs(self):
        task_logs = []
        log_errors = []

        topics, request_count = fetch_column_topics(
            "task-1",
            3,
            "https://example.test/topics",
            {},
            request_get=lambda *args, **kwargs: FakeResponse(status_code=503, text="service unavailable"),
            add_task_log=lambda task_id, message: task_logs.append((task_id, message)),
            log_error=log_errors.append,
        )

        self.assertIsNone(topics)
        self.assertEqual(1, request_count)
        self.assertEqual([("task-1", "   ⚠️ 获取文章列表失败: HTTP 503")], task_logs)
        self.assertEqual(
            ["获取专栏文章列表失败: column_id=3, HTTP 503, response=service unavailable"],
            log_errors,
        )

    def test_fetch_column_topics_preserves_json_failure_logs(self):
        task_logs = []
        log_exceptions = []

        topics, request_count = fetch_column_topics(
            "task-1",
            3,
            "https://example.test/topics",
            {},
            request_get=lambda *args, **kwargs: FakeResponse(ValueError("bad json"), text="not-json"),
            add_task_log=lambda task_id, message: task_logs.append((task_id, message)),
            log_exception=log_exceptions.append,
        )

        self.assertIsNone(topics)
        self.assertEqual(1, request_count)
        self.assertEqual([("task-1", "   ⚠️ 解析文章列表失败: bad json")], task_logs)
        self.assertEqual(
            ["解析专栏文章列表JSON失败: column_id=3, response=not-json"],
            log_exceptions,
        )


if __name__ == "__main__":
    unittest.main()
