import unittest
import tempfile
import contextlib
import datetime
import io
import json
from pathlib import Path
from unittest.mock import patch

from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.crawlers.zsxq_file_downloader_helpers import (
    API_FAILURE_NON_RETRY,
    API_FAILURE_PERMISSION_DENIED_1030,
    API_FAILURE_RETRY,
    API_FAILURE_RETRY_EXHAUSTED,
    HTTP_FAILURE_NON_RETRY,
    HTTP_FAILURE_RETRY,
    HTTP_FAILURE_RETRY_EXHAUSTED,
    add_import_stats,
    classify_api_failure,
    classify_http_failure,
    content_disposition_filename,
    download_exception_detail,
    download_expected_size,
    download_final_failure_detail,
    download_http_failure_detail,
    download_progress_message,
    download_url_failure_detail,
    download_file_data,
    download_interval_plan,
    download_target_path,
    empty_import_stats,
    existing_file_matches,
    filter_files_newer_than,
    has_retry_attempt_remaining,
    is_retryable_api_error,
    is_retryable_http_status,
    normalize_date_range,
    page_crosses_stop_before,
    partial_download_path,
    parse_create_time,
    remove_partial_download,
    download_retry_wait,
    download_size_mismatch_detail,
    download_total_size,
    safe_download_filename,
    should_retry_api_error,
    should_retry_http_status,
    should_log_full_response,
    summarize_page_time_range,
)


class FailingImportFileDb:
    def __init__(self):
        self.cursor = self
        self.conn = self
        self.import_calls = 0
        self.stats_calls = 0

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return (1,)

    def commit(self):
        pass

    def import_file_response(self, data):
        self.import_calls += 1
        raise RuntimeError("stable import failure")

    def get_database_stats(self):
        self.stats_calls += 1
        return {"files": 0}


class FakeDownloadFileDb:
    def __init__(self):
        self.status_updates = []

    def update_file_download_status(self, file_id, status, local_path=None, error_code=None, error_message=None):
        self.status_updates.append((file_id, status, local_path, error_code, error_message))


class FakeDownloadResponse:
    def __init__(self, status_code, chunks=b"", headers=None):
        self.status_code = status_code
        self._chunks = chunks
        self.headers = {"content-length": str(len(chunks))} if chunks else {}
        if headers:
            self.headers.update(headers)

    def iter_content(self, chunk_size=8192):
        yield self._chunks


class FakeChunkedDownloadResponse(FakeDownloadResponse):
    def __init__(self, chunks, headers=None):
        super().__init__(200, b"".join(chunks), headers=headers)
        self._chunk_list = list(chunks)

    def iter_content(self, chunk_size=8192):
        yield from self._chunk_list


class FakeJsonResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "succeeded": True,
            "resp_data": {"download_url": "https://files.example/signed-token"},
        }


class FakeFailedJsonResponse:
    status_code = 200
    text = ""

    def __init__(self, code, message):
        self.code = code
        self.message = message

    def json(self):
        return {
            "succeeded": False,
            "code": self.code,
            "message": self.message,
        }


class FakeInvalidJsonResponse:
    status_code = 200
    text = "{not json"

    def json(self):
        raise json.JSONDecodeError("bad json", self.text, 1)


class FakeDownloadSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.get_calls = []

    def get(self, url, timeout=None, stream=False, **kwargs):
        self.get_calls.append((url, timeout, stream))
        return self.responses.pop(0)


