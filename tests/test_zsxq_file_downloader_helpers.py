import unittest
import tempfile
import csv
import contextlib
import datetime
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.crawlers.zsxq_file_downloader import (
    BatchDownloadFileItemTarget,
    BatchDownloadNextIndexTarget,
    BatchDownloadPageFilesTarget,
    BatchDownloadResultTarget,
    BatchDownloadTarget,
    DownloadAttemptResult,
    DownloadAttemptTarget,
    DownloadBodyFinalizationDecisionTarget,
    DownloadBodyFinalizationTarget,
    DownloadBodyPreparationTarget,
    DownloadBodyResponseTarget,
    DownloadBodyResult,
    DownloadBodyTarget,
    DownloadBodyWriteTarget,
    DownloadCompletionTarget,
    DownloadExceptionTarget,
    DownloadFailureDetail,
    DownloadFileResponseRequestTarget,
    DownloadFinalFailureTarget,
    DownloadFileTarget,
    DownloadHttpFailureTarget,
    DownloadIntervalPlanTarget,
    DownloadIntervalValues,
    DownloadResponseTarget,
    DownloadRetryDecision,
    DownloadRetryLoopAttemptTarget,
    DownloadRetryState,
    DownloadSizeMismatchTarget,
    DownloadStopTarget,
    DownloadUrlResponseDecision,
    DownloadUrlRetryLoopTarget,
    DownloadUrlUnavailableTarget,
    ExistingDownloadTarget,
    ResponseFilenameOverrideTarget,
    ZSXQFileDownloader,
    _database_stats_time_range,
    _database_stats_total_size,
    _file_collection_log_id,
    _latest_file_create_time,
)
from backend.crawlers.zsxq_file_downloader_helpers import (
    API_FAILURE_NON_RETRY,
    API_FAILURE_PERMISSION_DENIED_1030,
    API_FAILURE_RETRY,
    API_FAILURE_RETRY_EXHAUSTED,
    HTTP_FAILURE_NON_RETRY,
    HTTP_FAILURE_RETRY,
    HTTP_FAILURE_RETRY_EXHAUSTED,
    add_file_collection_page_stats,
    add_import_stats,
    api_retry_user_agent_message,
    api_retry_wait_message,
    api_failure_detail,
    batch_download_completion_messages,
    batch_download_empty_page_message,
    batch_download_fetch_failed_message,
    batch_download_file_stop_message,
    batch_download_initial_stop_message,
    batch_download_item_message,
    batch_download_loop_stop_message,
    batch_download_next_page_plan,
    batch_download_page_files_message,
    batch_download_skipped_message,
    batch_download_start_messages,
    classify_api_failure,
    classify_http_failure,
    clean_cookie_result,
    content_disposition_filename,
    database_download_completion_messages,
    database_download_effective_last_days,
    database_download_filter_messages,
    database_download_file_info,
    database_download_start_messages,
    database_download_time_range_message,
    database_stats_api_response_query,
    database_stats_table_emoji,
    database_stats_time_range_query,
    database_stats_total_size_query,
    database_time_range_query,
    database_time_range_result,
    date_range_collection_start_messages,
    download_exception_detail,
    download_expected_size,
    download_final_failure_detail,
    download_http_failure_detail,
    download_progress_message,
    download_url_failure_detail,
    download_file_data,
    download_interval_plan,
    download_query_group_id,
    download_result_stats,
    download_settings_display_lines,
    download_target_path,
    download_url_api_failure_plan,
    empty_import_stats,
    existing_file_matches,
    file_collection_completion_messages,
    file_collection_empty_page_message,
    file_collection_exception_message,
    file_collection_fetch_failed_messages,
    file_collection_interrupted_message,
    file_collection_log_insert_query,
    file_collection_log_update_query,
    file_collection_next_page_plan,
    file_collection_page_files_message,
    file_collection_page_import_messages,
    file_collection_page_message,
    file_collection_page_stored_message,
    file_collection_start_message,
    file_collection_stats,
    file_collection_storage_failed_message,
    file_list_api_failure_plan,
    file_list_item_display_lines,
    file_list_next_index_message,
    file_list_request_params,
    file_list_response_page,
    file_list_start_messages,
    download_url_success_plan,
    filter_files_newer_than,
    has_retry_attempt_remaining,
    http_failure_plan,
    incremental_collection_empty_database_message,
    incremental_collection_missing_time_message,
    incremental_collection_start_index_message,
    incremental_collection_start_message,
    incremental_collection_status_messages,
    incremental_collection_target_message,
    incremental_collection_timestamp_failure_messages,
    incremental_start_index,
    is_retryable_api_error,
    is_retryable_http_status,
    json_decode_failure_plan,
    latest_file_create_time_query,
    normalize_date_range,
    page_crosses_stop_before,
    partial_download_path,
    parse_create_time,
    remove_partial_download,
    download_retry_wait,
    download_size_mismatch_detail,
    download_total_size,
    request_exception_plan,
    retry_exhausted_message,
    risk_event_header_user_agent,
    risk_event_header_profile_label,
    risk_event_row,
    risk_event_user_agent_label,
    sec_ch_ua_for_user_agent,
    safe_download_filename,
    should_retry_api_error,
    should_retry_http_status,
    should_log_full_response,
    stealth_accept_languages,
    stealth_base_headers,
    stealth_optional_headers,
    stealth_platforms,
    stealth_request_id_header_value,
    stealth_timestamp_header_value,
    stealth_user_agents,
    summarize_page_time_range,
    time_dedupe_page_messages,
    time_collection_database_status_message,
    time_collection_empty_page_message,
    time_collection_exception_message,
    time_collection_fetch_failed_messages,
    time_collection_initial_stop_message,
    time_collection_interrupted_message,
    time_collection_latest_file_time_message,
    time_collection_loop_stop_message,
    time_collection_page_import_messages,
    time_collection_page_files_message,
    time_collection_page_message,
    time_collection_page_time_range_message,
    time_collection_storage_failed_message,
    time_collection_stop_before_boundary_message,
    time_collection_final_summary,
    time_collection_mode,
    time_collection_next_page_plan,
    time_collection_start_messages,
    time_collection_summary_messages,
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


class CollectAllFileDb:
    def __init__(self):
        self.cursor = self
        self.conn = self
        self.executed = []
        self.commits = 0
        self.imported_responses = []

    def execute(self, query, params=()):
        self.executed.append((query, tuple(params)))
        return self

    def fetchone(self):
        return (99,)

    def commit(self):
        self.commits += 1

    def import_file_response(self, data):
        self.imported_responses.append(data)
        return {"files": 2, "topics": 3, "users": 4}


class MissingCollectionLogIdFileDb(CollectAllFileDb):
    def fetchone(self):
        return None


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


class DatabaseTimeRangeFileDb:
    def __init__(self, stats, row=None):
        self.cursor = self
        self.stats = dict(stats)
        self.row = row
        self.executed = []
        self.stats_calls = 0
        self.fetchone_calls = 0

    def get_database_stats(self):
        self.stats_calls += 1
        return dict(self.stats)

    def execute(self, query, params=()):
        self.executed.append((query, tuple(params)))
        return self

    def fetchone(self):
        self.fetchone_calls += 1
        return self.row


class ShowDatabaseStatsFileDb:
    def __init__(self):
        self.cursor = self
        self.executed = []
        self.fetchone_results = [
            (2 * 1024 * 1024,),
            ("2026-05-01 09:00:00", "2026-05-07 10:00:00", 2),
        ]

    def get_database_stats(self):
        return {
            "files": 2,
            "topics": 3,
            "users": 0,
            "groups": 1,
            "unknown_table": 4,
        }

    def execute(self, query, params=()):
        self.executed.append((query, tuple(params)))
        return self

    def fetchone(self):
        return self.fetchone_results.pop(0)

    def fetchall(self):
        return [(1, 5), (0, 2)]


class EmptyShowDatabaseStatsFileDb:
    def __init__(self):
        self.cursor = self
        self.executed = []
        self.fetchone_results = [(0,), (None, None, 0)]

    def get_database_stats(self):
        return {
            "files": 0,
            "topics": 0,
            "users": 0,
            "groups": 0,
        }

    def execute(self, query, params=()):
        self.executed.append((query, tuple(params)))
        return self

    def fetchone(self):
        return self.fetchone_results.pop(0)

    def fetchall(self):
        return []


class FakeDownloaderPathManager:
    def __init__(self, group_dir):
        self.group_dir = group_dir
        self.group_ids = []

    def get_group_dir(self, group_id):
        self.group_ids.append(group_id)
        return self.group_dir


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


class FakeMissingDownloadUrlJsonResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "succeeded": True,
            "resp_data": {},
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


class FakeHttpDownloadUrlResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


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
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FileDownloaderPaginationTests(unittest.TestCase):
    def _incremental_downloader(self, time_info=None, stopped=False):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.collect_calls = []
        downloader.time_range_calls = 0
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: stopped

        def get_database_time_range():
            downloader.time_range_calls += 1
            return time_info

        def collect_files_by_time(*args, **kwargs):
            downloader.collect_calls.append((args, kwargs))
            return {"total_files": 7, "new_files": 3}

        downloader.get_database_time_range = get_database_time_range
        downloader.collect_files_by_time = collect_files_by_time
        return downloader

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
                    "files": [
                        {"file": {"file_id": 101, "create_time": "2026-02-01T10:00:00.000+0800"}}
                    ],
                },
            }

        downloader.fetch_file_list = fetch_file_list
        return downloader

    def test_file_collection_helpers_preserve_messages_and_stats_defaults(self):
        self.assertEqual(
            {"total_files": 0, "new_files": 0, "skipped_files": 0},
            file_collection_stats(),
        )
        stats = file_collection_stats()
        add_file_collection_page_stats(stats, 3, {})
        self.assertEqual({"total_files": 3, "new_files": 0, "skipped_files": 0}, stats)
        add_file_collection_page_stats(stats, 1, {"files": 2})
        self.assertEqual({"total_files": 4, "new_files": 2, "skipped_files": 0}, stats)
        self.assertEqual(
            ("INSERT INTO collection_log (start_time) VALUES (?) RETURNING id", ("start",)),
            file_collection_log_insert_query("start"),
        )
        update_query, update_params = file_collection_log_update_query(
            "end",
            {"total_files": 4, "new_files": 2, "skipped_files": 0},
            99,
        )
        self.assertIn("UPDATE collection_log SET", update_query)
        self.assertIn("status = 'completed'", update_query)
        self.assertEqual(("end", 4, 2, 99), update_params)
        self.assertEqual(
            {"has_next": True, "next_index": "next-index", "delay_min": 2, "delay_max": 5},
            file_collection_next_page_plan("next-index"),
        )
        self.assertEqual(
            {"has_next": False, "next_index": None, "delay_min": None, "delay_max": None},
            file_collection_next_page_plan(""),
        )
        self.assertEqual("\n📊 开始收集文件列表到数据库...", file_collection_start_message())
        self.assertEqual("\n📄 收集第2页文件列表...", file_collection_page_message(2))
        self.assertEqual(
            ("❌ 第2页获取失败，收集过程中断", "💾 已成功收集前1页的数据"),
            file_collection_fetch_failed_messages(2),
        )
        self.assertEqual("📭 没有更多文件", file_collection_empty_page_message())
        self.assertEqual("   📋 当前页面: 3 个文件", file_collection_page_files_message(3))
        self.assertEqual(
            ("      ✅ 新增文件: 0", "      📊 其他数据: 话题+0, 用户+0"),
            file_collection_page_import_messages({}),
        )
        self.assertEqual(
            "   ❌ 第4页存储失败: stable import failure",
            file_collection_storage_failed_message(4, RuntimeError("stable import failure")),
        )
        self.assertEqual("   ✅ 第4页存储完成", file_collection_page_stored_message(4))
        self.assertEqual("\n⏹️ 用户中断收集", file_collection_interrupted_message())
        self.assertEqual(
            "\n❌ 收集过程异常: boom",
            file_collection_exception_message(RuntimeError("boom")),
        )
        self.assertEqual(
            (
                "\n🎉 文件列表收集完成:",
                "   📊 处理文件数: 2",
                "   ✅ 新增文件: 1",
                "   ⚠️ 跳过重复: 0",
                "   📄 收集页数: 3",
            ),
            file_collection_completion_messages({"total_files": 2, "new_files": 1}, 3),
        )

    def test_file_collection_log_id_preserves_empty_and_truthy_row_semantics(self):
        self.assertIsNone(_file_collection_log_id(None))
        self.assertIsNone(_file_collection_log_id(()))
        self.assertIsNone(_file_collection_log_id((None,)))
        self.assertEqual("", _file_collection_log_id(("",)))
        self.assertEqual(0, _file_collection_log_id((0,)))
        self.assertEqual(99, _file_collection_log_id((99,)))
        self.assertEqual(99, _file_collection_log_id((99, "ignored")))

    def test_collect_all_files_preserves_entry_log_loop_update_and_summary_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        stats = {"total_files": 2, "new_files": 1, "skipped_files": 0}
        calls = []

        def print_message(message=""):
            calls.append(("print", message))

        def create_file_collection_log(downloader_self):
            self.assertIs(downloader, downloader_self)
            calls.append(("create_log",))
            return "log-1"

        def file_collection_stats_target():
            calls.append(("stats",))
            return stats

        def run_file_collection_loop(downloader_self, stats_arg):
            self.assertIs(downloader, downloader_self)
            self.assertIs(stats, stats_arg)
            calls.append(("loop", stats_arg))
            return 3

        def update_file_collection_log(downloader_self, stats_arg, log_id):
            self.assertIs(downloader, downloader_self)
            self.assertIs(stats, stats_arg)
            calls.append(("update", stats_arg, log_id))

        def completion_messages(stats_arg, page_count):
            self.assertIs(stats, stats_arg)
            calls.append(("summary", stats_arg, page_count))
            return ("done-1", "done-2")

        with (
            patch("backend.crawlers.zsxq_file_downloader.print", print_message),
            patch.object(
                ZSXQFileDownloader,
                "_create_file_collection_log",
                create_file_collection_log,
            ),
            patch(
                "backend.crawlers.zsxq_file_downloader.file_collection_stats",
                file_collection_stats_target,
            ),
            patch.object(
                ZSXQFileDownloader,
                "_run_file_collection_loop",
                run_file_collection_loop,
            ),
            patch.object(
                ZSXQFileDownloader,
                "_update_file_collection_log",
                update_file_collection_log,
            ),
            patch(
                "backend.crawlers.zsxq_file_downloader.file_collection_completion_messages",
                completion_messages,
            ),
        ):
            result = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertIs(stats, result)
        self.assertEqual(
            [
                ("print", "\n📊 开始收集文件列表到数据库..."),
                ("create_log",),
                ("stats",),
                ("loop", stats),
                ("update", stats, "log-1"),
                ("summary", stats, 3),
                ("print", "done-1"),
                ("print", "done-2"),
            ],
            calls,
        )

    def test_collect_all_files_stops_when_page_import_fails(self):
        downloader = self._downloader_with_failing_import()

        stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual(1, len(downloader.fetch_calls))
        self.assertEqual(1, downloader.file_db.import_calls)
        self.assertEqual({"total_files": 0, "new_files": 0, "skipped_files": 0}, stats)

    def test_collect_all_files_import_failure_preserves_log_and_summary(self):
        downloader = self._downloader_with_failing_import()

        with contextlib.redirect_stdout(io.StringIO()) as output:
            stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual({"total_files": 0, "new_files": 0, "skipped_files": 0}, stats)
        self.assertEqual([{"count": 20, "index": None}], downloader.fetch_calls)
        self.assertEqual(1, downloader.file_db.import_calls)
        printed = output.getvalue()
        self.assertIn("📄 收集第1页文件列表", printed)
        self.assertIn("   📋 当前页面: 1 个文件", printed)
        self.assertIn("   ❌ 第1页存储失败: stable import failure", printed)
        self.assertNotIn("   ✅ 第1页存储完成", printed)
        self.assertIn("   📄 收集页数: 1", printed)

    def test_collect_all_files_preserves_fetch_failure_record_update_and_summary(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = CollectAllFileDb()
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return None

        downloader.fetch_file_list = fetch_file_list

        with contextlib.redirect_stdout(io.StringIO()) as output:
            stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual({"total_files": 0, "new_files": 0, "skipped_files": 0}, stats)
        self.assertEqual([{"count": 20, "index": None}], downloader.fetch_calls)
        self.assertEqual([], downloader.file_db.imported_responses)
        self.assertEqual(2, downloader.file_db.commits)
        update_query, update_params = downloader.file_db.executed[-1]
        self.assertIn("UPDATE collection_log SET", update_query)
        self.assertEqual(0, update_params[1])
        self.assertEqual(0, update_params[2])
        self.assertEqual(99, update_params[3])
        printed = output.getvalue()
        self.assertIn("❌ 第1页获取失败，收集过程中断", printed)
        self.assertIn("💾 已成功收集前0页的数据", printed)
        self.assertIn("   📄 收集页数: 1", printed)

    def test_collect_all_files_preserves_missing_collection_log_id_update(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = MissingCollectionLogIdFileDb()
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return None

        downloader.fetch_file_list = fetch_file_list

        with contextlib.redirect_stdout(io.StringIO()):
            stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual({"total_files": 0, "new_files": 0, "skipped_files": 0}, stats)
        self.assertEqual([{"count": 20, "index": None}], downloader.fetch_calls)
        self.assertEqual(2, downloader.file_db.commits)
        update_query, update_params = downloader.file_db.executed[-1]
        self.assertIn("UPDATE collection_log SET", update_query)
        self.assertEqual((0, 0, None), update_params[1:])

    def test_collect_all_files_empty_page_preserves_summary_without_import_or_sleep(self):
        page = {"resp_data": {"index": "ignored-next", "files": []}}
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = CollectAllFileDb()
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return page

        downloader.fetch_file_list = fetch_file_list

        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("backend.crawlers.zsxq_file_downloader.random.uniform") as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual({"total_files": 0, "new_files": 0, "skipped_files": 0}, stats)
        self.assertEqual([{"count": 20, "index": None}], downloader.fetch_calls)
        self.assertEqual([], downloader.file_db.imported_responses)
        self.assertEqual(2, downloader.file_db.commits)
        uniform.assert_not_called()
        sleep.assert_not_called()
        printed = output.getvalue()
        self.assertIn("📄 收集第1页文件列表", printed)
        self.assertIn("📭 没有更多文件", printed)
        self.assertNotIn("   📋 当前页面:", printed)
        self.assertIn("   📄 收集页数: 1", printed)

    def test_collect_all_files_preserves_success_import_log_and_collection_record(self):
        page = {
            "resp_data": {
                "index": None,
                "files": [
                    {
                        "file": {
                            "file_id": 101,
                            "create_time": "2026-02-01T10:00:00.000+0800",
                        }
                    },
                    {
                        "file": {
                            "file_id": 102,
                            "create_time": "2026-02-02T10:00:00.000+0800",
                        }
                    },
                ],
            }
        }
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = CollectAllFileDb()
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return page

        downloader.fetch_file_list = fetch_file_list

        with contextlib.redirect_stdout(io.StringIO()) as output:
            stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual({"total_files": 2, "new_files": 2, "skipped_files": 0}, stats)
        self.assertEqual([{"count": 20, "index": None}], downloader.fetch_calls)
        self.assertEqual([page], downloader.file_db.imported_responses)
        self.assertEqual(2, downloader.file_db.commits)
        self.assertIn("INSERT INTO collection_log", downloader.file_db.executed[0][0])
        update_query, update_params = downloader.file_db.executed[-1]
        self.assertIn("UPDATE collection_log SET", update_query)
        self.assertEqual(2, update_params[1])
        self.assertEqual(2, update_params[2])
        self.assertEqual(99, update_params[3])
        printed = output.getvalue()
        self.assertIn("📊 开始收集文件列表到数据库", printed)
        self.assertIn("📄 收集第1页文件列表", printed)
        self.assertIn("   📋 当前页面: 2 个文件", printed)
        self.assertIn("      ✅ 新增文件: 2", printed)
        self.assertIn("      📊 其他数据: 话题+3, 用户+4", printed)
        self.assertIn("   ✅ 第1页存储完成", printed)
        self.assertIn("🎉 文件列表收集完成", printed)

    def test_collect_all_files_finishes_without_sleep_when_no_next_page(self):
        page = {"resp_data": {"index": None, "files": [{"file": {"file_id": 101}}]}}
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = CollectAllFileDb()
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return page

        downloader.fetch_file_list = fetch_file_list

        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform") as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual([{"count": 20, "index": None}], downloader.fetch_calls)
        self.assertEqual([page], downloader.file_db.imported_responses)
        uniform.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual({"total_files": 1, "new_files": 2, "skipped_files": 0}, stats)

    def test_collect_all_files_preserves_next_page_sleep_and_fetch_index(self):
        pages = [
            {"resp_data": {"index": "next-page", "files": [{"file": {"file_id": 101}}]}},
            {"resp_data": {"index": None, "files": [{"file": {"file_id": 102}}]}},
        ]
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = CollectAllFileDb()
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return pages.pop(0)

        downloader.fetch_file_list = fetch_file_list

        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=2.5) as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual(
            [{"count": 20, "index": None}, {"count": 20, "index": "next-page"}],
            downloader.fetch_calls,
        )
        uniform.assert_called_once_with(2, 5)
        sleep.assert_called_once_with(2.5)
        self.assertEqual({"total_files": 2, "new_files": 4, "skipped_files": 0}, stats)

    def test_get_database_time_range_preserves_empty_database_without_query(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = DatabaseTimeRangeFileDb({"files": 0})

        result = ZSXQFileDownloader.get_database_time_range(downloader)

        self.assertEqual({"has_data": False, "total_files": 0}, result)
        self.assertEqual(1, downloader.file_db.stats_calls)
        self.assertEqual([], downloader.file_db.executed)
        self.assertEqual(0, downloader.file_db.fetchone_calls)

    def test_get_database_time_range_preserves_entry_query_and_result_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        row = ("2026-01-01T00:00:00", "2026-02-01T00:00:00", 7)
        result_payload = {"stable": "result"}
        calls = []

        class FileDb:
            cursor = None

            def __init__(self):
                self.cursor = self

            def get_database_stats(self):
                calls.append(("stats",))
                return {"files": 10}

            def execute(self, query, params):
                calls.append(("execute", query, params))

            def fetchone(self):
                calls.append(("fetchone",))
                return row

        def time_range_query(group_id):
            calls.append(("query", group_id))
            return "stable-query", ("stable-param",)

        def time_range_result(total_files, result):
            calls.append(("result", total_files, result))
            return result_payload

        downloader.file_db = FileDb()

        with (
            patch(
                "backend.crawlers.zsxq_file_downloader.database_time_range_query",
                time_range_query,
            ),
            patch(
                "backend.crawlers.zsxq_file_downloader.database_time_range_result",
                time_range_result,
            ),
        ):
            result = ZSXQFileDownloader.get_database_time_range(downloader)

        self.assertIs(result_payload, result)
        self.assertEqual(
            [
                ("stats",),
                ("query", 511),
                ("execute", "stable-query", ("stable-param",)),
                ("fetchone",),
                ("result", 10, row),
            ],
            calls,
        )

    def test_get_database_time_range_preserves_query_params_and_result_shape(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = DatabaseTimeRangeFileDb(
            {"files": 10},
            ("2026-01-01T00:00:00", "2026-02-01T00:00:00", 7),
        )

        result = ZSXQFileDownloader.get_database_time_range(downloader)

        self.assertEqual(
            {
                "has_data": True,
                "total_files": 10,
                "oldest_time": "2026-01-01T00:00:00",
                "newest_time": "2026-02-01T00:00:00",
                "time_based_count": 7,
            },
            result,
        )
        query, params = downloader.file_db.executed[0]
        self.assertIn("SELECT MIN(create_time) as oldest_time", query)
        self.assertIn("COUNT(*) as total_count", query)
        self.assertIn("group_id = ?", query)
        self.assertIn("create_time IS NOT NULL AND create_time != ''", query)
        self.assertEqual((511,), params)
        self.assertEqual(1, downloader.file_db.fetchone_calls)

    def test_get_database_time_range_preserves_missing_row_defaults(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = DatabaseTimeRangeFileDb({"files": 5}, None)

        result = ZSXQFileDownloader.get_database_time_range(downloader)

        self.assertEqual(
            {
                "has_data": True,
                "total_files": 5,
                "oldest_time": None,
                "newest_time": None,
                "time_based_count": 0,
            },
            result,
        )

    def test_collect_incremental_files_preserves_stop_before_time_range_lookup(self):
        downloader = self._incremental_downloader({"has_data": False}, stopped=True)

        result = ZSXQFileDownloader.collect_incremental_files(downloader)

        self.assertEqual({"total_files": 0, "new_files": 0}, result)
        self.assertEqual(["🔄 开始增量文件收集...", "🛑 任务被停止"], downloader.logs)
        self.assertEqual(0, downloader.time_range_calls)
        self.assertEqual([], downloader.collect_calls)

    def test_collect_incremental_files_preserves_entry_start_stop_and_time_info_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        time_info = {
            "has_data": True,
            "total_files": 5,
            "oldest_time": "1680000000000",
            "newest_time": "2026-05-02",
        }
        expected_stats = {"total_files": 8, "new_files": 4}
        calls = []

        downloader.log = lambda message: calls.append(("log", message))

        def should_stop_time_collection_initially(downloader_self):
            self.assertIs(downloader, downloader_self)
            calls.append(("should_stop",))
            return False

        def get_database_time_range():
            calls.append(("time_range",))
            return time_info

        def collect_incremental_from_time_info(downloader_self, time_info_arg):
            self.assertIs(downloader, downloader_self)
            calls.append(("collect", time_info_arg))
            return expected_stats

        downloader.get_database_time_range = get_database_time_range

        with (
            patch.object(
                ZSXQFileDownloader,
                "_should_stop_time_collection_initially",
                should_stop_time_collection_initially,
            ),
            patch.object(
                ZSXQFileDownloader,
                "_collect_incremental_from_time_info",
                collect_incremental_from_time_info,
            ),
        ):
            result = ZSXQFileDownloader.collect_incremental_files(downloader)

        self.assertIs(expected_stats, result)
        self.assertEqual(
            [
                ("log", "🔄 开始增量文件收集..."),
                ("should_stop",),
                ("time_range",),
                ("collect", time_info),
            ],
            calls,
        )

    def test_collect_incremental_files_preserves_empty_database_fallback(self):
        downloader = self._incremental_downloader({"has_data": False, "total_files": 0})

        result = ZSXQFileDownloader.collect_incremental_files(downloader)

        self.assertEqual({"total_files": 7, "new_files": 3}, result)
        self.assertEqual(
            ["🔄 开始增量文件收集...", "📊 数据库为空，将进行全量收集"],
            downloader.logs,
        )
        self.assertEqual(1, downloader.time_range_calls)
        self.assertEqual([((), {})], downloader.collect_calls)

    def test_collect_incremental_files_preserves_missing_oldest_time_fallback(self):
        downloader = self._incremental_downloader(
            {
                "has_data": True,
                "total_files": 5,
                "oldest_time": None,
                "newest_time": "2026-05-02",
            }
        )

        result = ZSXQFileDownloader.collect_incremental_files(downloader)

        self.assertEqual({"total_files": 7, "new_files": 3}, result)
        self.assertEqual(
            [
                "🔄 开始增量文件收集...",
                "📊 数据库现状:",
                "   现有文件数: 5",
                "   最老时间: None",
                "   最新时间: 2026-05-02",
                "⚠️ 数据库中没有有效的时间信息，进行全量收集",
            ],
            downloader.logs,
        )
        self.assertEqual([((), {})], downloader.collect_calls)

    def test_collect_incremental_files_preserves_start_index_collection_path(self):
        downloader = self._incremental_downloader(
            {
                "has_data": True,
                "total_files": 5,
                "oldest_time": "1680000000000",
                "newest_time": "2026-05-02",
            }
        )

        result = ZSXQFileDownloader.collect_incremental_files(downloader)

        self.assertEqual({"total_files": 7, "new_files": 3}, result)
        self.assertEqual(
            [
                "🔄 开始增量文件收集...",
                "📊 数据库现状:",
                "   现有文件数: 5",
                "   最老时间: 1680000000000",
                "   最新时间: 2026-05-02",
                "🎯 将从最老时间戳开始收集更早的文件...",
                "🚀 增量收集起始时间戳: 1680000000000",
            ],
            downloader.logs,
        )
        self.assertEqual([((), {"start_time": "1680000000000"})], downloader.collect_calls)

    def test_collect_incremental_files_preserves_timestamp_failure_fallback(self):
        downloader = self._incremental_downloader(
            {
                "has_data": True,
                "total_files": 5,
                "oldest_time": "not-a-time",
                "newest_time": "2026-05-02",
            }
        )

        result = ZSXQFileDownloader.collect_incremental_files(downloader)

        self.assertEqual({"total_files": 7, "new_files": 3}, result)
        self.assertEqual(
            [
                "🔄 开始增量文件收集...",
                "📊 数据库现状:",
                "   现有文件数: 5",
                "   最老时间: not-a-time",
                "   最新时间: 2026-05-02",
                "🎯 将从最老时间戳开始收集更早的文件...",
            ],
            downloader.logs[:6],
        )
        self.assertTrue(downloader.logs[6].startswith("⚠️ 时间戳处理失败: "))
        self.assertEqual("🔄 改为全量收集", downloader.logs[7])
        self.assertEqual(8, len(downloader.logs))
        self.assertEqual([((), {})], downloader.collect_calls)

    def test_collect_files_for_date_range_preserves_entry_normalize_and_collection_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        stop_before_time = datetime.datetime(2026, 5, 7)
        expected_stats = {"total_files": 11, "new_files": 6}
        calls = []

        def normalize_date_range_target(**kwargs):
            calls.append(("normalize", kwargs))
            return "2026-05-01", "2026-05-07", stop_before_time

        def collect_files_for_normalized_date_range(
            downloader_self,
            normalized_start,
            normalized_end,
            stop_before_arg,
        ):
            self.assertIs(downloader, downloader_self)
            calls.append(
                (
                    "collect",
                    normalized_start,
                    normalized_end,
                    stop_before_arg,
                )
            )
            return expected_stats

        with (
            patch(
                "backend.crawlers.zsxq_file_downloader.normalize_date_range",
                normalize_date_range_target,
            ),
            patch.object(
                ZSXQFileDownloader,
                "_collect_files_for_normalized_date_range",
                collect_files_for_normalized_date_range,
            ),
        ):
            stats = ZSXQFileDownloader.collect_files_for_date_range(
                downloader,
                start_date="raw-start",
                end_date="raw-end",
                last_days=7,
            )

        self.assertIs(expected_stats, stats)
        self.assertEqual(
            [
                (
                    "normalize",
                    {
                        "start_date": "raw-start",
                        "end_date": "raw-end",
                        "last_days": 7,
                    },
                ),
                (
                    "collect",
                    "2026-05-01",
                    "2026-05-07",
                    stop_before_time,
                ),
            ],
            calls,
        )

    def test_collect_files_for_date_range_preserves_normalized_collection_call(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.collect_calls = []
        downloader.log = downloader.logs.append

        def collect_files_by_time(*args, **kwargs):
            downloader.collect_calls.append((args, kwargs))
            return {"total_files": 9, "new_files": 4}

        downloader.collect_files_by_time = collect_files_by_time

        result = ZSXQFileDownloader.collect_files_for_date_range(
            downloader,
            start_date="2026-05-07",
            end_date="2026-05-01",
        )

        self.assertEqual({"total_files": 9, "new_files": 4}, result)
        self.assertEqual(
            [
                "📅 启动按时间范围收集文件列表...",
                "   范围: 2026-05-01 ~ 2026-05-07",
            ],
            downloader.logs,
        )
        self.assertEqual(1, len(downloader.collect_calls))
        args, kwargs = downloader.collect_calls[0]
        self.assertEqual((), args)
        self.assertEqual("by_create_time", kwargs["sort"])
        self.assertIsNone(kwargs["start_time"])
        self.assertEqual(datetime.datetime(2026, 5, 7), kwargs["stop_before_time"])

    def test_fetch_time_collection_page_preserves_fetch_shape_result_and_logs(self):
        files = [
            {"file": {"id": 101, "create_time": "2026-05-02 10:00:00"}},
            {"file": {"id": 102, "create_time": "2026-05-01 09:30:00"}},
        ]
        data = {"resp_data": {"index": "next-cursor", "files": files}}
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return data

        downloader.fetch_file_list = fetch_file_list

        page = ZSXQFileDownloader._fetch_time_collection_page(
            downloader,
            2,
            "cursor-1",
            "by_create_time",
        )

        self.assertEqual((data, files, "next-cursor"), page)
        self.assertEqual(
            [{"count": 20, "index": "cursor-1", "sort": "by_create_time"}],
            downloader.fetch_calls,
        )
        self.assertEqual(
            [
                "   📋 当前页面: 2 个文件",
                "   🗓️ 当前页文件时间范围: 2026-05-02 10:00:00 ~ 2026-05-01 09:30:00",
            ],
            downloader.logs,
        )

    def test_load_time_collection_database_state_preserves_stats_latest_query_and_logs(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb(
            "2026-05-02T00:00:00",
            initial_files=3,
            final_files=9,
        )
        downloader.logs = []
        downloader.log = downloader.logs.append

        state = ZSXQFileDownloader._load_time_collection_database_state(
            downloader,
            True,
        )

        self.assertEqual((3, "2026-05-02T00:00:00"), state)
        self.assertEqual(1, downloader.file_db.stats_calls)
        self.assertEqual(1, len(downloader.file_db.executed))
        latest_time_query, latest_time_params = downloader.file_db.executed[0]
        self.assertIn("SELECT MAX(create_time) FROM files", latest_time_query)
        self.assertEqual((511,), latest_time_params)
        self.assertEqual(
            [
                "   📊 数据库初始状态: 3 个文件",
                "   📅 数据库最新文件时间: 2026-05-02T00:00:00",
            ],
            downloader.logs,
        )

    def test_collect_files_by_time_preserves_entry_mode_stop_and_run_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        stop_before_time = datetime.datetime(2026, 5, 3, 12, 30)
        expected_stats = {"total_files": 9, "new_files": 2, "pages": 1}
        calls = []

        def initialize_time_collection_mode(
            downloader_self,
            sort,
            start_time,
            stop_before_arg,
            force_refresh,
        ):
            self.assertIs(downloader, downloader_self)
            calls.append(
                (
                    "initialize",
                    sort,
                    start_time,
                    stop_before_arg,
                    force_refresh,
                )
            )
            return False

        def should_stop_time_collection_initially(downloader_self):
            self.assertIs(downloader, downloader_self)
            calls.append(("should_stop",))
            return False

        def run_time_collection_after_initial_stop(
            downloader_self,
            start_time,
            sort,
            enable_time_dedupe,
            stop_before_arg,
        ):
            self.assertIs(downloader, downloader_self)
            calls.append(
                (
                    "run",
                    start_time,
                    sort,
                    enable_time_dedupe,
                    stop_before_arg,
                )
            )
            return expected_stats

        with (
            patch.object(
                ZSXQFileDownloader,
                "_initialize_time_collection_mode",
                initialize_time_collection_mode,
            ),
            patch.object(
                ZSXQFileDownloader,
                "_should_stop_time_collection_initially",
                should_stop_time_collection_initially,
            ),
            patch.object(
                ZSXQFileDownloader,
                "_run_time_collection_after_initial_stop",
                run_time_collection_after_initial_stop,
            ),
        ):
            stats = ZSXQFileDownloader.collect_files_by_time(
                downloader,
                sort="by_download_count",
                start_time="cursor-1",
                stop_before_time=stop_before_time,
                force_refresh=True,
                ignored_legacy_kwarg="still-accepted",
            )

        self.assertIs(expected_stats, stats)
        self.assertEqual(
            [
                (
                    "initialize",
                    "by_download_count",
                    "cursor-1",
                    stop_before_time,
                    True,
                ),
                ("should_stop",),
                (
                    "run",
                    "cursor-1",
                    "by_download_count",
                    False,
                    stop_before_time,
                ),
            ],
            calls,
        )

    def test_collect_files_by_time_preserves_database_state_initialization(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb(
            "2026-05-02T00:00:00",
            initial_files=3,
            final_files=3,
        )
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {"resp_data": {"index": None, "files": []}}

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual([{"count": 20, "index": None, "sort": "by_create_time"}], downloader.fetch_calls)
        self.assertEqual(2, downloader.file_db.stats_calls)
        self.assertEqual(1, len(downloader.file_db.executed))
        latest_time_query, latest_time_params = downloader.file_db.executed[0]
        self.assertIn("SELECT MAX(create_time) FROM files", latest_time_query)
        self.assertEqual((511,), latest_time_params)
        self.assertEqual(
            [
                "📊 开始按时间顺序收集文件列表到完整数据库...",
                "   📅 排序方式: by_create_time",
                "   ✅ 智能去重模式: 遇到已存在的文件将停止收集",
                "   📊 数据库初始状态: 3 个文件",
                "   📅 数据库最新文件时间: 2026-05-02T00:00:00",
                "📄 收集第1页文件列表...",
                "📭 没有更多文件",
            ],
            downloader.logs[:7],
        )
        self.assertEqual(3, stats["total_files"])
        self.assertEqual(0, stats["new_files"])
        self.assertEqual(1, stats["pages"])

    def test_collect_files_by_time_preserves_force_refresh_start_mode(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb(
            "2026-05-02T00:00:00",
            initial_files=5,
            final_files=5,
        )
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {"resp_data": {"index": None, "files": []}}

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.collect_files_by_time(
            downloader,
            start_time="start-cursor",
            force_refresh=True,
        )

        self.assertEqual([{"count": 20, "index": "start-cursor", "sort": "by_create_time"}], downloader.fetch_calls)
        self.assertEqual([], downloader.file_db.executed)
        self.assertEqual(
            [
                "📊 开始按时间顺序收集文件列表到完整数据库...",
                "   📅 排序方式: by_create_time",
                "   ⏰ 起始时间: start-cursor",
                "   🔄 强制刷新模式: 将收集所有文件（包括已存在的）",
                "   📊 数据库初始状态: 5 个文件",
                "📄 收集第1页文件列表...",
                "📭 没有更多文件",
            ],
            downloader.logs[:7],
        )
        self.assertNotIn("   ✅ 智能去重模式: 遇到已存在的文件将停止收集", downloader.logs)
        self.assertNotIn("   📅 数据库最新文件时间: 2026-05-02T00:00:00", downloader.logs)
        self.assertEqual(5, stats["total_files"])
        self.assertEqual(0, stats["new_files"])
        self.assertEqual(1, stats["pages"])

    def test_collect_files_by_time_initial_stop_skips_database_fetch_and_import(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb(
            "2026-05-02T00:00:00",
            initial_files=5,
            final_files=5,
        )
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: True

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            raise AssertionError("initial stop should not fetch file pages")

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual({"total_files": 0, "new_files": 0}, stats)
        self.assertEqual([], downloader.fetch_calls)
        self.assertEqual(0, downloader.file_db.stats_calls)
        self.assertEqual([], downloader.file_db.executed)
        self.assertEqual([], downloader.file_db.imported_responses)
        self.assertEqual(
            [
                "📊 开始按时间顺序收集文件列表到完整数据库...",
                "   📅 排序方式: by_create_time",
                "   ✅ 智能去重模式: 遇到已存在的文件将停止收集",
                "🛑 任务被停止",
            ],
            downloader.logs,
        )

    def test_collect_files_by_time_stops_when_page_import_fails(self):
        downloader = self._downloader_with_failing_import()

        stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual(1, len(downloader.fetch_calls))
        self.assertEqual(1, downloader.file_db.import_calls)
        self.assertEqual(2, downloader.file_db.stats_calls)
        self.assertIn("   ❌ 第1页存储失败: stable import failure", downloader.logs)
        self.assertNotIn("   ⏭️ 下一页时间戳: next-index", downloader.logs)
        self.assertEqual(1, stats["pages"])
        self.assertEqual(0, stats["files"])

    def test_collect_files_by_time_stops_when_fetch_returns_empty_response(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb(None, initial_files=0, final_files=0)
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return None

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual([{"count": 20, "index": None, "sort": "by_create_time"}], downloader.fetch_calls)
        self.assertEqual([], downloader.file_db.imported_responses)
        self.assertEqual(2, downloader.file_db.stats_calls)
        self.assertIn("❌ 第1页获取失败，收集过程中断", downloader.logs)
        self.assertIn("💾 已成功收集前0页的数据", downloader.logs)
        self.assertNotIn("📭 没有更多文件", downloader.logs)
        self.assertNotIn("   ⏭️ 下一页时间戳:", "\n".join(downloader.logs))
        self.assertIn("🎉 完整文件列表收集完成:", downloader.logs)
        self.assertIn("   📊 处理页数: 1", downloader.logs)
        self.assertIn("   📁 新增文件: 0 (总计: 0)", downloader.logs)
        self.assertIn("   📋 累计导入统计:", downloader.logs)
        self.assertIn("   📚 当前数据库状态:", downloader.logs)
        self.assertEqual(0, stats["total_files"])
        self.assertEqual(0, stats["new_files"])
        self.assertEqual(1, stats["pages"])
        self.assertEqual(0, stats["files"])

    def test_collect_files_by_time_preserves_loop_exception_summary(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb(None, initial_files=0, final_files=0)
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            raise RuntimeError("page boom")

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual([{"count": 20, "index": None, "sort": "by_create_time"}], downloader.fetch_calls)
        self.assertEqual([], downloader.file_db.imported_responses)
        self.assertEqual(2, downloader.file_db.stats_calls)
        self.assertIn("📄 收集第1页文件列表...", downloader.logs)
        self.assertIn("❌ 收集过程异常: page boom", downloader.logs)
        self.assertLess(
            downloader.logs.index("📄 收集第1页文件列表..."),
            downloader.logs.index("❌ 收集过程异常: page boom"),
        )
        self.assertIn("🎉 完整文件列表收集完成:", downloader.logs)
        self.assertIn("   📊 处理页数: 1", downloader.logs)
        self.assertEqual(0, stats["total_files"])
        self.assertEqual(0, stats["new_files"])
        self.assertEqual(1, stats["pages"])
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

    def test_collect_files_by_time_skips_import_when_dedupe_page_is_all_old(self):
        files = [
            {"file": {"file_id": 101, "create_time": "2026-05-01T10:00:00"}},
            {"file": {"file_id": 102, "create_time": "2026-05-01T09:00:00"}},
        ]
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb("2026-05-02T00:00:00", initial_files=10, final_files=10)
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {"resp_data": {"index": "next-page", "files": list(files)}}

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual([], downloader.file_db.imported_responses)
        self.assertEqual([{"count": 20, "index": None, "sort": "by_create_time"}], downloader.fetch_calls)
        self.assertEqual(1, len(downloader.file_db.executed))
        self.assertEqual(2, downloader.file_db.stats_calls)
        self.assertEqual(10, stats["total_files"])
        self.assertEqual(0, stats["new_files"])
        self.assertEqual(1, stats["pages"])
        self.assertEqual(0, stats["files"])
        self.assertIn("   📊 时间分析: 新于数据库0个, 旧于或等于数据库2个", downloader.logs)
        self.assertIn("   ✅ 本页全部文件均已存在于数据库（时间不晚于数据库最新），停止收集", downloader.logs)
        self.assertIn("   💡 提示: 如需强制重新收集，请传入 force_refresh=True 参数", downloader.logs)
        self.assertNotIn("   ✅ 第1页存储完成: 文件+0, 话题+0", downloader.logs)
        self.assertNotIn("   ⏭️ 下一页时间戳: next-page", downloader.logs)

    def test_collect_files_by_time_preserves_next_index_sleep_and_last_page_log(self):
        pages = [
            {
                "resp_data": {
                    "index": "next-page",
                    "files": [{"file": {"file_id": 101, "create_time": "2026-05-03T10:00:00"}}],
                },
            },
            {
                "resp_data": {
                    "index": None,
                    "files": [{"file": {"file_id": 102, "create_time": "2026-05-02T10:00:00"}}],
                },
            },
        ]
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb(None, initial_files=0, final_files=2)
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return pages.pop(0)

        downloader.fetch_file_list = fetch_file_list

        with (
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=2.5) as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual(
            [
                {"count": 20, "index": None, "sort": "by_create_time"},
                {"count": 20, "index": "next-page", "sort": "by_create_time"},
            ],
            downloader.fetch_calls,
        )
        uniform.assert_called_once_with(2, 5)
        sleep.assert_called_once_with(2.5)
        self.assertIn("   ⏭️ 下一页时间戳: next-page", downloader.logs)
        self.assertIn("📭 已到达最后一页", downloader.logs)
        self.assertEqual([], downloader.file_db.executed)
        self.assertNotIn("   📅 数据库最新文件时间: None", downloader.logs)
        self.assertEqual(2, stats["total_files"])
        self.assertEqual(2, stats["new_files"])
        self.assertEqual(2, stats["pages"])

    def test_collect_files_by_time_preserves_loop_stop_after_next_page(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb(None, initial_files=0, final_files=1)
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.stop_checks = 0
        downloader.log = downloader.logs.append

        def check_stop():
            downloader.stop_checks += 1
            return downloader.stop_checks >= 3

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {
                "resp_data": {
                    "index": "next-page",
                    "files": [{"file": {"file_id": 101, "create_time": "2026-05-03T10:00:00"}}],
                }
            }

        downloader.check_stop = check_stop
        downloader.fetch_file_list = fetch_file_list

        with (
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=2.5) as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual(3, downloader.stop_checks)
        self.assertEqual([{"count": 20, "index": None, "sort": "by_create_time"}], downloader.fetch_calls)
        uniform.assert_called_once_with(2, 5)
        sleep.assert_called_once_with(2.5)
        self.assertIn("   ⏭️ 下一页时间戳: next-page", downloader.logs)
        self.assertIn("🛑 文件收集任务被停止", downloader.logs)
        self.assertLess(
            downloader.logs.index("   ⏭️ 下一页时间戳: next-page"),
            downloader.logs.index("🛑 文件收集任务被停止"),
        )
        self.assertEqual(1, stats["total_files"])
        self.assertEqual(1, stats["new_files"])
        self.assertEqual(1, stats["pages"])

    def test_collect_files_by_time_preserves_stop_before_boundary_log_and_break(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = TimeDedupeFileDb(None, initial_files=0, final_files=1)
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {
                "resp_data": {
                    "index": "next-page",
                    "files": [{"file": {"file_id": 101, "create_time": "2026-05-01 09:00:00"}}],
                }
            }

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.collect_files_by_time(
            downloader,
            stop_before_time=datetime.datetime(2026, 5, 2),
        )

        self.assertEqual([{"count": 20, "index": None, "sort": "by_create_time"}], downloader.fetch_calls)
        self.assertEqual(1, len(downloader.file_db.imported_responses))
        imported_files = downloader.file_db.imported_responses[0]["resp_data"]["files"]
        self.assertEqual([101], [item["file"]["file_id"] for item in imported_files])
        self.assertIn(
            "🛑 当前页最老文件时间 2026-05-01 09:00:00 早于目标起始时间 2026-05-02，停止继续收集更早文件",
            downloader.logs,
        )
        self.assertNotIn("   ⏭️ 下一页时间戳: next-page", downloader.logs)
        self.assertEqual(1, stats["total_files"])
        self.assertEqual(1, stats["new_files"])
        self.assertEqual(1, stats["pages"])

    def test_show_file_list_preserves_page_output_and_next_index(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {
                "resp_data": {
                    "index": "next-page",
                    "files": [
                        {
                            "file": {
                                "name": "demo.pdf",
                                "size": 1048576,
                                "download_count": 7,
                                "create_time": "2026-05-03T10:00:00",
                            },
                            "topic": {"talk": {"text": "topic title"}},
                        }
                    ],
                }
            }

        downloader.fetch_file_list = fetch_file_list

        with contextlib.redirect_stdout(io.StringIO()) as output:
            next_index = ZSXQFileDownloader.show_file_list(downloader, count=1, index="cursor")

        self.assertEqual("next-page", next_index)
        self.assertEqual([{"count": 1, "index": "cursor"}], downloader.fetch_calls)
        printed = output.getvalue()
        self.assertIn("文件列表 (1 个文件)", printed)
        self.assertIn("demo.pdf", printed)
        self.assertIn("📑 下一页索引: next-page", printed)

    def test_show_file_list_preserves_entry_fetch_page_handoff_and_return(self):
        downloader = object.__new__(ZSXQFileDownloader)
        calls = []
        files = [{"file": {"name": "demo.pdf"}}]
        data = {"resp_data": {"index": "next-page", "files": files}}

        def fetch_file_list(**kwargs):
            calls.append(("fetch", kwargs))
            return data

        def print_file_list_page(page_files, next_index):
            calls.append(("print", page_files, next_index))

        downloader.fetch_file_list = fetch_file_list
        downloader._print_file_list_page = print_file_list_page

        next_index = ZSXQFileDownloader.show_file_list(downloader, count=7, index="cursor")

        self.assertEqual("next-page", next_index)
        self.assertEqual("fetch", calls[0][0])
        self.assertEqual({"count": 7, "index": "cursor"}, calls[0][1])
        self.assertEqual("print", calls[1][0])
        self.assertIs(files, calls[1][1])
        self.assertEqual("next-page", calls[1][2])

    def test_show_file_list_fetch_failure_returns_none_without_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return None

        downloader.fetch_file_list = fetch_file_list

        with contextlib.redirect_stdout(io.StringIO()) as output:
            next_index = ZSXQFileDownloader.show_file_list(downloader, count=3, index="cursor")

        self.assertIsNone(next_index)
        self.assertEqual([{"count": 3, "index": "cursor"}], downloader.fetch_calls)
        self.assertEqual("", output.getvalue())


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

    def test_batch_download_messages_preserve_start_and_completion_logs(self):
        self.assertEqual(
            ("📥 开始无限下载文件 (直到没有更多文件)",),
            batch_download_start_messages(None),
        )
        self.assertEqual(
            ("📥 开始批量下载文件 (最多2个)",),
            batch_download_start_messages(2),
        )
        self.assertEqual(
            (
                "🎉 批量下载完成:",
                "   📊 总文件数: 3",
                "   ✅ 下载成功: 1",
                "   ⚠️ 跳过: 1",
                "   ❌ 失败: 1",
            ),
            batch_download_completion_messages(
                {"total_files": 3, "downloaded": 1, "skipped": 1, "failed": 1}
            ),
        )

    def test_batch_download_page_messages_preserve_failure_empty_and_count_logs(self):
        self.assertEqual("❌ 获取文件列表失败", batch_download_fetch_failed_message())
        self.assertEqual("📭 没有更多文件", batch_download_empty_page_message())
        self.assertEqual("📋 当前批次: 0 个文件", batch_download_page_files_message(0))
        self.assertEqual("📋 当前批次: 3 个文件", batch_download_page_files_message(3))

    def test_batch_download_stop_messages_preserve_existing_logs(self):
        self.assertEqual("🛑 任务被停止", batch_download_initial_stop_message())
        self.assertEqual("🛑 批量下载任务被停止", batch_download_loop_stop_message())
        self.assertEqual("🛑 文件下载过程中被停止", batch_download_file_stop_message())

    def test_batch_download_item_messages_preserve_numbering_and_skip_log(self):
        self.assertEqual(
            "【第3个文件】memo.pdf",
            batch_download_item_message(3, None, "memo.pdf"),
        )
        self.assertEqual(
            "【1/2】skip.pdf",
            batch_download_item_message(1, 2, "skip.pdf"),
        )
        self.assertEqual(
            "【2/2】None",
            batch_download_item_message(2, 2, None),
        )
        self.assertEqual(
            "   ⚠️ 文件已跳过，继续下一个",
            batch_download_skipped_message(),
        )

    def test_batch_download_next_page_plan_preserves_truthiness_limit_and_delay(self):
        self.assertEqual(
            {
                "should_continue": True,
                "next_index": "next-page",
                "message": "📄 准备获取下一页: next-page",
                "delay": 2,
            },
            batch_download_next_page_plan("next-page", 1, 2),
        )
        self.assertEqual(
            {
                "should_continue": True,
                "next_index": "next-page",
                "message": "📄 准备获取下一页: next-page",
                "delay": 2,
            },
            batch_download_next_page_plan("next-page", 99, None),
        )
        self.assertEqual(
            {
                "should_continue": False,
                "next_index": None,
                "message": None,
                "delay": None,
            },
            batch_download_next_page_plan("next-page", 2, 2),
        )
        self.assertEqual(
            {
                "should_continue": False,
                "next_index": None,
                "message": None,
                "delay": None,
            },
            batch_download_next_page_plan("", 1, None),
        )

    def test_next_batch_download_index_preserves_log_sleep_and_terminal_paths(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append

        with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
            next_index = ZSXQFileDownloader._next_batch_download_index(
                downloader,
                "next-page",
                1,
                2,
            )
            terminal_index = ZSXQFileDownloader._next_batch_download_index(
                downloader,
                "ignored-page",
                2,
                2,
            )

        self.assertEqual("next-page", next_index)
        self.assertIsNone(terminal_index)
        sleep.assert_called_once_with(2)
        self.assertEqual(["📄 准备获取下一页: next-page"], downloader.logs)

    def test_next_batch_download_index_target_preserves_plan_side_effects(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append

        with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
            next_index = ZSXQFileDownloader._next_batch_download_index_target(
                downloader,
                BatchDownloadNextIndexTarget("next-page", 1, 2),
            )
            terminal_index = ZSXQFileDownloader._next_batch_download_index_target(
                downloader,
                BatchDownloadNextIndexTarget("ignored-page", 2, 2),
            )

        self.assertEqual("next-page", next_index)
        self.assertIsNone(terminal_index)
        sleep.assert_called_once_with(2)
        self.assertEqual(["📄 准备获取下一页: next-page"], downloader.logs)

    def test_apply_batch_download_result_preserves_stats_logs_and_delays(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        interval_events = []
        downloader.check_long_delay = lambda: interval_events.append("long")
        downloader.download_delay = lambda: interval_events.append("delay")
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}

        skipped = ZSXQFileDownloader._apply_batch_download_result(
            downloader,
            "skipped",
            has_more_in_batch=True,
            downloaded_in_batch=4,
            max_files=None,
            stats=stats,
        )
        downloaded_with_delay = ZSXQFileDownloader._apply_batch_download_result(
            downloader,
            True,
            has_more_in_batch=True,
            downloaded_in_batch=4,
            max_files=6,
            stats=stats,
        )
        downloaded_at_limit = ZSXQFileDownloader._apply_batch_download_result(
            downloader,
            True,
            has_more_in_batch=True,
            downloaded_in_batch=5,
            max_files=6,
            stats=stats,
        )
        failed = ZSXQFileDownloader._apply_batch_download_result(
            downloader,
            False,
            has_more_in_batch=True,
            downloaded_in_batch=6,
            max_files=None,
            stats=stats,
        )

        self.assertEqual(4, skipped)
        self.assertEqual(5, downloaded_with_delay)
        self.assertEqual(6, downloaded_at_limit)
        self.assertEqual(6, failed)
        self.assertEqual({"total_files": 0, "downloaded": 2, "skipped": 1, "failed": 1}, stats)
        self.assertEqual(["   ⚠️ 文件已跳过，继续下一个"], downloader.logs)
        self.assertEqual(["long", "delay", "long"], interval_events)

    def test_apply_batch_download_result_target_preserves_download_delay_order(self):
        downloader = object.__new__(ZSXQFileDownloader)
        events = []
        downloader.log = lambda message: events.append(("log", message))
        stats = {"total_files": 3, "downloaded": 1, "skipped": 0, "failed": 0}

        def check_long_delay():
            events.append(("long", stats["downloaded"]))

        def download_delay():
            events.append(("delay", stats["downloaded"]))

        downloader.check_long_delay = check_long_delay
        downloader.download_delay = download_delay

        downloaded = ZSXQFileDownloader._apply_batch_download_result_target(
            downloader,
            BatchDownloadResultTarget(
                True,
                True,
                4,
                6,
                stats,
            ),
        )

        self.assertEqual(5, downloaded)
        self.assertEqual({"total_files": 3, "downloaded": 2, "skipped": 0, "failed": 0}, stats)
        self.assertEqual([("long", 2), ("delay", 2)], events)

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

    def test_fetch_batch_download_page_preserves_fetch_args_success_and_terminal_logs(self):
        files = [{"file": {"id": 101, "name": "memo.pdf"}}]
        success_downloader = object.__new__(ZSXQFileDownloader)
        success_downloader.logs = []
        success_downloader.log = success_downloader.logs.append
        success_downloader.fetch_calls = []

        def fetch_success(**kwargs):
            success_downloader.fetch_calls.append(kwargs)
            return {"resp_data": {"files": files, "index": "next-page"}}

        success_downloader.fetch_file_list = fetch_success

        page = ZSXQFileDownloader._fetch_batch_download_page(success_downloader, "cursor")

        self.assertEqual([{"count": 20, "index": "cursor"}], success_downloader.fetch_calls)
        self.assertEqual(files, page.files)
        self.assertEqual("next-page", page.next_index)
        self.assertEqual(["📋 当前批次: 1 个文件"], success_downloader.logs)

        failure_downloader = object.__new__(ZSXQFileDownloader)
        failure_downloader.logs = []
        failure_downloader.log = failure_downloader.logs.append
        failure_downloader.fetch_file_list = lambda **kwargs: None

        self.assertIsNone(ZSXQFileDownloader._fetch_batch_download_page(failure_downloader, "failed"))
        self.assertEqual(["❌ 获取文件列表失败"], failure_downloader.logs)

        empty_downloader = object.__new__(ZSXQFileDownloader)
        empty_downloader.logs = []
        empty_downloader.log = empty_downloader.logs.append
        empty_downloader.fetch_file_list = lambda **kwargs: {"resp_data": {"files": [], "index": "ignored"}}

        self.assertIsNone(ZSXQFileDownloader._fetch_batch_download_page(empty_downloader, "empty"))
        self.assertEqual(["📭 没有更多文件"], empty_downloader.logs)

    def test_download_batch_file_item_preserves_limit_reached_delay_skip(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.download_file = lambda file_info: True
        interval_events = []
        downloader.check_long_delay = lambda: interval_events.append("long")
        downloader.download_delay = lambda: interval_events.append("delay")
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}

        downloaded = ZSXQFileDownloader._download_batch_file_item(
            downloader,
            {"file": {"id": 102, "name": "ok.pdf"}},
            item_number=2,
            max_files=2,
            has_more_in_batch=True,
            downloaded_in_batch=1,
            stats=stats,
        )

        self.assertEqual(2, downloaded)
        self.assertEqual({"total_files": 1, "downloaded": 1, "skipped": 0, "failed": 0}, stats)
        self.assertEqual(["long"], interval_events)
        self.assertEqual(["【2/2】ok.pdf"], downloader.logs)

    def test_download_batch_file_item_preserves_missing_file_name_fallback(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        payloads = []
        downloader.download_file = lambda file_info: payloads.append(file_info) or "skipped"
        downloader.check_long_delay = lambda: None
        downloader.download_delay = lambda: None
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        file_info = {}

        downloaded = ZSXQFileDownloader._download_batch_file_item(
            downloader,
            file_info,
            item_number=3,
            max_files=None,
            has_more_in_batch=False,
            downloaded_in_batch=2,
            stats=stats,
        )

        self.assertEqual(2, downloaded)
        self.assertEqual([file_info], payloads)
        self.assertEqual({"total_files": 1, "downloaded": 0, "skipped": 1, "failed": 0}, stats)
        self.assertEqual(["【第3个文件】Unknown", "   ⚠️ 文件已跳过，继续下一个"], downloader.logs)

    def test_download_batch_file_item_target_preserves_download_apply_and_total_order(self):
        downloader = object.__new__(ZSXQFileDownloader)
        events = []
        downloader.log = lambda message: events.append(("log", message))
        file_info = {"file": {"id": 103, "name": "target.pdf"}}
        stats = {"total_files": 4, "downloaded": 2, "skipped": 1, "failed": 1}

        def download_file(received_file_info):
            events.append(("download", received_file_info, stats["total_files"]))
            return "downloaded"

        def apply_result(result_target):
            events.append(
                (
                    "apply",
                    result_target.result,
                    result_target.has_more_in_batch,
                    result_target.downloaded_in_batch,
                    result_target.max_files,
                    result_target.stats["total_files"],
                )
            )
            return 3

        downloader.download_file = download_file
        downloader._apply_batch_download_result_target = apply_result

        downloaded = ZSXQFileDownloader._download_batch_file_item_target(
            downloader,
            BatchDownloadFileItemTarget(
                file_info,
                3,
                5,
                True,
                2,
                stats,
            ),
        )

        self.assertEqual(3, downloaded)
        self.assertEqual({"total_files": 5, "downloaded": 2, "skipped": 1, "failed": 1}, stats)
        self.assertEqual(
            [
                ("log", "【3/5】target.pdf"),
                ("download", file_info, 4),
                ("apply", "downloaded", True, 2, 5, 4),
            ],
            events,
        )

    def test_download_batch_page_files_preserves_item_targets_stop_and_limit(self):
        files = [
            {"file": {"id": 101, "name": "first.pdf"}},
            {"file": {"id": 102, "name": "second.pdf"}},
        ]
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        limit_downloader = object.__new__(ZSXQFileDownloader)
        limit_downloader.logs = []
        limit_downloader.log = limit_downloader.logs.append
        limit_downloader.check_stop = lambda: False
        limit_targets = []

        def limit_file_item(target):
            limit_targets.append(target)
            return target.downloaded_in_batch + 1

        limit_downloader._download_batch_file_item_target = limit_file_item

        limited = ZSXQFileDownloader._download_batch_page_files(
            limit_downloader,
            files,
            downloaded_in_batch=1,
            max_files=2,
            stats=stats,
        )

        self.assertEqual(2, limited)
        self.assertEqual([], limit_downloader.logs)
        self.assertEqual(1, len(limit_targets))
        self.assertEqual(files[0], limit_targets[0].file_info)
        self.assertEqual(2, limit_targets[0].item_number)
        self.assertEqual(2, limit_targets[0].max_files)
        self.assertTrue(limit_targets[0].has_more_in_batch)
        self.assertEqual(1, limit_targets[0].downloaded_in_batch)
        self.assertIs(stats, limit_targets[0].stats)

        stop_downloader = object.__new__(ZSXQFileDownloader)
        stop_downloader.logs = []
        stop_downloader.log = stop_downloader.logs.append
        stop_checks = iter([False, True])
        stop_downloader.check_stop = lambda: next(stop_checks)
        stop_targets = []

        def stop_file_item(target):
            stop_targets.append(target)
            return target.downloaded_in_batch + 1

        stop_downloader._download_batch_file_item_target = stop_file_item

        stopped = ZSXQFileDownloader._download_batch_page_files(
            stop_downloader,
            files,
            downloaded_in_batch=0,
            max_files=None,
            stats=stats,
        )

        self.assertEqual(1, stopped)
        self.assertEqual(1, len(stop_targets))
        self.assertEqual(files[0], stop_targets[0].file_info)
        self.assertIsNone(stop_targets[0].max_files)
        self.assertEqual(["🛑 文件下载过程中被停止"], stop_downloader.logs)

    def test_download_batch_page_files_target_preserves_item_target_construction(self):
        files = [
            {"file": {"id": 101, "name": "first.pdf"}},
            {"file": {"id": 102, "name": "second.pdf"}},
            {"file": {"id": 103, "name": "third.pdf"}},
        ]
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.check_stop = lambda: False
        targets = []

        def file_item(target):
            targets.append(
                (
                    target.file_info,
                    target.item_number,
                    target.max_files,
                    target.has_more_in_batch,
                    target.downloaded_in_batch,
                    target.stats is stats,
                )
            )
            return target.downloaded_in_batch + 1

        downloader._download_batch_file_item_target = file_item

        downloaded = ZSXQFileDownloader._download_batch_page_files_target(
            downloader,
            BatchDownloadPageFilesTarget(files, 2, None, stats),
        )

        self.assertEqual(5, downloaded)
        self.assertEqual(
            [
                (files[0], 3, None, True, 2, True),
                (files[1], 4, None, True, 3, True),
                (files[2], 5, None, False, 4, True),
            ],
            targets,
        )

    def test_run_batch_download_page_preserves_fetch_terminal_and_step_handoff(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        terminal_downloader = object.__new__(ZSXQFileDownloader)
        terminal_fetch_targets = []
        terminal_downloader._fetch_batch_download_page_target = (
            lambda target: terminal_fetch_targets.append(target) or None
        )

        terminal = ZSXQFileDownloader._run_batch_download_page(
            terminal_downloader,
            SimpleNamespace(downloaded_in_batch=7, next_index="cursor"),
            max_files=8,
            stats=stats,
        )

        self.assertIsNone(terminal)
        self.assertEqual(1, len(terminal_fetch_targets))
        self.assertEqual("cursor", terminal_fetch_targets[0].current_index)

        files = [{"file": {"id": 101, "name": "first.pdf"}}]
        downloader = object.__new__(ZSXQFileDownloader)
        fetch_targets = []
        page_targets = []
        next_targets = []

        def fetch_page(target):
            fetch_targets.append(target)
            return SimpleNamespace(files=files, next_index="next-page")

        def page_files(target):
            page_targets.append(target)
            return 3

        def next_index(target):
            next_targets.append(target)
            return "after-page"

        downloader._fetch_batch_download_page_target = fetch_page
        downloader._download_batch_page_files_target = page_files
        downloader._next_batch_download_index_target = next_index

        step = ZSXQFileDownloader._run_batch_download_page(
            downloader,
            SimpleNamespace(downloaded_in_batch=1, next_index="start"),
            max_files=4,
            stats=stats,
        )

        self.assertEqual(1, len(fetch_targets))
        self.assertEqual("start", fetch_targets[0].current_index)
        self.assertEqual(3, step.downloaded_in_batch)
        self.assertEqual("after-page", step.next_index)
        self.assertEqual(files, page_targets[0].files)
        self.assertEqual(1, page_targets[0].downloaded_in_batch)
        self.assertEqual(4, page_targets[0].max_files)
        self.assertIs(stats, page_targets[0].stats)
        self.assertEqual("next-page", next_targets[0].next_index)
        self.assertEqual(3, next_targets[0].downloaded_in_batch)
        self.assertEqual(4, next_targets[0].max_files)

    def test_run_batch_download_page_target_preserves_page_files_target_order(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        files = [{"file": {"id": 101, "name": "first.pdf"}}]
        downloader = object.__new__(ZSXQFileDownloader)
        events = []

        def fetch_page(target):
            events.append(("fetch", target.current_index))
            return SimpleNamespace(files=files, next_index="next-page")

        def page_files(target):
            events.append(
                (
                    "page_files",
                    target.files,
                    target.downloaded_in_batch,
                    target.max_files,
                    target.stats is stats,
                )
            )
            return 5

        def next_index(target):
            events.append(("next", target.next_index, target.downloaded_in_batch, target.max_files))
            return "after-page"

        downloader._fetch_batch_download_page_target = fetch_page
        downloader._download_batch_page_files_target = page_files
        downloader._next_batch_download_index_target = next_index

        step = ZSXQFileDownloader._run_batch_download_page_target(
            downloader,
            SimpleNamespace(
                step=SimpleNamespace(downloaded_in_batch=2, next_index="cursor"),
                max_files=7,
                stats=stats,
            ),
        )

        self.assertEqual(5, step.downloaded_in_batch)
        self.assertEqual("after-page", step.next_index)
        self.assertEqual(
            [
                ("fetch", "cursor"),
                ("page_files", files, 2, 7, True),
                ("next", "next-page", 5, 7),
            ],
            events,
        )

    def test_run_batch_download_page_target_preserves_fetch_target_terminal(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        fetch_targets = []

        def fetch_page(target):
            fetch_targets.append(target)
            return None

        def page_files(target):
            self.fail("terminal page fetch must not download batch page files")

        def next_index(target):
            self.fail("terminal page fetch must not compute next batch index")

        downloader._fetch_batch_download_page_target = fetch_page
        downloader._download_batch_page_files_target = page_files
        downloader._next_batch_download_index_target = next_index

        step = ZSXQFileDownloader._run_batch_download_page_target(
            downloader,
            SimpleNamespace(
                step=SimpleNamespace(downloaded_in_batch=2, next_index="cursor"),
                max_files=7,
                stats=stats,
            ),
        )

        self.assertIsNone(step)
        self.assertEqual(1, len(fetch_targets))
        self.assertEqual("cursor", fetch_targets[0].current_index)

    def test_run_batch_download_page_target_preserves_page_files_builder_handoff(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        page = SimpleNamespace(files=[{"file": {"id": 101, "name": "first.pdf"}}], next_index="next-page")
        page_files_target = SimpleNamespace(token="page-files-target")
        run_target = SimpleNamespace(
            step=SimpleNamespace(downloaded_in_batch=2, next_index="cursor"),
            max_files=7,
            stats=stats,
        )
        downloader = object.__new__(ZSXQFileDownloader)
        events = []

        def fetch_page(target):
            events.append(("fetch", target))
            return page

        def build_page_files(target, fetched_page):
            events.append(("build_page_files", target, fetched_page))
            return page_files_target

        def download_page_files(target):
            events.append(("download_page_files", target))
            return 5

        def next_index(target):
            events.append(("next", target.next_index, target.downloaded_in_batch, target.max_files))
            return "after-page"

        downloader._fetch_batch_download_page_for_run_target = fetch_page
        downloader._batch_page_files_target_for_page = build_page_files
        downloader._download_batch_page_files_target = download_page_files
        downloader._next_batch_download_index_target = next_index

        step = ZSXQFileDownloader._run_batch_download_page_target(downloader, run_target)

        self.assertEqual(5, step.downloaded_in_batch)
        self.assertEqual("after-page", step.next_index)
        self.assertEqual("fetch", events[0][0])
        self.assertIs(run_target, events[0][1])
        self.assertEqual("build_page_files", events[1][0])
        self.assertIs(run_target, events[1][1])
        self.assertIs(page, events[1][2])
        self.assertEqual("download_page_files", events[2][0])
        self.assertIs(page_files_target, events[2][1])
        self.assertEqual(("next", "next-page", 5, 7), events[3])

    def test_run_batch_download_page_target_preserves_next_index_handoff(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        page = SimpleNamespace(files=[{"file": {"id": 101, "name": "first.pdf"}}], next_index="next-page")
        run_target = SimpleNamespace(
            step=SimpleNamespace(downloaded_in_batch=2, next_index="cursor"),
            max_files=7,
            stats=stats,
        )
        downloader = object.__new__(ZSXQFileDownloader)
        next_targets = []

        downloader._fetch_batch_download_page_for_run_target = lambda target: page
        downloader._download_batch_page_files_for_run_target = lambda target, fetched_page: 5

        def next_index(target):
            next_targets.append(target)
            return "after-page"

        downloader._next_batch_download_index_target = next_index

        step = ZSXQFileDownloader._run_batch_download_page_target(downloader, run_target)

        self.assertEqual(5, step.downloaded_in_batch)
        self.assertEqual("after-page", step.next_index)
        self.assertEqual(1, len(next_targets))
        self.assertEqual("next-page", next_targets[0].next_index)
        self.assertEqual(5, next_targets[0].downloaded_in_batch)
        self.assertEqual(7, next_targets[0].max_files)

    def test_run_batch_download_loop_preserves_stop_page_handoff_and_terminal_paths(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        stop_downloader = object.__new__(ZSXQFileDownloader)
        stop_downloader.logs = []
        stop_downloader.log = stop_downloader.logs.append
        stop_downloader.check_stop = lambda: True
        stop_calls = []
        stop_downloader._run_batch_download_page_target = lambda target: stop_calls.append(target)

        ZSXQFileDownloader._run_batch_download_loop(
            stop_downloader,
            stats,
            max_files=3,
            start_index="unused",
        )

        self.assertEqual(["🛑 批量下载任务被停止"], stop_downloader.logs)
        self.assertEqual([], stop_calls)

        page_downloader = object.__new__(ZSXQFileDownloader)
        page_downloader.logs = []
        page_downloader.log = page_downloader.logs.append
        page_downloader.check_stop = lambda: False
        page_targets = []
        page_results = [
            SimpleNamespace(downloaded_in_batch=1, next_index="next-page"),
            SimpleNamespace(downloaded_in_batch=2, next_index=None),
        ]

        def run_page(target):
            page_targets.append(target)
            return page_results.pop(0)

        page_downloader._run_batch_download_page_target = run_page

        ZSXQFileDownloader._run_batch_download_loop(
            page_downloader,
            stats,
            max_files=4,
            start_index="start",
        )

        self.assertEqual([], page_downloader.logs)
        self.assertEqual(2, len(page_targets))
        self.assertEqual(0, page_targets[0].step.downloaded_in_batch)
        self.assertEqual("start", page_targets[0].step.next_index)
        self.assertEqual(4, page_targets[0].max_files)
        self.assertIs(stats, page_targets[0].stats)
        self.assertEqual(1, page_targets[1].step.downloaded_in_batch)
        self.assertEqual("next-page", page_targets[1].step.next_index)
        self.assertEqual(4, page_targets[1].max_files)
        self.assertIs(stats, page_targets[1].stats)

        terminal_downloader = object.__new__(ZSXQFileDownloader)
        terminal_downloader.logs = []
        terminal_downloader.log = terminal_downloader.logs.append
        terminal_downloader.check_stop = lambda: False
        terminal_targets = []
        terminal_downloader._run_batch_download_page_target = (
            lambda target: terminal_targets.append(target) or None
        )

        ZSXQFileDownloader._run_batch_download_loop(
            terminal_downloader,
            stats,
            max_files=None,
            start_index="terminal",
        )

        self.assertEqual([], terminal_downloader.logs)
        self.assertEqual(1, len(terminal_targets))
        self.assertEqual(0, terminal_targets[0].step.downloaded_in_batch)
        self.assertEqual("terminal", terminal_targets[0].step.next_index)
        self.assertIsNone(terminal_targets[0].max_files)
        self.assertIs(stats, terminal_targets[0].stats)

    def test_run_batch_download_loop_target_preserves_page_run_target_sequence(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.check_stop = lambda: False
        targets = []
        page_results = [
            SimpleNamespace(downloaded_in_batch=2, next_index="cursor-2"),
            SimpleNamespace(downloaded_in_batch=4, next_index=None),
        ]

        def run_page(target):
            targets.append(
                (
                    target.step.downloaded_in_batch,
                    target.step.next_index,
                    target.max_files,
                    target.stats is stats,
                )
            )
            return page_results.pop(0)

        downloader._run_batch_download_page_target = run_page

        ZSXQFileDownloader._run_batch_download_loop_target(
            downloader,
            SimpleNamespace(stats=stats, max_files=5, start_index="cursor-1"),
        )

        self.assertEqual(
            [
                (0, "cursor-1", 5, True),
                (2, "cursor-2", 5, True),
            ],
            targets,
        )

    def test_run_batch_download_loop_target_preserves_page_step_builder_handoff(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.check_stop = lambda: False
        sentinel_page_target = object()
        calls = []

        def page_run_target(target, step):
            calls.append(("build", step.downloaded_in_batch, step.next_index, target.stats is stats))
            return sentinel_page_target

        def run_page(target):
            calls.append(("run", target is sentinel_page_target))
            return None

        downloader._batch_download_page_run_target = page_run_target
        downloader._run_batch_download_page_target = run_page

        ZSXQFileDownloader._run_batch_download_loop_target(
            downloader,
            SimpleNamespace(stats=stats, max_files=None, start_index="cursor"),
        )

        self.assertEqual(
            [
                ("build", 0, "cursor", True),
                ("run", True),
            ],
            calls,
        )

    def test_run_batch_download_loop_target_preserves_next_index_terminal_stop_checks(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        stop_checks = []
        targets = []
        page_results = [
            SimpleNamespace(downloaded_in_batch=1, next_index="cursor-2"),
            SimpleNamespace(downloaded_in_batch=2, next_index=None),
        ]

        def check_stop():
            stop_checks.append("checked")
            return False

        def run_page(target):
            targets.append((target.step.downloaded_in_batch, target.step.next_index))
            return page_results.pop(0)

        downloader.check_stop = check_stop
        downloader._run_batch_download_page_target = run_page

        ZSXQFileDownloader._run_batch_download_loop_target(
            downloader,
            SimpleNamespace(stats=stats, max_files=5, start_index="cursor-1"),
        )

        self.assertEqual(["checked", "checked"], stop_checks)
        self.assertEqual([(0, "cursor-1"), (1, "cursor-2")], targets)
        self.assertEqual([], page_results)

    def test_run_batch_download_loop_target_preserves_none_step_terminal_stop_checks(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        stop_checks = []
        targets = []

        def check_stop():
            stop_checks.append("checked")
            return False

        def run_page(target):
            targets.append((target.step.downloaded_in_batch, target.step.next_index))
            return None

        downloader.check_stop = check_stop
        downloader._run_batch_download_page_target = run_page

        ZSXQFileDownloader._run_batch_download_loop_target(
            downloader,
            SimpleNamespace(stats=stats, max_files=None, start_index="cursor"),
        )

        self.assertEqual(["checked"], stop_checks)
        self.assertEqual([(0, "cursor")], targets)

    def test_run_batch_download_loop_target_preserves_initial_step_from_start_index(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.check_stop = lambda: False
        targets = []

        def run_page(target):
            targets.append(
                (
                    target.step.downloaded_in_batch,
                    target.step.next_index,
                    target.max_files,
                    target.stats is stats,
                )
            )
            return None

        downloader._run_batch_download_page_target = run_page

        ZSXQFileDownloader._run_batch_download_loop_target(
            downloader,
            SimpleNamespace(stats=stats, max_files=1, start_index=""),
        )

        self.assertEqual([(0, "", 1, True)], targets)

    def test_run_batch_download_loop_target_preserves_zero_max_without_stop_or_page(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append

        def check_stop():
            self.fail("zero max_files must not check stop inside the loop")

        def run_page(target):
            self.fail("zero max_files must not run any batch page")

        downloader.check_stop = check_stop
        downloader._run_batch_download_page_target = run_page

        ZSXQFileDownloader._run_batch_download_loop_target(
            downloader,
            SimpleNamespace(stats=stats, max_files=0, start_index="cursor"),
        )

        self.assertEqual([], downloader.logs)

    def test_run_batch_download_loop_target_preserves_stop_without_page(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        stop_checks = []

        def check_stop():
            stop_checks.append("checked")
            return True

        def run_page(target):
            self.fail("stopped loop must not run any batch page")

        downloader.check_stop = check_stop
        downloader._run_batch_download_page_target = run_page

        ZSXQFileDownloader._run_batch_download_loop_target(
            downloader,
            SimpleNamespace(stats=stats, max_files=1, start_index="cursor"),
        )

        self.assertEqual(["checked"], stop_checks)
        self.assertEqual(["🛑 批量下载任务被停止"], downloader.logs)

    def test_run_batch_download_loop_preserves_loop_target_construction(self):
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        downloader = object.__new__(ZSXQFileDownloader)
        targets = []

        downloader._run_batch_download_loop_target = targets.append

        ZSXQFileDownloader._run_batch_download_loop(
            downloader,
            stats,
            max_files=0,
            start_index="",
        )

        self.assertEqual(1, len(targets))
        self.assertIs(stats, targets[0].stats)
        self.assertEqual(0, targets[0].max_files)
        self.assertEqual("", targets[0].start_index)

    def test_download_files_batch_preserves_loop_target_stats_and_completion(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False
        loop_targets = []

        def run_loop(target):
            loop_targets.append(target)
            target.stats.update({"total_files": 3, "downloaded": 1, "skipped": 1, "failed": 1})

        downloader._run_batch_download_loop_target = run_loop

        stats = ZSXQFileDownloader.download_files_batch(
            downloader,
            max_files=5,
            start_index="cursor",
        )

        self.assertEqual({"total_files": 3, "downloaded": 1, "skipped": 1, "failed": 1}, stats)
        self.assertEqual(1, len(loop_targets))
        self.assertIs(stats, loop_targets[0].stats)
        self.assertEqual(5, loop_targets[0].max_files)
        self.assertEqual("cursor", loop_targets[0].start_index)
        self.assertEqual(
            [
                "📥 开始批量下载文件 (最多5个)",
                "🎉 批量下载完成:",
                "   📊 总文件数: 3",
                "   ✅ 下载成功: 1",
                "   ⚠️ 跳过: 1",
                "   ❌ 失败: 1",
            ],
            downloader.logs,
        )

    def test_download_files_batch_preserves_entry_target_and_return_value(self):
        downloader = object.__new__(ZSXQFileDownloader)
        targets = []
        expected_stats = {"total_files": 9, "downloaded": 8, "skipped": 1, "failed": 0}

        def run_target(target):
            targets.append(target)
            return expected_stats

        downloader._download_files_batch_target = run_target

        stats = ZSXQFileDownloader.download_files_batch(
            downloader,
            max_files=0,
            start_index="",
        )

        self.assertIs(expected_stats, stats)
        self.assertEqual([BatchDownloadTarget(0, "")], targets)

    def test_download_files_batch_target_preserves_start_loop_and_completion(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False
        loop_targets = []

        def run_loop(target):
            loop_targets.append(
                (
                    target.max_files,
                    target.start_index,
                    target.stats["total_files"],
                )
            )
            target.stats.update({"total_files": 2, "downloaded": 2, "skipped": 0, "failed": 0})

        downloader._run_batch_download_loop_target = run_loop

        stats = ZSXQFileDownloader._download_files_batch_target(
            downloader,
            BatchDownloadTarget(None, "cursor"),
        )

        self.assertEqual({"total_files": 2, "downloaded": 2, "skipped": 0, "failed": 0}, stats)
        self.assertEqual([(None, "cursor", 0)], loop_targets)
        self.assertEqual(
            [
                "📥 开始无限下载文件 (直到没有更多文件)",
                "🎉 批量下载完成:",
                "   📊 总文件数: 2",
                "   ✅ 下载成功: 2",
                "   ⚠️ 跳过: 0",
                "   ❌ 失败: 0",
            ],
            downloader.logs,
        )

    def test_download_files_batch_target_preserves_initial_stop_without_completion(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        stop_checks = []

        def check_stop():
            stop_checks.append("checked")
            return True

        def run_loop(target):
            self.fail("initial stop must not run the batch loop")

        downloader.check_stop = check_stop
        downloader._run_batch_download_loop_target = run_loop

        stats = ZSXQFileDownloader._download_files_batch_target(
            downloader,
            BatchDownloadTarget(3, "cursor"),
        )

        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertEqual(["checked"], stop_checks)
        self.assertEqual(
            ["📥 开始批量下载文件 (最多3个)", "🛑 任务被停止"],
            downloader.logs,
        )

    def test_download_files_batch_stops_page_after_success_limit(self):
        files = [
            {"file": {"id": 101, "name": "first.pdf"}},
            {"file": {"id": 102, "name": "second.pdf"}},
        ]
        downloader = self._downloader_for_batch(files)
        payloads = []
        interval_events = []
        downloader.download_file = lambda file_info: payloads.append(file_info) or True
        downloader.check_long_delay = lambda: interval_events.append("long")
        downloader.download_delay = lambda: interval_events.append("delay")

        stats = ZSXQFileDownloader.download_files_batch(downloader, max_files=1, start_index="start")

        self.assertEqual({"total_files": 1, "downloaded": 1, "skipped": 0, "failed": 0}, stats)
        self.assertEqual([{"count": 20, "index": "start"}], downloader.fetch_calls)
        self.assertEqual([files[0]], payloads)
        self.assertEqual(["long"], interval_events)
        self.assertIn("📋 当前批次: 2 个文件", downloader.logs)
        self.assertIn("【1/1】first.pdf", downloader.logs)
        self.assertNotIn("【2/1】second.pdf", downloader.logs)

    def test_download_files_batch_initial_stop_returns_empty_stats_without_fetch_or_completion(self):
        downloader = self._downloader_for_batch([{"file": {"id": 101, "name": "unused.pdf"}}])
        downloader.check_stop = lambda: True

        stats = ZSXQFileDownloader.download_files_batch(downloader, max_files=2, start_index="start")

        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertEqual([], downloader.fetch_calls)
        self.assertEqual(
            ["📥 开始批量下载文件 (最多2个)", "🛑 任务被停止"],
            downloader.logs,
        )

    def test_download_files_batch_loop_stop_returns_empty_stats_with_completion(self):
        downloader = self._downloader_for_batch([{"file": {"id": 101, "name": "unused.pdf"}}])
        stop_checks = [False, True]
        downloader.check_stop = lambda: stop_checks.pop(0)

        stats = ZSXQFileDownloader.download_files_batch(downloader, max_files=2, start_index="start")

        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertEqual([], downloader.fetch_calls)
        self.assertEqual(
            [
                "📥 开始批量下载文件 (最多2个)",
                "🛑 批量下载任务被停止",
                "🎉 批量下载完成:",
                "   📊 总文件数: 0",
                "   ✅ 下载成功: 0",
                "   ⚠️ 跳过: 0",
                "   ❌ 失败: 0",
            ],
            downloader.logs,
        )

    def test_download_files_batch_fetch_failure_preserves_log_and_completion(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return None

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.download_files_batch(downloader, max_files=2, start_index="start")

        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertEqual([{"count": 20, "index": "start"}], downloader.fetch_calls)
        self.assertEqual(
            [
                "📥 开始批量下载文件 (最多2个)",
                "❌ 获取文件列表失败",
                "🎉 批量下载完成:",
                "   📊 总文件数: 0",
                "   ✅ 下载成功: 0",
                "   ⚠️ 跳过: 0",
                "   ❌ 失败: 0",
            ],
            downloader.logs,
        )

    def test_download_files_batch_empty_page_preserves_log_and_completion(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False
        downloader.fetch_calls = []

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {"resp_data": {"files": [], "index": "ignored-next"}}

        downloader.fetch_file_list = fetch_file_list

        stats = ZSXQFileDownloader.download_files_batch(downloader, max_files=2, start_index="start")

        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertEqual([{"count": 20, "index": "start"}], downloader.fetch_calls)
        self.assertEqual(
            [
                "📥 开始批量下载文件 (最多2个)",
                "📭 没有更多文件",
                "🎉 批量下载完成:",
                "   📊 总文件数: 0",
                "   ✅ 下载成功: 0",
                "   ⚠️ 跳过: 0",
                "   ❌ 失败: 0",
            ],
            downloader.logs,
        )

    def test_download_files_batch_preserves_next_page_sleep_and_fetch_index(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False
        downloader.fetch_calls = []
        pages = [
            {"resp_data": {"files": [{"file": {"id": 101, "name": "first.pdf"}}], "index": "next-page"}},
            {"resp_data": {"files": [{"file": {"id": 102, "name": "second.pdf"}}], "index": None}},
        ]

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return pages.pop(0)

        downloader.fetch_file_list = fetch_file_list
        downloader.download_file = lambda file_info: True
        downloader.check_long_delay = lambda: None
        downloader.download_delay = lambda: None

        with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
            stats = ZSXQFileDownloader.download_files_batch(downloader, max_files=2, start_index="start")

        self.assertEqual({"total_files": 2, "downloaded": 2, "skipped": 0, "failed": 0}, stats)
        self.assertEqual(
            [{"count": 20, "index": "start"}, {"count": 20, "index": "next-page"}],
            downloader.fetch_calls,
        )
        sleep.assert_called_once_with(2)
        self.assertIn("📄 准备获取下一页: next-page", downloader.logs)
        self.assertEqual("   ❌ 失败: 0", downloader.logs[-1])


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

    def test_fetch_database_download_rows_preserves_execute_params_and_fetch_shape(self):
        rows = [(101, "memo.pdf", 2048, 7, "2026-05-03 10:00:00")]
        downloader = self._downloader_for_query_capture(rows=rows)
        query_plan = {
            "query": "SELECT id, name FROM files WHERE group_id = ?",
            "params": (511,),
        }

        fetched_rows = ZSXQFileDownloader._fetch_database_download_rows(
            downloader,
            query_plan,
        )

        self.assertEqual(rows, fetched_rows)
        self.assertEqual(101, fetched_rows[0].file_id)
        self.assertEqual("memo.pdf", fetched_rows[0].file_name)
        self.assertEqual(2048, fetched_rows[0].file_size)
        self.assertEqual(7, fetched_rows[0].download_count)
        self.assertEqual("2026-05-03 10:00:00", fetched_rows[0].create_time)
        self.assertEqual(
            [("SELECT id, name FROM files WHERE group_id = ?", (511,))],
            downloader.file_db.executed,
        )

    def test_fetch_database_download_rows_preserves_malformed_row_errors(self):
        downloader = self._downloader_for_query_capture(
            rows=[(101, "memo.pdf", 2048, 7)]
        )

        with self.assertRaises(TypeError):
            ZSXQFileDownloader._fetch_database_download_rows(
                downloader,
                {"query": "SELECT partial", "params": ()},
            )

    def test_run_database_download_rows_preserves_stats_handoff_and_completion(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        files_to_download = [
            SimpleNamespace(file_id=101, file_name="first.pdf"),
            SimpleNamespace(file_id=102, file_name="second.pdf"),
        ]
        loop_calls = []

        def download_rows(files, stats):
            loop_calls.append((files, stats))
            stats.update({"downloaded": 1, "skipped": 1, "failed": 0})

        downloader._download_database_file_rows = download_rows

        stats = ZSXQFileDownloader._run_database_download_rows(downloader, files_to_download)

        self.assertEqual({"total_files": 2, "downloaded": 1, "skipped": 1, "failed": 0}, stats)
        self.assertEqual(1, len(loop_calls))
        self.assertIs(files_to_download, loop_calls[0][0])
        self.assertIs(stats, loop_calls[0][1])
        self.assertEqual(
            [
                "🎉 数据库下载完成:",
                "   📊 总文件数: 2",
                "   ✅ 下载成功: 1",
                "   ⚠️ 跳过: 1",
                "   ❌ 失败: 0",
            ],
            downloader.logs,
        )

    def test_run_database_download_after_initial_stop_preserves_empty_and_nonempty_handoff(self):
        query_plan = {"query": "SELECT files", "params": (511,), "sort_by": "create_time"}

        empty_downloader = object.__new__(ZSXQFileDownloader)
        empty_fetch_calls = []
        empty_summary_calls = []
        empty_downloader._fetch_database_download_rows = lambda plan: empty_fetch_calls.append(plan) or []
        empty_downloader._log_database_download_rows_summary = (
            lambda files, sort_by: empty_summary_calls.append((files, sort_by))
        )
        empty_downloader._run_database_download_rows = lambda files: self.fail(
            "empty database download should not enter row runner"
        )

        empty_stats = ZSXQFileDownloader._run_database_download_after_initial_stop(
            empty_downloader,
            query_plan,
            "create_time",
        )

        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, empty_stats)
        self.assertEqual([query_plan], empty_fetch_calls)
        self.assertEqual([([], "create_time")], empty_summary_calls)

        rows = [SimpleNamespace(file_id=101, file_name="memo.pdf")]
        nonempty_downloader = object.__new__(ZSXQFileDownloader)
        nonempty_fetch_calls = []
        nonempty_summary_calls = []
        nonempty_run_calls = []
        expected_stats = {"total_files": 1, "downloaded": 1, "skipped": 0, "failed": 0}
        nonempty_downloader._fetch_database_download_rows = (
            lambda plan: nonempty_fetch_calls.append(plan) or rows
        )
        nonempty_downloader._log_database_download_rows_summary = (
            lambda files, sort_by: nonempty_summary_calls.append((files, sort_by))
        )
        nonempty_downloader._run_database_download_rows = (
            lambda files: nonempty_run_calls.append(files) or expected_stats
        )

        stats = ZSXQFileDownloader._run_database_download_after_initial_stop(
            nonempty_downloader,
            query_plan,
            "download_count",
        )

        self.assertIs(expected_stats, stats)
        self.assertEqual([query_plan], nonempty_fetch_calls)
        self.assertEqual([(rows, "download_count")], nonempty_summary_calls)
        self.assertEqual([rows], nonempty_run_calls)

    def test_download_files_from_database_preserves_entry_handoff_kwargs_and_initial_stop(self):
        downloader = object.__new__(ZSXQFileDownloader)
        start_calls = []
        query_calls = []
        after_calls = []
        query_plan = {"query": "SELECT files", "params": (511,), "sort_by": "create_time"}
        expected_stats = {"total_files": 2, "downloaded": 1, "skipped": 1, "failed": 0}
        downloader._log_database_download_start = (
            lambda max_files, status_filter: start_calls.append((max_files, status_filter))
        )

        def prepare_query(max_files, status_filter, sort_by, start_date, end_date, last_days, kwargs):
            query_calls.append((max_files, status_filter, sort_by, start_date, end_date, last_days, kwargs))
            return query_plan

        downloader._prepare_database_download_query_plan = prepare_query
        downloader._should_stop_database_download_initially = lambda: False
        downloader._run_database_download_after_initial_stop = (
            lambda plan, sort_by: after_calls.append((plan, sort_by)) or expected_stats
        )

        stats = ZSXQFileDownloader.download_files_from_database(
            downloader,
            max_files=9,
            status_filter="failed",
            sort_by="download_count",
            start_date="2026-05-01",
            end_date="2026-05-07",
            last_days=3,
            recent_days=5,
            order_by="create_time DESC",
        )

        self.assertIs(expected_stats, stats)
        self.assertEqual([(9, "failed")], start_calls)
        self.assertEqual(
            [
                (
                    9,
                    "failed",
                    "download_count",
                    "2026-05-01",
                    "2026-05-07",
                    3,
                    {"recent_days": 5, "order_by": "create_time DESC"},
                )
            ],
            query_calls,
        )
        self.assertEqual([(query_plan, "create_time")], after_calls)

        stopped_downloader = object.__new__(ZSXQFileDownloader)
        stopped_start_calls = []
        stopped_query_calls = []
        stopped_downloader._log_database_download_start = (
            lambda max_files, status_filter: stopped_start_calls.append((max_files, status_filter))
        )
        stopped_downloader._prepare_database_download_query_plan = (
            lambda *args: stopped_query_calls.append(args) or query_plan
        )
        stopped_downloader._should_stop_database_download_initially = lambda: True
        stopped_downloader._run_database_download_after_initial_stop = lambda *args: self.fail(
            "initial stop should not run database download"
        )

        stopped_stats = ZSXQFileDownloader.download_files_from_database(stopped_downloader)

        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stopped_stats)
        self.assertEqual([(None, "pending")], stopped_start_calls)
        self.assertEqual([(None, "pending", "download_count", None, None, None, {})], stopped_query_calls)

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

    def test_download_files_from_database_preserves_legacy_recent_days_fallback_for_query_plan(self):
        downloader = self._downloader_for_query_capture()

        with patch(
            "backend.crawlers.zsxq_file_downloader_helpers.normalize_date_range",
            return_value=("2026-05-01", "2026-05-07", None),
        ) as normalize:
            stats = ZSXQFileDownloader.download_files_from_database(downloader, recent_days=7)

        query, params = downloader.file_db.executed[-1]
        compact_query = self._compact_sql(query)
        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        normalize.assert_called_once_with(start_date=None, end_date=None, last_days=7)
        self.assertIn(
            "WHERE group_id = ? AND download_status = ? AND substr(create_time, 1, 10) >= ? "
            "AND substr(create_time, 1, 10) <= ?",
            compact_query,
        )
        self.assertEqual((511, "pending", "2026-05-01", "2026-05-07"), params)
        self.assertIn("   📅 下载区间: 2026-05-01 ~ 2026-05-07", downloader.logs)

    def test_download_files_from_database_initial_stop_skips_query_and_download(self):
        downloader = self._downloader_for_query_capture()
        downloader.check_stop = lambda: True
        downloader._download_database_file_rows = lambda *args: self.fail(
            "initial stop should not enter database download row loop"
        )

        stats = ZSXQFileDownloader.download_files_from_database(downloader)

        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertEqual([], downloader.file_db.executed)
        self.assertEqual(
            [
                "📥 开始从完整数据库下载文件...",
                "   🔍 状态筛选: pending",
                "   📌 下载排序: 按热度倒序",
                "🛑 任务被停止",
            ],
            downloader.logs,
        )

    def test_download_files_from_database_preserves_empty_result_log_order(self):
        downloader = self._downloader_for_query_capture()

        stats = ZSXQFileDownloader.download_files_from_database(downloader)

        self.assertEqual({"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertEqual(
            [
                "📥 开始从完整数据库下载文件...",
                "   🔍 状态筛选: pending",
                "   📌 下载排序: 按热度倒序",
                "📭 数据库中没有符合条件的文件可下载",
            ],
            downloader.logs,
        )

    def test_download_files_from_database_preserves_create_time_range_summary(self):
        downloader = self._downloader_for_query_capture(
            rows=[
                (101, "new.pdf", 2048, 7, "2026-05-03 10:00:00"),
                (102, "old.pdf", 1024, 9, "2026-05-01 09:00:00"),
            ],
        )
        loop_calls = []
        downloader._download_database_file_rows = lambda files, stats: loop_calls.append(
            (files, stats.copy())
        )

        stats = ZSXQFileDownloader.download_files_from_database(downloader, sort_by="create_time")

        self.assertEqual({"total_files": 2, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertEqual(1, len(loop_calls))
        self.assertEqual(
            "   🗓️ 本次待下载文件时间范围: 2026-05-03 10:00:00 ~ 2026-05-01 09:00:00",
            downloader.logs[4],
        )
        self.assertEqual("🎉 数据库下载完成:", downloader.logs[-5])

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

    def test_download_files_from_database_preserves_stop_before_row_loop(self):
        downloader = self._downloader_for_query_capture(
            rows=[
                (101, "first.pdf", 2048, 7, "2026-05-03 10:00:00"),
                (102, "second.pdf", 1024, 9, "2026-05-02 10:00:00"),
            ],
        )
        stop_checks = iter([False, True])
        processed_rows = []
        downloader.check_stop = lambda: next(stop_checks)
        downloader._download_database_file_row = lambda *args: processed_rows.append(args)

        stats = ZSXQFileDownloader.download_files_from_database(downloader)

        self.assertEqual({"total_files": 2, "downloaded": 0, "skipped": 0, "failed": 0}, stats)
        self.assertEqual([], processed_rows)
        self.assertIn("📋 找到 2 个待下载文件", downloader.logs)
        self.assertIn("🛑 下载任务被停止", downloader.logs)
        self.assertEqual("   ❌ 失败: 0", downloader.logs[-1])

    def test_download_files_from_database_preserves_row_exception_and_interrupt_handling(self):
        downloader = self._downloader_for_query_capture(
            rows=[
                (101, "boom.pdf", 2048, 7, "2026-05-03 10:00:00"),
                (102, "stop.pdf", 1024, 9, "2026-05-02 10:00:00"),
                (103, "unused.pdf", 512, 1, "2026-05-01 10:00:00"),
            ],
        )
        handled_rows = []

        def handle_row(file_row, position, total_files, stats):
            handled_rows.append((position, total_files, file_row[0]))
            if position == 1:
                raise RuntimeError("stable row failure")
            if position == 2:
                raise KeyboardInterrupt()
            stats["downloaded"] += 1

        downloader._download_database_file_row = handle_row

        stats = ZSXQFileDownloader.download_files_from_database(downloader)

        self.assertEqual({"total_files": 3, "downloaded": 0, "skipped": 0, "failed": 1}, stats)
        self.assertEqual([(1, 3, 101), (2, 3, 102)], handled_rows)
        self.assertIn("   ❌ 处理文件异常: stable row failure", downloader.logs)
        self.assertIn("⏹️ 用户中断下载", downloader.logs)
        self.assertEqual("   ❌ 失败: 1", downloader.logs[-1])


class FileDownloaderDatabaseStatsTests(unittest.TestCase):
    def test_database_stats_total_size_preserves_empty_zero_and_truthy_values(self):
        self.assertEqual(0, _database_stats_total_size(None))
        self.assertEqual(0, _database_stats_total_size(()))
        self.assertEqual(0, _database_stats_total_size((0,)))
        self.assertEqual(0, _database_stats_total_size((None,)))
        self.assertEqual(-1, _database_stats_total_size((-1,)))
        self.assertEqual(2048, _database_stats_total_size((2048,)))
        self.assertEqual(2048, _database_stats_total_size((2048, "ignored")))

    def test_database_stats_time_range_preserves_positive_only_named_shape(self):
        self.assertIsNone(_database_stats_time_range(None))
        self.assertIsNone(_database_stats_time_range(()))
        self.assertIsNone(_database_stats_time_range((None, None, 0)))
        self.assertIsNone(_database_stats_time_range((None, None, -1)))

        time_range = _database_stats_time_range(
            ("2026-05-01 09:00:00", "2026-05-07 10:00:00", 2)
        )

        self.assertEqual(("2026-05-01 09:00:00", "2026-05-07 10:00:00", 2), time_range)
        self.assertEqual("2026-05-01 09:00:00", time_range.min_time)
        self.assertEqual("2026-05-07 10:00:00", time_range.max_time)
        self.assertEqual(2, time_range.time_count)

    def test_database_stats_time_range_preserves_malformed_row_errors(self):
        with self.assertRaises(IndexError):
            _database_stats_time_range(("2026-05-01 09:00:00", "2026-05-07 10:00:00"))

        with self.assertRaises(ValueError):
            _database_stats_time_range(
                ("2026-05-01 09:00:00", "2026-05-07 10:00:00", 2, "extra")
            )

    def test_show_database_stats_preserves_entry_print_stats_and_target_order(self):
        stats = {"files": 2, "topics": 3}
        calls = []
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = SimpleNamespace(
            get_database_stats=lambda: calls.append(("get_stats",)) or stats
        )
        downloader._show_database_stats_target = lambda target: calls.append(
            ("target", target.stats)
        )

        def print_message(message=""):
            calls.append(("print", message))

        with patch("builtins.print", print_message):
            ZSXQFileDownloader.show_database_stats(downloader)

        self.assertEqual(
            [
                ("print", "\n📊 完整数据库统计信息:"),
                ("print", "=" * 60),
                ("print", "📁 PostgreSQL schema: zsxq_core"),
                ("get_stats",),
                ("target", stats),
                ("print", "=" * 60),
            ],
            calls,
        )
        self.assertIs(stats, calls[4][1])

    def test_show_database_stats_preserves_entry_handoff_and_print_order(self):
        stats = {"files": 2, "topics": 3}
        calls = []
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = SimpleNamespace(
            get_database_stats=lambda: calls.append(("get_stats", stats)) or stats
        )
        downloader._print_database_core_stats = lambda value: calls.append(("core", value))
        downloader._print_database_total_size = lambda: calls.append(("total_size", None))
        downloader._print_database_table_stats = lambda value: calls.append(("tables", value))
        downloader._print_database_time_range = lambda: calls.append(("time_range", None))
        downloader._print_database_api_response_stats = lambda: calls.append(("api_stats", None))

        with contextlib.redirect_stdout(io.StringIO()) as output:
            ZSXQFileDownloader.show_database_stats(downloader)

        self.assertEqual(
            ["get_stats", "core", "total_size", "tables", "time_range", "api_stats"],
            [name for name, _ in calls],
        )
        self.assertIs(stats, calls[1][1])
        self.assertIs(stats, calls[3][1])

        printed = output.getvalue()
        self.assertIn("📊 完整数据库统计信息:", printed)
        self.assertIn("📁 PostgreSQL schema:", printed)
        self.assertTrue(printed.rstrip().endswith("=" * 60))

    def test_show_database_stats_preserves_query_order_and_output_shape(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = ShowDatabaseStatsFileDb()

        with contextlib.redirect_stdout(io.StringIO()) as output:
            ZSXQFileDownloader.show_database_stats(downloader)

        executed = downloader.file_db.executed
        self.assertEqual(3, len(executed))
        size_query, size_params = executed[0]
        time_query, time_params = executed[1]
        api_query, api_params = executed[2]
        self.assertEqual(
            "SELECT SUM(size) FROM files WHERE group_id = ? AND size IS NOT NULL",
            size_query,
        )
        self.assertEqual((511,), size_params)
        self.assertIn("SELECT MIN(create_time), MAX(create_time), COUNT(*)", " ".join(time_query.split()))
        self.assertEqual((511,), time_params)
        self.assertIn("FROM api_responses", api_query)
        self.assertIn("GROUP BY succeeded", api_query)
        self.assertEqual((), api_params)

        printed = output.getvalue()
        self.assertIn("📊 完整数据库统计信息:", printed)
        self.assertIn("📁 PostgreSQL schema:", printed)
        self.assertIn("   📄 文件数量: 2", printed)
        self.assertIn("   👥 用户数量: 0", printed)
        self.assertIn("💾 总文件大小: 2.00 MB", printed)
        self.assertIn("   📊 unknown_table: 4", printed)
        self.assertIn("   最早文件: 2026-05-01 09:00:00", printed)
        self.assertIn("   ✅ 成功: 5", printed)
        self.assertIn("   ❌ 失败: 2", printed)

    def test_show_database_stats_omits_optional_sections_when_empty(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "511"
        downloader.file_db = EmptyShowDatabaseStatsFileDb()

        with contextlib.redirect_stdout(io.StringIO()) as output:
            ZSXQFileDownloader.show_database_stats(downloader)

        self.assertEqual(3, len(downloader.file_db.executed))
        printed = output.getvalue()
        self.assertIn("   📄 文件数量: 0", printed)
        self.assertIn("   🏠 群组数量: 0", printed)
        self.assertIn("\n📋 详细表统计:", printed)
        self.assertNotIn("💾 总文件大小:", printed)
        self.assertNotIn("\n⏰ 文件时间范围:", printed)
        self.assertNotIn("\n📡 API响应统计:", printed)
        self.assertNotIn("   📄 files: 0", printed)


class FileDownloaderTimeHelperTests(unittest.TestCase):
    def test_database_download_effective_last_days_preserves_legacy_recent_days_fallback(self):
        self.assertIsNone(database_download_effective_last_days(None, None))
        self.assertEqual(7, database_download_effective_last_days(None, 7))
        self.assertEqual(5, database_download_effective_last_days(5, 7))
        self.assertEqual(0, database_download_effective_last_days(0, 7))
        self.assertEqual("", database_download_effective_last_days(None, ""))

    def test_database_download_file_info_preserves_nested_payload_shape(self):
        self.assertEqual(
            {
                "file": {
                    "id": 101,
                    "name": "memo.pdf",
                    "size": 2048,
                    "download_count": 7,
                }
            },
            database_download_file_info(101, "memo.pdf", 2048, 7),
        )

    def test_database_download_completion_messages_preserves_summary_order(self):
        self.assertEqual(
            (
                "🎉 数据库下载完成:",
                "   📊 总文件数: 3",
                "   ✅ 下载成功: 1",
                "   ⚠️ 跳过: 1",
                "   ❌ 失败: 1",
            ),
            database_download_completion_messages(
                {"total_files": 3, "downloaded": 1, "skipped": 1, "failed": 1}
            ),
        )

    def test_database_download_filter_messages_preserves_range_and_sort_labels(self):
        self.assertEqual(
            (
                "   📅 下载区间: 2026-05-01 ~ 2026-05-07",
                "   📌 下载排序: 按时间倒序",
            ),
            database_download_filter_messages("2026-05-01", "2026-05-07", 7, "create_time"),
        )
        self.assertEqual(
            (
                "   📅 时间筛选: 最近7天",
                "   📌 下载排序: 按热度倒序",
            ),
            database_download_filter_messages(None, None, 7, "download_count"),
        )
        self.assertEqual(
            ("   📅 下载区间: - ~ 2026-05-07", "   📌 下载排序: 按热度倒序"),
            database_download_filter_messages(None, "2026-05-07", None, "download_count"),
        )

    def test_database_download_start_messages_preserves_limit_and_status_lines(self):
        self.assertEqual(
            (
                "📥 开始从完整数据库下载文件...",
                "   🎯 下载限制: 5个文件",
                "   🔍 状态筛选: failed",
            ),
            database_download_start_messages(5, "failed"),
        )
        self.assertEqual(
            (
                "📥 开始从完整数据库下载文件...",
                "   🔍 状态筛选: pending",
            ),
            database_download_start_messages(None, "pending"),
        )

    def test_database_download_time_range_message_preserves_create_time_only_log(self):
        rows = [
            (101, "new.pdf", 1024, 9, "2026-05-07 10:00:00"),
            (102, "old.pdf", 2048, 7, "2026-05-01 09:00:00"),
        ]

        self.assertEqual(
            "   🗓️ 本次待下载文件时间范围: 2026-05-07 10:00:00 ~ 2026-05-01 09:00:00",
            database_download_time_range_message(rows, "create_time"),
        )
        self.assertIsNone(database_download_time_range_message(rows, "download_count"))
        self.assertIsNone(database_download_time_range_message([], "create_time"))

    def test_date_range_collection_start_messages_preserves_optional_range_line(self):
        self.assertEqual(
            (
                "📅 启动按时间范围收集文件列表...",
                "   范围: 2026-05-01 ~ 2026-05-07",
            ),
            date_range_collection_start_messages("2026-05-01", "2026-05-07"),
        )
        self.assertEqual(
            (
                "📅 启动按时间范围收集文件列表...",
                "   范围: - ~ 2026-05-07",
            ),
            date_range_collection_start_messages(None, "2026-05-07"),
        )
        self.assertEqual(
            ("📅 启动按时间范围收集文件列表...",),
            date_range_collection_start_messages(None, None),
        )

    def test_incremental_start_index_preserves_millis_and_timezone_paths(self):
        self.assertEqual("1680000000000", incremental_start_index("1680000000000"))
        self.assertEqual("1777600800000", incremental_start_index("2026-05-01T10:00:00+0800"))
        with self.assertRaises(ValueError):
            incremental_start_index("not-a-time")

    def test_incremental_collection_messages_preserve_existing_text(self):
        self.assertEqual("🔄 开始增量文件收集...", incremental_collection_start_message())
        self.assertEqual("📊 数据库为空，将进行全量收集", incremental_collection_empty_database_message())
        self.assertEqual(
            (
                "📊 数据库现状:",
                "   现有文件数: 5",
                "   最老时间: old",
                "   最新时间: new",
            ),
            incremental_collection_status_messages(
                {"total_files": 5, "oldest_time": "old", "newest_time": "new"}
            ),
        )
        self.assertEqual(
            "⚠️ 数据库中没有有效的时间信息，进行全量收集",
            incremental_collection_missing_time_message(),
        )
        self.assertEqual(
            "🎯 将从最老时间戳开始收集更早的文件...",
            incremental_collection_target_message(),
        )
        self.assertEqual(
            "🚀 增量收集起始时间戳: 1680000000000",
            incremental_collection_start_index_message("1680000000000"),
        )
        self.assertEqual(
            ("⚠️ 时间戳处理失败: bad", "🔄 改为全量收集"),
            incremental_collection_timestamp_failure_messages(RuntimeError("bad")),
        )

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

    def test_time_dedupe_page_messages_preserve_analysis_stop_and_filter_logs(self):
        all_new_plan = {
            "newer_count": 2,
            "older_count": 0,
            "should_stop_before_insert": False,
            "should_filter_before_insert": False,
        }
        self.assertEqual(
            ("   📊 时间分析: 新于数据库2个, 旧于或等于数据库0个",),
            time_dedupe_page_messages(all_new_plan),
        )

        all_old_plan = {
            "newer_count": 0,
            "older_count": 2,
            "should_stop_before_insert": True,
            "should_filter_before_insert": False,
        }
        self.assertEqual(
            (
                "   📊 时间分析: 新于数据库0个, 旧于或等于数据库2个",
                "   ✅ 本页全部文件均已存在于数据库（时间不晚于数据库最新），停止收集",
                "   💡 提示: 如需强制重新收集，请传入 force_refresh=True 参数",
            ),
            time_dedupe_page_messages(all_old_plan),
        )

        mixed_plan = {
            "newer_count": 1,
            "older_count": 2,
            "should_stop_before_insert": False,
            "should_filter_before_insert": True,
        }
        self.assertEqual(
            (
                "   📊 时间分析: 新于数据库1个, 旧于或等于数据库2个",
                "   🔄 过滤掉2个旧数据，只插入1个新数据",
            ),
            time_dedupe_page_messages(mixed_plan),
        )

    def test_time_collection_page_import_messages_preserve_success_and_stop_logs(self):
        self.assertEqual(
            ("   ✅ 第3页存储完成: 文件+2, 话题+1",),
            time_collection_page_import_messages(3, {"files": 2, "topics": 1}, False),
        )
        self.assertEqual(
            (
                "   ✅ 第4页存储完成: 文件+0, 话题+0",
                "   ✅ 已插入本页新数据，后续页面均为旧数据，停止收集",
                "   💡 提示: 如需强制重新收集，请传入 force_refresh=True 参数",
            ),
            time_collection_page_import_messages(4, {}, True),
        )

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

    def test_time_collection_summary_messages_preserve_log_sequence(self):
        summary = {
            "new_files": 2,
            "final_files": 12,
            "imported_items": (("files", 2), ("users", 1)),
            "database_items": (("files", 12), ("topics", 3)),
        }

        self.assertEqual(
            (
                "🎉 完整文件列表收集完成:",
                "   📊 处理页数: 4",
                "   📁 新增文件: 2 (总计: 12)",
                "   📋 累计导入统计:",
                "      files: +2",
                "      users: +1",
                "   📚 当前数据库状态:",
                "      files: 12",
                "      topics: 3",
            ),
            time_collection_summary_messages(summary, 4),
        )

        empty_summary = {
            "new_files": 0,
            "final_files": 0,
            "imported_items": (),
            "database_items": (),
        }
        self.assertEqual(
            (
                "🎉 完整文件列表收集完成:",
                "   📊 处理页数: 0",
                "   📁 新增文件: 0 (总计: 0)",
                "   📋 累计导入统计:",
                "   📚 当前数据库状态:",
            ),
            time_collection_summary_messages(empty_summary, 0),
        )

    def test_latest_file_create_time_query_preserves_shape_and_params(self):
        query, params = latest_file_create_time_query(511)

        self.assertIn("SELECT MAX(create_time) FROM files", query)
        self.assertIn("group_id = ?", query)
        self.assertIn("create_time IS NOT NULL AND create_time != ''", query)
        self.assertEqual((511,), params)

    def test_latest_file_create_time_preserves_empty_falsy_and_truthy_rows(self):
        self.assertIsNone(_latest_file_create_time(None))
        self.assertIsNone(_latest_file_create_time(()))
        self.assertIsNone(_latest_file_create_time((None,)))
        self.assertIsNone(_latest_file_create_time(("",)))
        self.assertIsNone(_latest_file_create_time((0,)))
        self.assertEqual("2026-05-02T00:00:00", _latest_file_create_time(("2026-05-02T00:00:00",)))
        self.assertEqual(
            "2026-05-02T00:00:00",
            _latest_file_create_time(("2026-05-02T00:00:00", "ignored")),
        )

    def test_database_time_range_helpers_preserve_query_and_result_defaults(self):
        query, params = database_time_range_query(511)

        self.assertIn("SELECT MIN(create_time) as oldest_time", query)
        self.assertIn("MAX(create_time) as newest_time", query)
        self.assertIn("COUNT(*) as total_count", query)
        self.assertIn("group_id = ?", query)
        self.assertIn("create_time IS NOT NULL AND create_time != ''", query)
        self.assertEqual((511,), params)
        self.assertEqual(
            {"has_data": False, "total_files": 0},
            database_time_range_result(0, ("old", "new", 2)),
        )
        self.assertEqual(
            {
                "has_data": True,
                "total_files": 5,
                "oldest_time": None,
                "newest_time": None,
                "time_based_count": 0,
            },
            database_time_range_result(5, None),
        )
        self.assertEqual(
            {
                "has_data": True,
                "total_files": 5,
                "oldest_time": None,
                "newest_time": None,
                "time_based_count": 0,
            },
            database_time_range_result(5, ()),
        )
        self.assertEqual(
            {
                "has_data": True,
                "total_files": 5,
                "oldest_time": "old",
                "newest_time": "new",
                "time_based_count": 2,
            },
            database_time_range_result(5, ("old", "new", 2)),
        )
        self.assertEqual(
            {
                "has_data": True,
                "total_files": 5,
                "oldest_time": "old",
                "newest_time": "new",
                "time_based_count": 2,
            },
            database_time_range_result(5, ("old", "new", 2, "ignored")),
        )
        with self.assertRaises(IndexError):
            database_time_range_result(5, ("old",))
        with self.assertRaises(IndexError):
            database_time_range_result(5, ("old", "new"))

    def test_time_collection_mode_preserves_dedupe_and_force_refresh_rules(self):
        default_mode = time_collection_mode("by_create_time", False, None)
        self.assertTrue(default_mode["enable_time_dedupe"])
        self.assertEqual("   ✅ 智能去重模式: 遇到已存在的文件将停止收集", default_mode["mode_message"])

        force_mode = time_collection_mode("by_create_time", True, None)
        self.assertFalse(force_mode["enable_time_dedupe"])
        self.assertEqual("   🔄 强制刷新模式: 将收集所有文件（包括已存在的）", force_mode["mode_message"])

        bounded_mode = time_collection_mode("by_create_time", False, datetime.datetime(2026, 5, 1))
        self.assertFalse(bounded_mode["enable_time_dedupe"])
        self.assertIsNone(bounded_mode["mode_message"])

        heat_mode = time_collection_mode("by_download_count", False, None)
        self.assertFalse(heat_mode["enable_time_dedupe"])
        self.assertIsNone(heat_mode["mode_message"])

    def test_time_collection_start_messages_preserve_optional_lines(self):
        self.assertEqual(
            (
                "📊 开始按时间顺序收集文件列表到完整数据库...",
                "   📅 排序方式: by_create_time",
            ),
            time_collection_start_messages("by_create_time", "", None),
        )
        self.assertEqual(
            (
                "📊 开始按时间顺序收集文件列表到完整数据库...",
                "   📅 排序方式: by_download_count",
                "   ⏰ 起始时间: 2026-05-01T00:00:00",
                "   🎯 收集边界: 覆盖到 2026-05-01 即停止",
            ),
            time_collection_start_messages(
                "by_download_count",
                "2026-05-01T00:00:00",
                datetime.datetime(2026, 5, 1, 12, 30),
            ),
        )

    def test_time_collection_page_status_messages_preserve_existing_text(self):
        self.assertEqual(
            "   📊 数据库初始状态: 3 个文件",
            time_collection_database_status_message(3),
        )
        self.assertEqual(
            "   📅 数据库最新文件时间: 2026-05-02T00:00:00",
            time_collection_latest_file_time_message("2026-05-02T00:00:00"),
        )
        self.assertEqual("📄 收集第2页文件列表...", time_collection_page_message(2))
        self.assertEqual(
            ("❌ 第2页获取失败，收集过程中断", "💾 已成功收集前1页的数据"),
            time_collection_fetch_failed_messages(2),
        )
        self.assertEqual("📭 没有更多文件", time_collection_empty_page_message())
        self.assertEqual("   📋 当前页面: 4 个文件", time_collection_page_files_message(4))
        self.assertEqual(
            "   🗓️ 当前页文件时间范围: 2026-05-07 10:00:00 ~ 2026-05-01 09:00:00",
            time_collection_page_time_range_message(
                "2026-05-01 09:00:00",
                "2026-05-07 10:00:00",
            ),
        )
        self.assertIsNone(time_collection_page_time_range_message(None, "2026-05-07 10:00:00"))
        self.assertIsNone(time_collection_page_time_range_message("2026-05-01 09:00:00", None))
        self.assertEqual(
            "   ❌ 第2页存储失败: stable import failure",
            time_collection_storage_failed_message(2, RuntimeError("stable import failure")),
        )

    def test_time_collection_stop_and_exception_messages_preserve_existing_text(self):
        self.assertEqual("🛑 任务被停止", time_collection_initial_stop_message())
        self.assertEqual("🛑 文件收集任务被停止", time_collection_loop_stop_message())
        self.assertEqual(
            "🛑 当前页最老文件时间 2026-05-01 09:00:00 早于目标起始时间 2026-05-02，停止继续收集更早文件",
            time_collection_stop_before_boundary_message(
                datetime.datetime(2026, 5, 1, 9, 0, 0),
                datetime.datetime(2026, 5, 2, 12, 30, 0),
            ),
        )
        self.assertEqual("⏹️ 用户中断收集", time_collection_interrupted_message())
        self.assertEqual("❌ 收集过程异常: boom", time_collection_exception_message(RuntimeError("boom")))

    def test_time_collection_next_page_plan_preserves_messages_and_next_index(self):
        next_plan = time_collection_next_page_plan("next-page")
        self.assertTrue(next_plan["has_next"])
        self.assertEqual("next-page", next_plan["next_index"])
        self.assertEqual("   ⏭️ 下一页时间戳: next-page", next_plan["message"])

        terminal_plan = time_collection_next_page_plan(None)
        self.assertFalse(terminal_plan["has_next"])
        self.assertIsNone(terminal_plan["next_index"])
        self.assertEqual("📭 已到达最后一页", terminal_plan["message"])

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


class FileDownloaderInitTests(unittest.TestCase):
    def test_init_preserves_default_directory_intervals_and_storage_side_effects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            group_dir = str(Path(temp_dir) / "group-511")
            path_manager = FakeDownloaderPathManager(group_dir)
            fake_db = object()
            fake_session = object()
            expected_dir = str(Path(group_dir) / "downloads")

            with (
                patch.object(ZSXQFileDownloader, "clean_cookie", return_value="cleaned-cookie") as clean_cookie,
                patch("backend.core.db_path_manager.get_db_path_manager", return_value=path_manager),
                patch("backend.crawlers.zsxq_file_downloader.ZSXQFileDatabase", return_value=fake_db) as file_db,
                patch("backend.crawlers.zsxq_file_downloader.requests.Session", return_value=fake_session),
                patch("backend.crawlers.zsxq_file_downloader.os.makedirs") as makedirs,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                downloader = ZSXQFileDownloader(" raw-cookie ", "511")

        clean_cookie.assert_called_once_with(" raw-cookie ")
        file_db.assert_called_once_with("511")
        makedirs.assert_called_once_with(expected_dir, exist_ok=True)
        self.assertEqual(["511"], path_manager.group_ids)
        self.assertEqual("cleaned-cookie", downloader.cookie)
        self.assertEqual("511", downloader.group_id)
        self.assertEqual(expected_dir, downloader.download_dir)
        self.assertEqual(
            (1.0, 60.0, 10),
            (downloader.download_interval, downloader.long_sleep_interval, downloader.files_per_batch),
        )
        self.assertEqual(0, downloader.current_batch_count)
        self.assertFalse(downloader.use_random_interval)
        self.assertEqual((60, 180, 180, 300), (
            downloader.download_interval_min,
            downloader.download_interval_max,
            downloader.long_sleep_interval_min,
            downloader.long_sleep_interval_max,
        ))
        self.assertEqual("https://api.zsxq.com", downloader.base_url)
        self.assertIsNone(downloader.log_callback)
        self.assertIsNone(downloader.stop_check_func)
        self.assertIsNone(downloader.risk_event_log_path)
        self.assertFalse(downloader.stop_flag)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual((2.0, 5.0, 5), (downloader.min_delay, downloader.max_delay, downloader.long_delay_interval))
        self.assertEqual(
            (0, 0, False),
            (downloader.request_count, downloader.download_count, downloader.debug_mode),
        )
        self.assertIs(fake_session, downloader.session)
        self.assertIs(fake_db, downloader.file_db)
        printed = output.getvalue()
        self.assertIn(f"📁 群组 511 下载目录: {expected_dir}", printed)
        self.assertIn(f"📁 下载目录: {Path(expected_dir).absolute()}", printed)
        self.assertIn("📊 完整文件存储初始化完成: PostgreSQL schema=", printed)

    def test_init_preserves_custom_directory_and_random_interval_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_dir = str(Path(temp_dir) / "custom-downloads")
            fake_db = object()
            fake_session = object()
            expected_dir = str(Path(custom_dir) / "group_group-1")

            with (
                patch.object(ZSXQFileDownloader, "clean_cookie", return_value="cleaned-cookie"),
                patch("backend.core.db_path_manager.get_db_path_manager") as get_path_manager,
                patch("backend.crawlers.zsxq_file_downloader.ZSXQFileDatabase", return_value=fake_db),
                patch("backend.crawlers.zsxq_file_downloader.requests.Session", return_value=fake_session),
                patch("backend.crawlers.zsxq_file_downloader.os.makedirs") as makedirs,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                downloader = ZSXQFileDownloader(
                    "cookie",
                    "group-1",
                    download_dir=custom_dir,
                    download_interval=2.5,
                    long_sleep_interval=33.0,
                    files_per_batch=4,
                    download_interval_min=8,
                    download_interval_max=9,
                    long_sleep_interval_min=120,
                    long_sleep_interval_max=240,
                )

        get_path_manager.assert_not_called()
        makedirs.assert_called_once_with(expected_dir, exist_ok=True)
        self.assertEqual(expected_dir, downloader.download_dir)
        self.assertEqual(
            (2.5, 33.0, 4),
            (downloader.download_interval, downloader.long_sleep_interval, downloader.files_per_batch),
        )
        self.assertTrue(downloader.use_random_interval)
        self.assertEqual((8, 9, 120, 240), (
            downloader.download_interval_min,
            downloader.download_interval_max,
            downloader.long_sleep_interval_min,
            downloader.long_sleep_interval_max,
        ))
        self.assertIs(fake_session, downloader.session)
        self.assertIs(fake_db, downloader.file_db)


class FileDownloaderRuntimeStateTests(unittest.TestCase):
    def test_set_stop_flag_preserves_flag_update_log_and_return_value(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.stop_flag = False
        logs = []
        downloader.log = lambda message: logs.append(message)

        result = ZSXQFileDownloader.set_stop_flag(downloader)

        self.assertIsNone(result)
        self.assertTrue(downloader.stop_flag)
        self.assertEqual(["🛑 收到停止信号，任务将在下一个检查点停止"], logs)

    def test_is_stopped_preserves_local_stop_flag_short_circuit(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.stop_flag = True
        downloader.stop_check_func = lambda: self.fail("external stop check should not be called")

        self.assertTrue(ZSXQFileDownloader.is_stopped(downloader))
        self.assertTrue(downloader.stop_flag)

    def test_is_stopped_preserves_external_stop_sync(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.stop_flag = False
        calls = []

        def stop_check():
            calls.append("checked")
            return True

        downloader.stop_check_func = stop_check

        self.assertTrue(ZSXQFileDownloader.is_stopped(downloader))
        self.assertTrue(downloader.stop_flag)
        self.assertEqual(["checked"], calls)

    def test_is_stopped_preserves_false_paths(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.stop_flag = False
        downloader.stop_check_func = None

        self.assertFalse(ZSXQFileDownloader.is_stopped(downloader))
        self.assertFalse(downloader.stop_flag)

        downloader.stop_check_func = lambda: False

        self.assertFalse(ZSXQFileDownloader.is_stopped(downloader))
        self.assertFalse(downloader.stop_flag)

    def test_check_stop_preserves_legacy_alias_delegation(self):
        downloader = object.__new__(ZSXQFileDownloader)
        calls = []

        def is_stopped():
            calls.append("checked")
            return "stop-result"

        downloader.is_stopped = is_stopped

        self.assertEqual("stop-result", ZSXQFileDownloader.check_stop(downloader))
        self.assertEqual(["checked"], calls)

    def test_smart_delay_preserves_random_sleep_and_debug_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.min_delay = 2.0
        downloader.max_delay = 5.0
        downloader.debug_mode = True

        output = io.StringIO()
        with (
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=3.4) as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            contextlib.redirect_stdout(output),
        ):
            result = ZSXQFileDownloader.smart_delay(downloader)

        self.assertIsNone(result)
        uniform.assert_called_once_with(2.0, 5.0)
        sleep.assert_called_once_with(3.4)
        self.assertEqual("   ⏱️ 延迟 3.4秒\n", output.getvalue())

    def test_smart_delay_preserves_silent_non_debug_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.min_delay = 1.0
        downloader.max_delay = 2.0
        downloader.debug_mode = False

        output = io.StringIO()
        with (
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=1.25),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            contextlib.redirect_stdout(output),
        ):
            result = ZSXQFileDownloader.smart_delay(downloader)

        self.assertIsNone(result)
        sleep.assert_called_once_with(1.25)
        self.assertEqual("", output.getvalue())

    def test_check_long_delay_preserves_noop_when_threshold_not_reached(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.download_count = 4
        downloader.long_delay_interval = 5

        output = io.StringIO()
        with (
            patch("backend.crawlers.zsxq_file_downloader.random.uniform") as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            contextlib.redirect_stdout(output),
        ):
            result = ZSXQFileDownloader.check_long_delay(downloader)

        self.assertIsNone(result)
        uniform.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual("", output.getvalue())

    def test_check_long_delay_preserves_fixed_interval_sleep_and_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.download_count = 10
        downloader.long_delay_interval = 5
        downloader.use_random_interval = False
        downloader.long_sleep_interval = 120

        class FakeDateTime:
            calls = [
                datetime.datetime(2026, 6, 17, 9, 0, 0),
                datetime.datetime(2026, 6, 17, 9, 5, 0),
            ]

            @classmethod
            def now(cls):
                return cls.calls.pop(0)

        output = io.StringIO()
        with (
            patch("backend.crawlers.zsxq_file_downloader.datetime.datetime", FakeDateTime),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform") as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            contextlib.redirect_stdout(output),
        ):
            result = ZSXQFileDownloader.check_long_delay(downloader)

        self.assertIsNone(result)
        uniform.assert_not_called()
        sleep.assert_called_once_with(120)
        self.assertEqual(
            "\n".join([
                "🛌 长休眠开始: 120秒 (2.0分钟) [固定间隔]",
                "   已下载 10 个文件，进入长休眠模式...",
                "   ⏰ 开始时间: 09:00:00",
                "   🕐 预计恢复: 09:02:00",
                "😴 长休眠结束，继续下载...",
                "   🕐 实际结束: 09:05:00",
                "",
            ]),
            output.getvalue(),
        )

    def test_check_long_delay_preserves_random_interval_sleep_and_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.download_count = 6
        downloader.long_delay_interval = 3
        downloader.use_random_interval = True
        downloader.long_sleep_interval_min = 60
        downloader.long_sleep_interval_max = 180

        class FakeDateTime:
            calls = [
                datetime.datetime(2026, 6, 17, 9, 10, 0),
                datetime.datetime(2026, 6, 17, 9, 12, 0),
            ]

            @classmethod
            def now(cls):
                return cls.calls.pop(0)

        output = io.StringIO()
        with (
            patch("backend.crawlers.zsxq_file_downloader.datetime.datetime", FakeDateTime),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=90) as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            contextlib.redirect_stdout(output),
        ):
            result = ZSXQFileDownloader.check_long_delay(downloader)

        self.assertIsNone(result)
        uniform.assert_called_once_with(60, 180)
        sleep.assert_called_once_with(90)
        self.assertEqual(
            "\n".join([
                "🛌 长休眠开始: 90秒 (1.5分钟) [随机范围: 1.0-3.0分钟]",
                "   已下载 6 个文件，进入长休眠模式...",
                "   ⏰ 开始时间: 09:10:00",
                "   🕐 预计恢复: 09:11:30",
                "😴 长休眠结束，继续下载...",
                "   🕐 实际结束: 09:12:00",
                "",
            ]),
            output.getvalue(),
        )

    def test_download_delay_preserves_fixed_interval_sleep_and_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.use_random_interval = False
        downloader.download_interval = 15

        class FakeDateTime:
            calls = [
                datetime.datetime(2026, 6, 17, 10, 0, 0),
                datetime.datetime(2026, 6, 17, 10, 0, 20),
            ]

            @classmethod
            def now(cls):
                return cls.calls.pop(0)

        output = io.StringIO()
        with (
            patch("backend.crawlers.zsxq_file_downloader.datetime.datetime", FakeDateTime),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform") as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            contextlib.redirect_stdout(output),
        ):
            result = ZSXQFileDownloader.download_delay(downloader)

        self.assertIsNone(result)
        uniform.assert_not_called()
        sleep.assert_called_once_with(15)
        self.assertEqual(
            "\n".join([
                "⏳ 下载间隔: 15.0秒 [固定间隔]",
                "   ⏰ 开始时间: 10:00:00",
                "   🕐 预计恢复: 10:00:15",
                "   🕐 实际结束: 10:00:20",
                "",
            ]),
            output.getvalue(),
        )

    def test_download_delay_preserves_random_interval_sleep_and_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.use_random_interval = True
        downloader.download_interval_min = 30
        downloader.download_interval_max = 90

        class FakeDateTime:
            calls = [
                datetime.datetime(2026, 6, 17, 10, 5, 0),
                datetime.datetime(2026, 6, 17, 10, 5, 40),
            ]

            @classmethod
            def now(cls):
                return cls.calls.pop(0)

        output = io.StringIO()
        with (
            patch("backend.crawlers.zsxq_file_downloader.datetime.datetime", FakeDateTime),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=45) as uniform,
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            contextlib.redirect_stdout(output),
        ):
            result = ZSXQFileDownloader.download_delay(downloader)

        self.assertIsNone(result)
        uniform.assert_called_once_with(30, 90)
        sleep.assert_called_once_with(45)
        self.assertEqual(
            "\n".join([
                "⏳ 下载间隔: 45秒 (0.8分钟) [随机范围: 30-90秒]",
                "   ⏰ 开始时间: 10:05:00",
                "   🕐 预计恢复: 10:05:45",
                "   🕐 实际结束: 10:05:40",
                "",
            ]),
            output.getvalue(),
        )


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

    def test_download_result_stats_preserves_return_shape(self):
        self.assertEqual(
            {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0},
            download_result_stats(),
        )
        self.assertEqual(
            {"total_files": 3, "downloaded": 0, "skipped": 0, "failed": 0},
            download_result_stats(3),
        )

    def test_database_stats_table_emoji_preserves_known_and_default_labels(self):
        self.assertEqual("📄", database_stats_table_emoji("files"))
        self.assertEqual("👥", database_stats_table_emoji("users"))
        self.assertEqual("🔗", database_stats_table_emoji("file_topic_relations"))
        self.assertEqual("📊", database_stats_table_emoji("unknown_table"))

    def test_database_stats_queries_preserve_shape_and_params(self):
        size_query, size_params = database_stats_total_size_query(511)
        self.assertEqual(
            "SELECT SUM(size) FROM files WHERE group_id = ? AND size IS NOT NULL",
            size_query,
        )
        self.assertEqual((511,), size_params)

        time_query, time_params = database_stats_time_range_query("group-1")
        compact_time_query = " ".join(time_query.split())
        self.assertIn("SELECT MIN(create_time), MAX(create_time), COUNT(*) FROM files", compact_time_query)
        self.assertIn("WHERE group_id = ? AND create_time IS NOT NULL", compact_time_query)
        self.assertEqual(("group-1",), time_params)

        api_query = database_stats_api_response_query()
        compact_api_query = " ".join(api_query.split())
        self.assertEqual(
            "SELECT succeeded, COUNT(*) FROM api_responses GROUP BY succeeded",
            compact_api_query,
        )

    def test_download_settings_display_lines_preserve_existing_text(self):
        self.assertEqual(
            (
                "\n🔧 当前下载设置:",
                "   下载间隔: 60-120秒 (1.0-2.0分钟)",
                "   长休眠间隔: 每5个文件",
                "   长休眠时间: 300-600秒 (5.0-10.0分钟)",
                "   下载目录: output/downloads",
            ),
            download_settings_display_lines(60, 120, 5, 300, 600, "output/downloads"),
        )

    def test_adjust_settings_preserves_successful_update_and_directory_creation(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.download_interval_min = 60
        downloader.download_interval_max = 120
        downloader.long_delay_interval = 5
        downloader.long_delay_min = 300
        downloader.long_delay_max = 600
        downloader.download_dir = "old-downloads"
        new_dir = str(Path("output") / "downloads")

        with (
            patch("builtins.input", side_effect=["0", new_dir]),
            patch("backend.crawlers.zsxq_file_downloader.os.makedirs") as makedirs,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            ZSXQFileDownloader.adjust_settings(downloader)

        self.assertEqual(1, downloader.long_delay_interval)
        self.assertEqual(new_dir, downloader.download_dir)
        makedirs.assert_called_once_with(new_dir, exist_ok=True)
        printed = output.getvalue()
        self.assertIn("   下载目录: old-downloads", printed)
        self.assertIn(f"📁 下载目录已更新: {Path(new_dir).absolute()}", printed)
        self.assertIn("✅ 设置已更新", printed)

    def test_adjust_settings_preserves_entry_prompt_parse_and_apply_order(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.long_delay_interval = 5
        downloader.download_dir = "old-downloads"
        calls = []
        responses = iter(["8", " new-downloads "])

        downloader._print_download_settings = lambda: calls.append(("print_settings",))
        downloader._apply_adjusted_settings = lambda interval, directory: calls.append(
            ("apply", interval, directory)
        )

        def input_prompt(prompt):
            calls.append(("input", prompt))
            return next(responses)

        with patch("builtins.input", input_prompt):
            result = ZSXQFileDownloader.adjust_settings(downloader)

        self.assertIsNone(result)
        self.assertEqual(
            [
                ("print_settings",),
                ("input", "长休眠间隔 (当前每5个文件): "),
                ("input", "下载目录 (当前: old-downloads): "),
                ("apply", 8, "new-downloads"),
            ],
            calls,
        )

    def test_adjust_settings_preserves_invalid_input_without_changes(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.download_interval_min = 60
        downloader.download_interval_max = 120
        downloader.long_delay_interval = 5
        downloader.long_delay_min = 300
        downloader.long_delay_max = 600
        downloader.download_dir = "old-downloads"

        with (
            patch("builtins.input", side_effect=["invalid"]),
            patch("backend.crawlers.zsxq_file_downloader.os.makedirs") as makedirs,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            ZSXQFileDownloader.adjust_settings(downloader)

        self.assertEqual(5, downloader.long_delay_interval)
        self.assertEqual("old-downloads", downloader.download_dir)
        makedirs.assert_not_called()
        self.assertIn("❌ 输入无效，保持原设置", output.getvalue())

    def test_close_preserves_database_close_and_output_order(self):
        downloader = object.__new__(ZSXQFileDownloader)
        calls = []

        class FileDb:
            def close(self):
                calls.append(("close",))

        downloader.file_db = FileDb()

        def print_message(message=""):
            calls.append(("print", message))

        with patch("builtins.print", print_message):
            result = ZSXQFileDownloader.close(downloader)

        self.assertIsNone(result)
        self.assertEqual(
            [
                ("close",),
                ("print", "🔒 文件数据库连接已关闭"),
            ],
            calls,
        )

    def test_close_preserves_missing_or_empty_database_silent_return(self):
        downloader = object.__new__(ZSXQFileDownloader)

        with patch("builtins.print") as print_mock:
            result = ZSXQFileDownloader.close(downloader)

        self.assertIsNone(result)
        print_mock.assert_not_called()

        downloader.file_db = None
        with patch("builtins.print") as print_mock:
            result = ZSXQFileDownloader.close(downloader)

        self.assertIsNone(result)
        print_mock.assert_not_called()

    def test_download_query_group_id_preserves_cast_and_blank_semantics(self):
        self.assertEqual(123, download_query_group_id("123"))
        self.assertEqual(123, download_query_group_id(" 123 "))
        self.assertEqual("abc", download_query_group_id("abc"))
        self.assertEqual("", download_query_group_id(None))

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


class FileDownloaderCookieHelperTests(unittest.TestCase):
    def test_clean_cookie_result_preserves_existing_normalization(self):
        cases = [
            (b" a=1; b=2 \nignored", "a=1; b=2"),
            (
                " b'a=1; b=2\\n; q=\\\"x\\\"; s=\\'y\\'' ",
                "a=1; b=2; q=\"x\"; s='y'",
            ),
            ('"token=1; theme=dark"', "token=1; theme=dark"),
            (" a=1; b=2\\", "a=1; b=2"),
        ]

        for raw_cookie, expected in cases:
            with self.subTest(raw_cookie=raw_cookie):
                cleaned, error = clean_cookie_result(raw_cookie)
                self.assertIsNone(error)
                self.assertEqual(expected, cleaned)

    def test_clean_cookie_method_preserves_normalized_value_and_no_output(self):
        downloader = object.__new__(ZSXQFileDownloader)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader.clean_cookie(downloader, b" a=1; b=2 \nignored")

        self.assertEqual("a=1; b=2", result)
        self.assertEqual("", output.getvalue())

    def test_clean_cookie_method_preserves_failure_message_and_fallback_value(self):
        class StripFailure:
            def strip(self):
                raise RuntimeError("strip boom")

        raw_cookie = StripFailure()
        downloader = object.__new__(ZSXQFileDownloader)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader.clean_cookie(downloader, raw_cookie)

        self.assertIs(raw_cookie, result)
        self.assertIn("Cookie清理失败: strip boom", output.getvalue())


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

    def test_file_list_api_failure_decision_preserves_retry_stop_and_fallbacks(self):
        downloader = object.__new__(ZSXQFileDownloader)

        retry_decision = ZSXQFileDownloader._file_list_api_failure_decision(
            downloader,
            API_FAILURE_RETRY,
        )
        self.assertIsNone(retry_decision.result)
        self.assertTrue(retry_decision.should_retry)
        self.assertFalse(retry_decision.should_stop)

        non_retry_decision = ZSXQFileDownloader._file_list_api_failure_decision(
            downloader,
            API_FAILURE_NON_RETRY,
        )
        self.assertIsNone(non_retry_decision.result)
        self.assertFalse(non_retry_decision.should_retry)
        self.assertTrue(non_retry_decision.should_stop)

        permission_denied_decision = ZSXQFileDownloader._file_list_api_failure_decision(
            downloader,
            API_FAILURE_PERMISSION_DENIED_1030,
        )
        self.assertFalse(permission_denied_decision.should_retry)
        self.assertTrue(permission_denied_decision.should_stop)

        exhausted_decision = ZSXQFileDownloader._file_list_api_failure_decision(
            downloader,
            API_FAILURE_RETRY_EXHAUSTED,
        )
        self.assertIsNone(exhausted_decision.result)
        self.assertFalse(exhausted_decision.should_retry)
        self.assertFalse(exhausted_decision.should_stop)

    def test_handle_file_list_api_failure_response_preserves_retry_output_and_failure_class(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            failure_class = ZSXQFileDownloader._handle_file_list_api_failure_response(
                downloader,
                {"message": "slow down", "code": 1059},
                0,
                2,
            )

        self.assertEqual(API_FAILURE_RETRY, failure_class)
        self.assertEqual(
            [
                "   ❌ API返回失败: slow down (代码: 1059)",
                "   🔄 检测到可重试错误，准备重试...",
            ],
            output.getvalue().splitlines(),
        )

    def test_handle_file_list_api_failure_response_preserves_permission_and_exhausted_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        permission_output = io.StringIO()
        exhausted_output = io.StringIO()

        with contextlib.redirect_stdout(permission_output):
            permission_failure_class = ZSXQFileDownloader._handle_file_list_api_failure_response(
                downloader,
                {"message": "mobile only", "code": 1030},
                0,
                2,
            )
        with contextlib.redirect_stdout(exhausted_output):
            exhausted_failure_class = ZSXQFileDownloader._handle_file_list_api_failure_response(
                downloader,
                {"message": "slow down", "code": 1059},
                1,
                2,
            )

        self.assertEqual(API_FAILURE_PERMISSION_DENIED_1030, permission_failure_class)
        self.assertEqual(
            [
                "   ❌ API返回失败: mobile only (代码: 1030)",
                "   🚫 非可重试错误，停止重试",
            ],
            permission_output.getvalue().splitlines(),
        )
        self.assertEqual(API_FAILURE_RETRY_EXHAUSTED, exhausted_failure_class)
        self.assertEqual(
            ["   ❌ API返回失败: slow down (代码: 1059)"],
            exhausted_output.getvalue().splitlines(),
        )

    def test_handle_file_list_response_preserves_http_failure_decisions(self):
        downloader = object.__new__(ZSXQFileDownloader)

        with contextlib.redirect_stdout(io.StringIO()):
            retry_decision = ZSXQFileDownloader._handle_file_list_response(
                downloader,
                FakeHttpDownloadUrlResponse(500, "temporary outage"),
                0,
                2,
            )
        self.assertIsNone(retry_decision.result)
        self.assertTrue(retry_decision.should_retry)
        self.assertFalse(retry_decision.should_stop)

        with contextlib.redirect_stdout(io.StringIO()):
            stop_decision = ZSXQFileDownloader._handle_file_list_response(
                downloader,
                FakeHttpDownloadUrlResponse(403, "forbidden"),
                0,
                2,
            )
        self.assertIsNone(stop_decision.result)
        self.assertFalse(stop_decision.should_retry)
        self.assertTrue(stop_decision.should_stop)

        with contextlib.redirect_stdout(io.StringIO()):
            exhausted_decision = ZSXQFileDownloader._handle_file_list_response(
                downloader,
                FakeHttpDownloadUrlResponse(503, "still unavailable"),
                1,
                2,
            )
        self.assertIsNone(exhausted_decision.result)
        self.assertFalse(exhausted_decision.should_retry)
        self.assertFalse(exhausted_decision.should_stop)

    def test_handle_file_list_http_failure_response_preserves_output_and_failure_class(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            failure_class = ZSXQFileDownloader._handle_file_list_http_failure_response(
                downloader,
                FakeHttpDownloadUrlResponse(429, "temporary outage"),
                0,
                2,
            )

        self.assertEqual(HTTP_FAILURE_RETRY, failure_class)
        self.assertEqual(
            [
                "   ❌ HTTP错误: 429",
                "   📄 响应内容: temporary outage",
                "   🔄 服务器错误，准备重试...",
            ],
            output.getvalue().splitlines(),
        )

    def test_handle_file_list_request_exception_preserves_output_and_retry_decision(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            should_retry = ZSXQFileDownloader._handle_file_list_request_exception(
                downloader,
                RuntimeError("socket reset"),
                0,
                2,
            )

        self.assertTrue(should_retry)
        self.assertEqual(
            [
                "   ❌ 请求异常: socket reset",
                "   🔄 请求异常，准备重试...",
            ],
            output.getvalue().splitlines(),
        )

    def test_should_log_full_response_on_first_last_or_success(self):
        self.assertTrue(should_log_full_response(0, 3, False))
        self.assertFalse(should_log_full_response(1, 3, False))
        self.assertTrue(should_log_full_response(1, 3, True))
        self.assertTrue(should_log_full_response(2, 3, False))

    def test_get_download_url_preserves_entry_request_and_retry_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        expected_url = "https://api.example/v2/files/202/download_url"
        expected_result = "https://signed.example/file.pdf"
        calls = []

        def start_download_url_request(downloader_self, file_id):
            self.assertIs(downloader, downloader_self)
            calls.append(("start", file_id))
            return expected_url

        def run_download_url_retry_loop_target(downloader_self, target):
            self.assertIs(downloader, downloader_self)
            calls.append(
                (
                    "retry",
                    target.url,
                    target.file_id,
                    target.max_retries,
                )
            )
            return expected_result

        with (
            patch.object(
                ZSXQFileDownloader,
                "_start_download_url_request",
                start_download_url_request,
            ),
            patch.object(
                ZSXQFileDownloader,
                "_run_download_url_retry_loop_target",
                run_download_url_retry_loop_target,
            ),
        ):
            result = ZSXQFileDownloader.get_download_url(downloader, 202)

        self.assertEqual(expected_result, result)
        self.assertEqual(
            [
                ("start", 202),
                ("retry", expected_url, 202, 10),
            ],
            calls,
        )

    def test_file_list_request_params_preserve_index_truthiness_and_log_order(self):
        self.assertEqual(
            {"count": "20", "sort": "by_download_count", "index": "next-index"},
            file_list_request_params(20, "by_download_count", "next-index"),
        )
        self.assertEqual(
            {"count": "20", "sort": "by_create_time"},
            file_list_request_params(20, "by_create_time", ""),
        )
        self.assertEqual(
            (
                "🌐 获取文件列表",
                "   📊 参数: count=20, sort=by_download_count",
                "   📑 索引: next-index",
                "   🌐 请求URL: https://api.zsxq.com/v2/groups/511/files",
            ),
            file_list_start_messages(
                20,
                "by_download_count",
                "next-index",
                "https://api.zsxq.com/v2/groups/511/files",
            ),
        )
        self.assertEqual(
            (
                "🌐 获取文件列表",
                "   📊 参数: count=20, sort=by_create_time",
                "   🌐 请求URL: https://api.zsxq.com/v2/groups/511/files",
            ),
            file_list_start_messages(
                20,
                "by_create_time",
                None,
                "https://api.zsxq.com/v2/groups/511/files",
            ),
        )

    def test_file_list_response_page_preserves_nested_access_semantics(self):
        files = [{"file": {"id": 101}}]
        self.assertEqual(
            (files, "next-index"),
            file_list_response_page({"resp_data": {"files": files, "index": "next-index"}}),
        )
        self.assertEqual(([], None), file_list_response_page({"resp_data": {}}))
        self.assertEqual(
            (None, "cursor"),
            file_list_response_page({"resp_data": {"files": None, "index": "cursor"}}),
        )
        with self.assertRaises(AttributeError):
            file_list_response_page({"resp_data": None})

    def test_file_list_display_helpers_preserve_defaults_topic_and_footer(self):
        topic_text = "12345678901234567890123456789012345678901234567890tail"
        self.assertEqual(
            (
                " 3. 📄 demo.pdf",
                "    📊 大小: 1,048,576 bytes (1.00 MB)",
                "    📈 下载: 7 次",
                "    ⏰ 时间: 2026-05-03T10:00:00",
                "    💬 话题: 12345678901234567890123456789012345678901234567890...",
                "",
            ),
            file_list_item_display_lines(
                3,
                {
                    "file": {
                        "name": "demo.pdf",
                        "size": 1048576,
                        "download_count": 7,
                        "create_time": "2026-05-03T10:00:00",
                    },
                    "topic": {"talk": {"text": topic_text}},
                },
            ),
        )
        self.assertEqual(
            (
                " 1. 📄 Unknown",
                "    📊 大小: 0 bytes (0.00 MB)",
                "    📈 下载: 0 次",
                "    ⏰ 时间: Unknown",
                "",
            ),
            file_list_item_display_lines(1, {}),
        )
        self.assertEqual("📑 下一页索引: next-page", file_list_next_index_message("next-page"))
        self.assertEqual("📭 没有更多文件", file_list_next_index_message(""))

    def test_api_failure_detail_preserves_message_error_code_fallbacks(self):
        self.assertEqual(
            ("primary", 1059),
            api_failure_detail({"message": "primary", "error": "backup", "code": 1059}),
        )
        self.assertEqual(("backup", "N/A"), api_failure_detail({"error": "backup"}))
        self.assertEqual(("未知错误", "N/A"), api_failure_detail({}))
        self.assertEqual((None, None), api_failure_detail({"message": None, "code": None}))

    def test_classify_api_failure_distinguishes_retry_and_terminal_cases(self):
        self.assertEqual(API_FAILURE_RETRY, classify_api_failure("1059", 0, 2))
        self.assertEqual(API_FAILURE_RETRY_EXHAUSTED, classify_api_failure("1059", 1, 2))
        self.assertEqual(API_FAILURE_NON_RETRY, classify_api_failure("N/A", 0, 2))
        self.assertEqual(API_FAILURE_PERMISSION_DENIED_1030, classify_api_failure(1030, 0, 2))

    def test_file_list_api_failure_plan_preserves_retry_permission_and_exhausted_messages(self):
        retry_plan = file_list_api_failure_plan({"message": "slow", "code": 1059}, 0, 2)
        self.assertEqual(API_FAILURE_RETRY, retry_plan["failure_class"])
        self.assertEqual("slow", retry_plan["error_msg"])
        self.assertEqual(1059, retry_plan["error_code"])
        self.assertEqual(
            (
                "   ❌ API返回失败: slow (代码: 1059)",
                "   🔄 检测到可重试错误，准备重试...",
            ),
            retry_plan["messages"],
        )

        permission_plan = file_list_api_failure_plan({"message": "mobile only", "code": 1030}, 0, 2)
        self.assertEqual(API_FAILURE_PERMISSION_DENIED_1030, permission_plan["failure_class"])
        self.assertEqual(
            (
                "   ❌ API返回失败: mobile only (代码: 1030)",
                "   🚫 非可重试错误，停止重试",
            ),
            permission_plan["messages"],
        )

        exhausted_plan = file_list_api_failure_plan({"message": "slow", "code": 1059}, 1, 2)
        self.assertEqual(API_FAILURE_RETRY_EXHAUSTED, exhausted_plan["failure_class"])
        self.assertEqual(("   ❌ API返回失败: slow (代码: 1059)",), exhausted_plan["messages"])

    def test_download_url_api_failure_plan_preserves_retry_and_terminal_paths(self):
        retry_plan = download_url_api_failure_plan({"message": "slow", "code": 1059}, 0, 2)
        self.assertEqual(API_FAILURE_RETRY, retry_plan["failure_class"])
        self.assertEqual("slow", retry_plan["error_msg"])
        self.assertEqual(1059, retry_plan["error_code"])
        self.assertIsNone(retry_plan["last_download_url_error"])
        self.assertEqual(
            (
                "   ❌ API返回失败: slow (代码: 1059)",
                "   🔄 检测到可重试错误，准备重试...",
            ),
            retry_plan["messages"],
        )

        exhausted_plan = download_url_api_failure_plan({"message": "slow", "code": 1059}, 1, 2)
        self.assertEqual(API_FAILURE_RETRY_EXHAUSTED, exhausted_plan["failure_class"])
        self.assertIsNone(exhausted_plan["last_download_url_error"])
        self.assertEqual(("   ❌ API返回失败: slow (代码: 1059)",), exhausted_plan["messages"])

        permission_plan = download_url_api_failure_plan({"message": "mobile only", "code": 1030}, 0, 2)
        self.assertEqual(API_FAILURE_PERMISSION_DENIED_1030, permission_plan["failure_class"])
        self.assertEqual({"code": 1030, "message": "mobile only"}, permission_plan["last_download_url_error"])
        self.assertEqual(
            (
                "   ❌ API返回失败: mobile only (代码: 1030)",
                "   🚫 权限不足错误(1030)：此文件可能只能在手机端下载，已跳过当前文件",
            ),
            permission_plan["messages"],
        )

        non_retry_plan = download_url_api_failure_plan({"error": "final"}, 0, 2)
        self.assertEqual(API_FAILURE_NON_RETRY, non_retry_plan["failure_class"])
        self.assertEqual("final", non_retry_plan["error_msg"])
        self.assertEqual("N/A", non_retry_plan["error_code"])
        self.assertIsNone(non_retry_plan["last_download_url_error"])
        self.assertEqual(
            (
                "   ❌ API返回失败: final (代码: N/A)",
                "   🚫 非可重试错误，停止重试",
            ),
            non_retry_plan["messages"],
        )

    def test_download_url_data_decision_preserves_success_decision_and_event(self):
        downloader = object.__new__(ZSXQFileDownloader)
        events = []
        downloader._record_risk_event = lambda **kwargs: events.append(kwargs)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            decision = ZSXQFileDownloader._download_url_data_decision(
                downloader,
                {"succeeded": True, "resp_data": {"download_url": "https://files.example/signed-token"}},
                101,
                2,
                3,
                {"User-Agent": "unit-test-agent"},
                200,
            )

        self.assertEqual("https://files.example/signed-token", decision.download_url)
        self.assertFalse(decision.should_retry)
        self.assertFalse(decision.should_stop)
        self.assertEqual("   ✅ 重试成功！第2次重试获取到下载链接\n", output.getvalue())
        self.assertEqual(
            [
                {
                    "file_id": 101,
                    "phase": "download_url_retry_response",
                    "attempt": 2,
                    "headers": {"User-Agent": "unit-test-agent"},
                    "http_status": 200,
                    "status": "api_success",
                }
            ],
            events,
        )

    def test_download_url_data_decision_preserves_permission_failure_decision(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logged = []
        downloader.log = downloader.logged.append
        events = []
        downloader._record_risk_event = lambda **kwargs: events.append(kwargs)
        downloader.last_download_url_error = None

        decision = ZSXQFileDownloader._download_url_data_decision(
            downloader,
            {"succeeded": False, "message": "mobile only", "code": 1030},
            202,
            0,
            2,
            {"User-Agent": "unit-test-agent"},
            200,
        )

        self.assertIsNone(decision.download_url)
        self.assertFalse(decision.should_retry)
        self.assertTrue(decision.should_stop)
        self.assertEqual({"code": 1030, "message": "mobile only"}, downloader.last_download_url_error)
        self.assertEqual(
            [
                "   ❌ API返回失败: mobile only (代码: 1030)",
                "   🚫 权限不足错误(1030)：此文件可能只能在手机端下载，已跳过当前文件",
            ],
            downloader.logged,
        )
        self.assertEqual(
            [
                {
                    "file_id": 202,
                    "phase": "download_url_response",
                    "attempt": 0,
                    "headers": {"User-Agent": "unit-test-agent"},
                    "http_status": 200,
                    "api_code": 1030,
                    "api_message": "mobile only",
                    "status": "api_failed",
                }
            ],
            events,
        )

    def test_handle_download_url_api_failure_response_preserves_retry_logs_event_and_decision(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logged = []
        downloader.log = downloader.logged.append
        risk_events = []
        downloader._record_risk_event = lambda **kwargs: risk_events.append(kwargs)
        downloader.last_download_url_error = None

        failure_class = ZSXQFileDownloader._handle_download_url_api_failure_response(
            downloader,
            {"message": "slow down", "code": 1059},
            101,
            0,
            2,
            {"User-Agent": "unit-test-agent"},
            200,
        )

        self.assertEqual(API_FAILURE_RETRY, failure_class)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(
            [
                "   ❌ API返回失败: slow down (代码: 1059)",
                "   🔄 检测到可重试错误，准备重试...",
            ],
            downloader.logged,
        )
        self.assertEqual(
            [
                {
                    "file_id": 101,
                    "phase": "download_url_response",
                    "attempt": 0,
                    "headers": {"User-Agent": "unit-test-agent"},
                    "http_status": 200,
                    "api_code": 1059,
                    "api_message": "slow down",
                    "status": "api_failed",
                }
            ],
            risk_events,
        )

    def test_handle_download_url_api_failure_response_preserves_log_event_log_order(self):
        downloader = object.__new__(ZSXQFileDownloader)
        operations = []
        downloader.log = lambda message: operations.append(("log", message))
        downloader._record_risk_event = lambda **kwargs: operations.append(("event", kwargs))
        downloader.last_download_url_error = None

        failure_class = ZSXQFileDownloader._handle_download_url_api_failure_response(
            downloader,
            {"message": "slow down", "code": 1059},
            101,
            0,
            2,
            {"User-Agent": "unit-test-agent"},
            200,
        )

        self.assertEqual(API_FAILURE_RETRY, failure_class)
        self.assertEqual(
            [
                ("log", "   ❌ API返回失败: slow down (代码: 1059)"),
                (
                    "event",
                    {
                        "file_id": 101,
                        "phase": "download_url_response",
                        "attempt": 0,
                        "headers": {"User-Agent": "unit-test-agent"},
                        "http_status": 200,
                        "api_code": 1059,
                        "api_message": "slow down",
                        "status": "api_failed",
                    },
                ),
                ("log", "   🔄 检测到可重试错误，准备重试..."),
            ],
            operations,
        )

    def test_handle_download_url_api_failure_response_preserves_permission_error_state(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logged = []
        downloader.log = downloader.logged.append
        risk_events = []
        downloader._record_risk_event = lambda **kwargs: risk_events.append(kwargs)
        downloader.last_download_url_error = None

        failure_class = ZSXQFileDownloader._handle_download_url_api_failure_response(
            downloader,
            {"message": "mobile only", "code": 1030},
            202,
            0,
            2,
            {"User-Agent": "unit-test-agent"},
            403,
        )

        self.assertEqual(API_FAILURE_PERMISSION_DENIED_1030, failure_class)
        self.assertEqual({"code": 1030, "message": "mobile only"}, downloader.last_download_url_error)
        self.assertEqual(
            [
                "   ❌ API返回失败: mobile only (代码: 1030)",
                "   🚫 权限不足错误(1030)：此文件可能只能在手机端下载，已跳过当前文件",
            ],
            downloader.logged,
        )
        self.assertEqual(1, len(risk_events))
        self.assertEqual(202, risk_events[0]["file_id"])
        self.assertEqual(403, risk_events[0]["http_status"])
        self.assertEqual(1030, risk_events[0]["api_code"])
        self.assertEqual("mobile only", risk_events[0]["api_message"])

    def test_handle_download_url_http_failure_response_preserves_output_and_failure_class(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            failure_class = ZSXQFileDownloader._handle_download_url_http_failure_response(
                downloader,
                403,
                "forbidden",
                0,
                2,
            )

        self.assertEqual(HTTP_FAILURE_NON_RETRY, failure_class)
        self.assertEqual(
            [
                "   ❌ HTTP错误: 403",
                "   📄 响应内容: forbidden",
                "   🚫 非可重试HTTP错误，停止重试",
            ],
            output.getvalue().splitlines(),
        )

    def test_handle_download_url_request_exception_preserves_output_and_retry_decision(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            should_retry = ZSXQFileDownloader._handle_download_url_request_exception(
                downloader,
                RuntimeError("final"),
                1,
                2,
            )

        self.assertFalse(should_retry)
        self.assertEqual(
            [
                "   ❌ 请求异常: final",
            ],
            output.getvalue().splitlines(),
        )

    def test_classify_http_failure_distinguishes_retry_and_terminal_cases(self):
        self.assertEqual(HTTP_FAILURE_RETRY, classify_http_failure(429, 0, 2))
        self.assertEqual(HTTP_FAILURE_RETRY_EXHAUSTED, classify_http_failure(503, 1, 2))
        self.assertEqual(HTTP_FAILURE_NON_RETRY, classify_http_failure(403, 0, 2))

    def test_http_failure_plan_preserves_messages_redaction_and_terminal_paths(self):
        retry_plan = http_failure_plan(
            429,
            '{"download_url": "https://signed.example/file.pdf", "message": "slow down"}',
            0,
            2,
        )
        self.assertEqual(HTTP_FAILURE_RETRY, retry_plan["failure_class"])
        self.assertEqual(
            (
                "   ❌ HTTP错误: 429",
                '   📄 响应内容: {"download_url": "<redacted>", "message": "slow down"}',
                "   🔄 服务器错误，准备重试...",
            ),
            retry_plan["messages"],
        )

        non_retry_plan = http_failure_plan(403, "forbidden", 0, 2)
        self.assertEqual(HTTP_FAILURE_NON_RETRY, non_retry_plan["failure_class"])
        self.assertEqual(
            (
                "   ❌ HTTP错误: 403",
                "   📄 响应内容: forbidden",
                "   🚫 非可重试HTTP错误，停止重试",
            ),
            non_retry_plan["messages"],
        )

        exhausted_plan = http_failure_plan(503, "temporary", 1, 2)
        self.assertEqual(HTTP_FAILURE_RETRY_EXHAUSTED, exhausted_plan["failure_class"])
        self.assertEqual(
            (
                "   ❌ HTTP错误: 503",
                "   📄 响应内容: temporary",
            ),
            exhausted_plan["messages"],
        )

    def test_request_exception_plan_preserves_retry_messages_and_exhausted_message(self):
        retry_plan = request_exception_plan(RuntimeError("temporary"), 0, 2)
        self.assertTrue(retry_plan["should_retry"])
        self.assertEqual(
            (
                "   ❌ 请求异常: temporary",
                "   🔄 请求异常，准备重试...",
            ),
            retry_plan["messages"],
        )

        terminal_plan = request_exception_plan(RuntimeError("final"), 1, 2)
        self.assertFalse(terminal_plan["should_retry"])
        self.assertEqual(("   ❌ 请求异常: final",), terminal_plan["messages"])
        self.assertEqual("   🚫 已重试10次，全部失败", retry_exhausted_message(10))

    def test_api_retry_messages_preserve_wait_format_and_user_agent_truncation(self):
        self.assertEqual(
            "   🔄 第2次重试，等待15.2秒...",
            api_retry_wait_message(2, 15.24),
        )
        self.assertEqual(
            "   🔄 重试#2: 使用新的User-Agent: abc...",
            api_retry_user_agent_message(2, {"User-Agent": "abc"}),
        )
        self.assertEqual(
            "   🔄 重试#3: 使用新的User-Agent: 12345678901234567890123456789012345678901234567890...",
            api_retry_user_agent_message(3, {"User-Agent": "12345678901234567890123456789012345678901234567890tail"}),
        )
        self.assertEqual(
            "   🔄 重试#4: 使用新的User-Agent: N/A...",
            api_retry_user_agent_message(4, {}),
        )

    def test_json_decode_failure_plan_preserves_redaction_and_retry_paths(self):
        decode_error = json.JSONDecodeError("bad json", "{", 0)
        retry_plan = json_decode_failure_plan(
            decode_error,
            '{"download_url": "https://signed.example/file.pdf", "message": "bad"}',
            0,
            2,
        )
        self.assertTrue(retry_plan["should_retry"])
        self.assertEqual(
            (
                "   ❌ JSON解析失败: bad json: line 1 column 1 (char 0)",
                '   📄 原始响应: {"download_url": "<redacted>", "message": "bad"}',
                "   🔄 JSON解析失败，准备重试...",
            ),
            retry_plan["messages"],
        )

        terminal_plan = json_decode_failure_plan(decode_error, "not-json", 1, 2)
        self.assertFalse(terminal_plan["should_retry"])
        self.assertEqual(
            (
                "   ❌ JSON解析失败: bad json: line 1 column 1 (char 0)",
                "   📄 原始响应: not-json",
            ),
            terminal_plan["messages"],
        )

    def test_download_url_success_plan_preserves_first_attempt_and_retry_messages(self):
        self.assertEqual(
            ("   ✅ 获取下载链接成功", "download_url_response"),
            download_url_success_plan(0),
        )
        self.assertEqual(
            ("   ✅ 重试成功！第2次重试获取到下载链接", "download_url_retry_response"),
            download_url_success_plan(2),
        )

    def test_handle_download_url_success_response_preserves_missing_url_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader._handle_download_url_success_response(
                downloader,
                {"succeeded": True, "resp_data": {}},
                101,
                0,
                {"User-Agent": "unit-test-agent"},
                200,
            )

        self.assertIsNone(result)
        self.assertEqual("   ❌ 响应中无下载链接字段\n", output.getvalue())

    def test_handle_download_url_success_response_missing_url_does_not_record_risk_event(self):
        downloader = object.__new__(ZSXQFileDownloader)
        events = []
        downloader._record_risk_event = lambda **kwargs: events.append(kwargs)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader._handle_download_url_success_response(
                downloader,
                {"succeeded": True, "resp_data": {}},
                101,
                0,
                {"User-Agent": "unit-test-agent"},
                200,
            )

        self.assertIsNone(result)
        self.assertEqual([], events)
        self.assertEqual("   ❌ 响应中无下载链接字段\n", output.getvalue())

    def test_handle_download_url_success_response_preserves_print_event_order(self):
        downloader = object.__new__(ZSXQFileDownloader)
        operations = []
        downloader._record_risk_event = lambda **kwargs: operations.append(("event", kwargs))

        with patch(
            "backend.crawlers.zsxq_file_downloader.print",
            lambda message: operations.append(("print", message)),
        ):
            result = ZSXQFileDownloader._handle_download_url_success_response(
                downloader,
                {"succeeded": True, "resp_data": {"download_url": "https://files.example/signed-token"}},
                101,
                2,
                {"User-Agent": "unit-test-agent"},
                200,
            )

        self.assertEqual("https://files.example/signed-token", result)
        self.assertEqual(
            [
                ("print", "   ✅ 重试成功！第2次重试获取到下载链接"),
                (
                    "event",
                    {
                        "file_id": 101,
                        "phase": "download_url_retry_response",
                        "attempt": 2,
                        "headers": {"User-Agent": "unit-test-agent"},
                        "http_status": 200,
                        "status": "api_success",
                    },
                ),
            ],
            operations,
        )

    def test_handle_download_url_success_response_preserves_resp_data_none_error(self):
        downloader = object.__new__(ZSXQFileDownloader)

        with self.assertRaises(AttributeError):
            ZSXQFileDownloader._handle_download_url_success_response(
                downloader,
                {"succeeded": True, "resp_data": None},
                101,
                0,
                {"User-Agent": "unit-test-agent"},
                200,
            )

    def test_handle_download_url_ok_response_preserves_json_decode_retry_decision(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            decision = ZSXQFileDownloader._handle_download_url_ok_response(
                downloader,
                FakeInvalidJsonResponse(),
                101,
                0,
                2,
                {"User-Agent": "unit-test-agent"},
            )

        self.assertIsNone(decision.download_url)
        self.assertTrue(decision.should_retry)
        self.assertFalse(decision.should_stop)
        self.assertEqual(
            [
                "   ❌ JSON解析失败: bad json: line 1 column 2 (char 1)",
                "   📄 原始响应: {not json",
                "   🔄 JSON解析失败，准备重试...",
            ],
            output.getvalue().splitlines(),
        )

    def test_handle_download_url_ok_response_preserves_empty_json_retry_without_missing_url_output(self):
        class FakeEmptyJsonResponse:
            status_code = 200
            text = "{}"

            def json(self):
                return {}

        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            decision = ZSXQFileDownloader._handle_download_url_ok_response(
                downloader,
                FakeEmptyJsonResponse(),
                101,
                0,
                2,
                {"User-Agent": "unit-test-agent"},
            )

        self.assertIsNone(decision.download_url)
        self.assertTrue(decision.should_retry)
        self.assertFalse(decision.should_stop)
        self.assertIn("   📋 响应内容: {}", output.getvalue())
        self.assertNotIn("响应中无下载链接字段", output.getvalue())

    def test_handle_download_url_response_preserves_success_branch_output_and_event(self):
        downloader = object.__new__(ZSXQFileDownloader)
        events = []
        downloader._record_risk_event = lambda **kwargs: events.append(kwargs)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            decision = ZSXQFileDownloader._handle_download_url_response(
                downloader,
                FakeJsonResponse(),
                101,
                0,
                2,
                {"User-Agent": "unit-test-agent"},
            )

        printed = output.getvalue()
        self.assertEqual("https://files.example/signed-token", decision.download_url)
        self.assertFalse(decision.should_retry)
        self.assertFalse(decision.should_stop)
        self.assertIn("   📊 响应状态: 200", printed)
        self.assertIn('"download_url": "<redacted>"', printed)
        self.assertNotIn("https://files.example/signed-token", printed)
        self.assertIn("   ✅ 获取下载链接成功", printed)
        self.assertEqual(
            [
                {
                    "file_id": 101,
                    "phase": "download_url_response",
                    "attempt": 0,
                    "headers": {"User-Agent": "unit-test-agent"},
                    "http_status": 200,
                    "status": "api_success",
                }
            ],
            events,
        )

    def test_handle_download_url_response_preserves_http_failure_stop_decision(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            decision = ZSXQFileDownloader._handle_download_url_response(
                downloader,
                FakeHttpDownloadUrlResponse(403, "forbidden"),
                202,
                0,
                2,
                {"User-Agent": "unit-test-agent"},
            )

        self.assertIsNone(decision.download_url)
        self.assertFalse(decision.should_retry)
        self.assertTrue(decision.should_stop)
        self.assertEqual(
            [
                "   📊 响应状态: 403",
                "   ❌ HTTP错误: 403",
                "   📄 响应内容: forbidden",
                "   🚫 非可重试HTTP错误，停止重试",
            ],
            output.getvalue().splitlines(),
        )

    def test_run_download_url_attempt_preserves_success_handoff_order(self):
        downloader = object.__new__(ZSXQFileDownloader)
        headers = {"User-Agent": "unit-test-agent"}
        response = FakeJsonResponse()
        expected_decision = (None, True, False)
        operations = []

        def prepare_retry_api_request(attempt, file_id=None):
            operations.append(("prepare", attempt, file_id))
            return headers

        def request_download_url_response_target(target):
            operations.append(("request", target.url, target.headers))
            return response

        def handle_download_url_response_target(target):
            operations.append(
                (
                    "response",
                    target.response,
                    target.file_id,
                    target.attempt,
                    target.max_retries,
                    target.headers,
                )
            )
            return expected_decision

        downloader._prepare_retry_api_request = prepare_retry_api_request
        downloader._request_download_url_response_target = request_download_url_response_target
        downloader._handle_download_url_response_target = handle_download_url_response_target

        decision = ZSXQFileDownloader._run_download_url_attempt(
            downloader,
            "https://api.example/v2/files/101/download_url",
            101,
            1,
            3,
        )

        self.assertIs(expected_decision, decision)
        self.assertEqual(
            [
                ("prepare", 1, 101),
                ("request", "https://api.example/v2/files/101/download_url", headers),
                ("response", response, 101, 1, 3, headers),
            ],
            operations,
        )

    def test_run_download_url_attempt_preserves_exception_retry_decision(self):
        downloader = object.__new__(ZSXQFileDownloader)
        operations = []

        def prepare_retry_api_request(attempt, file_id=None):
            operations.append(("prepare", attempt, file_id))
            return {"User-Agent": "unit-test-agent"}

        def request_download_url_response_target(target):
            operations.append(("request", target.url, target.headers))
            raise RuntimeError("socket reset")

        def handle_download_url_request_exception_target(target):
            operations.append(("exception", str(target.exc), target.attempt, target.max_retries))
            return True

        downloader._prepare_retry_api_request = prepare_retry_api_request
        downloader._request_download_url_response_target = request_download_url_response_target
        downloader._handle_download_url_request_exception_target = handle_download_url_request_exception_target

        decision = ZSXQFileDownloader._run_download_url_attempt(
            downloader,
            "https://api.example/v2/files/202/download_url",
            202,
            0,
            2,
        )

        self.assertIsNone(decision.download_url)
        self.assertTrue(decision.should_retry)
        self.assertFalse(decision.should_stop)
        self.assertEqual(
            [
                ("prepare", 0, 202),
                ("request", "https://api.example/v2/files/202/download_url", {"User-Agent": "unit-test-agent"}),
                ("exception", "socket reset", 0, 2),
            ],
            operations,
        )

    def test_run_download_url_retry_loop_preserves_retry_then_success(self):
        downloader = object.__new__(ZSXQFileDownloader)
        calls = []
        decisions = [
            DownloadUrlResponseDecision(None, True, False),
            DownloadUrlResponseDecision("https://signed.example/file.pdf", False, False),
        ]

        def run_download_url_attempt_target(target):
            calls.append((target.url, target.file_id, target.attempt, target.max_retries))
            return decisions[target.attempt]

        downloader._run_download_url_attempt_target = run_download_url_attempt_target

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader._run_download_url_retry_loop_target(
                downloader,
                DownloadUrlRetryLoopTarget("https://api.example/v2/files/303/download_url", 303, 3),
            )

        self.assertEqual("https://signed.example/file.pdf", result)
        self.assertEqual(
            [
                ("https://api.example/v2/files/303/download_url", 303, 0, 3),
                ("https://api.example/v2/files/303/download_url", 303, 1, 3),
            ],
            calls,
        )
        self.assertEqual("", output.getvalue())

    def test_run_download_url_retry_loop_preserves_stop_without_exhausted_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        calls = []

        def run_download_url_attempt_target(target):
            calls.append((target.url, target.file_id, target.attempt, target.max_retries))
            return DownloadUrlResponseDecision(None, False, True)

        downloader._run_download_url_attempt_target = run_download_url_attempt_target

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader._run_download_url_retry_loop_target(
                downloader,
                DownloadUrlRetryLoopTarget("https://api.example/v2/files/404/download_url", 404, 3),
            )

        self.assertIsNone(result)
        self.assertEqual([("https://api.example/v2/files/404/download_url", 404, 0, 3)], calls)
        self.assertEqual("", output.getvalue())

    def test_run_download_url_retry_loop_preserves_exhausted_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        calls = []

        def run_download_url_attempt_target(target):
            calls.append((target.url, target.file_id, target.attempt, target.max_retries))
            return DownloadUrlResponseDecision(None, True, False)

        downloader._run_download_url_attempt_target = run_download_url_attempt_target

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader._run_download_url_retry_loop_target(
                downloader,
                DownloadUrlRetryLoopTarget("https://api.example/v2/files/505/download_url", 505, 2),
            )

        self.assertIsNone(result)
        self.assertEqual(
            [
                ("https://api.example/v2/files/505/download_url", 505, 0, 2),
                ("https://api.example/v2/files/505/download_url", 505, 1, 2),
            ],
            calls,
        )
        self.assertEqual([retry_exhausted_message(2)], output.getvalue().splitlines())

    def test_risk_event_user_agent_label_preserves_browser_platform_labels(self):
        self.assertEqual(
            "Edge Windows",
            risk_event_user_agent_label(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Edg/131.0.0.0"
            ),
        )
        self.assertEqual(
            "Safari Mac",
            risk_event_user_agent_label("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15"),
        )
        self.assertEqual("Other Other", risk_event_user_agent_label(""))

    def test_risk_event_header_profile_label_preserves_order_and_case_handling(self):
        self.assertEqual(
            "referer+origin+sec-fetch+sec-ch+x-timestamp+x-request-id",
            risk_event_header_profile_label(
                {
                    "Referer": "https://wx.zsxq.com",
                    "Origin": "https://wx.zsxq.com",
                    "Sec-Fetch-Site": "same-site",
                    "Sec-Ch-Ua": '"Chromium";v="131"',
                    "X-Timestamp": "123",
                    "X-Request-Id": "req-1",
                }
            ),
        )
        self.assertEqual("minimal", risk_event_header_profile_label({}))

    def test_risk_event_header_user_agent_preserves_case_fallback_order(self):
        self.assertEqual(
            "upper-ua",
            risk_event_header_user_agent({"User-Agent": "upper-ua", "user-agent": "lower-ua"}),
        )
        self.assertEqual("lower-ua", risk_event_header_user_agent({"user-agent": "lower-ua"}))
        self.assertEqual("", risk_event_header_user_agent({}))
        self.assertEqual("", risk_event_header_user_agent(None))

    def test_risk_event_row_preserves_field_order_labels_and_empty_values(self):
        row = risk_event_row(
            "2026-06-13T22:15:00",
            "group-1",
            101,
            "download_url_response",
            2,
            {
                "user-agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/132.0",
                "Referer": "https://wx.zsxq.com/dweb2/index/group/group-1",
                "Sec-Ch-Ua": '"Chromium";v="131"',
                "X-Request-Id": "req-1",
            },
            None,
            "",
            None,
            "api_failed",
        )

        self.assertEqual(
            [
                "timestamp",
                "group_id",
                "file_id",
                "phase",
                "attempt",
                "ua_label",
                "header_profile",
                "status",
                "http_status",
                "api_code",
                "api_message",
            ],
            list(row.keys()),
        )
        self.assertEqual("2026-06-13T22:15:00", row["timestamp"])
        self.assertEqual("group-1", row["group_id"])
        self.assertEqual(101, row["file_id"])
        self.assertEqual("download_url_response", row["phase"])
        self.assertEqual(2, row["attempt"])
        self.assertEqual("Firefox Linux", row["ua_label"])
        self.assertEqual("referer+sec-ch+x-request-id", row["header_profile"])
        self.assertEqual("api_failed", row["status"])
        self.assertEqual("", row["http_status"])
        self.assertEqual("", row["api_code"])
        self.assertEqual("", row["api_message"])

    def test_sec_ch_ua_for_user_agent_preserves_existing_mapping(self):
        self.assertEqual(
            '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            sec_ch_ua_for_user_agent("Mozilla/5.0 Chrome/131.0.0.0 Safari/537.36"),
        )
        self.assertEqual(
            '"Google Chrome";v="130", "Chromium";v="130", "Not?A_Brand";v="99"',
            sec_ch_ua_for_user_agent("Mozilla/5.0 Chrome/130.0.0.0 Safari/537.36"),
        )
        self.assertEqual(
            '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
            sec_ch_ua_for_user_agent("Mozilla/5.0 Chrome/129.0.0.0 Safari/537.36"),
        )
        self.assertEqual(
            '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            sec_ch_ua_for_user_agent("Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"),
        )
        self.assertEqual(
            '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            sec_ch_ua_for_user_agent("Mozilla/5.0 Firefox/132.0"),
        )

    def test_stealth_header_option_pools_preserve_existing_order(self):
        self.assertEqual(
            [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
            ],
            stealth_user_agents(),
        )
        self.assertEqual(
            [
                'zh-CN,zh;q=0.9,en;q=0.8',
                'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
                'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
            ],
            stealth_accept_languages(),
        )
        self.assertEqual(['"Windows"', '"macOS"', '"Linux"'], stealth_platforms())

    def test_stealth_base_headers_preserve_existing_values_and_order(self):
        headers = stealth_base_headers(
            "cookie-value",
            "group-1",
            "ua-value",
            '"Chromium";v="131"',
            'zh-CN,zh;q=0.9,en;q=0.8',
            '"Windows"',
        )

        self.assertEqual(
            [
                'Accept',
                'Accept-Language',
                'Accept-Encoding',
                'Cache-Control',
                'Connection',
                'Cookie',
                'Host',
                'Origin',
                'Pragma',
                'Referer',
                'Sec-Ch-Ua',
                'Sec-Ch-Ua-Mobile',
                'Sec-Ch-Ua-Platform',
                'Sec-Fetch-Dest',
                'Sec-Fetch-Mode',
                'Sec-Fetch-Site',
                'User-Agent',
            ],
            list(headers.keys()),
        )
        self.assertEqual('application/json, text/plain, */*', headers['Accept'])
        self.assertEqual('zh-CN,zh;q=0.9,en;q=0.8', headers['Accept-Language'])
        self.assertEqual('gzip, deflate, br', headers['Accept-Encoding'])
        self.assertEqual('no-cache', headers['Cache-Control'])
        self.assertEqual('keep-alive', headers['Connection'])
        self.assertEqual('cookie-value', headers['Cookie'])
        self.assertEqual('api.zsxq.com', headers['Host'])
        self.assertEqual('https://wx.zsxq.com', headers['Origin'])
        self.assertEqual('no-cache', headers['Pragma'])
        self.assertEqual('https://wx.zsxq.com/dweb2/index/group/group-1', headers['Referer'])
        self.assertEqual('"Chromium";v="131"', headers['Sec-Ch-Ua'])
        self.assertEqual('?0', headers['Sec-Ch-Ua-Mobile'])
        self.assertEqual('"Windows"', headers['Sec-Ch-Ua-Platform'])
        self.assertEqual('empty', headers['Sec-Fetch-Dest'])
        self.assertEqual('cors', headers['Sec-Fetch-Mode'])
        self.assertEqual('same-site', headers['Sec-Fetch-Site'])
        self.assertEqual('ua-value', headers['User-Agent'])

    def test_stealth_optional_headers_preserve_existing_values_and_order(self):
        self.assertEqual(
            {
                'DNT': '1',
                'Sec-GPC': '1',
                'Upgrade-Insecure-Requests': '1',
                'X-Requested-With': 'XMLHttpRequest',
            },
            stealth_optional_headers(),
        )
        self.assertEqual(
            ['DNT', 'Sec-GPC', 'Upgrade-Insecure-Requests', 'X-Requested-With'],
            list(stealth_optional_headers().keys()),
        )

    def test_stealth_dynamic_header_values_preserve_existing_format(self):
        self.assertEqual("1700000005", stealth_timestamp_header_value(1700000000, 5))
        self.assertEqual("1699999970", stealth_timestamp_header_value(1700000000, -30))
        self.assertEqual("req-100000000000", stealth_request_id_header_value(100000000000))
        self.assertEqual("req-999999999999", stealth_request_id_header_value(999999999999))

    def test_get_stealth_headers_preserves_random_order_and_dynamic_headers(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.cookie = "cookie-value"
        downloader.group_id = "group-1"

        selected_ua = stealth_user_agents()[0]
        selected_language = stealth_accept_languages()[2]
        selected_platform = stealth_platforms()[1]

        with (
            patch(
                "backend.crawlers.zsxq_file_downloader.random.choice",
                side_effect=[selected_ua, selected_language, selected_platform],
            ) as random_choice,
            patch(
                "backend.crawlers.zsxq_file_downloader.random.random",
                side_effect=[0.6, 0.4, 0.8, 0.51, 0.8, 0.7],
            ) as random_value,
            patch(
                "backend.crawlers.zsxq_file_downloader.random.randint",
                side_effect=[5, 123456789012],
            ) as random_int,
            patch("backend.crawlers.zsxq_file_downloader.time.time", return_value=1700000000),
        ):
            headers = ZSXQFileDownloader.get_stealth_headers(downloader)

        self.assertEqual(
            [stealth_user_agents(), stealth_accept_languages(), stealth_platforms()],
            [call.args[0] for call in random_choice.call_args_list],
        )
        self.assertEqual(6, random_value.call_count)
        self.assertEqual(
            [(-30, 30), (100000000000, 999999999999)],
            [call.args for call in random_int.call_args_list],
        )
        self.assertEqual(
            list(
                stealth_base_headers(
                    "cookie-value",
                    "group-1",
                    selected_ua,
                    sec_ch_ua_for_user_agent(selected_ua),
                    selected_language,
                    selected_platform,
                ).keys()
            )
            + ["DNT", "Upgrade-Insecure-Requests", "X-Requested-With", "X-Timestamp", "X-Request-Id"],
            list(headers.keys()),
        )
        self.assertEqual(selected_ua, headers["User-Agent"])
        self.assertEqual(selected_language, headers["Accept-Language"])
        self.assertEqual(selected_platform, headers["Sec-Ch-Ua-Platform"])
        self.assertEqual("1", headers["DNT"])
        self.assertNotIn("Sec-GPC", headers)
        self.assertEqual("1", headers["Upgrade-Insecure-Requests"])
        self.assertEqual("XMLHttpRequest", headers["X-Requested-With"])
        self.assertEqual("1700000005", headers["X-Timestamp"])
        self.assertEqual("req-123456789012", headers["X-Request-Id"])

    def test_prepare_retry_api_request_sleeps_counts_and_rotates_headers(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.log_callback = None

        with (
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            headers = ZSXQFileDownloader._prepare_retry_api_request(downloader, 1)

        sleep.assert_called_once_with(15.0)
        self.assertEqual({"User-Agent": "unit-test-agent"}, headers)
        self.assertEqual(1, downloader.request_count)

    def test_prepare_retry_api_request_without_risk_log_preserves_no_ua_log(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
        }
        downloader.logs = []
        downloader.log = downloader.logs.append

        headers = ZSXQFileDownloader._prepare_retry_api_request(downloader, 0, file_id=101)

        self.assertIn("User-Agent", headers)
        self.assertEqual([], downloader.logs)

    def test_prepare_retry_api_request_with_risk_log_records_request_event(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            risk_log = Path(temp_dir) / "risk.csv"
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.group_id = "group-1"
            downloader.risk_event_log_path = str(risk_log)
            downloader.request_count = 0
            downloader.smart_delay = lambda: None
            downloader.get_stealth_headers = lambda: {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
                "Referer": "https://wx.zsxq.com/dweb2/index/group/group-1",
                "Sec-Fetch-Site": "same-site",
            }
            downloader.logs = []
            downloader.log = downloader.logs.append

            ZSXQFileDownloader._prepare_retry_api_request(downloader, 0, file_id=101)

            with risk_log.open("r", encoding="utf-8-sig", newline="") as file_obj:
                rows = list(csv.DictReader(file_obj))

        self.assertEqual(1, len(rows))
        self.assertEqual("group-1", rows[0]["group_id"])
        self.assertEqual("101", rows[0]["file_id"])
        self.assertEqual("download_url_request", rows[0]["phase"])
        self.assertEqual("Chrome Windows", rows[0]["ua_label"])
        self.assertEqual("referer+sec-fetch", rows[0]["header_profile"])
        self.assertEqual(["   🧭 UA分类: Chrome Windows"], downloader.logs)

    def test_parse_api_json_response_logs_redacted_success_payload(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            data, should_retry = ZSXQFileDownloader._parse_api_json_response(
                downloader,
                FakeJsonResponse(),
                0,
                2,
            )

        self.assertEqual(
            {
                "succeeded": True,
                "resp_data": {"download_url": "https://files.example/signed-token"},
            },
            data,
        )
        self.assertFalse(should_retry)
        self.assertIn("响应内容", output.getvalue())
        self.assertIn('"download_url": "<redacted>"', output.getvalue())
        self.assertNotIn("https://files.example/signed-token", output.getvalue())

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

    def test_parse_api_json_response_preserves_decode_failure_output_and_retry_result(self):
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
        self.assertEqual(
            [
                "   ❌ JSON解析失败: bad json: line 1 column 2 (char 1)",
                "   📄 原始响应: {not json",
                "   🔄 JSON解析失败，准备重试...",
            ],
            output.getvalue().splitlines(),
        )

    def test_parse_api_json_response_preserves_terminal_decode_failure_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            data, should_retry = ZSXQFileDownloader._parse_api_json_response(
                downloader,
                FakeInvalidJsonResponse(),
                1,
                2,
            )

        self.assertIsNone(data)
        self.assertFalse(should_retry)
        self.assertEqual(
            [
                "   ❌ JSON解析失败: bad json: line 1 column 2 (char 1)",
                "   📄 原始响应: {not json",
            ],
            output.getvalue().splitlines(),
        )

    def test_handle_file_list_success_response_preserves_first_attempt_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        data = {"resp_data": {"files": [{"file_id": 1}, {"file_id": 2}], "index": "next"}}
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader._handle_file_list_success_response(
                downloader,
                data,
                0,
            )

        self.assertIs(data, result)
        self.assertEqual("   ✅ 获取成功: 2个文件\n", output.getvalue())

    def test_handle_file_list_success_response_preserves_retry_output(self):
        downloader = object.__new__(ZSXQFileDownloader)
        data = {"resp_data": {"files": [{"file_id": 1}], "index": None}}
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader._handle_file_list_success_response(
                downloader,
                data,
                2,
            )

        self.assertIs(data, result)
        self.assertEqual("   ✅ 重试成功！第2次重试获取到文件列表\n", output.getvalue())

    def test_fetch_file_list_preserves_entry_url_params_logs_and_response_handoff(self):
        class CapturingFileListSession:
            def __init__(self):
                self.response = SimpleNamespace(status_code=200)
                self.get_calls = []

            def get(self, url, headers=None, params=None, timeout=None):
                self.get_calls.append((url, headers, params, timeout))
                return self.response

        expected_result = {"succeeded": True, "resp_data": {"files": [], "index": "next"}}
        session = CapturingFileListSession()
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.logs = []
        downloader.log = downloader.logs.append
        prepare_calls = []
        response_targets = []
        downloader._prepare_retry_api_request = (
            lambda attempt: prepare_calls.append(attempt) or {"X-Test": "header"}
        )
        downloader._handle_file_list_response_target = (
            lambda target: response_targets.append(target)
            or SimpleNamespace(result=expected_result, should_retry=False, should_stop=False)
        )

        result = ZSXQFileDownloader.fetch_file_list(
            downloader,
            count=7,
            index="cursor",
            sort="by_create_time",
        )

        self.assertIs(expected_result, result)
        self.assertEqual([0], prepare_calls)
        self.assertEqual(
            [
                (
                    "https://api.example/v2/groups/group-1/files",
                    {"X-Test": "header"},
                    {"count": "7", "sort": "by_create_time", "index": "cursor"},
                    30,
                )
            ],
            session.get_calls,
        )
        self.assertEqual(
            [
                "🌐 获取文件列表",
                "   📊 参数: count=7, sort=by_create_time",
                "   📑 索引: cursor",
                "   🌐 请求URL: https://api.example/v2/groups/group-1/files",
            ],
            downloader.logs,
        )
        self.assertEqual(1, len(response_targets))
        self.assertIs(session.response, response_targets[0].response)
        self.assertEqual(0, response_targets[0].attempt)
        self.assertEqual(10, response_targets[0].max_retries)

    def test_fetch_file_list_retries_json_decode_failure_then_success(self):
        class FakeFileListJsonResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "succeeded": True,
                    "resp_data": {"files": [{"file": {"id": 101}}], "index": "next"},
                }

        session = FakeDownloadSession([FakeInvalidJsonResponse(), FakeFileListJsonResponse()])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.fetch_file_list(downloader, count=20)

        self.assertEqual(
            {"succeeded": True, "resp_data": {"files": [{"file": {"id": 101}}], "index": "next"}},
            result,
        )
        self.assertEqual(2, downloader.request_count)
        self.assertEqual(
            [
                ("https://api.example/v2/groups/group-1/files", 30, False),
                ("https://api.example/v2/groups/group-1/files", 30, False),
            ],
            session.get_calls,
        )
        sleep.assert_called_once_with(15.0)
        printed = output.getvalue()
        self.assertIn("   ❌ JSON解析失败: bad json", printed)
        self.assertIn("   🔄 JSON解析失败，准备重试...", printed)
        self.assertIn("   ✅ 重试成功！第1次重试获取到文件列表", printed)

    def test_fetch_file_list_preserves_first_attempt_success_output_and_logs(self):
        class FakeFileListJsonResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "succeeded": True,
                    "resp_data": {
                        "files": [{"file": {"id": 101}}, {"file": {"id": 102}}],
                        "index": "next",
                    },
                }

        session = FakeDownloadSession([FakeFileListJsonResponse()])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader.fetch_file_list(
                downloader,
                count=2,
                index="cursor",
                sort="by_create_time",
            )

        self.assertEqual(
            {
                "succeeded": True,
                "resp_data": {
                    "files": [{"file": {"id": 101}}, {"file": {"id": 102}}],
                    "index": "next",
                },
            },
            result,
        )
        self.assertEqual(1, downloader.request_count)
        self.assertEqual(
            [("https://api.example/v2/groups/group-1/files", 30, False)],
            session.get_calls,
        )
        self.assertEqual(
            [
                "🌐 获取文件列表",
                "   📊 参数: count=2, sort=by_create_time",
                "   📑 索引: cursor",
                "   🌐 请求URL: https://api.example/v2/groups/group-1/files",
            ],
            downloader.logs,
        )
        printed = output.getvalue()
        self.assertIn("   📊 响应状态: 200", printed)
        self.assertIn("   ✅ 获取成功: 2个文件", printed)

    def test_fetch_file_list_retries_api_failure_then_success(self):
        class FakeFileListJsonResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "succeeded": True,
                    "resp_data": {"files": [{"file": {"id": 101}}], "index": "next"},
                }

        session = FakeDownloadSession([
            FakeFailedJsonResponse(1059, "slow down"),
            FakeFileListJsonResponse(),
        ])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.fetch_file_list(downloader, count=20)

        self.assertEqual(
            {"succeeded": True, "resp_data": {"files": [{"file": {"id": 101}}], "index": "next"}},
            result,
        )
        self.assertEqual(2, downloader.request_count)
        self.assertEqual(
            [
                ("https://api.example/v2/groups/group-1/files", 30, False),
                ("https://api.example/v2/groups/group-1/files", 30, False),
            ],
            session.get_calls,
        )
        sleep.assert_called_once_with(15.0)
        printed = output.getvalue()
        self.assertIn("   ❌ API返回失败: slow down (代码: 1059)", printed)
        self.assertIn("   🔄 检测到可重试错误，准备重试...", printed)
        self.assertIn("   ✅ 重试成功！第1次重试获取到文件列表", printed)

    def test_fetch_file_list_stops_on_non_retry_api_failure(self):
        session = FakeDownloadSession([FakeFailedJsonResponse("4001", "final failure")])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader.fetch_file_list(downloader, count=20)

        self.assertIsNone(result)
        self.assertEqual(1, downloader.request_count)
        self.assertEqual(
            [("https://api.example/v2/groups/group-1/files", 30, False)],
            session.get_calls,
        )
        printed = output.getvalue()
        self.assertIn("   ❌ API返回失败: final failure (代码: 4001)", printed)
        self.assertIn("   🚫 非可重试错误，停止重试", printed)

    def test_fetch_file_list_retryable_api_failure_exhausts_retries(self):
        session = FakeDownloadSession([
            FakeFailedJsonResponse(1059, "slow down")
            for _ in range(10)
        ])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.fetch_file_list(downloader, count=20)

        self.assertIsNone(result)
        self.assertEqual(10, downloader.request_count)
        self.assertEqual(10, len(session.get_calls))
        self.assertEqual(9, sleep.call_count)
        printed = output.getvalue()
        self.assertIn("   ❌ API返回失败: slow down (代码: 1059)", printed)
        self.assertIn("   🔄 检测到可重试错误，准备重试...", printed)
        self.assertIn("   🚫 已重试10次，全部失败", printed)

    def test_fetch_file_list_retries_http_failure_then_success(self):
        class FakeFileListJsonResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "succeeded": True,
                    "resp_data": {"files": [{"file": {"id": 101}}], "index": "next"},
                }

        session = FakeDownloadSession([
            FakeHttpDownloadUrlResponse(500, "temporary outage"),
            FakeFileListJsonResponse(),
        ])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.fetch_file_list(downloader, count=20)

        self.assertEqual(
            {"succeeded": True, "resp_data": {"files": [{"file": {"id": 101}}], "index": "next"}},
            result,
        )
        self.assertEqual(2, downloader.request_count)
        self.assertEqual(
            [
                ("https://api.example/v2/groups/group-1/files", 30, False),
                ("https://api.example/v2/groups/group-1/files", 30, False),
            ],
            session.get_calls,
        )
        sleep.assert_called_once_with(15.0)
        printed = output.getvalue()
        self.assertIn("   ❌ HTTP错误: 500", printed)
        self.assertIn("   📄 响应内容: temporary outage", printed)
        self.assertIn("   🔄 服务器错误，准备重试...", printed)
        self.assertIn("   ✅ 重试成功！第1次重试获取到文件列表", printed)

    def test_fetch_file_list_stops_on_non_retry_http_failure(self):
        session = FakeDownloadSession([FakeHttpDownloadUrlResponse(403, "forbidden")])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader.fetch_file_list(downloader, count=20)

        self.assertIsNone(result)
        self.assertEqual(1, downloader.request_count)
        self.assertEqual(
            [("https://api.example/v2/groups/group-1/files", 30, False)],
            session.get_calls,
        )
        printed = output.getvalue()
        self.assertIn("   ❌ HTTP错误: 403", printed)
        self.assertIn("   📄 响应内容: forbidden", printed)
        self.assertIn("   🚫 非可重试HTTP错误，停止重试", printed)

    def test_fetch_file_list_retryable_http_failure_exhausts_retries(self):
        session = FakeDownloadSession([
            FakeHttpDownloadUrlResponse(503, "temporary outage")
            for _ in range(10)
        ])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.fetch_file_list(downloader, count=20)

        self.assertIsNone(result)
        self.assertEqual(10, downloader.request_count)
        self.assertEqual(10, len(session.get_calls))
        self.assertEqual(9, sleep.call_count)
        printed = output.getvalue()
        self.assertIn("   ❌ HTTP错误: 503", printed)
        self.assertIn("   📄 响应内容: temporary outage", printed)
        self.assertIn("   🔄 服务器错误，准备重试...", printed)
        self.assertIn("   🚫 已重试10次，全部失败", printed)

    def test_fetch_file_list_retries_request_exception_then_success(self):
        class FakeFileListJsonResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "succeeded": True,
                    "resp_data": {"files": [{"file": {"id": 101}}], "index": "next"},
                }

        session = FakeDownloadSession([
            RuntimeError("socket reset"),
            FakeFileListJsonResponse(),
        ])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.fetch_file_list(downloader, count=20)

        self.assertEqual(
            {"succeeded": True, "resp_data": {"files": [{"file": {"id": 101}}], "index": "next"}},
            result,
        )
        self.assertEqual(2, downloader.request_count)
        self.assertEqual(
            [
                ("https://api.example/v2/groups/group-1/files", 30, False),
                ("https://api.example/v2/groups/group-1/files", 30, False),
            ],
            session.get_calls,
        )
        sleep.assert_called_once_with(15.0)
        printed = output.getvalue()
        self.assertIn("   ❌ 请求异常: socket reset", printed)
        self.assertIn("   🔄 请求异常，准备重试...", printed)
        self.assertIn("   ✅ 重试成功！第1次重试获取到文件列表", printed)

    def test_fetch_file_list_request_exception_exhausts_retries(self):
        session = FakeDownloadSession([
            RuntimeError("socket reset")
            for _ in range(10)
        ])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.group_id = "group-1"
        downloader.session = session
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.fetch_file_list(downloader, count=20)

        self.assertIsNone(result)
        self.assertEqual(10, downloader.request_count)
        self.assertEqual(10, len(session.get_calls))
        self.assertEqual(9, sleep.call_count)
        printed = output.getvalue()
        self.assertIn("   ❌ 请求异常: socket reset", printed)
        self.assertIn("   🔄 请求异常，准备重试...", printed)
        self.assertIn("   🚫 已重试10次，全部失败", printed)


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

    def test_download_file_preserves_entry_prepare_skip_and_retry_handoff(self):
        file_info = {"file": {"id": 101, "name": "memo.pdf", "size": 4}}
        prepared = SimpleNamespace(file_id=101, file_path="memo.pdf", file_size=4)

        skipped_downloader = object.__new__(ZSXQFileDownloader)
        skipped_calls = []
        skipped_downloader._prepare_download_file_target = (
            lambda value: skipped_calls.append(("prepare", value)) or prepared
        )
        skipped_downloader._skip_existing_download_target = (
            lambda target: skipped_calls.append(("skip", target)) or "skipped"
        )
        skipped_downloader._run_download_retry_loop = lambda value: self.fail(
            "existing file skip should not run retry loop"
        )

        skipped_result = ZSXQFileDownloader.download_file(skipped_downloader, file_info)

        self.assertEqual("skipped", skipped_result)
        self.assertEqual("prepare", skipped_calls[0][0])
        self.assertIs(file_info, skipped_calls[0][1])
        self.assertEqual("skip", skipped_calls[1][0])
        self.assertEqual((101, "memo.pdf", 4), skipped_calls[1][1])

        downloaded_downloader = object.__new__(ZSXQFileDownloader)
        downloaded_calls = []
        downloaded_downloader._prepare_download_file_target = (
            lambda value: downloaded_calls.append(("prepare", value)) or prepared
        )
        downloaded_downloader._skip_existing_download_target = (
            lambda target: downloaded_calls.append(("skip", target)) or None
        )
        downloaded_downloader._run_download_retry_loop = (
            lambda value: downloaded_calls.append(("retry", value)) or True
        )

        downloaded_result = ZSXQFileDownloader.download_file(downloaded_downloader, file_info)

        self.assertTrue(downloaded_result)
        self.assertEqual(["prepare", "skip", "retry"], [name for name, *_ in downloaded_calls])
        self.assertIs(prepared, downloaded_calls[2][1])

        missing_downloader = object.__new__(ZSXQFileDownloader)
        missing_calls = []
        missing_downloader._prepare_download_file_target = (
            lambda value: missing_calls.append(("prepare", value)) or None
        )
        missing_downloader._skip_existing_download_target = lambda value: self.fail(
            "missing prepared file should not check existing file"
        )
        missing_downloader._run_download_retry_loop = lambda value: self.fail(
            "missing prepared file should not run retry loop"
        )

        missing_result = ZSXQFileDownloader.download_file(missing_downloader, file_info)

        self.assertFalse(missing_result)
        self.assertEqual([("prepare", file_info)], missing_calls)

    def test_run_download_retry_loop_preserves_initial_state_and_success_return(self):
        downloader = object.__new__(ZSXQFileDownloader)
        prepared_file = DownloadFileTarget(101, "memo.pdf", 4, "memo.pdf", "C:\\Downloads\\memo.pdf")
        calls = []

        def run_download_retry_loop_attempt_target(target):
            calls.append((target.attempt, target.download_retries, target.prepared_file, target.retry_state))
            if target.attempt == 0:
                self.assertEqual(
                    DownloadRetryState("memo.pdf", "memo.pdf", "C:\\Downloads\\memo.pdf", None, None),
                    target.retry_state,
                )
                return DownloadRetryDecision(
                    target.retry_state._replace(last_error_code="http_status", last_error="HTTP 500"),
                    None,
                )
            self.assertEqual(
                DownloadRetryState("memo.pdf", "memo.pdf", "C:\\Downloads\\memo.pdf", "http_status", "HTTP 500"),
                target.retry_state,
            )
            return DownloadRetryDecision(target.retry_state, True)

        downloader._run_download_retry_loop_attempt_target = run_download_retry_loop_attempt_target
        downloader._mark_download_failed_after_retries_target = lambda target: self.fail(
            "successful retry loop should not mark final failure"
        )

        result = ZSXQFileDownloader._run_download_retry_loop(downloader, prepared_file)

        self.assertTrue(result)
        self.assertEqual([0, 1], [attempt for attempt, *_ in calls])
        self.assertEqual([3, 3], [download_retries for _, download_retries, *_ in calls])
        self.assertTrue(all(call[2] is prepared_file for call in calls))

    def test_run_download_retry_loop_preserves_final_failure_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        prepared_file = DownloadFileTarget(202, "report.pdf", 10, "report.pdf", "C:\\Downloads\\report.pdf")
        attempt_states = []
        final_failures = []

        def run_download_retry_loop_attempt_target(target):
            attempt_states.append(target.retry_state)
            return DownloadRetryDecision(
                target.retry_state._replace(
                    last_error_code="download_exception",
                    last_error=f"stream down {target.attempt}",
                ),
                None,
            )

        def mark_download_failed_after_retries_target(target):
            final_failures.append(
                (
                    target.file_id,
                    target.download_retries,
                    target.last_error_code,
                    target.last_error,
                )
            )

        downloader._run_download_retry_loop_attempt_target = run_download_retry_loop_attempt_target
        downloader._mark_download_failed_after_retries_target = mark_download_failed_after_retries_target

        result = ZSXQFileDownloader._run_download_retry_loop(downloader, prepared_file)

        self.assertFalse(result)
        self.assertEqual(3, len(attempt_states))
        self.assertEqual(
            DownloadRetryState("report.pdf", "report.pdf", "C:\\Downloads\\report.pdf", None, None),
            attempt_states[0],
        )
        self.assertEqual(
            [(202, 3, "download_exception", "stream down 2")],
            final_failures,
        )

    def test_run_download_retry_loop_attempt_preserves_state_file_target_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        prepared_file = DownloadFileTarget(303, "original.pdf", 4, "original.pdf", "C:\\Downloads\\original.pdf")
        retry_state = DownloadRetryState("renamed.pdf", "renamed.pdf", "C:\\Downloads\\renamed.pdf", None, None)
        attempt_result = DownloadAttemptResult(True, None, "renamed.pdf", "renamed.pdf", "C:\\Downloads\\renamed.pdf")
        expected_decision = DownloadRetryDecision(retry_state, True)
        calls = []

        def run_download_attempt_target(target):
            calls.append(("attempt", target.attempt, target.download_retries, target.file_target))
            return attempt_result

        def apply_download_attempt_result_target(target):
            calls.append(("apply", target.attempt_result, target.retry_state))
            return expected_decision

        downloader._run_download_attempt_target = run_download_attempt_target
        downloader._apply_download_attempt_result_target = apply_download_attempt_result_target
        downloader._record_download_retry_exception_target = lambda target: self.fail(
            "successful attempt should not record an exception"
        )

        decision = ZSXQFileDownloader._run_download_retry_loop_attempt_target(
            downloader,
            DownloadRetryLoopAttemptTarget(1, 3, prepared_file, retry_state),
        )

        self.assertIs(expected_decision, decision)
        self.assertEqual(
            [
                (
                    "attempt",
                    1,
                    3,
                    DownloadFileTarget(303, "renamed.pdf", 4, "renamed.pdf", "C:\\Downloads\\renamed.pdf"),
                ),
                ("apply", attempt_result, retry_state),
            ],
            calls,
        )

    def test_run_download_retry_loop_attempt_preserves_exception_retry_decision(self):
        downloader = object.__new__(ZSXQFileDownloader)
        prepared_file = DownloadFileTarget(404, "memo.pdf", 4, "memo.pdf", "C:\\Downloads\\memo.pdf")
        retry_state = DownloadRetryState("memo.pdf", "memo.pdf", "C:\\Downloads\\memo.pdf", None, None)
        updated_state = retry_state._replace(last_error_code="download_exception", last_error="socket down")
        calls = []

        def run_download_attempt_target(target):
            calls.append(("attempt", target.attempt, target.download_retries, target.file_target))
            raise RuntimeError("socket down")

        def record_download_retry_exception_target(target):
            calls.append(("exception", str(target.exc), target.retry_state))
            return updated_state

        downloader._run_download_attempt_target = run_download_attempt_target
        downloader._apply_download_attempt_result_target = lambda target: self.fail(
            "failed attempt should not apply a result"
        )
        downloader._record_download_retry_exception_target = record_download_retry_exception_target

        decision = ZSXQFileDownloader._run_download_retry_loop_attempt_target(
            downloader,
            DownloadRetryLoopAttemptTarget(2, 3, prepared_file, retry_state),
        )

        self.assertEqual(DownloadRetryDecision(updated_state, None), decision)
        self.assertEqual(
            [
                ("attempt", 2, 3, prepared_file),
                ("exception", "socket down", retry_state),
            ],
            calls,
        )

    def test_apply_download_attempt_result_preserves_false_retry_decision(self):
        downloader = object.__new__(ZSXQFileDownloader)
        retry_state = DownloadRetryState("old.pdf", "old.pdf", "C:\\Downloads\\old.pdf", "old_code", "old error")
        attempt_result = DownloadAttemptResult(False, None, "new.pdf", "new.pdf", "C:\\Downloads\\new.pdf")

        decision = ZSXQFileDownloader._apply_download_attempt_result(downloader, attempt_result, retry_state)

        self.assertEqual(
            DownloadRetryDecision(
                DownloadRetryState("new.pdf", "new.pdf", "C:\\Downloads\\new.pdf", "old_code", "old error"),
                False,
            ),
            decision,
        )

    def test_apply_download_attempt_result_preserves_empty_failure_detail_as_success(self):
        downloader = object.__new__(ZSXQFileDownloader)
        retry_state = DownloadRetryState("old.pdf", "old.pdf", "C:\\Downloads\\old.pdf", "old_code", "old error")
        attempt_result = DownloadAttemptResult(None, None, "new.pdf", "new.pdf", "C:\\Downloads\\new.pdf")

        decision = ZSXQFileDownloader._apply_download_attempt_result(downloader, attempt_result, retry_state)

        self.assertEqual(
            DownloadRetryDecision(
                DownloadRetryState("new.pdf", "new.pdf", "C:\\Downloads\\new.pdf", "old_code", "old error"),
                True,
            ),
            decision,
        )

    def test_apply_download_attempt_result_preserves_failure_detail_retry_state(self):
        downloader = object.__new__(ZSXQFileDownloader)
        retry_state = DownloadRetryState("old.pdf", "old.pdf", "C:\\Downloads\\old.pdf", "old_code", "old error")
        attempt_result = DownloadAttemptResult(
            None,
            DownloadFailureDetail("size_mismatch", "size mismatch"),
            "new.pdf",
            "new.pdf",
            "C:\\Downloads\\new.pdf",
        )

        decision = ZSXQFileDownloader._apply_download_attempt_result(downloader, attempt_result, retry_state)

        self.assertEqual(
            DownloadRetryDecision(
                DownloadRetryState("new.pdf", "new.pdf", "C:\\Downloads\\new.pdf", "size_mismatch", "size mismatch"),
                None,
            ),
            decision,
        )

    def test_run_download_attempt_preserves_retry_wait_and_missing_url_result(self):
        downloader = object.__new__(ZSXQFileDownloader)
        file_target = DownloadFileTarget(505, "memo.pdf", 4, "memo.pdf", "C:\\Downloads\\memo.pdf")
        calls = []

        def wait_before_download_retry_target(target):
            calls.append(("wait", target.attempt, target.download_retries))

        def get_download_url_or_mark_unavailable(file_id):
            calls.append(("url", file_id))
            return None

        downloader._wait_before_download_retry_target = wait_before_download_retry_target
        downloader._get_download_url_or_mark_unavailable = get_download_url_or_mark_unavailable
        downloader._request_download_response = lambda url: self.fail("missing URL should not request a response")
        downloader._handle_download_response_result_target = lambda target: self.fail(
            "missing URL should not handle a response"
        )

        result = ZSXQFileDownloader._run_download_attempt_target(
            downloader,
            DownloadAttemptTarget(1, 3, file_target),
        )

        self.assertEqual(
            DownloadAttemptResult(False, None, "memo.pdf", "memo.pdf", "C:\\Downloads\\memo.pdf"),
            result,
        )
        self.assertEqual([("wait", 1, 3), ("url", 505)], calls)

    def test_run_download_attempt_preserves_response_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        file_target = DownloadFileTarget(606, "memo.pdf", 4, "memo.pdf", "C:\\Downloads\\memo.pdf")
        response = object()
        expected_result = DownloadAttemptResult(True, None, "memo.pdf", "memo.pdf", "C:\\Downloads\\memo.pdf")
        calls = []

        def get_download_url_or_mark_unavailable(file_id):
            calls.append(("url", file_id))
            return "https://download.test/606"

        def request_download_response(url):
            calls.append(("request", url))
            return response

        def handle_download_response_result_target(target):
            calls.append(("handle", target))
            return expected_result

        downloader._wait_before_download_retry_target = lambda target: self.fail("first attempt should not wait")
        downloader._get_download_url_or_mark_unavailable = get_download_url_or_mark_unavailable
        downloader._request_download_response = request_download_response
        downloader._handle_download_response_result_target = handle_download_response_result_target

        result = ZSXQFileDownloader._run_download_attempt_target(
            downloader,
            DownloadAttemptTarget(0, 3, file_target),
        )

        self.assertIs(expected_result, result)
        self.assertEqual(
            [
                ("url", 606),
                ("request", "https://download.test/606"),
                ("handle", DownloadResponseTarget(response, file_target)),
            ],
            calls,
        )

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

    def test_prepare_download_file_target_skips_stop_check_when_file_id_missing(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.download_dir = "C:\\Downloads"
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: self.fail("missing file_id should return before stop check")

        prepared = ZSXQFileDownloader._prepare_download_file_target(
            downloader,
            {"file": {"name": "memo.pdf", "size": 4, "download_count": 2}},
        )

        self.assertIsNone(prepared)
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

    def test_prepare_download_file_target_preserves_path_handoff_after_stop_check(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.download_dir = "C:\\Downloads"
        downloader.logs = []
        downloader.log = downloader.logs.append
        calls = []

        def check_stop():
            calls.append(("stop",))
            return False

        def target_path(download_dir, file_name, file_id):
            calls.append(("path", download_dir, file_name, file_id))
            return "safe.pdf", "C:\\Downloads\\safe.pdf"

        downloader.check_stop = check_stop

        with patch("backend.crawlers.zsxq_file_downloader.download_target_path", target_path):
            prepared = ZSXQFileDownloader._prepare_download_file_target(
                downloader,
                {"file": {"id": 707, "name": "memo?.pdf", "size": 9, "download_count": 1}},
            )

        self.assertEqual(
            DownloadFileTarget(707, "memo?.pdf", 9, "safe.pdf", "C:\\Downloads\\safe.pdf"),
            prepared,
        )
        self.assertEqual(
            [("stop",), ("path", "C:\\Downloads", "memo?.pdf", 707)],
            calls,
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

    def test_skip_existing_download_target_preserves_missing_file_noop(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.file_db = FakeDownloadFileDb()

        with patch(
            "backend.crawlers.zsxq_file_downloader.existing_file_matches",
            return_value=(False, False, 0),
        ) as matches:
            result = ZSXQFileDownloader._skip_existing_download_target(
                downloader,
                ExistingDownloadTarget(101, "C:\\Downloads\\memo.pdf", 4),
            )

        self.assertIsNone(result)
        matches.assert_called_once_with("C:\\Downloads\\memo.pdf", 4)
        self.assertEqual([], downloader.logs)
        self.assertEqual([], downloader.file_db.status_updates)

    def test_skip_existing_download_target_preserves_completed_update(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.file_db = FakeDownloadFileDb()

        with patch(
            "backend.crawlers.zsxq_file_downloader.existing_file_matches",
            return_value=(True, True, 4),
        ):
            result = ZSXQFileDownloader._skip_existing_download_target(
                downloader,
                ExistingDownloadTarget(101, "C:\\Downloads\\memo.pdf", 4),
            )

        self.assertEqual("skipped", result)
        self.assertEqual(["   ✅ 文件已存在且大小匹配，跳过下载"], downloader.logs)
        self.assertEqual(
            [(101, "completed", "C:\\Downloads\\memo.pdf", None, None)],
            downloader.file_db.status_updates,
        )

    def test_skip_existing_download_target_preserves_size_mismatch_redownload(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.file_db = FakeDownloadFileDb()

        with patch(
            "backend.crawlers.zsxq_file_downloader.existing_file_matches",
            return_value=(True, False, 3),
        ):
            result = ZSXQFileDownloader._skip_existing_download_target(
                downloader,
                ExistingDownloadTarget(101, "C:\\Downloads\\memo.pdf", 4),
            )

        self.assertIsNone(result)
        self.assertEqual(["   ⚠️ 文件已存在但大小不匹配，重新下载"], downloader.logs)
        self.assertEqual([], downloader.file_db.status_updates)

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

    def test_complete_successful_download_target_preserves_side_effect_order(self):
        events = []

        class RecordingFileDb:
            def update_file_download_status(
                self,
                file_id,
                status,
                file_path=None,
                error_code=None,
                error_message=None,
            ):
                events.append((file_id, status, file_path, error_code, error_message))

        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = RecordingFileDb()
        downloader.download_count = 5
        downloader.current_batch_count = 7

        def log(message):
            events.append(("log", message))

        def apply_intervals():
            events.append(
                ("intervals", downloader.download_count, downloader.current_batch_count)
            )

        downloader.log = log
        downloader._apply_download_intervals = apply_intervals

        with patch("backend.crawlers.zsxq_file_downloader.os.replace") as replace:
            replace.side_effect = lambda temp_path, file_path: events.append(
                ("replace", temp_path, file_path)
            )
            ZSXQFileDownloader._complete_successful_download_target(
                downloader,
                DownloadCompletionTarget(202, "target.pdf", "final.pdf", "temp.part"),
            )

        self.assertEqual(6, downloader.download_count)
        self.assertEqual(8, downloader.current_batch_count)
        self.assertEqual(
            [
                ("replace", "temp.part", "final.pdf"),
                ("log", "   ✅ 下载完成: target.pdf"),
                ("log", "   💾 保存路径: final.pdf"),
                (202, "completed", "final.pdf", None, None),
                ("intervals", 6, 8),
            ],
            events,
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

    def test_apply_response_filename_override_target_uses_target_fields(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.download_dir = "C:\\Downloads"
        downloader.logs = []
        downloader.log = downloader.logs.append
        calls = []
        override_headers = {"content-disposition": 'attachment; filename="real?.pdf"'}
        noop_headers = {"content-disposition": 'attachment; filename="ignored.pdf"'}

        def filename_override(file_name, file_id, download_dir, response_headers):
            calls.append((file_name, file_id, download_dir, response_headers))
            if file_name == "file_201":
                return ("real?.pdf", "real.pdf", "C:\\Downloads\\real.pdf")
            return None

        with patch(
            "backend.crawlers.zsxq_file_downloader.response_filename_override",
            filename_override,
        ):
            override = ZSXQFileDownloader._apply_response_filename_override_target(
                downloader,
                ResponseFilenameOverrideTarget("file_201", 201, override_headers),
            )
            noop = ZSXQFileDownloader._apply_response_filename_override_target(
                downloader,
                ResponseFilenameOverrideTarget("memo.pdf", 202, noop_headers),
            )

        self.assertEqual(("real?.pdf", "real.pdf", "C:\\Downloads\\real.pdf"), override)
        self.assertIsNone(noop)
        self.assertEqual(
            [
                ("file_201", 201, "C:\\Downloads", override_headers),
                ("memo.pdf", 202, "C:\\Downloads", noop_headers),
            ],
            calls,
        )
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

    def test_record_download_http_failure_target_uses_target_status(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append

        failure = ZSXQFileDownloader._record_download_http_failure_target(
            downloader,
            DownloadHttpFailureTarget(503),
        )

        self.assertEqual(("http_status", "HTTP 503"), failure)
        self.assertEqual(["   ❌ 下载失败: HTTP 503"], downloader.logs)

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

    def test_record_download_exception_target_uses_target_file_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "target-name.pdf"
            partial_path = Path(f"{file_path}.part")
            partial_path.write_bytes(b"pa")
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.logs = []
            downloader.log = downloader.logs.append

            failure = ZSXQFileDownloader._record_download_exception_target(
                downloader,
                DownloadExceptionTarget(RuntimeError("target stream down"), str(file_path)),
            )

            self.assertEqual(("download_exception", "target stream down"), failure)
            self.assertFalse(partial_path.exists())
            self.assertEqual(
                [
                    "   ❌ 下载异常: target stream down",
                    "   🗑️ 删除不完整文件",
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

    def test_request_download_response_target_uses_target_url(self):
        response = FakeDownloadResponse(200, b"memo")
        session = FakeDownloadSession([response])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.session = session
        downloader.logs = []
        downloader.log = downloader.logs.append

        requested_response = ZSXQFileDownloader._request_download_response_target(
            downloader,
            DownloadFileResponseRequestTarget("https://download.test/target"),
        )

        self.assertIs(response, requested_response)
        self.assertEqual([("https://download.test/target", 300, True)], session.get_calls)
        self.assertEqual(["   🚀 开始下载..."], downloader.logs)

    def test_download_attempt_result_for_response_status_target_preserves_branches(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        file_target = DownloadFileTarget(
            101,
            "memo.pdf",
            4,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        success_response = FakeDownloadResponse(200, b"memo")
        success_calls = []

        def successful_download_attempt_result_target(target):
            success_calls.append(target)
            return DownloadAttemptResult(
                True,
                None,
                "memo.pdf",
                "memo.pdf",
                "C:\\Downloads\\memo.pdf",
            )

        downloader._successful_download_attempt_result_target = successful_download_attempt_result_target

        success = ZSXQFileDownloader._download_attempt_result_for_response_status_target(
            downloader,
            DownloadResponseTarget(success_response, file_target),
        )
        failure = ZSXQFileDownloader._download_attempt_result_for_response_status_target(
            downloader,
            DownloadResponseTarget(FakeDownloadResponse(503), file_target),
        )

        self.assertEqual((True, None, "memo.pdf", "memo.pdf", "C:\\Downloads\\memo.pdf"), success)
        self.assertEqual([DownloadResponseTarget(success_response, file_target)], success_calls)
        self.assertEqual(
            (None, ("http_status", "HTTP 503"), "memo.pdf", "memo.pdf", "C:\\Downloads\\memo.pdf"),
            failure,
        )
        self.assertEqual(["   ❌ 下载失败: HTTP 503"], downloader.logs)

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

    def test_handle_download_response_result_target_records_exception_for_response_target(self):
        downloader = object.__new__(ZSXQFileDownloader)
        original_target = DownloadFileTarget(
            101,
            "file_101",
            4,
            "file_101",
            "C:\\Downloads\\file_101",
        )
        response_target = original_target._replace(
            file_name="real?.pdf",
            safe_filename="real.pdf",
            file_path="C:\\Downloads\\real.pdf",
        )
        response = FakeDownloadResponse(200)
        failure_exc = RuntimeError("body down")
        calls = []
        exception_targets = []

        def download_target_for_response_target(target):
            calls.append(("target", target))
            return response_target

        def download_attempt_result_for_response_status_target(target):
            calls.append(("status", target))
            raise failure_exc

        def record_download_exception_target(target):
            exception_targets.append(target)
            return DownloadFailureDetail("download_exception", "body down")

        downloader._download_target_for_response_target = download_target_for_response_target
        downloader._download_attempt_result_for_response_status_target = (
            download_attempt_result_for_response_status_target
        )
        downloader._record_download_exception_target = record_download_exception_target

        result = ZSXQFileDownloader._handle_download_response_result_target(
            downloader,
            DownloadResponseTarget(response, original_target),
        )

        self.assertEqual(
            [
                ("target", DownloadResponseTarget(response, original_target)),
                ("status", DownloadResponseTarget(response, response_target)),
            ],
            calls,
        )
        self.assertEqual(
            (None, ("download_exception", "body down"), "real?.pdf", "real.pdf", "C:\\Downloads\\real.pdf"),
            result,
        )
        self.assertEqual(1, len(exception_targets))
        self.assertIs(failure_exc, exception_targets[0].exc)
        self.assertEqual("C:\\Downloads\\real.pdf", exception_targets[0].file_path)

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

    def test_prepare_download_body_target_from_target_preserves_values_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "memo.pdf"
            partial_path = Path(f"{file_path}.part")
            partial_path.write_bytes(b"stale")
            downloader = object.__new__(ZSXQFileDownloader)

            prepared = ZSXQFileDownloader._prepare_download_body_target_from_target(
                downloader,
                DownloadBodyPreparationTarget(
                    {"content-length": "8"},
                    4,
                    str(file_path),
                ),
            )

            self.assertEqual((8, 4, str(partial_path)), prepared)
            self.assertFalse(partial_path.exists())

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

    def test_handle_successful_download_response_result_target_preserves_target_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        response = FakeDownloadResponse(200, b"memo", headers={"content-length": "8"})
        file_target = DownloadFileTarget(
            101,
            "memo?.pdf",
            4,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        body_target = DownloadBodyTarget(
            8,
            4,
            "C:\\Downloads\\memo.pdf.part",
        )
        result_target = DownloadBodyResult(True, None)
        calls = []

        def prepare_download_body_target_from_target(target):
            calls.append(("prepare", target))
            return body_target

        def write_download_response_body_result_target(target):
            calls.append(("write", target))
            return 4

        def finalize_download_body_result_decision_target(target):
            calls.append(("finalize", target))
            return result_target

        downloader._prepare_download_body_target_from_target = prepare_download_body_target_from_target
        downloader._write_download_response_body_result_target = write_download_response_body_result_target
        downloader._finalize_download_body_result_decision_target = (
            finalize_download_body_result_decision_target
        )

        result = ZSXQFileDownloader._handle_successful_download_response_result_target(
            downloader,
            DownloadResponseTarget(response, file_target),
        )

        self.assertEqual(result_target, result)
        self.assertEqual(
            [
                (
                    "prepare",
                    DownloadBodyPreparationTarget(
                        response.headers,
                        4,
                        "C:\\Downloads\\memo.pdf",
                    ),
                ),
                (
                    "write",
                    DownloadBodyResponseTarget(
                        response,
                        DownloadBodyWriteTarget(
                            "C:\\Downloads\\memo.pdf.part",
                            8,
                            101,
                        ),
                    ),
                ),
                (
                    "finalize",
                    DownloadBodyFinalizationDecisionTarget(
                        4,
                        DownloadBodyFinalizationTarget(
                            4,
                            "C:\\Downloads\\memo.pdf.part",
                            101,
                            "memo.pdf",
                            "C:\\Downloads\\memo.pdf",
                        ),
                    ),
                ),
            ],
            calls,
        )

    def test_handle_successful_download_response_result_target_preserves_body_preparation_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        response = FakeDownloadResponse(200, b"memo", headers={"content-length": "8"})
        file_target = DownloadFileTarget(
            101,
            "memo?.pdf",
            4,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        body_target = DownloadBodyTarget(
            8,
            4,
            "C:\\Downloads\\memo.pdf.part",
        )
        result_target = DownloadBodyResult(True, None)
        calls = []

        def prepare_download_body_target_from_target(target):
            calls.append(("prepare", target))
            return body_target

        def download_body_result_for_response_target(target, prepared_body_target):
            calls.append(("body", target, prepared_body_target))
            return result_target

        downloader._prepare_download_body_target_from_target = prepare_download_body_target_from_target
        downloader._download_body_result_for_response_target = download_body_result_for_response_target

        result = ZSXQFileDownloader._handle_successful_download_response_result_target(
            downloader,
            DownloadResponseTarget(response, file_target),
        )

        self.assertEqual(result_target, result)
        self.assertEqual(
            [
                (
                    "prepare",
                    DownloadBodyPreparationTarget(
                        response.headers,
                        4,
                        "C:\\Downloads\\memo.pdf",
                    ),
                ),
                (
                    "body",
                    DownloadResponseTarget(response, file_target),
                    body_target,
                ),
            ],
            calls,
        )

    def test_download_body_result_for_response_target_preserves_write_and_finalize_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        response = FakeDownloadResponse(200, b"memo", headers={"content-length": "8"})
        file_target = DownloadFileTarget(
            202,
            "memo?.pdf",
            4,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        body_target = DownloadBodyTarget(
            8,
            4,
            "C:\\Downloads\\memo.pdf.part",
        )
        result_target = DownloadBodyResult(True, None)
        calls = []

        def write_download_response_body_result_target(target):
            calls.append(("write", target))
            return 4

        def finalize_download_body_result_decision_target(target):
            calls.append(("finalize", target))
            return result_target

        downloader._write_download_response_body_result_target = write_download_response_body_result_target
        downloader._finalize_download_body_result_decision_target = (
            finalize_download_body_result_decision_target
        )

        result = ZSXQFileDownloader._download_body_result_for_response_target(
            downloader,
            DownloadResponseTarget(response, file_target),
            body_target,
        )

        self.assertEqual(result_target, result)
        self.assertEqual(
            [
                (
                    "write",
                    DownloadBodyResponseTarget(
                        response,
                        DownloadBodyWriteTarget(
                            "C:\\Downloads\\memo.pdf.part",
                            8,
                            202,
                        ),
                    ),
                ),
                (
                    "finalize",
                    DownloadBodyFinalizationDecisionTarget(
                        4,
                        DownloadBodyFinalizationTarget(
                            4,
                            "C:\\Downloads\\memo.pdf.part",
                            202,
                            "memo.pdf",
                            "C:\\Downloads\\memo.pdf",
                        ),
                    ),
                ),
            ],
            calls,
        )

    def test_download_body_result_for_response_target_preserves_finalization_decision_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        response = FakeDownloadResponse(200, b"memo", headers={"content-length": "8"})
        file_target = DownloadFileTarget(
            303,
            "memo?.pdf",
            4,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        body_target = DownloadBodyTarget(
            8,
            4,
            "C:\\Downloads\\memo.pdf.part",
        )
        write_target = DownloadBodyResponseTarget(
            response,
            DownloadBodyWriteTarget(
                "C:\\Downloads\\memo.pdf.part",
                8,
                303,
            ),
        )
        result_target = DownloadBodyResult(True, None)
        calls = []

        def download_body_write_response_target(target, prepared_body_target):
            calls.append(("write-target", target, prepared_body_target))
            return write_target

        def write_download_response_body_result_target(target):
            calls.append(("write", target))
            return 4

        def finalize_download_body_result_decision_target(target):
            calls.append(("finalize", target))
            return result_target

        downloader._download_body_write_response_target = download_body_write_response_target
        downloader._write_download_response_body_result_target = write_download_response_body_result_target
        downloader._finalize_download_body_result_decision_target = (
            finalize_download_body_result_decision_target
        )

        response_target = DownloadResponseTarget(response, file_target)
        result = ZSXQFileDownloader._download_body_result_for_response_target(
            downloader,
            response_target,
            body_target,
        )

        self.assertEqual(result_target, result)
        self.assertEqual(
            [
                (
                    "write-target",
                    response_target,
                    body_target,
                ),
                (
                    "write",
                    write_target,
                ),
                (
                    "finalize",
                    DownloadBodyFinalizationDecisionTarget(
                        4,
                        DownloadBodyFinalizationTarget(
                            4,
                            "C:\\Downloads\\memo.pdf.part",
                            303,
                            "memo.pdf",
                            "C:\\Downloads\\memo.pdf",
                        ),
                    ),
                ),
            ],
            calls,
        )

    def test_download_body_result_for_response_target_preserves_stopped_write_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        response = FakeDownloadResponse(200, b"memo", headers={"content-length": "8"})
        file_target = DownloadFileTarget(
            404,
            "memo?.pdf",
            4,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        body_target = DownloadBodyTarget(
            8,
            4,
            "C:\\Downloads\\memo.pdf.part",
        )
        write_target = DownloadBodyResponseTarget(
            response,
            DownloadBodyWriteTarget(
                "C:\\Downloads\\memo.pdf.part",
                8,
                404,
            ),
        )
        result_target = DownloadBodyResult(False, None)
        calls = []

        def download_body_write_response_target(target, prepared_body_target):
            calls.append(("write-target", target, prepared_body_target))
            return write_target

        def write_download_response_body_result_target(target):
            calls.append(("write", target))
            return None

        def finalize_download_body_result_decision_target(target):
            calls.append(("finalize", target))
            return result_target

        downloader._download_body_write_response_target = download_body_write_response_target
        downloader._write_download_response_body_result_target = write_download_response_body_result_target
        downloader._finalize_download_body_result_decision_target = (
            finalize_download_body_result_decision_target
        )

        response_target = DownloadResponseTarget(response, file_target)
        result = ZSXQFileDownloader._download_body_result_for_response_target(
            downloader,
            response_target,
            body_target,
        )

        self.assertEqual(result_target, result)
        self.assertEqual(
            [
                (
                    "write-target",
                    response_target,
                    body_target,
                ),
                (
                    "write",
                    write_target,
                ),
                (
                    "finalize",
                    DownloadBodyFinalizationDecisionTarget(
                        None,
                        DownloadBodyFinalizationTarget(
                            4,
                            "C:\\Downloads\\memo.pdf.part",
                            404,
                            "memo.pdf",
                            "C:\\Downloads\\memo.pdf",
                        ),
                    ),
                ),
            ],
            calls,
        )

    def test_finalize_download_body_result_preserves_stop_mismatch_and_success_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.file_db = FakeDownloadFileDb()
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.download_count = 0
            downloader.current_batch_count = 0
            interval_snapshots = []
            downloader._apply_download_intervals = lambda: interval_snapshots.append(
                (downloader.download_count, downloader.current_batch_count)
            )

            stopped_part = Path(temp_dir) / "stopped.pdf.part"
            stopped_part.write_bytes(b"stop")
            stopped = ZSXQFileDownloader._finalize_download_body_result(
                downloader,
                None,
                4,
                str(stopped_part),
                101,
                "stopped.pdf",
                str(Path(temp_dir) / "stopped.pdf"),
            )

            self.assertEqual((False, None), stopped)
            self.assertTrue(stopped_part.exists())
            self.assertEqual([], downloader.file_db.status_updates)

            mismatch_part = Path(temp_dir) / "mismatch.pdf.part"
            mismatch_part.write_bytes(b"bad")
            mismatch = ZSXQFileDownloader._finalize_download_body_result(
                downloader,
                3,
                4,
                str(mismatch_part),
                102,
                "mismatch.pdf",
                str(Path(temp_dir) / "mismatch.pdf"),
            )

            self.assertEqual((None, ("size_mismatch", "文件大小不匹配: 预期4, 实际3")), mismatch)
            self.assertFalse(mismatch_part.exists())
            self.assertEqual(["   ⚠️ 文件大小不匹配: 预期4, 实际3"], downloader.logs)
            self.assertEqual([], downloader.file_db.status_updates)

            success_part = Path(temp_dir) / "memo.pdf.part"
            success_path = Path(temp_dir) / "memo.pdf"
            success_part.write_bytes(b"memo")
            success = ZSXQFileDownloader._finalize_download_body_result(
                downloader,
                4,
                4,
                str(success_part),
                103,
                "memo.pdf",
                str(success_path),
            )

            self.assertEqual((True, None), success)
            self.assertEqual(b"memo", success_path.read_bytes())
            self.assertFalse(success_part.exists())
            self.assertEqual((103, "completed", str(success_path)), downloader.file_db.status_updates[-1][:3])
            self.assertEqual((1, 1), (downloader.download_count, downloader.current_batch_count))
            self.assertEqual([(1, 1)], interval_snapshots)

    def test_finalize_download_body_result_decision_target_preserves_branch_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        finalization_target = DownloadBodyFinalizationTarget(
            4,
            "C:\\Downloads\\memo.pdf.part",
            101,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )

        downloader._handle_download_size_mismatch_target = lambda target: self.fail(
            "stop path should not check size mismatch"
        )
        downloader._complete_successful_download_target = lambda target: self.fail(
            "stop path should not complete download"
        )
        stopped = ZSXQFileDownloader._finalize_download_body_result_decision_target(
            downloader,
            DownloadBodyFinalizationDecisionTarget(None, finalization_target),
        )

        self.assertEqual((False, None), stopped)

        mismatch_detail = DownloadFailureDetail("size_mismatch", "bad size")
        mismatch_calls = []

        def mismatch_target_for_failure(target):
            mismatch_calls.append(target)
            return mismatch_detail

        downloader._handle_download_size_mismatch_target = mismatch_target_for_failure
        downloader._complete_successful_download_target = lambda target: self.fail(
            "mismatch path should not complete download"
        )
        mismatch = ZSXQFileDownloader._finalize_download_body_result_decision_target(
            downloader,
            DownloadBodyFinalizationDecisionTarget(3, finalization_target),
        )

        self.assertEqual((None, mismatch_detail), mismatch)
        self.assertEqual(
            [DownloadSizeMismatchTarget(4, "C:\\Downloads\\memo.pdf.part")],
            mismatch_calls,
        )

        success_calls = []

        def mismatch_target_for_success(target):
            success_calls.append(("mismatch", target))
            return None

        def complete_successful_download_target(target):
            success_calls.append(("complete", target))

        downloader._handle_download_size_mismatch_target = mismatch_target_for_success
        downloader._complete_successful_download_target = complete_successful_download_target
        success = ZSXQFileDownloader._finalize_download_body_result_decision_target(
            downloader,
            DownloadBodyFinalizationDecisionTarget(4, finalization_target),
        )

        self.assertEqual((True, None), success)
        self.assertEqual(
            [
                ("mismatch", DownloadSizeMismatchTarget(4, "C:\\Downloads\\memo.pdf.part")),
                (
                    "complete",
                    DownloadCompletionTarget(
                        101,
                        "memo.pdf",
                        "C:\\Downloads\\memo.pdf",
                        "C:\\Downloads\\memo.pdf.part",
                    ),
                ),
            ],
            success_calls,
        )

    def test_finalize_download_body_result_decision_target_preserves_stopped_result_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        finalization_target = DownloadBodyFinalizationTarget(
            4,
            "C:\\Downloads\\memo.pdf.part",
            303,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )

        downloader._download_size_mismatch_detail_for_finalization = lambda target: self.fail(
            "stop path should not check size mismatch"
        )
        downloader._successful_download_body_result_target = lambda target: self.fail(
            "stop path should not complete download"
        )

        result = ZSXQFileDownloader._finalize_download_body_result_decision_target(
            downloader,
            DownloadBodyFinalizationDecisionTarget(None, finalization_target),
        )

        self.assertEqual((False, None), result)

    def test_finalize_download_body_result_decision_target_preserves_size_mismatch_target_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        finalization_target = DownloadBodyFinalizationTarget(
            17,
            "C:\\Downloads\\pending.tmp",
            505,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        mismatch_detail = DownloadFailureDetail("size_mismatch", "bad size")
        calls = []

        def handle_download_size_mismatch_target(target):
            calls.append(target)
            return mismatch_detail

        downloader._handle_download_size_mismatch_target = handle_download_size_mismatch_target
        downloader._successful_download_body_result_target = lambda target: self.fail(
            "mismatch path should not complete download"
        )

        result = ZSXQFileDownloader._finalize_download_body_result_decision_target(
            downloader,
            DownloadBodyFinalizationDecisionTarget(99, finalization_target),
        )

        self.assertEqual((None, mismatch_detail), result)
        self.assertEqual(
            [DownloadSizeMismatchTarget(17, "C:\\Downloads\\pending.tmp")],
            calls,
        )

    def test_finalize_download_body_result_decision_target_preserves_size_mismatch_detail_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        finalization_target = DownloadBodyFinalizationTarget(
            23,
            "C:\\Downloads\\pending.part",
            606,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        size_mismatch_target = DownloadSizeMismatchTarget(23, "C:\\Downloads\\pending.part")
        mismatch_detail = DownloadFailureDetail("size_mismatch", "bad size")
        calls = []

        def download_size_mismatch_target_for_finalization(target):
            calls.append(("target", target))
            return size_mismatch_target

        def handle_download_size_mismatch_target(target):
            calls.append(("mismatch", target))
            return mismatch_detail

        downloader._download_size_mismatch_target_for_finalization = (
            download_size_mismatch_target_for_finalization
        )
        downloader._handle_download_size_mismatch_target = handle_download_size_mismatch_target
        downloader._successful_download_body_result_target = lambda target: self.fail(
            "mismatch path should not complete download"
        )

        result = ZSXQFileDownloader._finalize_download_body_result_decision_target(
            downloader,
            DownloadBodyFinalizationDecisionTarget(99, finalization_target),
        )

        self.assertEqual((None, mismatch_detail), result)
        self.assertEqual(
            [
                ("target", finalization_target),
                ("mismatch", size_mismatch_target),
            ],
            calls,
        )

    def test_finalize_download_body_result_decision_target_preserves_size_mismatch_result_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        finalization_target = DownloadBodyFinalizationTarget(
            4,
            "C:\\Downloads\\memo.pdf.part",
            707,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        mismatch_detail = DownloadFailureDetail("size_mismatch", "bad size")
        calls = []

        def download_size_mismatch_detail_for_finalization(target):
            calls.append(("mismatch-detail", target))
            return mismatch_detail

        downloader._download_size_mismatch_detail_for_finalization = (
            download_size_mismatch_detail_for_finalization
        )
        downloader._successful_download_body_result_target = lambda target: self.fail(
            "mismatch path should not complete download"
        )

        result = ZSXQFileDownloader._finalize_download_body_result_decision_target(
            downloader,
            DownloadBodyFinalizationDecisionTarget(4, finalization_target),
        )

        self.assertEqual((None, mismatch_detail), result)
        self.assertEqual([("mismatch-detail", finalization_target)], calls)

    def test_successful_download_body_result_target_preserves_completion_target_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        finalization_target = DownloadBodyFinalizationTarget(
            42,
            "C:\\Downloads\\memo.pdf.part",
            808,
            "memo.pdf",
            "C:\\Downloads\\memo.pdf",
        )
        calls = []

        def complete_successful_download_target(target):
            calls.append(target)

        downloader._complete_successful_download_target = complete_successful_download_target

        result = ZSXQFileDownloader._successful_download_body_result_target(
            downloader,
            finalization_target,
        )

        self.assertEqual((True, None), result)
        self.assertEqual(
            [
                DownloadCompletionTarget(
                    808,
                    "memo.pdf",
                    "C:\\Downloads\\memo.pdf",
                    "C:\\Downloads\\memo.pdf.part",
                ),
            ],
            calls,
        )

    def test_successful_download_body_result_target_preserves_success_result_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        finalization_target = DownloadBodyFinalizationTarget(
            17,
            "C:\\Downloads\\ready.part",
            909,
            "ready.pdf",
            "C:\\Downloads\\ready.pdf",
        )
        completion_target = DownloadCompletionTarget(
            909,
            "ready.pdf",
            "C:\\Downloads\\ready.pdf",
            "C:\\Downloads\\ready.part",
        )
        calls = []

        def download_completion_target_for_finalization(target):
            calls.append(("target", target))
            return completion_target

        def complete_successful_download_target(target):
            calls.append(("complete", target))

        downloader._download_completion_target_for_finalization = (
            download_completion_target_for_finalization
        )
        downloader._complete_successful_download_target = complete_successful_download_target

        result = ZSXQFileDownloader._successful_download_body_result_target(
            downloader,
            finalization_target,
        )

        self.assertEqual((True, None), result)
        self.assertEqual(
            [
                ("target", finalization_target),
                ("complete", completion_target),
            ],
            calls,
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

    def test_write_download_response_body_result_target_preserves_chunk_order(self):
        class RecordingChunkResponse:
            def __init__(self):
                self.chunk_sizes = []

            def iter_content(self, chunk_size=8192):
                self.chunk_sizes.append(chunk_size)
                yield b"ab"
                yield b""
                yield b"cd"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "memo.pdf.part"
            response = RecordingChunkResponse()
            events = []
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.log = lambda message: events.append(("log", message))

            def check_stop():
                events.append(("stop",))
                return False

            downloader.check_stop = check_stop

            downloaded_size = ZSXQFileDownloader._write_download_response_body_result_target(
                downloader,
                DownloadBodyResponseTarget(
                    response,
                    DownloadBodyWriteTarget(str(temp_path), 4, 101),
                ),
            )

            self.assertEqual(4, downloaded_size)
            self.assertEqual([8192], response.chunk_sizes)
            self.assertEqual(b"abcd", temp_path.read_bytes())
            self.assertEqual(
                [
                    ("stop",),
                    ("log", "   📊 进度: 100.0% (4/4 bytes)"),
                    ("stop",),
                ],
                events,
            )

    def test_write_download_response_body_result_target_stops_after_nonempty_chunk(self):
        class StoppingChunkResponse:
            def __init__(self):
                self.seen = []

            def iter_content(self, chunk_size=8192):
                self.seen.append(("chunk_size", chunk_size))
                yield b"ab"
                self.seen.append(("after_first",))
                yield b"cd"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "memo.pdf.part"
            response = StoppingChunkResponse()
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.file_db = FakeDownloadFileDb()
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.check_stop = lambda: True

            with patch(
                "backend.crawlers.zsxq_file_downloader.remove_partial_download",
                return_value=True,
            ) as remove_partial:
                downloaded_size = ZSXQFileDownloader._write_download_response_body_result_target(
                    downloader,
                    DownloadBodyResponseTarget(
                        response,
                        DownloadBodyWriteTarget(str(temp_path), 0, 101),
                    ),
                )

            self.assertIsNone(downloaded_size)
            self.assertEqual([("chunk_size", 8192)], response.seen)
            self.assertEqual(b"ab", temp_path.read_bytes())
            remove_partial.assert_called_once_with(str(temp_path))
            self.assertEqual(
                (101, "failed", None, "stopped", "下载过程中被停止"),
                downloader.file_db.status_updates[-1],
            )
            self.assertEqual(
                ["   📊 已下载: 2 bytes", "🛑 下载过程中被停止"],
                downloader.logs,
            )

    def test_write_download_response_body_result_target_truncates_existing_partial_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "memo.pdf.part"
            temp_path.write_bytes(b"old-body")
            response = FakeChunkedDownloadResponse([b"new"])
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.logs = []
            downloader.log = downloader.logs.append
            downloader.check_stop = lambda: False

            downloaded_size = ZSXQFileDownloader._write_download_response_body_result_target(
                downloader,
                DownloadBodyResponseTarget(
                    response,
                    DownloadBodyWriteTarget(str(temp_path), 3, 101),
                ),
            )

            self.assertEqual(3, downloaded_size)
            self.assertEqual(b"new", temp_path.read_bytes())
            self.assertEqual(["   📊 进度: 100.0% (3/3 bytes)"], downloader.logs)

    def test_write_download_body_chunk_preserves_write_size_and_progress_log(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.logs = []
        downloader.log = downloader.logs.append
        file_obj = io.BytesIO()

        downloaded_size = ZSXQFileDownloader._write_download_body_chunk(
            downloader,
            file_obj,
            b"ab",
            0,
            4,
        )

        self.assertEqual(2, downloaded_size)
        self.assertEqual(b"ab", file_obj.getvalue())
        self.assertEqual([], downloader.logs)

        downloaded_size = ZSXQFileDownloader._write_download_body_chunk(
            downloader,
            file_obj,
            b"cd",
            downloaded_size,
            4,
        )

        self.assertEqual(4, downloaded_size)
        self.assertEqual(b"abcd", file_obj.getvalue())
        self.assertEqual(["   📊 进度: 100.0% (4/4 bytes)"], downloader.logs)

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

    def test_download_file_retries_request_exception_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            partial_path = Path(temp_dir) / "memo.pdf.part"
            partial_path.write_bytes(b"stale")
            session = FakeDownloadSession([
                RuntimeError("socket down"),
                RuntimeError("socket down"),
                RuntimeError("socket down"),
            ])
            downloader = self._downloader_for_download(temp_dir, session)

            with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
                result = ZSXQFileDownloader.download_file(
                    downloader,
                    {"file": {"id": 101, "name": "memo.pdf", "size": 4, "download_count": 0}},
                )

            self.assertFalse(result)
            self.assertEqual(3, len(session.get_calls))
            self.assertEqual(2, sleep.call_count)
            self.assertFalse(partial_path.exists())
            self.assertEqual(
                (101, "failed", None, "download_exception", "socket down"),
                downloader.file_db.status_updates[-1],
            )
            self.assertIn("   ❌ 下载异常: socket down", downloader.logs)
            self.assertIn("   🗑️ 删除不完整文件", downloader.logs)
            self.assertIn("   🚫 文件下载重试3次仍失败: socket down", downloader.logs)

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

    def test_mark_download_url_unavailable_target_uses_target_error_detail(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = FakeDownloadFileDb()
        downloader.logs = []
        downloader.log = downloader.logs.append
        downloader.last_download_url_error = {"code": "ignored", "message": "ignored"}

        ZSXQFileDownloader._mark_download_url_unavailable_target(
            downloader,
            DownloadUrlUnavailableTarget(201, {"code": 1030, "message": "mobile only"}),
        )

        self.assertEqual(
            [(201, "failed", None, "1030", "mobile only")],
            downloader.file_db.status_updates,
        )
        self.assertEqual(["   ❌ 无法获取下载链接"], downloader.logs)

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

    def test_mark_download_failed_after_retries_target_uses_target_detail(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.file_db = FakeDownloadFileDb()
        downloader.logs = []
        downloader.log = downloader.logs.append

        ZSXQFileDownloader._mark_download_failed_after_retries_target(
            downloader,
            DownloadFinalFailureTarget(201, 4, "download_exception", "socket down"),
        )

        self.assertEqual(
            [(201, "failed", None, "download_exception", "socket down")],
            downloader.file_db.status_updates,
        )
        self.assertEqual(
            ["   🚫 文件下载重试4次仍失败: socket down"],
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

    def test_handle_download_size_mismatch_target_preserves_cleanup_and_noop_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.logs = []
            downloader.log = downloader.logs.append

            mismatch_path = Path(temp_dir) / "mismatch.pdf.part"
            mismatch_path.write_bytes(b"bad")
            mismatch_detail = ZSXQFileDownloader._handle_download_size_mismatch_target(
                downloader,
                DownloadSizeMismatchTarget(4, str(mismatch_path)),
            )

            matching_path = Path(temp_dir) / "matching.pdf.part"
            matching_path.write_bytes(b"memo")
            matching_detail = ZSXQFileDownloader._handle_download_size_mismatch_target(
                downloader,
                DownloadSizeMismatchTarget(4, str(matching_path)),
            )

            self.assertEqual(
                ("size_mismatch", "文件大小不匹配: 预期4, 实际3"),
                mismatch_detail,
            )
            self.assertFalse(mismatch_path.exists())
            self.assertIsNone(matching_detail)
            self.assertTrue(matching_path.exists())
            self.assertEqual(["   ⚠️ 文件大小不匹配: 预期4, 实际3"], downloader.logs)

    def test_handle_download_size_mismatch_target_preserves_raw_detail_handoff(self):
        downloader = object.__new__(ZSXQFileDownloader)
        target = DownloadSizeMismatchTarget(17, "C:\\Downloads\\memo.pdf.part")
        failure_detail = DownloadFailureDetail("size_mismatch", "bad size")
        calls = []

        def getsize(temp_path):
            calls.append(("getsize", temp_path))
            return 13

        def size_mismatch_detail(expected_size, final_size):
            calls.append(("detail", expected_size, final_size))
            return ("size_mismatch", "bad size")

        def download_size_mismatch_failure_detail(detail_target, raw_mismatch_detail):
            calls.append(("failure", detail_target, raw_mismatch_detail))
            return failure_detail

        downloader._download_size_mismatch_failure_detail = (
            download_size_mismatch_failure_detail
        )

        with (
            patch("backend.crawlers.zsxq_file_downloader.os.path.getsize", getsize),
            patch(
                "backend.crawlers.zsxq_file_downloader.download_size_mismatch_detail",
                size_mismatch_detail,
            ),
        ):
            result = ZSXQFileDownloader._handle_download_size_mismatch_target(
                downloader,
                target,
            )

        self.assertEqual(failure_detail, result)
        self.assertEqual(
            [
                ("getsize", "C:\\Downloads\\memo.pdf.part"),
                ("detail", 17, 13),
                ("failure", target, ("size_mismatch", "bad size")),
            ],
            calls,
        )

    def test_download_size_mismatch_failure_detail_preserves_log_cleanup_and_return(self):
        downloader = object.__new__(ZSXQFileDownloader)
        target = DownloadSizeMismatchTarget(17, "C:\\Downloads\\memo.pdf.part")
        raw_mismatch_detail = ("size_mismatch", "bad size")
        calls = []
        downloader.log = lambda message: calls.append(("log", message))

        def remove(temp_path):
            calls.append(("remove", temp_path))

        with patch("backend.crawlers.zsxq_file_downloader.os.remove", remove):
            result = ZSXQFileDownloader._download_size_mismatch_failure_detail(
                downloader,
                target,
                raw_mismatch_detail,
            )

        self.assertEqual(DownloadFailureDetail("size_mismatch", "bad size"), result)
        self.assertEqual(
            [
                ("log", "   ⚠️ bad size"),
                ("remove", "C:\\Downloads\\memo.pdf.part"),
            ],
            calls,
        )

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

    def test_handle_download_stop_target_preserves_status_log_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "memo.pdf.part"
            temp_path.write_bytes(b"memo")
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.file_db = FakeDownloadFileDb()
            downloader.logs = []
            downloader.log = downloader.logs.append

            ZSXQFileDownloader._handle_download_stop_target(
                downloader,
                DownloadStopTarget(101, str(temp_path)),
            )

            self.assertEqual(
                (101, "failed", None, "stopped", "下载过程中被停止"),
                downloader.file_db.status_updates[-1],
            )
            self.assertFalse(temp_path.exists())
            self.assertEqual(["🛑 下载过程中被停止"], downloader.logs)

    def test_record_download_stop_target_preserves_log_status_and_cleanup_order(self):
        downloader = object.__new__(ZSXQFileDownloader)
        calls = []
        downloader.log = lambda message: calls.append(("log", message))

        class RecordingFileDb:
            def update_file_download_status(self, file_id, status, **kwargs):
                calls.append(("status", file_id, status, kwargs))

        downloader.file_db = RecordingFileDb()

        def remove_partial(temp_path):
            calls.append(("remove", temp_path))
            return True

        with patch(
            "backend.crawlers.zsxq_file_downloader.remove_partial_download",
            remove_partial,
        ):
            ZSXQFileDownloader._record_download_stop_target(
                downloader,
                DownloadStopTarget(202, "C:\\Downloads\\memo.pdf.part"),
            )

        self.assertEqual(
            [
                ("log", "🛑 下载过程中被停止"),
                (
                    "status",
                    202,
                    "failed",
                    {
                        "error_code": "stopped",
                        "error_message": "下载过程中被停止",
                    },
                ),
                ("remove", "C:\\Downloads\\memo.pdf.part"),
            ],
            calls,
        )

    def test_download_interval_values_preserves_random_long_sleep_priority(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.current_batch_count = 10
        downloader.files_per_batch = 10
        downloader.download_interval = 1
        downloader.long_sleep_interval = 60
        downloader.use_random_interval = True
        downloader.download_interval_min = 8
        downloader.download_interval_max = 20
        downloader.long_sleep_interval_min = 300
        downloader.long_sleep_interval_max = 900

        with patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=480.0) as uniform:
            values = ZSXQFileDownloader._download_interval_values(downloader)

        uniform.assert_called_once_with(300, 900)
        self.assertEqual(DownloadIntervalValues(1, 480.0), values)

    def test_apply_download_interval_plan_target_preserves_sleep_reset_and_logs(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.current_batch_count = 7
        downloader.logs = []
        downloader.log = downloader.logs.append

        with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
            ZSXQFileDownloader._apply_download_interval_plan_target(
                downloader,
                DownloadIntervalPlanTarget(
                    10,
                    10,
                    DownloadIntervalValues(1, 60),
                ),
            )

        sleep.assert_called_once_with(60)
        self.assertEqual(0, downloader.current_batch_count)
        self.assertEqual(
            [
                "⏰ 已下载 10 个文件，开始长休眠 60 秒...",
                "😴 长休眠结束，继续下载",
            ],
            downloader.logs,
        )

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

    def test_apply_download_intervals_uses_random_interval_range(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.current_batch_count = 1
        downloader.files_per_batch = 10
        downloader.download_interval = 1
        downloader.long_sleep_interval = 60
        downloader.use_random_interval = True
        downloader.download_interval_min = 8
        downloader.download_interval_max = 20
        downloader.long_sleep_interval_min = 300
        downloader.long_sleep_interval_max = 900
        downloader.logs = []
        downloader.log = downloader.logs.append

        with patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=12.5) as uniform:
            with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
                ZSXQFileDownloader._apply_download_intervals(downloader)

        uniform.assert_called_once_with(8, 20)
        sleep.assert_called_once_with(12.5)
        self.assertEqual(["⏱️ 下载间隔休眠 12.5 秒..."], downloader.logs)

    def test_apply_download_intervals_uses_random_long_sleep_range_at_batch_boundary(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.current_batch_count = 10
        downloader.files_per_batch = 10
        downloader.download_interval = 1
        downloader.long_sleep_interval = 60
        downloader.use_random_interval = True
        downloader.download_interval_min = 8
        downloader.download_interval_max = 20
        downloader.long_sleep_interval_min = 300
        downloader.long_sleep_interval_max = 900
        downloader.logs = []
        downloader.log = downloader.logs.append

        with patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=480.0) as uniform:
            with patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep:
                ZSXQFileDownloader._apply_download_intervals(downloader)

        uniform.assert_called_once_with(300, 900)
        sleep.assert_called_once_with(480.0)
        self.assertEqual(0, downloader.current_batch_count)
        self.assertEqual(
            [
                "⏰ 已下载 10 个文件，开始长休眠 480.0 秒...",
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

    def test_get_download_url_writes_opt_in_risk_log_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([FakeJsonResponse()])
            risk_log = Path(temp_dir) / "risk.csv"
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.base_url = "https://api.example"
            downloader.session = session
            downloader.group_id = "group-1"
            downloader.cookie = "cookie"
            downloader.risk_event_log_path = str(risk_log)
            downloader.request_count = 0
            downloader.smart_delay = lambda: None
            downloader.get_stealth_headers = lambda: {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
                "Referer": "https://wx.zsxq.com/dweb2/index/group/group-1",
            }
            downloader.logs = []
            downloader.log = downloader.logs.append

            result = ZSXQFileDownloader.get_download_url(downloader, 101)

            with risk_log.open("r", encoding="utf-8-sig", newline="") as file_obj:
                rows = list(csv.DictReader(file_obj))

        self.assertEqual("https://files.example/signed-token", result)
        self.assertEqual(["download_url_request", "download_url_response"], [row["phase"] for row in rows])
        self.assertEqual(["observed", "api_success"], [row["status"] for row in rows])
        self.assertEqual(["", "200"], [row["http_status"] for row in rows])
        self.assertIn("   🧭 UA分类: Chrome Windows", downloader.logs)

    def test_get_download_url_retries_api_failure_then_success_preserves_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeFailedJsonResponse(1059, "slow down"),
                FakeJsonResponse(),
            ])
            risk_log = Path(temp_dir) / "risk.csv"
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.base_url = "https://api.example"
            downloader.session = session
            downloader.group_id = "group-1"
            downloader.cookie = "cookie"
            downloader.risk_event_log_path = str(risk_log)
            downloader.request_count = 0
            downloader.smart_delay = lambda: None
            downloader.get_stealth_headers = lambda: {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
                "Referer": "https://wx.zsxq.com/dweb2/index/group/group-1",
            }
            downloader.logs = []
            downloader.log = downloader.logs.append

            output = io.StringIO()
            with (
                contextlib.redirect_stdout(output),
                patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
                patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            ):
                result = ZSXQFileDownloader.get_download_url(downloader, 101)

            with risk_log.open("r", encoding="utf-8-sig", newline="") as file_obj:
                rows = list(csv.DictReader(file_obj))

        self.assertEqual("https://files.example/signed-token", result)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(2, downloader.request_count)
        self.assertEqual(2, len(session.get_calls))
        sleep.assert_called_once_with(15.0)
        self.assertIn("   ✅ 重试成功！第1次重试获取到下载链接", output.getvalue())
        self.assertEqual(
            [
                "download_url_request",
                "download_url_response",
                "download_url_request",
                "download_url_retry_response",
            ],
            [row["phase"] for row in rows],
        )
        self.assertEqual(["observed", "api_failed", "observed", "api_success"], [row["status"] for row in rows])
        self.assertEqual(["0", "0", "1", "1"], [row["attempt"] for row in rows])
        self.assertEqual(["", "200", "", "200"], [row["http_status"] for row in rows])
        self.assertEqual(["", "1059", "", ""], [row["api_code"] for row in rows])
        self.assertEqual(
            [
                "   🔗 获取下载链接: ID=101",
                "   🌐 请求URL: https://api.example/v2/files/101/download_url",
                "   🧭 UA分类: Chrome Windows",
                "   ❌ API返回失败: slow down (代码: 1059)",
                "   🔄 检测到可重试错误，准备重试...",
                "   🧭 UA分类: Chrome Windows",
            ],
            downloader.logs,
        )

    def test_get_download_url_retries_http_failure_then_success_preserves_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeHttpDownloadUrlResponse(500, "temporary outage"),
                FakeJsonResponse(),
            ])
            risk_log = Path(temp_dir) / "risk.csv"
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.base_url = "https://api.example"
            downloader.session = session
            downloader.group_id = "group-1"
            downloader.cookie = "cookie"
            downloader.risk_event_log_path = str(risk_log)
            downloader.request_count = 0
            downloader.smart_delay = lambda: None
            downloader.get_stealth_headers = lambda: {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
                "Referer": "https://wx.zsxq.com/dweb2/index/group/group-1",
            }
            downloader.logs = []
            downloader.log = downloader.logs.append

            output = io.StringIO()
            with (
                contextlib.redirect_stdout(output),
                patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
                patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            ):
                result = ZSXQFileDownloader.get_download_url(downloader, 101)

            with risk_log.open("r", encoding="utf-8-sig", newline="") as file_obj:
                rows = list(csv.DictReader(file_obj))

        printed = output.getvalue()
        self.assertEqual("https://files.example/signed-token", result)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(2, downloader.request_count)
        self.assertEqual(2, len(session.get_calls))
        sleep.assert_called_once_with(15.0)
        self.assertIn("   ❌ HTTP错误: 500", printed)
        self.assertIn("   📄 响应内容: temporary outage", printed)
        self.assertIn("   🔄 服务器错误，准备重试...", printed)
        self.assertIn("   ✅ 重试成功！第1次重试获取到下载链接", printed)
        self.assertEqual(
            [
                "download_url_request",
                "download_url_request",
                "download_url_retry_response",
            ],
            [row["phase"] for row in rows],
        )
        self.assertEqual(["observed", "observed", "api_success"], [row["status"] for row in rows])
        self.assertEqual(["0", "1", "1"], [row["attempt"] for row in rows])
        self.assertEqual(["", "", "200"], [row["http_status"] for row in rows])
        self.assertEqual(
            [
                "   🔗 获取下载链接: ID=101",
                "   🌐 请求URL: https://api.example/v2/files/101/download_url",
                "   🧭 UA分类: Chrome Windows",
                "   🧭 UA分类: Chrome Windows",
            ],
            downloader.logs,
        )

    def test_get_download_url_stops_on_non_retry_http_failure(self):
        session = FakeDownloadSession([FakeHttpDownloadUrlResponse(403, "forbidden")])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.session = session
        downloader.group_id = "group-1"
        downloader.cookie = "cookie"
        downloader.risk_event_log_path = None
        downloader.last_download_url_error = {"code": 1030, "message": "previous"}
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {"User-Agent": "unit-test-agent"}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = ZSXQFileDownloader.get_download_url(downloader, 202)

        printed = output.getvalue()
        self.assertIsNone(result)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(1, downloader.request_count)
        self.assertEqual(
            [("https://api.example/v2/files/202/download_url", 30, False)],
            session.get_calls,
        )
        self.assertIn("   📊 响应状态: 403", printed)
        self.assertIn("   ❌ HTTP错误: 403", printed)
        self.assertIn("   📄 响应内容: forbidden", printed)
        self.assertIn("   🚫 非可重试HTTP错误，停止重试", printed)
        self.assertNotIn("全部失败", printed)
        self.assertEqual(
            [
                "   🔗 获取下载链接: ID=202",
                "   🌐 请求URL: https://api.example/v2/files/202/download_url",
            ],
            downloader.logs,
        )

    def test_get_download_url_retries_request_exception_then_success_preserves_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                RuntimeError("socket reset"),
                FakeJsonResponse(),
            ])
            risk_log = Path(temp_dir) / "risk.csv"
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.base_url = "https://api.example"
            downloader.session = session
            downloader.group_id = "group-1"
            downloader.cookie = "cookie"
            downloader.risk_event_log_path = str(risk_log)
            downloader.request_count = 0
            downloader.smart_delay = lambda: None
            downloader.get_stealth_headers = lambda: {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
                "Referer": "https://wx.zsxq.com/dweb2/index/group/group-1",
            }
            downloader.logs = []
            downloader.log = downloader.logs.append

            output = io.StringIO()
            with (
                contextlib.redirect_stdout(output),
                patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
                patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            ):
                result = ZSXQFileDownloader.get_download_url(downloader, 101)

            with risk_log.open("r", encoding="utf-8-sig", newline="") as file_obj:
                rows = list(csv.DictReader(file_obj))

        printed = output.getvalue()
        self.assertEqual("https://files.example/signed-token", result)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(2, downloader.request_count)
        self.assertEqual(2, len(session.get_calls))
        sleep.assert_called_once_with(15.0)
        self.assertIn("   ❌ 请求异常: socket reset", printed)
        self.assertIn("   🔄 请求异常，准备重试...", printed)
        self.assertIn("   ✅ 重试成功！第1次重试获取到下载链接", printed)
        self.assertEqual(
            [
                "download_url_request",
                "download_url_request",
                "download_url_retry_response",
            ],
            [row["phase"] for row in rows],
        )
        self.assertEqual(["observed", "observed", "api_success"], [row["status"] for row in rows])
        self.assertEqual(["0", "1", "1"], [row["attempt"] for row in rows])
        self.assertEqual(["", "", "200"], [row["http_status"] for row in rows])
        self.assertEqual(
            [
                "   🔗 获取下载链接: ID=101",
                "   🌐 请求URL: https://api.example/v2/files/101/download_url",
                "   🧭 UA分类: Chrome Windows",
                "   🧭 UA分类: Chrome Windows",
            ],
            downloader.logs,
        )

    def test_get_download_url_request_exception_exhausts_retries(self):
        session = FakeDownloadSession([RuntimeError("socket reset") for _ in range(10)])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.session = session
        downloader.group_id = "group-1"
        downloader.cookie = "cookie"
        downloader.risk_event_log_path = None
        downloader.last_download_url_error = {"code": 1030, "message": "previous"}
        downloader.request_count = 0
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.get_download_url(downloader, 303)

        printed = output.getvalue()
        self.assertIsNone(result)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(10, downloader.request_count)
        self.assertEqual(
            [("https://api.example/v2/files/303/download_url", 30, False)] * 10,
            session.get_calls,
        )
        self.assertEqual(9, sleep.call_count)
        self.assertEqual(10, printed.count("   ❌ 请求异常: socket reset"))
        self.assertNotIn("请求异常，停止重试", printed)
        self.assertIn("🚫 已重试10次，全部失败", printed)
        self.assertNotIn("重试成功", printed)
        self.assertEqual(
            [
                "   🔗 获取下载链接: ID=303",
                "   🌐 请求URL: https://api.example/v2/files/303/download_url",
            ],
            downloader.logs,
        )

    def test_get_download_url_retries_json_decode_failure_then_success_preserves_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeDownloadSession([
                FakeInvalidJsonResponse(),
                FakeJsonResponse(),
            ])
            risk_log = Path(temp_dir) / "risk.csv"
            downloader = object.__new__(ZSXQFileDownloader)
            downloader.base_url = "https://api.example"
            downloader.session = session
            downloader.group_id = "group-1"
            downloader.cookie = "cookie"
            downloader.risk_event_log_path = str(risk_log)
            downloader.request_count = 0
            downloader.smart_delay = lambda: None
            downloader.get_stealth_headers = lambda: {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
                "Referer": "https://wx.zsxq.com/dweb2/index/group/group-1",
            }
            downloader.logs = []
            downloader.log = downloader.logs.append

            output = io.StringIO()
            with (
                contextlib.redirect_stdout(output),
                patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
                patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
            ):
                result = ZSXQFileDownloader.get_download_url(downloader, 101)

            with risk_log.open("r", encoding="utf-8-sig", newline="") as file_obj:
                rows = list(csv.DictReader(file_obj))

        printed = output.getvalue()
        self.assertEqual("https://files.example/signed-token", result)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(2, downloader.request_count)
        self.assertEqual(2, len(session.get_calls))
        sleep.assert_called_once_with(15.0)
        self.assertIn("   ❌ JSON解析失败: bad json", printed)
        self.assertIn("   📄 原始响应: {not json", printed)
        self.assertIn("   🔄 JSON解析失败，准备重试...", printed)
        self.assertIn("   ✅ 重试成功！第1次重试获取到下载链接", printed)
        self.assertEqual(
            [
                "download_url_request",
                "download_url_request",
                "download_url_retry_response",
            ],
            [row["phase"] for row in rows],
        )
        self.assertEqual(["observed", "observed", "api_success"], [row["status"] for row in rows])
        self.assertEqual(["0", "1", "1"], [row["attempt"] for row in rows])
        self.assertEqual(["", "", "200"], [row["http_status"] for row in rows])
        self.assertEqual(
            [
                "   🔗 获取下载链接: ID=101",
                "   🌐 请求URL: https://api.example/v2/files/101/download_url",
                "   🧭 UA分类: Chrome Windows",
                "   🧭 UA分类: Chrome Windows",
            ],
            downloader.logs,
        )

    def test_get_download_url_initial_request_preserves_url_timeout_retry_limit_and_error_reset(self):
        session = FakeDownloadSession([FakeMissingDownloadUrlJsonResponse() for _ in range(10)])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.session = session
        downloader.group_id = "group-1"
        downloader.cookie = "cookie"
        downloader.request_count = 0
        downloader.last_download_url_error = {"code": 1030, "message": "previous"}
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep"),
        ):
            result = ZSXQFileDownloader.get_download_url(downloader, 202)

        self.assertIsNone(result)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(10, downloader.request_count)
        self.assertEqual(
            [("https://api.example/v2/files/202/download_url", 30, False)] * 10,
            session.get_calls,
        )
        self.assertIn("🚫 已重试10次，全部失败", output.getvalue())
        self.assertEqual(
            [
                "   🔗 获取下载链接: ID=202",
                "   🌐 请求URL: https://api.example/v2/files/202/download_url",
            ],
            downloader.logs,
        )

    def test_get_download_url_missing_url_field_exhausts_retries(self):
        session = FakeDownloadSession([FakeMissingDownloadUrlJsonResponse() for _ in range(10)])
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
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.get_download_url(downloader, 101)

        printed = output.getvalue()
        self.assertIsNone(result)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(10, downloader.request_count)
        self.assertEqual(10, len(session.get_calls))
        self.assertEqual(9, sleep.call_count)
        self.assertEqual(10, printed.count("❌ 响应中无下载链接字段"))
        self.assertIn("🚫 已重试10次，全部失败", printed)

    def test_get_download_url_empty_json_response_exhausts_retries(self):
        class FakeEmptyJsonResponse:
            status_code = 200
            text = "{}"

            def json(self):
                return {}

        session = FakeDownloadSession([FakeEmptyJsonResponse() for _ in range(10)])
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.base_url = "https://api.example"
        downloader.session = session
        downloader.group_id = "group-1"
        downloader.cookie = "cookie"
        downloader.request_count = 0
        downloader.last_download_url_error = {"code": 1030, "message": "previous"}
        downloader.smart_delay = lambda: None
        downloader.get_stealth_headers = lambda: {}
        downloader.logs = []
        downloader.log = downloader.logs.append

        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch("backend.crawlers.zsxq_file_downloader.random.uniform", return_value=15.0),
            patch("backend.crawlers.zsxq_file_downloader.time.sleep") as sleep,
        ):
            result = ZSXQFileDownloader.get_download_url(downloader, 101)

        printed = output.getvalue()
        self.assertIsNone(result)
        self.assertIsNone(downloader.last_download_url_error)
        self.assertEqual(10, downloader.request_count)
        self.assertEqual(10, len(session.get_calls))
        self.assertEqual(9, sleep.call_count)
        self.assertIn("🚫 已重试10次，全部失败", printed)
        self.assertNotIn("❌ 响应中无下载链接字段", printed)

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
