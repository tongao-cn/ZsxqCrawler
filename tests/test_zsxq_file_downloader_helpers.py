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
    latest_file_create_time_query,
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
    time_collection_final_summary,
    time_dedupe_page_plan,
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


class QueryCaptureFileDb:
    def __init__(self, rows=()):
        self.cursor = self
        self.rows = list(rows)
        self.executed = []

    def execute(self, query, params=()):
        self.executed.append((query, tuple(params)))
        return self

    def fetchall(self):
        return list(self.rows)


class TimeDedupeFileDb:
    def __init__(self, latest_time, initial_files=10, final_files=11):
        self.cursor = self
        self.latest_time = latest_time
        self.initial_files = initial_files
        self.final_files = final_files
        self.stats_calls = 0
        self.executed = []
        self.imported_responses = []

    def execute(self, query, params=()):
        self.executed.append((query, tuple(params)))
        return self

    def fetchone(self):
        return (self.latest_time,)

    def get_database_stats(self):
        self.stats_calls += 1
        if self.stats_calls == 1:
            return {"files": self.initial_files}
        return {"files": self.final_files, "topics": 2}

    def import_file_response(self, data):
        self.imported_responses.append(data)
        return {"files": 1, "topics": 2}


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


class FakeFailingBodyDownloadResponse(FakeDownloadResponse):
    def __init__(self, headers=None):
        response_headers = {"content-length": "4"}
        if headers:
            response_headers.update(headers)
        super().__init__(200, b"", headers=response_headers)

    def iter_content(self, chunk_size=8192):
        yield b"pa"
        raise RuntimeError("stream down")


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

    def test_collect_files_by_time_filters_old_files_and_stops_after_mixed_page(self):
        files = [
            {"file": {"file_id": 101, "create_time": "2026-05-03T10:00:00"}},
            {"file": {"file_id": 102, "create_time": "2026-05-01T10:00:00"}},
        ]
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb("2026-05-02T00:00:00")
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {"resp_data": {"index": "next-page", "files": list(files)}}

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        imported_files = downloader.file_db.imported_responses[0]["resp_data"]["files"]
        self.assertEqual([101], [item["file"]["file_id"] for item in imported_files])
        self.assertEqual(1, len(downloader.fetch_calls))
        self.assertEqual([{"count": 20, "index": None, "sort": "by_create_time"}], downloader.fetch_calls)
        self.assertEqual(1, len(downloader.file_db.executed))
        latest_time_query, latest_time_params = downloader.file_db.executed[0]
        self.assertIn("SELECT MAX(create_time) FROM files", latest_time_query)
        self.assertIn("group_id = ?", latest_time_query)
        self.assertIn("create_time IS NOT NULL AND create_time != ''", latest_time_query)
        self.assertEqual((511,), latest_time_params)
        self.assertEqual(2, downloader.file_db.stats_calls)
        self.assertEqual(11, stats["total_files"])
        self.assertEqual(1, stats["new_files"])
        self.assertEqual(1, stats["pages"])
        self.assertEqual(1, stats["files"])
        self.assertEqual(2, stats["topics"])
        self.assertIn("   📅 数据库最新文件时间: 2026-05-02T00:00:00", downloader.logs)
        self.assertIn("   📊 时间分析: 新于数据库1个, 旧于或等于数据库1个", downloader.logs)
        self.assertIn("   🔄 过滤掉1个旧数据，只插入1个新数据", downloader.logs)
        self.assertIn("   ✅ 已插入本页新数据，后续页面均为旧数据，停止收集", downloader.logs)
        self.assertNotIn("   ⏭️ 下一页时间戳: next-page", downloader.logs)


class FileDownloaderBatchDownloadTests(unittest.TestCase):
    def _downloader_for_batch(self, files):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {"resp_data": {"files": files, "index": None}}

        downloader.fetch_file_list = fetch_file_list
        return downloader

    def test_download_files_batch_preserves_result_stats_payloads_and_delays(self):
        files = [
            {"file": {"id": 101, "name": "skip.pdf"}},
            {"file": {"id": 102, "name": "ok.pdf"}},
            {"file": {"id": 103, "name": "bad.pdf"}},
        ]
        downloader = self._downloader_for_batch(files)
        payloads = []
        results = ["skipped", True, False]
        interval_events = []

        def download_file(file_info):
            payloads.append(file_info)
            return results.pop(0)

        downloader.download_file = download_file
        downloader.check_long_delay = lambda: interval_events.append("long")
        downloader.download_delay = lambda: interval_events.append("delay")

        stats = ZSXQFileDownloader.download_files_batch(downloader, max_files=2, start_index="start")

        self.assertEqual({"total_files": 3, "downloaded": 1, "skipped": 1, "failed": 1}, stats)
        self.assertEqual([{"count": 20, "index": "start"}], downloader.fetch_calls)
        self.assertEqual(files, payloads)
        self.assertEqual(["long", "delay"], interval_events)
        self.assertIn("📥 开始批量下载文件 (最多2个)", downloader.logs)
        self.assertIn("📋 当前批次: 3 个文件", downloader.logs)
        self.assertIn("【1/2】skip.pdf", downloader.logs)
        self.assertIn("【1/2】ok.pdf", downloader.logs)
        self.assertIn("【2/2】bad.pdf", downloader.logs)
        self.assertIn("   ⚠️ 文件已跳过，继续下一个", downloader.logs)
        self.assertEqual("   ❌ 失败: 1", downloader.logs[-1])