class FileDownloaderPaginationTests(unittest.TestCase):
    def _downloader_with_failing_import(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "group-1"
        downloader.file_db = FailingImportFileDb()
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {
                "succeeded": True,
                "resp_data": {
                    "index": "next-index",
                    "files": [{"file": {"file_id": 101, "create_time": "2026-02-01T10:00:00.000+0800"}}],
                },
            }

        downloader.fetch_file_list = fetch_file_list
        return downloader

    def test_collect_all_files_stops_when_page_import_fails(self):
        downloader = self._downloader_with_failing_import()

        stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual(1, len(downloader.fetch_calls))
        self.assertEqual(1, downloader.file_db.import_calls)
        self.assertEqual({"total_files": 0, "new_files": 0, "skipped_files": 0}, stats)

    def test_collect_files_by_time_stops_when_page_import_fails(self):
        downloader = self._downloader_with_failing_import()

        stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual(1, len(downloader.fetch_calls))
        self.assertEqual(1, downloader.file_db.import_calls)
        self.assertEqual(0, stats["files"])


class FileDownloaderTimeHelperTests(unittest.TestCase):
    def test_parse_create_time_accepts_common_formats(self):
        self.assertEqual(
            datetime.datetime(2026, 5, 1, 10, 30, 0),
            parse_create_time("2026-05-01 10:30:00"),
        )
        self.assertEqual(datetime.datetime(2026, 5, 1), parse_create_time("2026-05-01"))
        self.assertIsNone(parse_create_time("not-a-date"))

    def test_normalize_date_range_trims_and_swaps_reversed_range(self):
        start, end, stop_before = normalize_date_range(" 2026-05-07 ", "2026-05-01")

        self.assertEqual(("2026-05-01", "2026-05-07"), (start, end))
        self.assertEqual(datetime.datetime(2026, 5, 7), stop_before)

    def test_summarize_page_time_range_ignores_invalid_timestamps(self):
        oldest, newest = summarize_page_time_range(
            [
                {"file": {"create_time": "2026-05-02 10:00:00"}},
                {"file": {"create_time": "bad"}},
                {"file": {"create_time": "2026-05-01 09:00:00"}},
            ]
        )

        self.assertEqual("2026-05-01 09:00:00", oldest)
        self.assertEqual("2026-05-02 10:00:00", newest)

    def test_filter_files_newer_than_returns_newer_files_and_older_count(self):
        newer_files, older_count = filter_files_newer_than(
            [
                {"file": {"file_id": 1, "create_time": "2026-05-03T00:00:00"}},
                {"file": {"file_id": 2, "create_time": "2026-05-01T00:00:00"}},
                {"file": {"file_id": 3}},
            ],
            "2026-05-02T00:00:00",
        )

        self.assertEqual([1], [item["file"]["file_id"] for item in newer_files])
        self.assertEqual(2, older_count)

    def test_page_crosses_stop_before_returns_oldest_time(self):
        crossed, oldest = page_crosses_stop_before(
            [
                {"file": {"create_time": "2026-05-03 10:00:00"}},
                {"file": {"create_time": "2026-05-01 09:00:00"}},
            ],
            datetime.datetime(2026, 5, 2),
        )

        self.assertTrue(crossed)
        self.assertEqual(datetime.datetime(2026, 5, 1, 9, 0), oldest)


class FileDownloaderFileDataHelperTests(unittest.TestCase):
    def test_download_file_data_accepts_id_or_file_id(self):
        self.assertEqual(
            101,
            download_file_data({"file": {"file_id": 101, "name": "memo.pdf"}})["file_id"],
        )
        self.assertEqual(
            202,
            download_file_data({"file": {"id": 202, "name": "memo.pdf"}})["file_id"],
        )

    def test_safe_download_filename_keeps_supported_characters(self):
        self.assertEqual("memo（）[v1].pdf", safe_download_filename("memo（）[v1].pdf", 101))
        self.assertEqual("file_101", safe_download_filename("///", 101))

    def test_download_target_path_reuses_safe_filename_contract(self):
        self.assertEqual(
            ("..memo.pdf", str(Path("downloads") / "..memo.pdf")),
            download_target_path("downloads", "../memo?.pdf", 101),
        )
        self.assertEqual(
            ("file_101", str(Path("downloads") / "file_101")),
            download_target_path("downloads", "///", 101),
        )

    def test_existing_file_matches_size_or_nonzero_unknown_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "memo.pdf"
            file_path.write_bytes(b"memo")

            self.assertEqual((True, True, 4), existing_file_matches(str(file_path), 4))
            self.assertEqual((True, True, 4), existing_file_matches(str(file_path), 0))
            self.assertEqual((True, False, 4), existing_file_matches(str(file_path), 5))
            self.assertEqual((False, False, 0), existing_file_matches(str(file_path.with_suffix(".missing")), 4))

    def test_remove_partial_download_deletes_existing_file_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            partial_path = Path(temp_dir) / "memo.pdf.part"
            missing_path = Path(temp_dir) / "missing.pdf.part"
            partial_path.write_bytes(b"partial")

            self.assertTrue(remove_partial_download(str(partial_path)))
            self.assertFalse(partial_path.exists())
            self.assertFalse(remove_partial_download(str(missing_path)))

    def test_download_progress_message_preserves_known_total_messages(self):
        self.assertEqual("   📊 进度: 100.0% (4/4 bytes)", download_progress_message(4, 4))
        self.assertIsNone(download_progress_message(4, 8))

    def test_download_progress_message_preserves_unknown_total_messages(self):
        self.assertEqual("   📊 已下载: 4 bytes", download_progress_message(4, 0))
        self.assertIsNone(download_progress_message(10 * 1024 * 1024, 0))

    def test_download_url_failure_detail_preserves_defaults_and_api_errors(self):
        self.assertEqual(
            ("download_url_unavailable", "无法获取下载链接"),
            download_url_failure_detail(None),
        )
        self.assertEqual(
            ("1030", "mobile only"),
            download_url_failure_detail({"code": 1030, "message": "mobile only"}),
        )
        self.assertEqual(
            ("download_url_unavailable", "无法获取下载链接"),
            download_url_failure_detail({"code": "", "message": ""}),
        )

    def test_download_retry_wait_preserves_delay_and_message(self):
        self.assertEqual(
            (
                4,
                "   🔄 文件下载重试 3/5，等待 4 秒...",
            ),
            download_retry_wait(2, 5),
        )

    def test_download_interval_plan_preserves_long_sleep_branch(self):
        self.assertEqual(
            (
                60,
                (
                    "⏰ 已下载 10 个文件，开始长休眠 60 秒...",
                    "😴 长休眠结束，继续下载",
                ),
                True,
            ),
            download_interval_plan(10, 10, 1, 60),
        )

    def test_download_interval_plan_preserves_normal_and_no_sleep_branches(self):
        self.assertEqual(
            (
                1.5,
                ("⏱️ 下载间隔休眠 1.5 秒...",),
                False,
            ),
            download_interval_plan(3, 10, 1.5, 60),
        )
        self.assertEqual((None, (), False), download_interval_plan(3, 10, 0, 60))

    def test_download_size_mismatch_detail_preserves_error_contract(self):
        self.assertEqual(
            (
                "size_mismatch",
                "文件大小不匹配: 预期1,024, 实际512",
            ),
            download_size_mismatch_detail(1024, 512),
        )
        self.assertIsNone(download_size_mismatch_detail(0, 512))
        self.assertIsNone(download_size_mismatch_detail(512, 512))

    def test_download_http_failure_detail_preserves_error_contract(self):
        self.assertEqual(("http_status", "HTTP 500"), download_http_failure_detail(500))

    def test_download_exception_detail_preserves_error_contract(self):
        self.assertEqual(("download_exception", "network down"), download_exception_detail(RuntimeError("network down")))

    def test_download_final_failure_detail_preserves_defaults_and_last_error(self):
        self.assertEqual(("download_failed", "文件下载失败"), download_final_failure_detail(None, None))
        self.assertEqual(("download_failed", "文件下载失败"), download_final_failure_detail("", ""))
        self.assertEqual(("http_status", "HTTP 500"), download_final_failure_detail("http_status", "HTTP 500"))

    def test_download_expected_size_prefers_positive_file_size(self):
        self.assertEqual(1024, download_expected_size(1024, 2048))
        self.assertEqual(2048, download_expected_size(0, 2048))
        self.assertEqual(2048, download_expected_size(-1, 2048))

    def test_download_total_size_preserves_header_parsing(self):
        self.assertEqual(4096, download_total_size({"content-length": "4096"}))
        self.assertEqual(0, download_total_size({}))
        with self.assertRaises(ValueError):
            download_total_size({"content-length": "not-a-number"})

    def test_partial_download_path_appends_part_suffix(self):
        self.assertEqual(r"C:\downloads\memo.pdf.part", partial_download_path(r"C:\downloads\memo.pdf"))

    def test_content_disposition_filename_extracts_plain_filename(self):
        self.assertEqual("memo.pdf", content_disposition_filename('attachment; filename="memo.pdf"'))
        self.assertIsNone(content_disposition_filename("attachment"))


class FileDownloaderImportStatsHelperTests(unittest.TestCase):
    def test_add_import_stats_accumulates_known_keys(self):
        total_stats = empty_import_stats()

        add_import_stats(total_stats, {"files": 2, "topics": "3", "unknown": 99})
        add_import_stats(total_stats, {"files": 1, "users": 4})

        self.assertEqual(3, total_stats["files"])
        self.assertEqual(3, total_stats["topics"])
        self.assertEqual(4, total_stats["users"])
        self.assertNotIn("unknown", total_stats)


class FileDownloaderRetryHelperTests(unittest.TestCase):
    def test_retryable_api_error_accepts_numeric_and_string_codes(self):
        self.assertTrue(is_retryable_api_error(1059))
        self.assertTrue(is_retryable_api_error("1059"))
        self.assertTrue(is_retryable_api_error("503"))
        self.assertFalse(is_retryable_api_error(1030))
        self.assertFalse(is_retryable_api_error("N/A"))

    def test_retryable_http_status_only_accepts_transient_statuses(self):
        self.assertTrue(is_retryable_http_status(429))
        self.assertTrue(is_retryable_http_status(503))
        self.assertFalse(is_retryable_http_status(403))
        self.assertFalse(is_retryable_http_status(404))

    def test_retry_attempt_remaining_stops_on_last_attempt(self):
        self.assertTrue(has_retry_attempt_remaining(0, 3))
        self.assertTrue(has_retry_attempt_remaining(1, 3))
        self.assertFalse(has_retry_attempt_remaining(2, 3))

    def test_retry_decisions_include_error_type_and_remaining_attempts(self):
        self.assertTrue(should_retry_api_error("1059", 0, 2))
        self.assertFalse(should_retry_api_error("1030", 0, 2))
        self.assertFalse(should_retry_api_error("1059", 1, 2))
        self.assertTrue(should_retry_http_status(429, 0, 2))
        self.assertFalse(should_retry_http_status(403, 0, 2))
        self.assertFalse(should_retry_http_status(429, 1, 2))

    def test_should_log_full_response_on_first_last_or_success(self):
        self.assertTrue(should_log_full_response(0, 3, False))
        self.assertFalse(should_log_full_response(1, 3, False))
        self.assertTrue(should_log_full_response(1, 3, True))
        self.assertTrue(should_log_full_response(2, 3, False))

    def test_classify_api_failure_distinguishes_retry_and_terminal_cases(self):
        self.assertEqual(API_FAILURE_RETRY, classify_api_failure("1059", 0, 2))
        self.assertEqual(API_FAILURE_RETRY_EXHAUSTED, classify_api_failure("1059", 1, 2))
        self.assertEqual(API_FAILURE_NON_RETRY, classify_api_failure("N/A", 0, 2))
        self.assertEqual(API_FAILURE_PERMISSION_DENIED_1030, classify_api_failure(1030, 0, 2))

    def test_classify_http_failure_distinguishes_retry_and_terminal_cases(self):
        self.assertEqual(HTTP_FAILURE_RETRY, classify_http_failure(429, 0, 2))
        self.assertEqual(HTTP_FAILURE_RETRY_EXHAUSTED, classify_http_failure(503, 1, 2))
        self.assertEqual(HTTP_FAILURE_NON_RETRY, classify_http_failure(403, 0, 2))

    def test_prepare_retry_api_request_sleeps_counts_and_rotates_headers(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}

        with (
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            headers = ZSXQFileDownloader._prepare_retry_api_request(downloader, 1)

        sleep.assert_called_once_with(15.0)
        self.assertEqual({"User-Agent": "unit-test-agent"}, headers)
        self.assertEqual(1, downloader.request_count)

    def test_parse_api_json_response_returns_retry_on_decode_error(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            data, should_retry = ZSXQFileDownloader._parse_api_json_response(
                downloader,
                FakeInvalidJsonResponse(),
                0,
                2,
            )

        self.assertIsNone(data)
        self.assertTrue(should_retry)
        self.assertIn("JSON解析失败", output.getvalue())
        self.assertIn("准备重试", output.getvalue())


class FileDownloaderDownloadTests(unittest.TestCase):
    def _downloader_for_download(self, temp_dir, session):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.download_dir = temp_dir
        downloader.file_db = FakeDownloadFileDb()
        downloader.session = session
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False
        downloader.get_download_url = lambda file_id: f"https://download.test/{file_id}"
        downloader.download_count = 0
        downloader.current_batch_count = 0
        downloader.files_per_batch = 10
        downloader.download_interval = 0
        downloader.long_sleep_interval = 0
        return downloader

    def test_download_file_accepts_raw_file_id_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([FakeDownloadResponse(200, b"memo")])
            downloader = self._downloader_for_download(temp_dir, session)

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"file_id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
            )

            self.assertTrue(result)
            self.assertTrue(session.get_calls)
            self.assertEqual("https://download.test/101", session.get_calls[0][0])
            self.assertEqual((101, "completed"), downloader.file_db.status_updates[-1][:2])

    def test_download_file_uses_safe_filename_for_local_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([FakeDownloadResponse(200, b"memo")])
            downloader = self._downloader_for_download(temp_dir, session)

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"id": 101, "name": "../memo?.pdf", "size": 4, "download_count": 0}},
            )

            expected_path = str(Path(temp_dir) / "..memo.pdf")
            self.assertTrue(result)
            self.assertTrue((Path(temp_dir) / "..memo.pdf").exists())
            self.assertEqual((101, "completed", expected_path), downloader.file_db.status_updates[-1][:3])

    def test_download_file_uses_content_disposition_for_default_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            response = FakeDownloadResponse(
                200,
                b"memo",
                headers={"content-disposition": 'attachment; filename="real.pdf"'},
            )
            session = FakeDownloadSession([response])
            downloader = self._downloader_for_download(temp_dir, session)

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"id": 101, "name": "file_101", "size": 4, "download_count": 0}},
            )

            expected_path = str(Path(temp_dir) / "real.pdf")
            self.assertTrue(result)
            self.assertTrue((Path(temp_dir) / "real.pdf").exists())
            self.assertEqual((101, "completed", expected_path), downloader.file_db.status_updates[-1][:3])

    def test_download_file_preserves_progress_for_chunked_body_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([FakeChunkedDownloadResponse([b"memo", b""])])
            downloader = self._downloader_for_download(temp_dir, session)

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
            )

            self.assertTrue(result)
            self.assertEqual(b"memo", (Path(temp_dir) / "memo.pdf").read_bytes())
            self.assertIn("   📊 进度: 100.0% (4/4 bytes)", downloader.logs)

    def test_write_download_response_body_preserves_progress_stop_and_empty_chunks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "memo.pdf.part"
            response = FakeChunkedDownloadResponse([b"memo", b""])
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.file_db = FakeDownloadFileDb()
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.check_stop = lambda: False

            downloaded_size = ZSXQFileDownloader._write_download_response_body(
                downloader,
                response,
                str(temp_path),
                4,
                101,
            )

            self.assertEqual(4, downloaded_size)
            self.assertEqual(b"memo", temp_path.read_bytes())
            self.assertEqual(["   📊 进度: 100.0% (4/4 bytes)"], downloader.logs)
            self.assertEqual([], downloader.file_db.status_updates)

            stopping_path = Path(temp_dir) / "stopping.pdf.part"
            stopping_response = FakeChunkedDownloadResponse([b"stop"])
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.check_stop = lambda: True

            with patch(
                "backend.crawlers.zsxq_file_downloader.remove_partial_download",
                return_value=True,
            ) as remove_partial:
                self.assertIsNone(
                    ZSXQFileDownloader._write_download_response_body(
                        downloader,
                        stopping_response,
                        str(stopping_path),
                        0,
                        102,
                    )
                )

            remove_partial.assert_called_once_with(str(stopping_path))
            self.assertEqual(
                (102, "failed", None, "stopped", "下载过程中被停止"),
                downloader.file_db.status_updates[-1],
            )
            self.assertEqual(
                ["   📊 已下载: 4 bytes", "🛑 下载过程中被停止"],
                downloader.logs,
            )

    def test_download_file_stops_during_body_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([FakeDownloadResponse(200, b"memo")])
            downloader = self._downloader_for_download(temp_dir, session)
            stop_checks = iter([False, True])
            downloader.check_stop = lambda: next(stop_checks)
            expected_partial_path = str(Path(temp_dir) / "memo.pdf.part")

            with patch(
                "backend.crawlers.zsxq_file_downloader.remove_partial_download",
                return_value=True,
            ) as remove_partial:
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
                )

            self.assertFalse(result)
            self.assertEqual(
                (101, "failed", None, "stopped", "下载过程中被停止"),
                downloader.file_db.status_updates[-1],
            )
            self.assertEqual(2, remove_partial.call_count)
            remove_partial.assert_called_with(expected_partial_path)
            self.assertFalse((Path(temp_dir) / "memo.pdf").exists())

    def test_download_file_marks_failed_when_download_url_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([])
            downloader = self._downloader_for_download(temp_dir, session)
            downloader.get_download_url = lambda file_id: None
            downloader.last_download_url_error = None

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
            )

            self.assertFalse(result)
            self.assertEqual([], session.get_calls)
            self.assertEqual(
                (101, "failed", None, "download_url_unavailable", "无法获取下载链接"),
                downloader.file_db.status_updates[-1],
            )

    def test_download_file_retries_body_download_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeDownloadResponse(500),
                FakeDownloadResponse(200, b"memo"),
            ])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch("backend.crawlers.zsxq_file_downloader.time.sleep"):
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
                )

            self.assertTrue(result)
            self.assertEqual(2, len(session.get_calls))
            self.assertEqual((101, "completed"), downloader.file_db.status_updates[-1][:2])

    def test_download_file_retries_and_fails_on_size_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeDownloadResponse(200, b"bad"),
                FakeDownloadResponse(200, b"bad"),
                FakeDownloadResponse(200, b"bad"),
            ])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch("backend.crawlers.zsxq_file_downloader.time.sleep"):
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
                )

            self.assertFalse(result)
            self.assertEqual(3, len(session.get_calls))
            self.assertEqual((101, "failed", None, "size_mismatch"), downloader.file_db.status_updates[-1][:4])
            self.assertFalse((Path(temp_dir) / "memo.pdf").exists())
            self.assertFalse((Path(temp_dir) / "memo.pdf.part").exists())

    def test_handle_download_stop_preserves_status_log_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "memo.pdf.part"
            temp_path.write_bytes(b"memo")
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.file_db = FakeDownloadFileDb()
            downloader.logs = []
            downloader.log = downloader.logs.append

            ZSXQFileDownloader._handle_download_stop(downloader, 101, str(temp_path))

            self.assertEqual(
                (101, "failed", None, "stopped", "下载过程中被停止"),
                downloader.file_db.status_updates[-1],
            )
            self.assertFalse(temp_path.exists())
            self.assertEqual(["🛑 下载过程中被停止"], downloader.logs)

    def test_apply_download_intervals_preserves_long_sleep_side_effects(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.current_batch_count = 10
        downloader.files_per_batch = 10
        downloader.download_interval = 1
        downloader.long_sleep_interval = 60
        downloader.logs = []
        downloader.log = downloader.logs.append

        with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
            ZSXQFileDownloader._apply_download_intervals(downloader)

        sleep.assert_called_once_with(60)
        self.assertEqual(0, downloader.current_batch_count)
        self.assertEqual(
            [
                "⏰ 已下载 10 个文件，开始长休眠 60 秒...",
                "😴 长休眠结束，继续下载",
            ],
            downloader.logs,
        )

    def test_get_download_url_redacts_signed_url_in_stdout(self):
        session = FakeDownloadSession([FakeJsonResponse()])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.session = session
        downloader.group_id = "group-1"
        downloader.cookie = "cookie"
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {}
        downloader.log = lambda message: None

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader.get_download_url(downloader, 101)

        self.assertEqual("https://files.example/signed-token", result)
        self.assertIn("<redacted>", output.getvalue())
        self.assertNotIn("signed-token", output.getvalue())

    def test_get_download_url_1030_does_not_stop_whole_task(self):
        session = FakeDownloadSession([FakeFailedJsonResponse(1030, "mobile only")])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.session = session
        downloader.group_id = "group-1"
        downloader.cookie = "cookie"
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {}
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.stop_flag = False

        result = ZSXQFileDownloader.get_download_url(downloader, 101)

        self.assertIsNone(result)
        self.assertFalse(downloader.stop_flag)
        self.assertEqual({"code": 1030, "message": "mobile only"}, downloader.last_download_url_error)


if __name__ == "__main__":
    unittest.main()