class FileDownloaderDatabaseDownloadTests(unittest.TestCase):
    def _downloader_for_query_capture(self, group_id="511", rows=()):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = group_id
        downloader.file_db = QueryCaptureFileDb(rows)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False
        return downloader

    def _compact_sql(self, sql):
        return " ".join(sql.split())

    def test_download_files_from_database_preserves_filtered_query_shape_and_legacy_order_by(self):
        downloader = self._downloader_for_query_capture()

        stats = ZSXQFileDownloader.download_files_from_database(
            downloader,
            max_files=5,
            status_filter="failed",
            start_date="2026-05-01",
            end_date="2026-05-07",
            order_by="create_time DESC",
        )

        query, params = downloader.file_db.executed[-1]
        compact_query = self._compact_sql(query)
        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertIn(
            "WHERE group_id = ? AND download_status = ? AND substr(create_time, 1, 10) >= ? "
            "AND substr(create_time, 1, 10) <= ?",
            compact_query,
        )
        self.assertIn("ORDER BY create_time DESC, download_count DESC", compact_query)
        self.assertTrue(compact_query.endswith("LIMIT ?"))
        self.assertEqual((511, "failed", "2026-05-01", "2026-05-07", 5), params)
        self.assertIn("   📌 下载排序: 按时间倒序", downloader.logs)

    def test_download_files_from_database_preserves_unfiltered_heat_sort_query_shape(self):
        downloader = self._downloader_for_query_capture(group_id="group-1")

        stats = ZSXQFileDownloader.download_files_from_database(
            downloader,
            status_filter="",
            sort_by="download_count",
        )

        query, params = downloader.file_db.executed[-1]
        compact_query = self._compact_sql(query)
        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertIn("WHERE group_id = ?", compact_query)
        self.assertNotIn("download_status = ?", compact_query)
        self.assertIn("ORDER BY download_count DESC, size ASC", compact_query)
        self.assertNotIn("LIMIT ?", compact_query)
        self.assertEqual(("group-1",), params)
        self.assertIn("   📌 下载排序: 按热度倒序", downloader.logs)

    def test_download_files_from_database_preserves_result_stats_payloads_and_delays(self):
        downloader = self._downloader_for_query_capture(
            rows=[
                (101, "skip.pdf", 2048, 7, "2026-05-03 10:00:00"),
                (102, "ok.pdf", 1024, 9, "2026-05-02 10:00:00"),
                (103, "bad.pdf", 512, 1, "2026-05-01 10:00:00"),
            ],
        )
        payloads = []
        results = ["skipped", True, False]
        interval_events = []

        def download_file(file_info):
            payloads.append(file_info)
            return results.pop(0)

        downloader.download_file = download_file
        downloader.check_long_delay = lambda: interval_events.append("long")
        downloader.download_delay = lambda: interval_events.append("delay")

        stats = ZSXQFileDownloader.download_files_from_database(downloader)

        self.assertEqual({"total_files": 3, "downloaded": 1, "skipped": 1, "failed": 1}, stats)
        self.assertEqual(
            [
                {"file": {"id": 101, "name": "skip.pdf", "size": 2048, "download_count": 7}},
                {"file": {"id": 102, "name": "ok.pdf", "size": 1024, "download_count": 9}},
                {"file": {"id": 103, "name": "bad.pdf", "size": 512, "download_count": 1}},
            ],
            payloads,
        )
        self.assertEqual(["long", "delay"], interval_events)
        self.assertIn("📋 找到 3 个待下载文件", downloader.logs)
        self.assertIn("【1/3】skip.pdf", downloader.logs)
        self.assertIn("   📊 文件ID: 101, 大小: 2.0KB, 下载次数: 7", downloader.logs)
        self.assertIn("   ⚠️ 文件已跳过", downloader.logs)
        self.assertIn("   ❌ 下载失败", downloader.logs)
        self.assertEqual("   ❌ 失败: 1", downloader.logs[-1])


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

    def test_time_dedupe_page_plan_flags_mixed_and_all_old_pages(self):
        mixed_plan = time_dedupe_page_plan(
            [
                {"file": {"file_id": 1, "create_time": "2026-05-03T00:00:00"}},
                {"file": {"file_id": 2, "create_time": "2026-05-01T00:00:00"}},
            ],
            "2026-05-02T00:00:00",
        )

        self.assertEqual([1], [item["file"]["file_id"] for item in mixed_plan["newer_files"]])
        self.assertEqual(1, mixed_plan["newer_count"])
        self.assertEqual(1, mixed_plan["older_count"])
        self.assertFalse(mixed_plan["should_stop_before_insert"])
        self.assertTrue(mixed_plan["should_filter_before_insert"])
        self.assertTrue(mixed_plan["should_stop_after_insert"])

        old_plan = time_dedupe_page_plan(
            [{"file": {"file_id": 3, "create_time": "2026-05-01T00:00:00"}}],
            "2026-05-02T00:00:00",
        )

        self.assertEqual([], old_plan["newer_files"])
        self.assertEqual(0, old_plan["newer_count"])
        self.assertEqual(1, old_plan["older_count"])
        self.assertTrue(old_plan["should_stop_before_insert"])
        self.assertFalse(old_plan["should_filter_before_insert"])
        self.assertFalse(old_plan["should_stop_after_insert"])

    def test_time_collection_final_summary_preserves_result_and_positive_log_items(self):
        total_imported_stats = empty_import_stats()
        total_imported_stats.update({"files": 2, "topics": 0, "users": 1})

        summary = time_collection_final_summary(
            {"files": 12, "topics": 3, "users": 0},
            initial_files=10,
            total_imported_stats=total_imported_stats,
            page_count=4,
        )

        self.assertEqual(12, summary["final_files"])
        self.assertEqual(2, summary["new_files"])
        self.assertEqual((("files", 2), ("users", 1)), summary["imported_items"])
        self.assertEqual((("files", 12), ("topics", 3)), summary["database_items"])
        self.assertEqual(
            {
                "total_files": 12,
                "new_files": 2,
                "pages": 4,
                **total_imported_stats,
            },
            summary["result"],
        )

    def test_latest_file_create_time_query_preserves_shape_and_params(self):
        query, params = latest_file_create_time_query(511)

        self.assertIn("SELECT MAX(create_time) FROM files", query)
        self.assertIn("group_id = ?", query)
        self.assertIn("create_time IS NOT NULL AND create_time != ''", query)
        self.assertEqual((511,), params)

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

    def test_download_file_without_file_id_logs_and_returns_before_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([])
            downloader = self._downloader_for_download(temp_dir, session)

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"name": "memo.pdf", "size": 4, "download_count": 2}},
            )

            self.assertFalse(result)
            self.assertEqual([], session.get_calls)
            self.assertEqual([], downloader.file_db.status_updates)
            self.assertEqual(
                [
                    "📥 准备下载文件:",
                    "   📄 名称: memo.pdf",
                    "   📊 大小: 4 bytes (0.00 MB)",
                    "   📈 下载次数: 2",
                    "   ❌ 文件缺少 file_id，无法下载",
                ],
                downloader.logs,
            )

    def test_prepare_download_file_target_preserves_logs_target_and_early_returns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.download_dir = temp_dir
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.check_stop = lambda: False

            prepared = ZSXQFileDownloader._prepare_download_file_target(
                downloader,
                {"file": {"id": 101, "name": "../memo?.pdf", "size": 4, "download_count": 2}},
            )

            self.assertEqual(
                (101, "../memo?.pdf", 4, "..memo.pdf", str(Path(temp_dir) / "..memo.pdf")),
                prepared,
            )
            self.assertEqual(
                [
                    "📥 准备下载文件:",
                    "   📄 名称: ../memo?.pdf",
                    "   📊 大小: 4 bytes (0.00 MB)",
                    "   📈 下载次数: 2",
                ],
                downloader.logs,
            )

            downloader.logs = []
            downloader.log = downloader.logs.append
            self.assertIsNone(
                ZSXQFileDownloader._prepare_download_file_target(
                    downloader,
                    {"file": {"name": "memo.pdf", "size": 4, "download_count": 2}},
                )
            )
            self.assertEqual(
                [
                    "📥 准备下载文件:",
                    "   📄 名称: memo.pdf",
                    "   📊 大小: 4 bytes (0.00 MB)",
                    "   📈 下载次数: 2",
                    "   ❌ 文件缺少 file_id，无法下载",
                ],
                downloader.logs,
            )

            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.check_stop = lambda: True
            self.assertIsNone(
                ZSXQFileDownloader._prepare_download_file_target(
                    downloader,
                    {"file": {"id": 102, "name": "stop.pdf", "size": 8, "download_count": 3}},
                )
            )
            self.assertEqual(
                [
                    "📥 准备下载文件:",
                    "   📄 名称: stop.pdf",
                    "   📊 大小: 8 bytes (0.00 MB)",
                    "   📈 下载次数: 3",
                    "🛑 下载任务被停止",
                ],
                downloader.logs,
            )

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

    def test_download_file_skips_existing_matching_file_without_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            existing_path = Path(temp_dir) / "memo.pdf"
            existing_path.write_bytes(b"memo")
            session = FakeDownloadSession([])
            downloader = self._downloader_for_download(temp_dir, session)

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
            )

            self.assertEqual("skipped", result)
            self.assertEqual([], session.get_calls)
            self.assertEqual(
                (101, "completed", str(existing_path)),
                downloader.file_db.status_updates[-1][:3],
            )
            self.assertIn("   ✅ 文件已存在且大小匹配，跳过下载", downloader.logs)

    def test_download_file_redownloads_existing_size_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            existing_path = Path(temp_dir) / "memo.pdf"
            existing_path.write_bytes(b"old")
            session = FakeDownloadSession([FakeDownloadResponse(200, b"memo")])
            downloader = self._downloader_for_download(temp_dir, session)

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
            )

            self.assertTrue(result)
            self.assertEqual(b"memo", existing_path.read_bytes())
            self.assertEqual(1, len(session.get_calls))
            self.assertEqual(
                (101, "completed", str(existing_path)),
                downloader.file_db.status_updates[-1][:3],
            )
            self.assertIn("   ⚠️ 文件已存在但大小不匹配，重新下载", downloader.logs)

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

    def test_download_file_keeps_named_file_despite_content_disposition(self):
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
                {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
            )

            expected_path = str(Path(temp_dir) / "memo.pdf")
            self.assertTrue(result)
            self.assertTrue((Path(temp_dir) / "memo.pdf").exists())
            self.assertFalse((Path(temp_dir) / "real.pdf").exists())
            self.assertEqual((101, "completed", expected_path), downloader.file_db.status_updates[-1][:3])
            self.assertNotIn("   📝 从响应头获取到真实文件名: real.pdf", downloader.logs)

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

    def test_download_file_finalizes_success_with_status_counters_logs_and_interval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([FakeDownloadResponse(200, b"memo")])
            downloader = self._downloader_for_download(temp_dir, session)
            interval_snapshots = []

            def apply_intervals():
                interval_snapshots.append(
                    (downloader.download_count, downloader.current_batch_count)
                )

            downloader._apply_download_intervals = apply_intervals

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
            )

            expected_path = str(Path(temp_dir) / "memo.pdf")
            self.assertTrue(result)
            self.assertEqual(b"memo", (Path(temp_dir) / "memo.pdf").read_bytes())
            self.assertFalse((Path(temp_dir) / "memo.pdf.part").exists())
            self.assertEqual((101, "completed", expected_path), downloader.file_db.status_updates[-1][:3])
            self.assertEqual(1, downloader.download_count)
            self.assertEqual(1, downloader.current_batch_count)
            self.assertEqual([(1, 1)], interval_snapshots)
            self.assertIn("   ✅ 下载完成: memo.pdf", downloader.logs)
            self.assertIn(f"   💾 保存路径: {expected_path}", downloader.logs)

    def test_complete_successful_download_preserves_side_effect_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "memo.pdf.part"
            file_path = Path(temp_dir) / "memo.pdf"
            temp_path.write_bytes(b"memo")
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.file_db = FakeDownloadFileDb()
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.download_count = 3
            downloader.current_batch_count = 4
            interval_snapshots = []

            def apply_intervals():
                interval_snapshots.append(
                    (downloader.download_count, downloader.current_batch_count)
                )

            downloader._apply_download_intervals = apply_intervals

            ZSXQFileDownloader._complete_successful_download(
                downloader,
                101,
                "memo.pdf",
                str(file_path),
                str(temp_path),
            )

            self.assertEqual(b"memo", file_path.read_bytes())
            self.assertFalse(temp_path.exists())
            self.assertEqual(
                (101, "completed", str(file_path), None, None),
                downloader.file_db.status_updates[-1],
            )
            self.assertEqual(4, downloader.download_count)
            self.assertEqual(5, downloader.current_batch_count)
            self.assertEqual([(4, 5)], interval_snapshots)
            self.assertEqual(
                [
                    "   ✅ 下载完成: memo.pdf",
                    f"   💾 保存路径: {file_path}",
                ],
                downloader.logs,
            )

    def test_apply_response_filename_override_preserves_override_and_noop_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.download_dir = temp_dir
            downloader.logs = []
            downloader.log = downloader.logs.append

            override = ZSXQFileDownloader._apply_response_filename_override(
                downloader,
                "file_101",
                101,
                {"content-disposition": 'attachment; filename="real?.pdf"'},
            )
            noop = ZSXQFileDownloader._apply_response_filename_override(
                downloader,
                "memo.pdf",
                102,
                {"content-disposition": 'attachment; filename="ignored.pdf"'},
            )

            self.assertEqual(("real?.pdf", "real.pdf", str(Path(temp_dir) / "real.pdf")), override)
            self.assertIsNone(noop)
            self.assertEqual(["   📝 从响应头获取到真实文件名: real?.pdf"], downloader.logs)

    def test_record_download_http_failure_preserves_error_detail_and_log(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append

        failure_500 = ZSXQFileDownloader._record_download_http_failure(downloader, 500)
        failure_404 = ZSXQFileDownloader._record_download_http_failure(downloader, 404)

        self.assertEqual(("http_status", "HTTP 500"), failure_500)
        self.assertEqual(("http_status", "HTTP 404"), failure_404)
        self.assertEqual(
            ["   ❌ 下载失败: HTTP 500", "   ❌ 下载失败: HTTP 404"],
            downloader.logs,
        )

    def test_record_download_exception_preserves_error_detail_log_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "memo.pdf"
            partial_path = Path(f"{file_path}.part")
            partial_path.write_bytes(b"pa")
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.logs = []
            downloader.log = downloader.logs.append

            failure_with_partial = ZSXQFileDownloader._record_download_exception(
                downloader,
                RuntimeError("stream down"),
                str(file_path),
            )
            failure_without_partial = ZSXQFileDownloader._record_download_exception(
                downloader,
                ValueError("no part"),
                str(file_path),
            )

            self.assertEqual(("download_exception", "stream down"), failure_with_partial)
            self.assertEqual(("download_exception", "no part"), failure_without_partial)
            self.assertFalse(partial_path.exists())
            self.assertEqual(
                [
                    "   ❌ 下载异常: stream down",
                    "   🗑️ 删除不完整文件",
                    "   ❌ 下载异常: no part",
                ],
                downloader.logs,
            )

    def test_wait_before_download_retry_preserves_log_and_delay(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append

        with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
            ZSXQFileDownloader._wait_before_download_retry(downloader, 2, 5)

        sleep.assert_called_once_with(4)
        self.assertEqual(
            ["   🔄 文件下载重试 3/5，等待 4 秒..."],
            downloader.logs,
        )

    def test_request_download_response_preserves_stream_timeout_and_log(self):
        response = FakeDownloadResponse(200, b"memo")
        session = FakeDownloadSession([response])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.session = session
        downloader.logs = []
        downloader.log = downloader.logs.append

        requested_response = ZSXQFileDownloader._request_download_response(
            downloader,
            "https://download.test/101",
        )

        self.assertIs(response, requested_response)
        self.assertEqual([("https://download.test/101", 300, True)], session.get_calls)
        self.assertEqual(["   🚀 开始下载..."], downloader.logs)

    def test_handle_download_response_preserves_override_http_failure_and_success_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.download_dir = temp_dir
            downloader.file_db = FakeDownloadFileDb()
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.check_stop = lambda: False
            downloader.download_count = 0
            downloader.current_batch_count = 0
            downloader._apply_download_intervals = lambda: None

            http_failure = ZSXQFileDownloader._handle_download_response(
                downloader,
                FakeDownloadResponse(
                    500,
                    headers={"content-disposition": 'attachment; filename="real?.pdf"'},
                ),
                101,
                "file_101",
                4,
                "file_101",
                str(Path(temp_dir) / "file_101"),
            )

            self.assertEqual(
                (
                    None,
                    ("http_status", "HTTP 500"),
                    "real?.pdf",
                    "real.pdf",
                    str(Path(temp_dir) / "real.pdf"),
                ),
                http_failure,
            )
            self.assertEqual(
                ["   📝 从响应头获取到真实文件名: real?.pdf", "   ❌ 下载失败: HTTP 500"],
                downloader.logs,
            )
            self.assertEqual([], downloader.file_db.status_updates)

            downloader.logs = []
            downloader.log = downloader.logs.append
            success_path = Path(temp_dir) / "memo.pdf"
            success = ZSXQFileDownloader._handle_download_response(
                downloader,
                FakeDownloadResponse(200, b"memo"),
                102,
                "memo.pdf",
                4,
                "memo.pdf",
                str(success_path),
            )

            self.assertEqual((True, None, "memo.pdf", "memo.pdf", str(success_path)), success)
            self.assertEqual(b"memo", success_path.read_bytes())
            self.assertEqual((102, "completed", str(success_path)), downloader.file_db.status_updates[-1][:3])

    def test_prepare_download_body_target_preserves_sizes_temp_path_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "memo.pdf"
            partial_path = Path(f"{file_path}.part")
            partial_path.write_bytes(b"stale")
            downloader = object.__new__(ZSXQFileDownloader)

            prepared = ZSXQFileDownloader._prepare_download_body_target(
                downloader,
                {"content-length": "8"},
                4,
                str(file_path),
            )
            fallback_prepared = ZSXQFileDownloader._prepare_download_body_target(
                downloader,
                {"content-length": "8"},
                0,
                str(Path(temp_dir) / "unknown.bin"),
            )

            self.assertEqual((8, 4, str(partial_path)), prepared)
            self.assertFalse(partial_path.exists())
            self.assertEqual(
                (8, 8, str(Path(temp_dir) / "unknown.bin.part")),
                fallback_prepared,
            )

    def test_handle_successful_download_response_preserves_completion_retry_and_stop_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "memo.pdf"
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.file_db = FakeDownloadFileDb()
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.check_stop = lambda: False
            downloader.download_count = 0
            downloader.current_batch_count = 0
            interval_snapshots = []
            downloader._apply_download_intervals = lambda: interval_snapshots.append(
                (downloader.download_count, downloader.current_batch_count)
            )

            completed = ZSXQFileDownloader._handle_successful_download_response(
                downloader,
                FakeDownloadResponse(200, b"memo"),
                101,
                4,
                "memo.pdf",
                str(file_path),
            )

            self.assertEqual((True, None), completed)
            self.assertEqual(b"memo", file_path.read_bytes())
            self.assertFalse(Path(f"{file_path}.part").exists())
            self.assertEqual((101, "completed", str(file_path)), downloader.file_db.status_updates[-1][:3])
            self.assertEqual((1, 1), (downloader.download_count, downloader.current_batch_count))
            self.assertEqual([(1, 1)], interval_snapshots)

            mismatch_path = Path(temp_dir) / "mismatch.pdf"
            downloader.logs = []
            downloader.log = downloader.logs.append
            mismatch = ZSXQFileDownloader._handle_successful_download_response(
                downloader,
                FakeDownloadResponse(200, b"bad"),
                102,
                4,
                "mismatch.pdf",
                str(mismatch_path),
            )

            self.assertEqual((None, ("size_mismatch", "文件大小不匹配: 预期4, 实际3")), mismatch)
            self.assertFalse(mismatch_path.exists())
            self.assertFalse(Path(f"{mismatch_path}.part").exists())
            self.assertEqual(
                ["   📊 进度: 100.0% (3/3 bytes)", "   ⚠️ 文件大小不匹配: 预期4, 实际3"],
                downloader.logs,
            )

            stopped_path = Path(temp_dir) / "stopped.pdf"
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.check_stop = lambda: True

            with patch(
                "backend.crawlers.zsxq_file_downloader.remove_partial_download",
                return_value=True,
            ) as remove_partial:
                stopped = ZSXQFileDownloader._handle_successful_download_response(
                    downloader,
                    FakeDownloadResponse(200, b"stop"),
                    103,
                    4,
                    "stopped.pdf",
                    str(stopped_path),
                )

            self.assertEqual((False, None), stopped)
            self.assertFalse(stopped_path.exists())
            self.assertEqual(2, remove_partial.call_count)
            remove_partial.assert_called_with(str(Path(f"{stopped_path}.part")))
            self.assertEqual(
                (103, "failed", None, "stopped", "下载过程中被停止"),
                downloader.file_db.status_updates[-1],
            )

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

    def test_download_file_marks_failed_with_download_url_api_error_detail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([])
            downloader = self._downloader_for_download(temp_dir, session)
            downloader.get_download_url = lambda file_id: None
            downloader.last_download_url_error = {"code": 1030, "message": "mobile only"}

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
            )

            self.assertFalse(result)
            self.assertEqual([], session.get_calls)
            self.assertEqual(
                (101, "failed", None, "1030", "mobile only"),
                downloader.file_db.status_updates[-1],
            )
            self.assertIn("   ❌ 无法获取下载链接", downloader.logs)

    def test_get_download_url_or_mark_unavailable_preserves_success_and_failure_paths(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = FakeDownloadFileDb()
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.last_download_url_error = None
        requested_file_ids = []

        def successful_url(file_id):
            requested_file_ids.append(file_id)
            return f"https://download.test/{file_id}"

        downloader.get_download_url = successful_url
        self.assertEqual(
            "https://download.test/101",
            ZSXQFileDownloader._get_download_url_or_mark_unavailable(downloader, 101),
        )
        self.assertEqual([101], requested_file_ids)
        self.assertEqual([], downloader.file_db.status_updates)
        self.assertEqual([], downloader.logs)

        downloader.last_download_url_error = {"code": 1030, "message": "mobile only"}
        downloader.get_download_url = lambda file_id: None
        self.assertIsNone(
            ZSXQFileDownloader._get_download_url_or_mark_unavailable(downloader, 102)
        )
        self.assertEqual(
            (102, "failed", None, "1030", "mobile only"),
            downloader.file_db.status_updates[-1],
        )
        self.assertEqual(["   ❌ 无法获取下载链接"], downloader.logs)

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

    def test_download_file_requests_response_with_stream_timeout_and_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([FakeDownloadResponse(200, b"memo")])
            downloader = self._downloader_for_download(temp_dir, session)

            result = ZSXQFileDownloader.download_file(
                downloader,
                {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
            )

            self.assertTrue(result)
            self.assertEqual(
                [("https://download.test/101", 300, True)],
                session.get_calls,
            )
            self.assertIn("   🚀 开始下载...", downloader.logs)

    def test_download_file_clears_existing_partial_file_before_successful_body_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            partial_path = Path(temp_dir) / "memo.pdf.part"
            partial_path.write_bytes(b"stale")
            session = FakeDownloadSession([FakeDownloadResponse(200, b"memo")])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch(
                "backend.crawlers.zsxq_file_downloader.remove_partial_download",
                wraps=remove_partial_download,
            ) as remove_partial:
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
                )

            self.assertTrue(result)
            remove_partial.assert_called_once_with(str(partial_path))
            self.assertEqual(b"memo", (Path(temp_dir) / "memo.pdf").read_bytes())
            self.assertFalse(partial_path.exists())

    def test_download_file_preserves_retry_wait_log_and_delay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeDownloadResponse(500),
                FakeDownloadResponse(200, b"memo"),
            ])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
                )

            self.assertTrue(result)
            sleep.assert_called_once_with(2)
            self.assertIn("   🔄 文件下载重试 2/3，等待 2 秒...", downloader.logs)
            self.assertLess(
                downloader.logs.index("   ❌ 下载失败: HTTP 500"),
                downloader.logs.index("   🔄 文件下载重试 2/3，等待 2 秒..."),
            )

    def test_download_file_applies_response_filename_override_before_http_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeDownloadResponse(
                    500,
                    headers={"content-disposition": 'attachment; filename="real?.pdf"'},
                ),
                FakeDownloadResponse(500),
                FakeDownloadResponse(500),
            ])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch("backend.crawlers.zsxq_file_downloader.time.sleep"):
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "file_101", "size": 4, "download_count": 0}},
                )

            self.assertFalse(result)
            self.assertEqual(3, len(session.get_calls))
            self.assertEqual(
                (101, "failed", None, "http_status", "HTTP 500"),
                downloader.file_db.status_updates[-1],
            )
            self.assertLess(
                downloader.logs.index("   📝 从响应头获取到真实文件名: real?.pdf"),
                downloader.logs.index("   ❌ 下载失败: HTTP 500"),
            )
            self.assertFalse((Path(temp_dir) / "real.pdf").exists())

    def test_download_file_marks_final_failure_after_http_retries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeDownloadResponse(500),
                FakeDownloadResponse(500),
                FakeDownloadResponse(500),
            ])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch("backend.crawlers.zsxq_file_downloader.time.sleep"):
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
                )

            self.assertFalse(result)
            self.assertEqual(3, len(session.get_calls))
            self.assertEqual(
                (101, "failed", None, "http_status", "HTTP 500"),
                downloader.file_db.status_updates[-1],
            )
            self.assertIn("   🚫 文件下载重试3次仍失败: HTTP 500", downloader.logs)
            self.assertFalse((Path(temp_dir) / "memo.pdf").exists())
            self.assertFalse((Path(temp_dir) / "memo.pdf.part").exists())

    def test_download_file_retries_and_marks_final_failure_after_http_404(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeDownloadResponse(404),
                FakeDownloadResponse(404),
                FakeDownloadResponse(404),
            ])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch("backend.crawlers.zsxq_file_downloader.time.sleep"):
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
                )

            self.assertFalse(result)
            self.assertEqual(3, len(session.get_calls))
            self.assertEqual(
                (101, "failed", None, "http_status", "HTTP 404"),
                downloader.file_db.status_updates[-1],
            )
            self.assertIn("   ❌ 下载失败: HTTP 404", downloader.logs)
            self.assertIn("   🚫 文件下载重试3次仍失败: HTTP 404", downloader.logs)

    def test_download_file_cleans_partial_file_after_body_exception_retries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeFailingBodyDownloadResponse(),
                FakeFailingBodyDownloadResponse(),
                FakeFailingBodyDownloadResponse(),
            ])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch("backend.crawlers.zsxq_file_downloader.time.sleep"):
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
                )

            self.assertFalse(result)
            self.assertEqual(3, len(session.get_calls))
            self.assertEqual(
                (101, "failed", None, "download_exception", "stream down"),
                downloader.file_db.status_updates[-1],
            )
            self.assertIn("   ❌ 下载异常: stream down", downloader.logs)
            self.assertIn("   🗑️ 删除不完整文件", downloader.logs)
            self.assertIn("   🚫 文件下载重试3次仍失败: stream down", downloader.logs)
            self.assertFalse((Path(temp_dir) / "memo.pdf").exists())
            self.assertFalse((Path(temp_dir) / "memo.pdf.part").exists())

    def test_download_file_cleans_overridden_partial_file_after_body_exception(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            override_header = {"content-disposition": 'attachment; filename="real.pdf"'}
            session = FakeDownloadSession([
                FakeFailingBodyDownloadResponse(headers=override_header),
                FakeFailingBodyDownloadResponse(headers=override_header),
                FakeFailingBodyDownloadResponse(headers=override_header),
            ])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch("backend.crawlers.zsxq_file_downloader.time.sleep"):
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "file_101", "size": 4, "download_count": 0}},
                )

            self.assertFalse(result)
            self.assertEqual(
                (101, "failed", None, "download_exception", "stream down"),
                downloader.file_db.status_updates[-1],
            )
            self.assertIn("   📝 从响应头获取到真实文件名: real.pdf", downloader.logs)
            self.assertFalse((Path(temp_dir) / "file_101.part").exists())
            self.assertFalse((Path(temp_dir) / "real.pdf.part").exists())

    def test_mark_download_url_unavailable_preserves_default_and_api_error_details(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = FakeDownloadFileDb()
        downloader.logs = []
        downloader.log = downloader.logs.append

        downloader.last_download_url_error = None
        ZSXQFileDownloader._mark_download_url_unavailable(downloader, 101)

        downloader.last_download_url_error = {"code": 1030, "message": "mobile only"}
        ZSXQFileDownloader._mark_download_url_unavailable(downloader, 102)

        self.assertEqual(
            (101, "failed", None, "download_url_unavailable", "无法获取下载链接"),
            downloader.file_db.status_updates[0],
        )
        self.assertEqual(
            (102, "failed", None, "1030", "mobile only"),
            downloader.file_db.status_updates[1],
        )
        self.assertEqual(
            ["   ❌ 无法获取下载链接", "   ❌ 无法获取下载链接"],
            downloader.logs,
        )

    def test_mark_download_failed_after_retries_preserves_error_detail_defaults(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = FakeDownloadFileDb()
        downloader.logs = []
        downloader.log = downloader.logs.append

        ZSXQFileDownloader._mark_download_failed_after_retries(
            downloader,
            101,
            3,
            "http_status",
            "HTTP 500",
        )
        ZSXQFileDownloader._mark_download_failed_after_retries(
            downloader,
            102,
            3,
            None,
            None,
        )

        self.assertEqual(
            (101, "failed", None, "http_status", "HTTP 500"),
            downloader.file_db.status_updates[0],
        )
        self.assertEqual(
            (102, "failed", None, "download_failed", "文件下载失败"),
            downloader.file_db.status_updates[1],
        )
        self.assertEqual(
            [
                "   🚫 文件下载重试3次仍失败: HTTP 500",
                "   🚫 文件下载重试3次仍失败: None",
            ],
            downloader.logs,
        )

    def test_download_file_retries_after_size_mismatch_before_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeDownloadResponse(200, b"bad"),
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
            self.assertEqual(
                (101, "completed", str(Path(temp_dir) / "memo.pdf")),
                downloader.file_db.status_updates[-1][:3],
            )
            self.assertEqual(b"memo", (Path(temp_dir) / "memo.pdf").read_bytes())
            self.assertFalse((Path(temp_dir) / "memo.pdf.part").exists())
            self.assertIn("   ⚠️ 文件大小不匹配: 预期4, 实际3", downloader.logs)

    def test_handle_download_size_mismatch_preserves_cleanup_and_noop_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.logs = []
            downloader.log = downloader.logs.append

            mismatch_path = Path(temp_dir) / "mismatch.pdf.part"
            mismatch_path.write_bytes(b"bad")
            mismatch_detail = ZSXQFileDownloader._handle_download_size_mismatch(
                downloader,
                4,
                str(mismatch_path),
            )

            matching_path = Path(temp_dir) / "matching.pdf.part"
            matching_path.write_bytes(b"memo")
            matching_detail = ZSXQFileDownloader._handle_download_size_mismatch(
                downloader,
                4,
                str(matching_path),
            )

            self.assertEqual(
                ("size_mismatch", "文件大小不匹配: 预期4, 实际3"),
                mismatch_detail,
            )
            self.assertFalse(mismatch_path.exists())
            self.assertIsNone(matching_detail)
            self.assertTrue(matching_path.exists())
            self.assertEqual(["   ⚠️ 文件大小不匹配: 预期4, 实际3"], downloader.logs)

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
