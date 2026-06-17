#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识星球文件下载器
Author: AI Assistant
Date: 2024-12-19
Description: 专门用于下载知识星球文件的工具
"""

import datetime
import json
import os
import random
import time
from typing import Dict, NamedTuple, Optional, Any, Tuple

import requests

from backend.core.console_output import safe_console_print as print
from backend.core.log_redaction import redact_json_like
from backend.crawlers.zsxq_file_downloader_helpers import (
    API_FAILURE_NON_RETRY,
    API_FAILURE_PERMISSION_DENIED_1030,
    API_FAILURE_RETRY,
    HTTP_FAILURE_NON_RETRY,
    HTTP_FAILURE_RETRY,
    add_file_collection_page_stats,
    api_retry_user_agent_message,
    api_retry_wait_message,
    add_import_stats,
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
    clean_cookie_result,
    database_download_completion_messages,
    database_download_effective_last_days,
    database_download_filter_messages,
    database_download_file_info,
    database_download_query_plan,
    database_download_start_messages,
    database_download_time_range_message,
    database_stats_api_response_query,
    database_stats_table_emoji,
    database_stats_time_range_query,
    database_stats_total_size_query,
    database_time_range_query,
    database_time_range_result,
    date_range_collection_start_messages,
    download_settings_display_lines,
    download_file_data,
    download_exception_detail,
    download_expected_size,
    download_final_failure_detail,
    download_http_failure_detail,
    download_interval_plan,
    download_progress_message,
    download_query_group_id,
    download_result_stats,
    download_retry_wait,
    download_size_mismatch_detail,
    download_target_path,
    download_total_size,
    download_url_api_failure_plan,
    download_url_failure_detail,
    download_url_from_response_data,
    download_url_success_plan,
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
    http_failure_plan,
    incremental_collection_empty_database_message,
    incremental_collection_missing_time_message,
    incremental_collection_start_index_message,
    incremental_collection_start_message,
    incremental_collection_status_messages,
    incremental_collection_target_message,
    incremental_collection_timestamp_failure_messages,
    incremental_start_index,
    json_decode_failure_plan,
    latest_file_create_time_query,
    normalize_date_range,
    page_crosses_stop_before,
    partial_download_path,
    remove_partial_download,
    response_filename_override,
    request_exception_plan,
    retry_exhausted_message,
    risk_event_header_user_agent,
    risk_event_header_profile_label,
    risk_event_row,
    risk_event_user_agent_label,
    sec_ch_ua_for_user_agent,
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
    time_collection_fetch_failed_messages,
    time_collection_exception_message,
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
from backend.storage.postgres_core_schema import CORE_SCHEMA
from backend.storage.zsxq_file_database import ZSXQFileDatabase


DOWNLOAD_URL_MAX_RETRIES = 10
DOWNLOAD_URL_REQUEST_TIMEOUT_SECONDS = 30
DOWNLOAD_FILE_MAX_RETRIES = 3
DOWNLOAD_FILE_RESPONSE_TIMEOUT_SECONDS = 300


class ApiJsonParseResult(NamedTuple):
    data: Optional[Dict[str, Any]]
    should_retry: bool


class ParseApiJsonResponseTarget(NamedTuple):
    response: requests.Response
    attempt: int
    max_retries: int


class FileListResponseDecision(NamedTuple):
    result: Optional[Dict[str, Any]]
    should_retry: bool
    should_stop: bool


class FileListResponseTarget(NamedTuple):
    response: requests.Response
    attempt: int
    max_retries: int


class FileListOkResponseTarget(NamedTuple):
    response: requests.Response
    attempt: int
    max_retries: int


class FileListSuccessResponseTarget(NamedTuple):
    data: Dict[str, Any]
    attempt: int


class FileListApiFailureResponseTarget(NamedTuple):
    data: Dict[str, Any]
    attempt: int
    max_retries: int


class FileListHttpFailureResponseTarget(NamedTuple):
    response: requests.Response
    attempt: int
    max_retries: int


class HttpFailureOutputTarget(NamedTuple):
    http_status: int
    response_text: str
    attempt: int
    max_retries: int


class FileListRequestExceptionTarget(NamedTuple):
    exc: Exception
    attempt: int
    max_retries: int


class RequestExceptionOutputTarget(NamedTuple):
    exc: Exception
    attempt: int
    max_retries: int


class JsonDecodeFailureOutputTarget(NamedTuple):
    exc: json.JSONDecodeError
    response_text: str
    attempt: int
    max_retries: int


class FetchFileListTarget(NamedTuple):
    count: int
    index: Optional[str]
    sort: str


class StealthHeaderSelection(NamedTuple):
    user_agent: str
    sec_ch_ua: str
    accept_language: str
    platform: str


class DownloadUrlResponseDecision(NamedTuple):
    download_url: Optional[str]
    should_retry: bool
    should_stop: bool


class DownloadUrlEntryTarget(NamedTuple):
    file_id: int


class DownloadUrlRequestTarget(NamedTuple):
    url: str
    headers: Dict[str, str]


class DownloadUrlResponseTarget(NamedTuple):
    response: Any
    file_id: int
    attempt: int
    max_retries: int
    headers: Dict[str, str]


class DownloadUrlOkResponseTarget(NamedTuple):
    response: Any
    file_id: int
    attempt: int
    max_retries: int
    headers: Dict[str, str]


class DownloadUrlDataDecisionTarget(NamedTuple):
    data: Dict[str, Any]
    file_id: int
    attempt: int
    max_retries: int
    headers: Dict[str, str]
    http_status: int


class DownloadUrlSuccessResponseTarget(NamedTuple):
    data: Dict[str, Any]
    file_id: int
    attempt: int
    headers: Dict[str, str]
    http_status: int


class DownloadUrlSuccessEventTarget(NamedTuple):
    file_id: int
    phase: str
    attempt: int
    headers: Dict[str, str]
    http_status: int


class DownloadUrlApiFailureResponseTarget(NamedTuple):
    data: Dict[str, Any]
    file_id: int
    attempt: int
    max_retries: int
    headers: Dict[str, str]
    http_status: int


class DownloadUrlApiFailureEventTarget(NamedTuple):
    file_id: int
    attempt: int
    headers: Dict[str, str]
    http_status: int
    error_code: Any
    error_msg: Any


class DownloadUrlHttpFailureResponseTarget(NamedTuple):
    http_status: int
    response_text: str
    attempt: int
    max_retries: int


class DownloadUrlRequestExceptionTarget(NamedTuple):
    exc: Exception
    attempt: int
    max_retries: int


class DownloadUrlAttemptTarget(NamedTuple):
    url: str
    file_id: int
    attempt: int
    max_retries: int


class DownloadUrlRetryLoopTarget(NamedTuple):
    url: str
    file_id: int
    max_retries: int


class DownloadUrlRetryLoopStepDecision(NamedTuple):
    result: Optional[str]
    should_continue: bool


class DownloadRetryWaitTarget(NamedTuple):
    attempt: int
    download_retries: int


class DownloadFileResponseRequestTarget(NamedTuple):
    download_url: str


class DownloadFileEntryTarget(NamedTuple):
    file_info: Dict[str, Any]


class DownloadFileTarget(NamedTuple):
    file_id: int
    file_name: str
    file_size: int
    safe_filename: str
    file_path: str


class DownloadFilePreparationData(NamedTuple):
    file_id: Any
    file_name: Any
    file_size: Any
    download_count: Any


class ExistingDownloadTarget(NamedTuple):
    file_id: int
    file_path: str
    file_size: int


class ExistingDownloadMatch(NamedTuple):
    file_exists: bool
    size_matches: bool
    existing_size: int


class DownloadFilenameOverride(NamedTuple):
    file_name: str
    safe_filename: str
    file_path: str


class ResponseFilenameOverrideTarget(NamedTuple):
    file_name: str
    file_id: int
    response_headers: Dict[str, Any]


class DownloadFailureDetail(NamedTuple):
    error_code: str
    error_message: str


class DownloadHttpFailureTarget(NamedTuple):
    status_code: int


class DownloadUrlUnavailableTarget(NamedTuple):
    file_id: int
    last_download_url_error: Optional[Dict[str, Any]]


class DownloadExceptionTarget(NamedTuple):
    exc: Exception
    file_path: str


class DownloadFinalFailureTarget(NamedTuple):
    file_id: int
    download_retries: int
    last_error_code: Optional[str]
    last_error: Optional[str]


class DownloadBodyPreparationTarget(NamedTuple):
    response_headers: Dict[str, Any]
    file_size: int
    file_path: str


class DownloadBodyTarget(NamedTuple):
    total_size: int
    expected_size: int
    temp_path: str


class DownloadBodyWriteTarget(NamedTuple):
    temp_path: str
    total_size: int
    file_id: int


class DownloadBodyResponseTarget(NamedTuple):
    response: Any
    body_target: DownloadBodyWriteTarget


class DownloadStopTarget(NamedTuple):
    file_id: int
    temp_path: str


class DownloadCompletionTarget(NamedTuple):
    file_id: int
    safe_filename: str
    file_path: str
    temp_path: str


class DownloadBodyFinalizationTarget(NamedTuple):
    expected_size: int
    temp_path: str
    file_id: int
    safe_filename: str
    file_path: str


class DownloadBodyFinalizationDecisionTarget(NamedTuple):
    downloaded_size: Optional[int]
    finalization_target: DownloadBodyFinalizationTarget


class DownloadSizeMismatchTarget(NamedTuple):
    expected_size: int
    temp_path: str


class DownloadBodyResult(NamedTuple):
    success_result: Optional[bool]
    failure_detail: Optional[DownloadFailureDetail]


class DownloadAttemptResult(NamedTuple):
    success_result: Optional[bool]
    failure_detail: Optional[DownloadFailureDetail]
    file_name: str
    safe_filename: str
    file_path: str


class DownloadRetryState(NamedTuple):
    file_name: str
    safe_filename: str
    file_path: str
    last_error_code: Optional[str]
    last_error: Optional[str]


class DownloadAttemptResultTarget(NamedTuple):
    attempt_result: DownloadAttemptResult
    retry_state: DownloadRetryState


class DownloadRetryExceptionTarget(NamedTuple):
    exc: Exception
    retry_state: DownloadRetryState


class DownloadAttemptTarget(NamedTuple):
    attempt: int
    download_retries: int
    file_target: DownloadFileTarget


class DownloadAttemptResponseTarget(NamedTuple):
    download_url: str
    file_target: DownloadFileTarget


class DownloadResponseTarget(NamedTuple):
    response: Any
    file_target: DownloadFileTarget


class DownloadRetryLoopAttemptTarget(NamedTuple):
    attempt: int
    download_retries: int
    prepared_file: DownloadFileTarget
    retry_state: DownloadRetryState


class DownloadRetryDecision(NamedTuple):
    state: DownloadRetryState
    result: Optional[bool]


class DownloadRetryLoopFailureTarget(NamedTuple):
    prepared_file: DownloadFileTarget
    download_retries: int
    retry_state: DownloadRetryState


class DownloadIntervalValues(NamedTuple):
    download_interval: float
    long_sleep_interval: float


class DownloadIntervalPlanTarget(NamedTuple):
    current_batch_count: int
    files_per_batch: int
    interval_values: DownloadIntervalValues


class FileCollectionTarget(NamedTuple):
    pass


class DatabaseTimeRangeTarget(NamedTuple):
    pass


class FileCollectionPage(NamedTuple):
    data: Dict[str, Any]
    files: list[Dict[str, Any]]
    next_index: Optional[Any]


class TimeCollectionPage(NamedTuple):
    data: Dict[str, Any]
    files: list[Dict[str, Any]]
    next_index: Optional[Any]


class ShowFileListTarget(NamedTuple):
    count: int
    index: Optional[str]


class TimeCollectionPageImportResult(NamedTuple):
    should_stop_after_insert: bool


class TimeCollectionLoopContext(NamedTuple):
    sort: str
    enable_time_dedupe: bool
    db_latest_time: Optional[Any]
    total_imported_stats: Dict[str, int]
    stop_before_time: Optional[datetime.datetime]


class TimeCollectionTarget(NamedTuple):
    sort: str
    start_time: Optional[str]
    stop_before_time: Optional[datetime.datetime]
    force_refresh: bool


class IncrementalCollectionTarget(NamedTuple):
    pass


class DateRangeCollectionTarget(NamedTuple):
    start_date: Optional[str]
    end_date: Optional[str]
    last_days: Optional[int]


class BatchDownloadPage(NamedTuple):
    files: list[Dict[str, Any]]
    next_index: Optional[Any]


class BatchDownloadLoopStep(NamedTuple):
    downloaded_in_batch: int
    next_index: Optional[str]


class BatchDownloadFetchTarget(NamedTuple):
    current_index: Optional[str]


class BatchDownloadPageRunTarget(NamedTuple):
    step: BatchDownloadLoopStep
    max_files: Optional[int]
    stats: Dict[str, int]


class BatchDownloadLoopTarget(NamedTuple):
    stats: Dict[str, int]
    max_files: Optional[int]
    start_index: Optional[str]


class BatchDownloadTarget(NamedTuple):
    max_files: Optional[int]
    start_index: Optional[str]


class BatchDownloadNextIndexTarget(NamedTuple):
    next_index: Optional[str]
    downloaded_in_batch: int
    max_files: Optional[int]


class BatchDownloadPageFilesTarget(NamedTuple):
    files: list[Dict[str, Any]]
    downloaded_in_batch: int
    max_files: Optional[int]
    stats: Dict[str, int]


class BatchDownloadFileItemTarget(NamedTuple):
    file_info: Dict[str, Any]
    item_number: int
    max_files: Optional[int]
    has_more_in_batch: bool
    downloaded_in_batch: int
    stats: Dict[str, int]


class BatchDownloadResultTarget(NamedTuple):
    result: Any
    has_more_in_batch: bool
    downloaded_in_batch: int
    max_files: Optional[int]
    stats: Dict[str, int]


class TimeCollectionDatabaseState(NamedTuple):
    initial_files: Any
    db_latest_time: Optional[Any]


class DatabaseDownloadRow(NamedTuple):
    file_id: Any
    file_name: Any
    file_size: Any
    download_count: Any
    create_time: Any


class DatabaseDownloadRowsTarget(NamedTuple):
    files_to_download: list[DatabaseDownloadRow]


class DatabaseDownloadAfterInitialStopTarget(NamedTuple):
    query_plan: Dict[str, Any]
    sort_by: str


class DatabaseDownloadTarget(NamedTuple):
    max_files: Optional[int]
    status_filter: str
    sort_by: str
    start_date: Optional[str]
    end_date: Optional[str]
    last_days: Optional[int]
    kwargs: Dict[str, Any]


class DatabaseStatsTotalSize(NamedTuple):
    total_size: Any


class DatabaseStatsTimeRange(NamedTuple):
    min_time: Any
    max_time: Any
    time_count: Any


class ShowDatabaseStatsEntryTarget(NamedTuple):
    pass


class ShowDatabaseStatsTarget(NamedTuple):
    stats: Dict[str, Any]


class AdjustSettingsTarget(NamedTuple):
    pass


class CloseTarget(NamedTuple):
    pass


class SetStopFlagTarget(NamedTuple):
    pass


class IsStoppedTarget(NamedTuple):
    pass


class CheckStopTarget(NamedTuple):
    pass


class CleanCookieTarget(NamedTuple):
    cookie: Any


class SmartDelayTarget(NamedTuple):
    pass


class CheckLongDelayTarget(NamedTuple):
    pass


class DownloadDelayTarget(NamedTuple):
    pass


class PrepareRetryApiRequestTarget(NamedTuple):
    attempt: int
    file_id: Optional[int]


class FileCollectionLogRow(NamedTuple):
    log_id: Any


class LatestFileCreateTimeRow(NamedTuple):
    create_time: Any


def _query_group_id(group_id: str) -> Any:
    return download_query_group_id(group_id)


def _file_collection_log_row(row: Any) -> Optional[FileCollectionLogRow]:
    if not row:
        return None
    return FileCollectionLogRow(row[0])


def _file_collection_log_id(row: Any) -> Optional[Any]:
    collection_log = _file_collection_log_row(row)
    if not collection_log:
        return None
    return collection_log.log_id


def _latest_file_create_time_row(row: Any) -> Optional[LatestFileCreateTimeRow]:
    if not row or not row[0]:
        return None
    return LatestFileCreateTimeRow(row[0])


def _latest_file_create_time(row: Any) -> Optional[Any]:
    latest_file = _latest_file_create_time_row(row)
    if not latest_file:
        return None
    return latest_file.create_time


def _http_failure_class_with_output(target: HttpFailureOutputTarget) -> str:
    http_failure = http_failure_plan(
        target.http_status,
        target.response_text,
        target.attempt,
        target.max_retries,
    )
    for message in http_failure["messages"]:
        print(message)
    return http_failure["failure_class"]


def _request_exception_should_retry_with_output(
    target: RequestExceptionOutputTarget,
) -> bool:
    request_exception = request_exception_plan(
        target.exc,
        target.attempt,
        target.max_retries,
    )
    for message in request_exception["messages"]:
        print(message)
    return request_exception["should_retry"]


def _json_decode_failure_result_with_output(
    target: JsonDecodeFailureOutputTarget,
) -> ApiJsonParseResult:
    decode_failure = json_decode_failure_plan(
        target.exc,
        target.response_text,
        target.attempt,
        target.max_retries,
    )
    for message in decode_failure["messages"]:
        print(message)
    return ApiJsonParseResult(None, decode_failure["should_retry"])


def _database_stats_total_size_row(result: Any) -> Optional[DatabaseStatsTotalSize]:
    if not result or not result[0]:
        return None
    return DatabaseStatsTotalSize(result[0])


def _database_stats_total_size(result: Any) -> Any:
    total_size = _database_stats_total_size_row(result)
    if not total_size:
        return 0
    return total_size.total_size


def _database_stats_time_range_row(result: Any) -> Optional[DatabaseStatsTimeRange]:
    if not result or result[2] <= 0:
        return None

    min_time, max_time, time_count = result
    return DatabaseStatsTimeRange(min_time, max_time, time_count)


def _database_stats_time_range(result: Any) -> Optional[DatabaseStatsTimeRange]:
    return _database_stats_time_range_row(result)


def _database_download_row(row: Any) -> DatabaseDownloadRow:
    return DatabaseDownloadRow(*row)


def _record_file_download_result(result: Any, stats: Dict[str, int]) -> str:
    if result == "skipped":
        stats['skipped'] += 1
        return "skipped"
    if result:
        stats['downloaded'] += 1
        return "downloaded"
    stats['failed'] += 1
    return "failed"


def _batch_download_file_name(file_info: Dict[str, Any]) -> Any:
    file_data = file_info.get('file', {})
    return file_data.get('name', 'Unknown')


class ZSXQFileDownloader:
    """知识星球文件下载器"""
    
    def __init__(self, cookie: str, group_id: str, download_dir: str = "downloads",
                 download_interval: float = 1.0, long_sleep_interval: float = 60.0,
                 files_per_batch: int = 10, download_interval_min: float = None,
                 download_interval_max: float = None, long_sleep_interval_min: float = None,
                 long_sleep_interval_max: float = None):
        """
        初始化文件下载器

        Args:
            cookie: 登录凭证
            group_id: 星球ID
            download_dir: 下载目录
            download_interval: 单次下载间隔（秒），默认1秒
            long_sleep_interval: 长休眠间隔（秒），默认60秒
            files_per_batch: 下载多少文件后触发长休眠，默认10个文件
            download_interval_min: 随机下载间隔最小值（秒）
            download_interval_max: 随机下载间隔最大值（秒）
            long_sleep_interval_min: 随机长休眠间隔最小值（秒）
            long_sleep_interval_max: 随机长休眠间隔最大值（秒）
        """
        self.cookie = self.clean_cookie(cookie)
        self.group_id = group_id

        self._configure_download_intervals(
            download_interval,
            long_sleep_interval,
            files_per_batch,
            download_interval_min,
            download_interval_max,
            long_sleep_interval_min,
            long_sleep_interval_max,
        )
        self.download_dir = self._resolve_download_dir(group_id, download_dir)

        print(f"📁 群组 {group_id} 下载目录: {self.download_dir}")

        self._initialize_runtime_state()
        self._initialize_download_storage(group_id)

    def _configure_download_intervals(
        self,
        download_interval: float,
        long_sleep_interval: float,
        files_per_batch: int,
        download_interval_min: Optional[float],
        download_interval_max: Optional[float],
        long_sleep_interval_min: Optional[float],
        long_sleep_interval_max: Optional[float],
    ) -> None:
        self.download_interval = download_interval
        self.long_sleep_interval = long_sleep_interval
        self.files_per_batch = files_per_batch
        self.current_batch_count = 0  # 当前批次已下载文件数

        self.use_random_interval = download_interval_min is not None
        if self.use_random_interval:
            self.download_interval_min = download_interval_min
            self.download_interval_max = download_interval_max
            self.long_sleep_interval_min = long_sleep_interval_min
            self.long_sleep_interval_max = long_sleep_interval_max
        else:
            # 使用固定间隔时的默认范围值（保持向后兼容）
            self.download_interval_min = 60  # 下载间隔最小值（1分钟）
            self.download_interval_max = 180  # 下载间隔最大值（3分钟）
            self.long_sleep_interval_min = 180  # 长休眠最小值（3分钟）
            self.long_sleep_interval_max = 300  # 长休眠最大值（5分钟）

    def _resolve_download_dir(self, group_id: str, download_dir: str) -> str:
        if download_dir == "downloads":  # 默认目录
            from backend.core.db_path_manager import get_db_path_manager
            path_manager = get_db_path_manager()
            group_dir = path_manager.get_group_dir(group_id)
            return os.path.join(group_dir, "downloads")
        return os.path.join(download_dir, f"group_{group_id}")

    def _initialize_runtime_state(self) -> None:
        self.base_url = "https://api.zsxq.com"

        self.log_callback = None
        self.stop_check_func = None
        self.risk_event_log_path = None
        self.stop_flag = False  # 本地停止标志
        self.last_download_url_error = None

        self.min_delay = 2.0  # 最小延迟（秒）
        self.max_delay = 5.0  # 最大延迟（秒）
        self.long_delay_interval = 5  # 每N个文件进行长休眠

        self.request_count = 0
        self.download_count = 0
        self.debug_mode = False

    def _initialize_download_storage(self, group_id: str) -> None:
        self.session = requests.Session()

        os.makedirs(self.download_dir, exist_ok=True)
        self.log(f"📁 下载目录: {os.path.abspath(self.download_dir)}")

        self.file_db = ZSXQFileDatabase(group_id)
        self.log(f"📊 完整文件存储初始化完成: PostgreSQL schema={CORE_SCHEMA}")

    def log(self, message: str):
        """统一的日志输出方法"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def set_stop_flag(self):
        """设置停止标志"""
        return self._set_stop_flag_target(SetStopFlagTarget())

    def _set_stop_flag_target(
        self,
        target: SetStopFlagTarget,
    ) -> None:
        self.stop_flag = True
        self.log("🛑 收到停止信号，任务将在下一个检查点停止")

    def is_stopped(self):
        """检查是否被停止（综合检查本地标志和外部函数）"""
        return self._is_stopped_target(IsStoppedTarget())

    def _is_stopped_target(
        self,
        target: IsStoppedTarget,
    ) -> bool:
        # 首先检查本地停止标志
        if self.stop_flag:
            return True
        # 然后检查外部停止检查函数
        if self.stop_check_func and self.stop_check_func():
            self.stop_flag = True  # 同步本地标志
            return True
        return False

    def check_stop(self):
        """检查是否需要停止（兼容旧方法名）"""
        return self._check_stop_target(CheckStopTarget())

    def _check_stop_target(
        self,
        target: CheckStopTarget,
    ) -> Any:
        return self.is_stopped()
    
    def clean_cookie(self, cookie: str) -> str:
        """清理Cookie字符串，去除不合法字符
        
        Args:
            cookie (str): 原始Cookie字符串
        
        Returns:
            str: 清理后的Cookie字符串
        """
        return self._clean_cookie_target(CleanCookieTarget(cookie))

    def _clean_cookie_target(
        self,
        target: CleanCookieTarget,
    ) -> Any:
        cookie, error = clean_cookie_result(target.cookie)
        if error is not None:
            print(f"Cookie清理失败: {error}")
        return cookie
    
    def _select_stealth_header_values(self) -> StealthHeaderSelection:
        user_agents = stealth_user_agents()
        selected_ua = random.choice(user_agents)
        sec_ch_ua = sec_ch_ua_for_user_agent(selected_ua)

        accept_languages = stealth_accept_languages()
        platforms = stealth_platforms()
        accept_language = random.choice(accept_languages)
        platform = random.choice(platforms)

        return StealthHeaderSelection(selected_ua, sec_ch_ua, accept_language, platform)

    def _apply_optional_stealth_headers(self, headers: Dict[str, str]) -> None:
        optional_headers = stealth_optional_headers()
        for key, value in optional_headers.items():
            if random.random() > 0.5:  # 50%概率添加
                headers[key] = value

    def _apply_dynamic_stealth_headers(self, headers: Dict[str, str]) -> None:
        if random.random() > 0.7:  # 30%概率添加
            headers['X-Timestamp'] = stealth_timestamp_header_value(
                int(time.time()),
                random.randint(-30, 30),
            )

        if random.random() > 0.6:  # 40%概率添加
            headers['X-Request-Id'] = stealth_request_id_header_value(
                random.randint(100000000000, 999999999999),
            )

    def get_stealth_headers(self) -> Dict[str, str]:
        """获取反检测请求头（每次调用随机化）"""
        selection = self._select_stealth_header_values()
        headers = stealth_base_headers(
            self.cookie,
            self.group_id,
            selection.user_agent,
            selection.sec_ch_ua,
            selection.accept_language,
            selection.platform,
        )
        self._apply_optional_stealth_headers(headers)
        self._apply_dynamic_stealth_headers(headers)
        return headers
    
    def smart_delay(self):
        """智能延迟"""
        return self._smart_delay_target(SmartDelayTarget())

    def _smart_delay_target(
        self,
        target: SmartDelayTarget,
    ) -> None:
        delay = random.uniform(self.min_delay, self.max_delay)
        if self.debug_mode:
            print(f"   ⏱️ 延迟 {delay:.1f}秒")
        time.sleep(delay)

    @staticmethod
    def _user_agent_label(user_agent: str) -> str:
        return risk_event_user_agent_label(user_agent)

    @staticmethod
    def _header_profile_label(headers: Dict[str, str]) -> str:
        return risk_event_header_profile_label(headers)

    def _prepare_risk_event_log_path(self) -> Optional[Any]:
        if not getattr(self, "risk_event_log_path", None):
            return None

        from pathlib import Path

        path = Path(self.risk_event_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _write_risk_event_row(self, path: Any, row: Dict[str, Any]) -> None:
        import csv

        fieldnames = tuple(row.keys())
        write_header = not path.exists()
        with path.open("a", encoding="utf-8-sig", newline="") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    def _record_risk_event(
        self,
        *,
        file_id: int,
        phase: str,
        attempt: int = 0,
        headers: Optional[Dict[str, str]] = None,
        http_status: Optional[int] = None,
        api_code: Optional[Any] = None,
        api_message: Optional[str] = None,
        status: str = "observed",
    ) -> None:
        path = self._prepare_risk_event_log_path()
        if path is None:
            return

        row = risk_event_row(
            datetime.datetime.now().isoformat(timespec="seconds"),
            self.group_id,
            file_id,
            phase,
            attempt,
            headers,
            http_status,
            api_code,
            api_message,
            status,
        )
        self._write_risk_event_row(path, row)

    def download_delay(self):
        """下载间隔延迟"""
        return self._download_delay_target(DownloadDelayTarget())

    def _download_delay_target(
        self,
        target: DownloadDelayTarget,
    ) -> None:
        if self.use_random_interval:
            # 使用API传入的随机间隔范围
            delay = random.uniform(self.download_interval_min, self.download_interval_max)
            print(f"⏳ 下载间隔: {delay:.0f}秒 ({delay/60:.1f}分钟) [随机范围: {self.download_interval_min}-{self.download_interval_max}秒]")
        else:
            # 使用固定间隔
            delay = self.download_interval
            print(f"⏳ 下载间隔: {delay:.1f}秒 [固定间隔]")

        start_time = datetime.datetime.now()
        end_time = start_time + datetime.timedelta(seconds=delay)

        print(f"   ⏰ 开始时间: {start_time.strftime('%H:%M:%S')}")
        print(f"   🕐 预计恢复: {end_time.strftime('%H:%M:%S')}")

        time.sleep(delay)

        actual_end_time = datetime.datetime.now()
        print(f"   🕐 实际结束: {actual_end_time.strftime('%H:%M:%S')}")
    
    def check_long_delay(self):
        """检查是否需要长休眠"""
        return self._check_long_delay_target(CheckLongDelayTarget())

    def _check_long_delay_target(
        self,
        target: CheckLongDelayTarget,
    ) -> None:
        if self.download_count > 0 and self.download_count % self.long_delay_interval == 0:
            if self.use_random_interval:
                # 使用API传入的随机长休眠间隔范围
                delay = random.uniform(self.long_sleep_interval_min, self.long_sleep_interval_max)
                print(f"🛌 长休眠开始: {delay:.0f}秒 ({delay/60:.1f}分钟) [随机范围: {self.long_sleep_interval_min/60:.1f}-{self.long_sleep_interval_max/60:.1f}分钟]")
            else:
                # 使用固定长休眠间隔
                delay = self.long_sleep_interval
                print(f"🛌 长休眠开始: {delay:.0f}秒 ({delay/60:.1f}分钟) [固定间隔]")

            start_time = datetime.datetime.now()
            end_time = start_time + datetime.timedelta(seconds=delay)

            print(f"   已下载 {self.download_count} 个文件，进入长休眠模式...")
            print(f"   ⏰ 开始时间: {start_time.strftime('%H:%M:%S')}")
            print(f"   🕐 预计恢复: {end_time.strftime('%H:%M:%S')}")

            time.sleep(delay)

            actual_end_time = datetime.datetime.now()
            print(f"😴 长休眠结束，继续下载...")
            print(f"   🕐 实际结束: {actual_end_time.strftime('%H:%M:%S')}")
    
    def _prepare_retry_api_request(self, attempt: int, file_id: Optional[int] = None) -> Dict[str, str]:
        return self._prepare_retry_api_request_target(
            PrepareRetryApiRequestTarget(attempt, file_id),
        )

    def _prepare_retry_api_request_target(
        self,
        target: PrepareRetryApiRequestTarget,
    ) -> Dict[str, str]:
        if target.attempt > 0:
            retry_delay = random.uniform(15, 30)
            print(api_retry_wait_message(target.attempt, retry_delay))
            time.sleep(retry_delay)

        self.smart_delay()
        self.request_count += 1
        headers = self.get_stealth_headers()
        if target.file_id is not None and getattr(self, "risk_event_log_path", None):
            user_agent = risk_event_header_user_agent(headers)
            self.log(f"   🧭 UA分类: {self._user_agent_label(user_agent)}")
        if target.file_id is not None:
            self._record_risk_event(
                file_id=target.file_id,
                phase="download_url_request",
                attempt=target.attempt,
                headers=headers,
            )

        if target.attempt > 0:
            print(api_retry_user_agent_message(target.attempt, headers))
        return headers

    def _parse_api_json_response(
        self,
        response: requests.Response,
        attempt: int,
        max_retries: int,
    ) -> ApiJsonParseResult:
        return self._parse_api_json_response_target(
            ParseApiJsonResponseTarget(response, attempt, max_retries),
        )

    def _parse_api_json_response_target(
        self,
        target: ParseApiJsonResponseTarget,
    ) -> ApiJsonParseResult:
        try:
            data = target.response.json()
        except json.JSONDecodeError as e:
            return _json_decode_failure_result_with_output(
                JsonDecodeFailureOutputTarget(
                    e,
                    target.response.text,
                    target.attempt,
                    target.max_retries,
                ),
            )

        if should_log_full_response(target.attempt, target.max_retries, data.get('succeeded')):
            print(f"   📋 响应内容: {json.dumps(redact_json_like(data), ensure_ascii=False, indent=2)}")
        return ApiJsonParseResult(data, False)

    def _handle_file_list_success_response(self, data: Dict[str, Any], attempt: int) -> Dict[str, Any]:
        return self._handle_file_list_success_response_target(
            FileListSuccessResponseTarget(data, attempt),
        )

    def _handle_file_list_success_response_target(
        self,
        target: FileListSuccessResponseTarget,
    ) -> Dict[str, Any]:
        files, _ = file_list_response_page(target.data)
        if target.attempt > 0:
            print(f"   ✅ 重试成功！第{target.attempt}次重试获取到文件列表")
        else:
            print(f"   ✅ 获取成功: {len(files)}个文件")
        return target.data

    def _handle_file_list_api_failure_response(
        self,
        data: Dict[str, Any],
        attempt: int,
        max_retries: int,
    ) -> str:
        return self._handle_file_list_api_failure_response_target(
            FileListApiFailureResponseTarget(data, attempt, max_retries),
        )

    def _handle_file_list_api_failure_response_target(
        self,
        target: FileListApiFailureResponseTarget,
    ) -> str:
        api_failure = file_list_api_failure_plan(
            target.data,
            target.attempt,
            target.max_retries,
        )
        for message in api_failure["messages"]:
            print(message)
        return api_failure["failure_class"]

    def _handle_file_list_http_failure_response(
        self,
        response: requests.Response,
        attempt: int,
        max_retries: int,
    ) -> str:
        return self._handle_file_list_http_failure_response_target(
            FileListHttpFailureResponseTarget(response, attempt, max_retries),
        )

    def _handle_file_list_http_failure_response_target(
        self,
        target: FileListHttpFailureResponseTarget,
    ) -> str:
        return _http_failure_class_with_output(
            HttpFailureOutputTarget(
                target.response.status_code,
                target.response.text,
                target.attempt,
                target.max_retries,
            ),
        )

    def _handle_file_list_request_exception(
        self,
        exc: Exception,
        attempt: int,
        max_retries: int,
    ) -> bool:
        return self._handle_file_list_request_exception_target(
            FileListRequestExceptionTarget(exc, attempt, max_retries),
        )

    def _handle_file_list_request_exception_target(
        self,
        target: FileListRequestExceptionTarget,
    ) -> bool:
        return _request_exception_should_retry_with_output(
            RequestExceptionOutputTarget(
                target.exc,
                target.attempt,
                target.max_retries,
            ),
        )

    def _file_list_api_failure_decision(self, failure_class: str) -> FileListResponseDecision:
        if failure_class == API_FAILURE_RETRY:
            return FileListResponseDecision(None, True, False)
        if failure_class in {API_FAILURE_NON_RETRY, API_FAILURE_PERMISSION_DENIED_1030}:
            return FileListResponseDecision(None, False, True)
        return FileListResponseDecision(None, False, False)

    def _file_list_http_failure_decision(self, failure_class: str) -> FileListResponseDecision:
        if failure_class == HTTP_FAILURE_RETRY:
            return FileListResponseDecision(None, True, False)
        if failure_class == HTTP_FAILURE_NON_RETRY:
            return FileListResponseDecision(None, False, True)
        return FileListResponseDecision(None, False, False)

    def _handle_file_list_ok_response(
        self,
        response: requests.Response,
        attempt: int,
        max_retries: int,
    ) -> FileListResponseDecision:
        return self._handle_file_list_ok_response_target(
            FileListOkResponseTarget(response, attempt, max_retries),
        )

    def _handle_file_list_ok_response_target(
        self,
        target: FileListOkResponseTarget,
    ) -> FileListResponseDecision:
        json_parse = self._parse_api_json_response(
            target.response,
            target.attempt,
            target.max_retries,
        )
        if json_parse.should_retry:
            return FileListResponseDecision(None, True, False)
        data = json_parse.data
        if not data:
            return FileListResponseDecision(None, True, False)

        if data.get('succeeded'):
            return FileListResponseDecision(
                self._handle_file_list_success_response(data, target.attempt),
                False,
                False,
            )

        failure_class = self._handle_file_list_api_failure_response_target(
            FileListApiFailureResponseTarget(
                data,
                target.attempt,
                target.max_retries,
            ),
        )
        return self._file_list_api_failure_decision(failure_class)

    def _handle_file_list_response(
        self,
        response: requests.Response,
        attempt: int,
        max_retries: int,
    ) -> FileListResponseDecision:
        return self._handle_file_list_response_target(
            FileListResponseTarget(response, attempt, max_retries),
        )

    def _handle_file_list_response_target(
        self,
        target: FileListResponseTarget,
    ) -> FileListResponseDecision:
        print(f"   📊 响应状态: {target.response.status_code}")

        if target.response.status_code == 200:
            return self._handle_file_list_ok_response_target(
                FileListOkResponseTarget(
                    target.response,
                    target.attempt,
                    target.max_retries,
                ),
            )

        http_failure_class = self._handle_file_list_http_failure_response_target(
            FileListHttpFailureResponseTarget(
                target.response,
                target.attempt,
                target.max_retries,
            ),
        )
        return self._file_list_http_failure_decision(http_failure_class)

    def fetch_file_list(self, count: int = 20, index: Optional[str] = None, sort: str = "by_download_count") -> Optional[Dict[str, Any]]:
        """获取文件列表（带重试机制）"""
        return self._fetch_file_list_target(FetchFileListTarget(count, index, sort))

    def _fetch_file_list_target(self, target: FetchFileListTarget) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/v2/groups/{self.group_id}/files"
        max_retries = 10

        params = file_list_request_params(target.count, target.sort, target.index)
        for message in file_list_start_messages(target.count, target.sort, target.index, url):
            self.log(message)
        
        for attempt in range(max_retries):
            headers = self._prepare_retry_api_request(attempt)
            
            try:
                response = self.session.get(url, headers=headers, params=params, timeout=30)
                decision = self._handle_file_list_response_target(
                    FileListResponseTarget(response, attempt, max_retries),
                )
                if decision.result is not None:
                    return decision.result
                if decision.should_retry:
                    continue
                if decision.should_stop:
                    return None
                    
            except Exception as e:
                if self._handle_file_list_request_exception_target(
                    FileListRequestExceptionTarget(e, attempt, max_retries),
                ):
                    continue
        
        print(retry_exhausted_message(max_retries))
        return None

    def _handle_download_url_success_response(
        self,
        data: Dict[str, Any],
        file_id: int,
        attempt: int,
        headers: Dict[str, str],
        http_status: int,
    ) -> Optional[str]:
        return self._handle_download_url_success_response_target(
            DownloadUrlSuccessResponseTarget(
                data,
                file_id,
                attempt,
                headers,
                http_status,
            ),
        )

    def _handle_download_url_success_response_target(
        self,
        target: DownloadUrlSuccessResponseTarget,
    ) -> Optional[str]:
        download_url = download_url_from_response_data(target.data)
        if download_url:
            success_message, success_phase = download_url_success_plan(target.attempt)
            print(success_message)
            self._record_download_url_success_event(
                DownloadUrlSuccessEventTarget(
                    target.file_id,
                    success_phase,
                    target.attempt,
                    target.headers,
                    target.http_status,
                ),
            )
            return download_url

        return self._handle_missing_download_url_response()

    def _handle_missing_download_url_response(self) -> Optional[str]:
        print(f"   ❌ 响应中无下载链接字段")
        return None

    def _record_download_url_success_event(
        self,
        target: DownloadUrlSuccessEventTarget,
    ) -> None:
        self._record_risk_event(
            file_id=target.file_id,
            phase=target.phase,
            attempt=target.attempt,
            headers=target.headers,
            http_status=target.http_status,
            status="api_success",
        )

    def _handle_download_url_api_failure_response(
        self,
        data: Dict[str, Any],
        file_id: int,
        attempt: int,
        max_retries: int,
        headers: Dict[str, str],
        http_status: int,
    ) -> str:
        return self._handle_download_url_api_failure_response_target(
            DownloadUrlApiFailureResponseTarget(
                data,
                file_id,
                attempt,
                max_retries,
                headers,
                http_status,
            ),
        )

    def _handle_download_url_api_failure_response_target(
        self,
        target: DownloadUrlApiFailureResponseTarget,
    ) -> str:
        api_failure = download_url_api_failure_plan(
            target.data,
            target.attempt,
            target.max_retries,
        )
        return self._apply_download_url_api_failure_plan(target, api_failure)

    def _apply_download_url_api_failure_plan(
        self,
        target: DownloadUrlApiFailureResponseTarget,
        api_failure: Dict[str, Any],
    ) -> str:
        self.log(api_failure["messages"][0])
        self._record_download_url_api_failure_event(
            DownloadUrlApiFailureEventTarget(
                target.file_id,
                target.attempt,
                target.headers,
                target.http_status,
                api_failure["error_code"],
                api_failure["error_msg"],
            ),
        )
        for message in api_failure["messages"][1:]:
            self.log(message)

        failure_class = api_failure["failure_class"]
        if failure_class == API_FAILURE_PERMISSION_DENIED_1030:
            self.last_download_url_error = api_failure["last_download_url_error"]
        return failure_class

    def _record_download_url_api_failure_event(
        self,
        target: DownloadUrlApiFailureEventTarget,
    ) -> None:
        self._record_risk_event(
            file_id=target.file_id,
            phase="download_url_response",
            attempt=target.attempt,
            headers=target.headers,
            http_status=target.http_status,
            api_code=target.error_code,
            api_message=target.error_msg,
            status="api_failed",
        )

    def _handle_download_url_http_failure_response(
        self,
        http_status: int,
        response_text: str,
        attempt: int,
        max_retries: int,
    ) -> str:
        return self._handle_download_url_http_failure_response_target(
            DownloadUrlHttpFailureResponseTarget(
                http_status,
                response_text,
                attempt,
                max_retries,
            ),
        )

    def _handle_download_url_http_failure_response_target(
        self,
        target: DownloadUrlHttpFailureResponseTarget,
    ) -> str:
        return _http_failure_class_with_output(
            HttpFailureOutputTarget(
                target.http_status,
                target.response_text,
                target.attempt,
                target.max_retries,
            ),
        )

    def _download_url_http_failure_decision(
        self,
        failure_class: str,
    ) -> DownloadUrlResponseDecision:
        if failure_class == HTTP_FAILURE_RETRY:
            return DownloadUrlResponseDecision(None, True, False)
        if failure_class == HTTP_FAILURE_NON_RETRY:
            return DownloadUrlResponseDecision(None, False, True)
        return DownloadUrlResponseDecision(None, False, False)

    def _handle_download_url_request_exception(
        self,
        exc: Exception,
        attempt: int,
        max_retries: int,
    ) -> bool:
        return self._handle_download_url_request_exception_target(
            DownloadUrlRequestExceptionTarget(exc, attempt, max_retries),
        )

    def _handle_download_url_request_exception_target(
        self,
        target: DownloadUrlRequestExceptionTarget,
    ) -> bool:
        return _request_exception_should_retry_with_output(
            RequestExceptionOutputTarget(
                target.exc,
                target.attempt,
                target.max_retries,
            ),
        )

    def _download_url_api_failure_decision(
        self,
        failure_class: str,
    ) -> DownloadUrlResponseDecision:
        if failure_class == API_FAILURE_PERMISSION_DENIED_1030:
            return DownloadUrlResponseDecision(None, False, True)
        if failure_class == API_FAILURE_RETRY:
            return DownloadUrlResponseDecision(None, True, False)
        if failure_class == API_FAILURE_NON_RETRY:
            return DownloadUrlResponseDecision(None, False, True)
        return DownloadUrlResponseDecision(None, False, False)

    def _handle_download_url_ok_response(
        self,
        response: Any,
        file_id: int,
        attempt: int,
        max_retries: int,
        headers: Dict[str, str],
    ) -> DownloadUrlResponseDecision:
        return self._handle_download_url_ok_response_target(
            DownloadUrlOkResponseTarget(
                response,
                file_id,
                attempt,
                max_retries,
                headers,
            ),
        )

    def _handle_download_url_ok_response_target(
        self,
        target: DownloadUrlOkResponseTarget,
    ) -> DownloadUrlResponseDecision:
        json_parse = self._parse_api_json_response(
            target.response,
            target.attempt,
            target.max_retries,
        )
        return self._download_url_json_parse_decision(target, json_parse)

    def _download_url_json_parse_decision(
        self,
        target: DownloadUrlOkResponseTarget,
        json_parse: ApiJsonParseResult,
    ) -> DownloadUrlResponseDecision:
        if json_parse.should_retry:
            return DownloadUrlResponseDecision(None, True, False)
        data = json_parse.data
        if not data:
            return DownloadUrlResponseDecision(None, True, False)

        return self._download_url_data_decision_target(
            DownloadUrlDataDecisionTarget(
                data,
                target.file_id,
                target.attempt,
                target.max_retries,
                target.headers,
                target.response.status_code,
            ),
        )

    def _download_url_data_decision(
        self,
        data: Dict[str, Any],
        file_id: int,
        attempt: int,
        max_retries: int,
        headers: Dict[str, str],
        http_status: int,
    ) -> DownloadUrlResponseDecision:
        return self._download_url_data_decision_target(
            DownloadUrlDataDecisionTarget(
                data,
                file_id,
                attempt,
                max_retries,
                headers,
                http_status,
            ),
        )

    def _download_url_data_decision_target(
        self,
        target: DownloadUrlDataDecisionTarget,
    ) -> DownloadUrlResponseDecision:
        if target.data.get('succeeded'):
            return self._download_url_success_data_decision(target)

        return self._download_url_api_failure_data_decision(target)

    def _download_url_success_data_decision(
        self,
        target: DownloadUrlDataDecisionTarget,
    ) -> DownloadUrlResponseDecision:
        download_url = self._handle_download_url_success_response_target(
            DownloadUrlSuccessResponseTarget(
                target.data,
                target.file_id,
                target.attempt,
                target.headers,
                target.http_status,
            ),
        )
        return DownloadUrlResponseDecision(download_url, False, False)

    def _download_url_api_failure_data_decision(
        self,
        target: DownloadUrlDataDecisionTarget,
    ) -> DownloadUrlResponseDecision:
        failure_class = self._handle_download_url_api_failure_response_target(
            DownloadUrlApiFailureResponseTarget(
                target.data,
                target.file_id,
                target.attempt,
                target.max_retries,
                target.headers,
                target.http_status,
            ),
        )

        return self._download_url_api_failure_decision(failure_class)

    def _handle_download_url_response(
        self,
        response: Any,
        file_id: int,
        attempt: int,
        max_retries: int,
        headers: Dict[str, str],
    ) -> DownloadUrlResponseDecision:
        return self._handle_download_url_response_target(
            DownloadUrlResponseTarget(
                response,
                file_id,
                attempt,
                max_retries,
                headers,
            ),
        )

    def _handle_download_url_response_target(
        self,
        target: DownloadUrlResponseTarget,
    ) -> DownloadUrlResponseDecision:
        print(f"   📊 响应状态: {target.response.status_code}")
        return self._download_url_status_decision(target)

    def _download_url_status_decision(
        self,
        target: DownloadUrlResponseTarget,
    ) -> DownloadUrlResponseDecision:
        if target.response.status_code == 200:
            return self._handle_download_url_ok_response_target(
                DownloadUrlOkResponseTarget(
                    target.response,
                    target.file_id,
                    target.attempt,
                    target.max_retries,
                    target.headers,
                ),
            )

        http_failure_class = self._handle_download_url_http_failure_response_target(
            DownloadUrlHttpFailureResponseTarget(
                target.response.status_code,
                target.response.text,
                target.attempt,
                target.max_retries,
            ),
        )
        return self._download_url_http_failure_decision(http_failure_class)

    def _start_download_url_request(self, file_id: int) -> str:
        url = f"{self.base_url}/v2/files/{file_id}/download_url"
        self.last_download_url_error = None
        self.log(f"   🔗 获取下载链接: ID={file_id}")
        self.log(f"   🌐 请求URL: {url}")
        return url

    def _request_download_url_response(self, url: str, headers: Dict[str, str]) -> Any:
        return self._request_download_url_response_target(
            DownloadUrlRequestTarget(url, headers),
        )

    def _request_download_url_response_target(
        self,
        target: DownloadUrlRequestTarget,
    ) -> Any:
        return self.session.get(
            target.url,
            headers=target.headers,
            timeout=DOWNLOAD_URL_REQUEST_TIMEOUT_SECONDS,
        )

    def _run_download_url_attempt(
        self,
        url: str,
        file_id: int,
        attempt: int,
        max_retries: int,
    ) -> DownloadUrlResponseDecision:
        return self._run_download_url_attempt_target(
            DownloadUrlAttemptTarget(url, file_id, attempt, max_retries),
        )

    def _run_download_url_attempt_target(
        self,
        target: DownloadUrlAttemptTarget,
    ) -> DownloadUrlResponseDecision:
        headers = self._prepare_retry_api_request(target.attempt, file_id=target.file_id)

        try:
            response = self._request_download_url_response_target(
                DownloadUrlRequestTarget(target.url, headers),
            )
            return self._handle_download_url_attempt_response(target, headers, response)
        except Exception as e:
            return self._handle_download_url_attempt_exception(target, e)

    def _handle_download_url_attempt_response(
        self,
        target: DownloadUrlAttemptTarget,
        headers: Dict[str, str],
        response: Any,
    ) -> DownloadUrlResponseDecision:
        return self._handle_download_url_response_target(
            DownloadUrlResponseTarget(
                response,
                target.file_id,
                target.attempt,
                target.max_retries,
                headers,
            ),
        )

    def _handle_download_url_attempt_exception(
        self,
        target: DownloadUrlAttemptTarget,
        exc: Exception,
    ) -> DownloadUrlResponseDecision:
        if self._handle_download_url_request_exception_target(
            DownloadUrlRequestExceptionTarget(exc, target.attempt, target.max_retries),
        ):
            return DownloadUrlResponseDecision(None, True, False)
        return DownloadUrlResponseDecision(None, False, False)

    def _download_url_retry_loop_step_decision(
        self,
        decision: DownloadUrlResponseDecision,
    ) -> DownloadUrlRetryLoopStepDecision:
        if decision.download_url:
            return DownloadUrlRetryLoopStepDecision(decision.download_url, False)
        if decision.should_retry:
            return DownloadUrlRetryLoopStepDecision(None, True)
        if decision.should_stop:
            return DownloadUrlRetryLoopStepDecision(None, False)
        return DownloadUrlRetryLoopStepDecision(None, True)

    def _run_download_url_retry_loop_target(
        self,
        target: DownloadUrlRetryLoopTarget,
    ) -> Optional[str]:
        for attempt in range(target.max_retries):
            decision = self._run_download_url_attempt_target(
                DownloadUrlAttemptTarget(target.url, target.file_id, attempt, target.max_retries),
            )
            step_decision = self._download_url_retry_loop_step_decision(decision)
            if step_decision.should_continue:
                continue
            return step_decision.result

        print(retry_exhausted_message(target.max_retries))
        return None

    def get_download_url(self, file_id: int) -> Optional[str]:
        """获取文件下载链接（带重试机制）

        注意：file_id 参数在不同场景下含义不同：
        - 边获取边下载时：传入的是真实的 file_id
        - 从数据库下载时：传入的是 topic_id
        """
        return self._get_download_url_target(DownloadUrlEntryTarget(file_id))

    def _get_download_url_target(
        self,
        target: DownloadUrlEntryTarget,
    ) -> Optional[str]:
        url = self._start_download_url_request(target.file_id)
        return self._run_download_url_retry_loop_target(
            DownloadUrlRetryLoopTarget(url, target.file_id, DOWNLOAD_URL_MAX_RETRIES),
        )

    def download_file(self, file_info: Dict[str, Any]) -> bool:
        """下载单个文件"""
        return self._download_file_target(DownloadFileEntryTarget(file_info))

    def _download_file_target(self, target: DownloadFileEntryTarget) -> bool:
        prepared_file = self._prepare_download_file_target(target.file_info)
        if not prepared_file:
            return False

        # 🚀 优化：先检查本地文件，避免无意义的API请求
        existing_file_result = self._skip_existing_download_target(
            ExistingDownloadTarget(
                prepared_file.file_id,
                prepared_file.file_path,
                prepared_file.file_size,
            ),
        )
        if existing_file_result:
            return existing_file_result

        return self._run_download_retry_loop(prepared_file)

    def _run_download_retry_loop(
        self,
        prepared_file: DownloadFileTarget,
    ) -> bool:
        download_retries = DOWNLOAD_FILE_MAX_RETRIES
        retry_state = self._initial_download_retry_state(prepared_file)

        for attempt in range(download_retries):
            retry_decision = self._run_download_retry_loop_attempt_target(
                DownloadRetryLoopAttemptTarget(
                    attempt,
                    download_retries,
                    prepared_file,
                    retry_state,
                ),
            )
            retry_state = retry_decision.state
            if retry_decision.result is None:
                continue
            return retry_decision.result

        return self._finish_download_retry_loop_failure_target(
            DownloadRetryLoopFailureTarget(prepared_file, download_retries, retry_state),
        )

    def _initial_download_retry_state(
        self,
        prepared_file: DownloadFileTarget,
    ) -> DownloadRetryState:
        return DownloadRetryState(
            prepared_file.file_name,
            prepared_file.safe_filename,
            prepared_file.file_path,
            None,
            None,
        )

    def _finish_download_retry_loop_failure_target(
        self,
        target: DownloadRetryLoopFailureTarget,
    ) -> bool:
        self._mark_download_failed_after_retries_target(
            DownloadFinalFailureTarget(
                target.prepared_file.file_id,
                target.download_retries,
                target.retry_state.last_error_code,
                target.retry_state.last_error,
            ),
        )
        return False

    def _run_download_retry_loop_attempt(
        self,
        attempt: int,
        download_retries: int,
        prepared_file: DownloadFileTarget,
        retry_state: DownloadRetryState,
    ) -> DownloadRetryDecision:
        return self._run_download_retry_loop_attempt_target(
            DownloadRetryLoopAttemptTarget(
                attempt,
                download_retries,
                prepared_file,
                retry_state,
            ),
        )

    def _run_download_retry_loop_attempt_target(
        self,
        target: DownloadRetryLoopAttemptTarget,
    ) -> DownloadRetryDecision:
        try:
            attempt_target = self._download_retry_attempt_file_target(target)
            attempt_result = self._run_download_attempt_target(
                DownloadAttemptTarget(
                    target.attempt,
                    target.download_retries,
                    attempt_target,
                ),
            )
            return self._apply_download_attempt_result_target(
                DownloadAttemptResultTarget(attempt_result, target.retry_state),
            )
        except Exception as e:
            return self._handle_download_retry_loop_attempt_exception(target, e)

    def _download_retry_attempt_file_target(
        self,
        target: DownloadRetryLoopAttemptTarget,
    ) -> DownloadFileTarget:
        return target.prepared_file._replace(
            file_name=target.retry_state.file_name,
            safe_filename=target.retry_state.safe_filename,
            file_path=target.retry_state.file_path,
        )

    def _handle_download_retry_loop_attempt_exception(
        self,
        target: DownloadRetryLoopAttemptTarget,
        exc: Exception,
    ) -> DownloadRetryDecision:
        return DownloadRetryDecision(
            self._record_download_retry_exception_target(
                DownloadRetryExceptionTarget(exc, target.retry_state),
            ),
            None,
        )

    def _apply_download_attempt_result(
        self,
        attempt_result: DownloadAttemptResult,
        retry_state: DownloadRetryState,
    ) -> DownloadRetryDecision:
        return self._apply_download_attempt_result_target(
            DownloadAttemptResultTarget(attempt_result, retry_state),
        )

    def _apply_download_attempt_result_target(
        self,
        target: DownloadAttemptResultTarget,
    ) -> DownloadRetryDecision:
        retry_state = self._download_retry_state_after_attempt_result(target)
        return self._download_retry_decision_after_attempt_result(
            DownloadAttemptResultTarget(target.attempt_result, retry_state),
        )

    def _download_retry_state_after_attempt_result(
        self,
        target: DownloadAttemptResultTarget,
    ) -> DownloadRetryState:
        attempt_result = target.attempt_result
        retry_state = target.retry_state
        return DownloadRetryState(
            attempt_result.file_name,
            attempt_result.safe_filename,
            attempt_result.file_path,
            retry_state.last_error_code,
            retry_state.last_error,
        )

    def _download_retry_decision_after_attempt_result(
        self,
        target: DownloadAttemptResultTarget,
    ) -> DownloadRetryDecision:
        attempt_result = target.attempt_result
        retry_state = target.retry_state
        if attempt_result.success_result is False:
            return DownloadRetryDecision(retry_state, False)
        if not attempt_result.failure_detail:
            return DownloadRetryDecision(retry_state, True)
        return DownloadRetryDecision(
            retry_state._replace(
                last_error_code=attempt_result.failure_detail.error_code,
                last_error=attempt_result.failure_detail.error_message,
            ),
            None,
        )

    def _record_download_retry_exception(
        self,
        exc: Exception,
        retry_state: DownloadRetryState,
    ) -> DownloadRetryState:
        return self._record_download_retry_exception_target(
            DownloadRetryExceptionTarget(exc, retry_state),
        )

    def _record_download_retry_exception_target(
        self,
        target: DownloadRetryExceptionTarget,
    ) -> DownloadRetryState:
        retry_state = target.retry_state
        failure_detail = self._record_download_exception_target(
            DownloadExceptionTarget(target.exc, retry_state.file_path),
        )
        return retry_state._replace(
            last_error_code=failure_detail.error_code,
            last_error=failure_detail.error_message,
        )

    def _run_download_attempt(
        self,
        attempt: int,
        download_retries: int,
        target: DownloadFileTarget,
    ) -> DownloadAttemptResult:
        return self._run_download_attempt_target(
            DownloadAttemptTarget(attempt, download_retries, target),
        )

    def _run_download_attempt_target(
        self,
        target: DownloadAttemptTarget,
    ) -> DownloadAttemptResult:
        if target.attempt > 0:
            self._wait_before_download_retry_target(
                DownloadRetryWaitTarget(target.attempt, target.download_retries),
            )

        file_target = target.file_target
        download_url = self._get_download_url_or_mark_unavailable(file_target.file_id)
        if not download_url:
            return self._download_attempt_missing_url_result(file_target)

        return self._run_download_attempt_response_target(
            DownloadAttemptResponseTarget(download_url, file_target),
        )

    def _download_attempt_missing_url_result(
        self,
        file_target: DownloadFileTarget,
    ) -> DownloadAttemptResult:
        return DownloadAttemptResult(
            False,
            None,
            file_target.file_name,
            file_target.safe_filename,
            file_target.file_path,
        )

    def _run_download_attempt_response_target(
        self,
        target: DownloadAttemptResponseTarget,
    ) -> DownloadAttemptResult:
        response = self._request_download_response(target.download_url)
        return self._handle_download_response_result_target(
            DownloadResponseTarget(response, target.file_target),
        )

    def _prepare_download_file_target(
        self,
        file_info: Dict[str, Any],
    ) -> Optional[DownloadFileTarget]:
        file_data = self._download_file_preparation_data(file_info)
        self._log_download_file_preparation(file_data)
        if not file_data.file_id:
            self.log("   ❌ 文件缺少 file_id，无法下载")
            return None

        if self.check_stop():
            self.log("🛑 下载任务被停止")
            return None

        return self._download_file_target_from_preparation_data(file_data)

    def _download_file_preparation_data(
        self,
        file_info: Dict[str, Any],
    ) -> DownloadFilePreparationData:
        file_data = download_file_data(file_info)
        return DownloadFilePreparationData(
            file_data["file_id"],
            file_data["file_name"],
            file_data["file_size"],
            file_data["download_count"],
        )

    def _log_download_file_preparation(
        self,
        file_data: DownloadFilePreparationData,
    ) -> None:
        self.log(f"📥 准备下载文件:")
        self.log(f"   📄 名称: {file_data.file_name}")
        self.log(f"   📊 大小: {file_data.file_size:,} bytes ({file_data.file_size/1024/1024:.2f} MB)")
        self.log(f"   📈 下载次数: {file_data.download_count}")

    def _download_file_target_from_preparation_data(
        self,
        file_data: DownloadFilePreparationData,
    ) -> DownloadFileTarget:
        safe_filename, file_path = download_target_path(
            self.download_dir,
            file_data.file_name,
            file_data.file_id,
        )
        return DownloadFileTarget(
            file_data.file_id,
            file_data.file_name,
            file_data.file_size,
            safe_filename,
            file_path,
        )

    def _skip_existing_download_if_complete(
        self,
        file_id: int,
        file_path: str,
        file_size: int,
    ) -> Optional[str]:
        return self._skip_existing_download_target(
            ExistingDownloadTarget(
                file_id,
                file_path,
                file_size,
            ),
        )

    def _skip_existing_download_target(
        self,
        target: ExistingDownloadTarget,
    ) -> Optional[str]:
        existing_match = self._existing_download_match(target)
        if not existing_match.file_exists:
            return None

        if existing_match.size_matches:
            return self._mark_existing_download_completed_target(target)

        self.log(f"   ⚠️ 文件已存在但大小不匹配，重新下载")
        return None

    def _existing_download_match(
        self,
        target: ExistingDownloadTarget,
    ) -> ExistingDownloadMatch:
        file_exists, size_matches, existing_size = existing_file_matches(
            target.file_path,
            target.file_size,
        )
        return ExistingDownloadMatch(file_exists, size_matches, existing_size)

    def _mark_existing_download_completed_target(
        self,
        target: ExistingDownloadTarget,
    ) -> str:
        self.log(f"   ✅ 文件已存在且大小匹配，跳过下载")
        self.file_db.update_file_download_status(
            target.file_id,
            'completed',
            target.file_path,
        )
        return "skipped"

    def _get_download_url_or_mark_unavailable(self, file_id: int) -> Optional[str]:
        download_url = self.get_download_url(file_id)
        if download_url:
            return download_url

        self._mark_download_url_unavailable_target(
            DownloadUrlUnavailableTarget(
                file_id,
                self.last_download_url_error,
            ),
        )
        return None

    def _mark_download_url_unavailable(self, file_id: int) -> None:
        self._mark_download_url_unavailable_target(
            DownloadUrlUnavailableTarget(
                file_id,
                self.last_download_url_error,
            ),
        )

    def _mark_download_url_unavailable_target(
        self,
        target: DownloadUrlUnavailableTarget,
    ) -> None:
        self.log(f"   ❌ 无法获取下载链接")
        failure_detail = self._download_url_unavailable_failure_detail(target)
        self._update_download_url_unavailable_status(target.file_id, failure_detail)

    def _download_url_unavailable_failure_detail(
        self,
        target: DownloadUrlUnavailableTarget,
    ) -> DownloadFailureDetail:
        error_code, error_message = download_url_failure_detail(target.last_download_url_error)
        return DownloadFailureDetail(error_code, error_message)

    def _update_download_url_unavailable_status(
        self,
        file_id: int,
        failure_detail: DownloadFailureDetail,
    ) -> None:
        self.file_db.update_file_download_status(
            file_id,
            'failed',
            error_code=failure_detail.error_code,
            error_message=failure_detail.error_message,
        )

    def _mark_download_failed_after_retries(
        self,
        file_id: int,
        download_retries: int,
        last_error_code: Optional[str],
        last_error: Optional[str],
    ) -> None:
        self._mark_download_failed_after_retries_target(
            DownloadFinalFailureTarget(
                file_id,
                download_retries,
                last_error_code,
                last_error,
            ),
        )

    def _mark_download_failed_after_retries_target(
        self,
        target: DownloadFinalFailureTarget,
    ) -> None:
        self.log(f"   🚫 文件下载重试{target.download_retries}次仍失败: {target.last_error}")
        failure_detail = self._download_final_failure_detail(target)
        self._update_download_final_failure_status(target.file_id, failure_detail)

    def _download_final_failure_detail(
        self,
        target: DownloadFinalFailureTarget,
    ) -> DownloadFailureDetail:
        error_code, error_message = download_final_failure_detail(
            target.last_error_code,
            target.last_error,
        )
        return DownloadFailureDetail(error_code, error_message)

    def _update_download_final_failure_status(
        self,
        file_id: int,
        failure_detail: DownloadFailureDetail,
    ) -> None:
        self.file_db.update_file_download_status(
            file_id,
            'failed',
            error_code=failure_detail.error_code,
            error_message=failure_detail.error_message,
        )

    def _complete_successful_download(
        self,
        file_id: int,
        safe_filename: str,
        file_path: str,
        temp_path: str,
    ) -> None:
        self._complete_successful_download_target(
            DownloadCompletionTarget(
                file_id,
                safe_filename,
                file_path,
                temp_path,
            ),
        )

    def _complete_successful_download_target(
        self,
        target: DownloadCompletionTarget,
    ) -> None:
        self._replace_successful_download_file(target)
        self._log_successful_download_target(target)
        self._mark_successful_download_completed(target)
        self._increment_successful_download_counters()
        self._apply_download_intervals()

    def _replace_successful_download_file(
        self,
        target: DownloadCompletionTarget,
    ) -> None:
        os.replace(target.temp_path, target.file_path)

    def _log_successful_download_target(
        self,
        target: DownloadCompletionTarget,
    ) -> None:
        self.log(f"   ✅ 下载完成: {target.safe_filename}")
        self.log(f"   💾 保存路径: {target.file_path}")

    def _mark_successful_download_completed(
        self,
        target: DownloadCompletionTarget,
    ) -> None:
        self.file_db.update_file_download_status(
            target.file_id,
            'completed',
            target.file_path,
        )

    def _increment_successful_download_counters(self) -> None:
        self.download_count += 1
        self.current_batch_count += 1

    def _write_download_response_body(
        self,
        response,
        temp_path: str,
        total_size: int,
        file_id: int,
    ) -> Optional[int]:
        return self._write_download_response_body_target(
            response,
            DownloadBodyWriteTarget(temp_path, total_size, file_id),
        )

    def _write_download_response_body_target(
        self,
        response: Any,
        target: DownloadBodyWriteTarget,
    ) -> Optional[int]:
        return self._write_download_response_body_result_target(
            DownloadBodyResponseTarget(response, target),
        )

    def _write_download_response_body_result_target(
        self,
        target: DownloadBodyResponseTarget,
    ) -> Optional[int]:
        return self._write_download_body_response_stream(
            target.response,
            target.body_target,
        )

    def _write_download_body_response_stream(
        self,
        response: Any,
        body_target: DownloadBodyWriteTarget,
    ) -> Optional[int]:
        downloaded_size = 0
        with open(body_target.temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    chunk_result = self._write_download_body_content_chunk(
                        f,
                        chunk,
                        downloaded_size,
                        body_target,
                    )
                    if chunk_result is None:
                        return None
                    downloaded_size = chunk_result

        return downloaded_size

    def _write_download_body_content_chunk(
        self,
        file_obj: Any,
        chunk: bytes,
        downloaded_size: int,
        body_target: DownloadBodyWriteTarget,
    ) -> Optional[int]:
        downloaded_size = self._write_download_body_chunk(
            file_obj,
            chunk,
            downloaded_size,
            body_target.total_size,
        )
        if self._stop_download_body_if_requested(body_target):
            return None
        return downloaded_size

    def _write_download_body_chunk(
        self,
        file_obj: Any,
        chunk: bytes,
        downloaded_size: int,
        total_size: int,
    ) -> int:
        file_obj.write(chunk)
        downloaded_size += len(chunk)
        self._log_download_body_progress(downloaded_size, total_size)
        return downloaded_size

    def _log_download_body_progress(
        self,
        downloaded_size: int,
        total_size: int,
    ) -> None:
        progress_message = download_progress_message(
            downloaded_size,
            total_size,
        )
        if progress_message:
            self.log(progress_message)

    def _stop_download_body_if_requested(
        self,
        target: DownloadBodyWriteTarget,
    ) -> bool:
        if not self.check_stop():
            return False

        self._handle_download_stop_target(
            DownloadStopTarget(
                target.file_id,
                target.temp_path,
            ),
        )
        return True

    def _apply_response_filename_override(
        self,
        file_name: str,
        file_id: int,
        response_headers: Dict[str, Any],
    ) -> Optional[DownloadFilenameOverride]:
        return self._apply_response_filename_override_target(
            ResponseFilenameOverrideTarget(file_name, file_id, response_headers),
        )

    def _apply_response_filename_override_target(
        self,
        target: ResponseFilenameOverrideTarget,
    ) -> Optional[DownloadFilenameOverride]:
        filename_override = self._response_filename_override_for_target(target)
        if not filename_override:
            return None

        return self._download_filename_override_from_raw(filename_override)

    def _response_filename_override_for_target(
        self,
        target: ResponseFilenameOverrideTarget,
    ) -> Optional[Tuple[str, str, str]]:
        return response_filename_override(
            target.file_name,
            target.file_id,
            self.download_dir,
            target.response_headers,
        )

    def _download_filename_override_from_raw(
        self,
        filename_override: Tuple[str, str, str],
    ) -> DownloadFilenameOverride:
        real_filename, safe_filename, file_path = filename_override
        self.log(f"   📝 从响应头获取到真实文件名: {real_filename}")
        return DownloadFilenameOverride(real_filename, safe_filename, file_path)

    def _record_download_http_failure(self, status_code: int) -> DownloadFailureDetail:
        return self._record_download_http_failure_target(
            DownloadHttpFailureTarget(status_code),
        )

    def _record_download_http_failure_target(
        self,
        target: DownloadHttpFailureTarget,
    ) -> DownloadFailureDetail:
        error_code, error_message = self._download_http_failure_detail(target)
        self._log_download_http_failure(error_message)
        return DownloadFailureDetail(error_code, error_message)

    def _download_http_failure_detail(
        self,
        target: DownloadHttpFailureTarget,
    ) -> Tuple[str, str]:
        return download_http_failure_detail(target.status_code)

    def _log_download_http_failure(self, error_message: str) -> None:
        self.log(f"   ❌ 下载失败: {error_message}")

    def _record_download_exception(self, exc: Exception, file_path: str) -> DownloadFailureDetail:
        return self._record_download_exception_target(DownloadExceptionTarget(exc, file_path))

    def _record_download_exception_target(
        self,
        target: DownloadExceptionTarget,
    ) -> DownloadFailureDetail:
        error_code, error_message = self._download_exception_detail(target)
        self._log_download_exception(target.exc)
        self._remove_partial_download_after_exception(target.file_path)
        return DownloadFailureDetail(error_code, error_message)

    def _download_exception_detail(
        self,
        target: DownloadExceptionTarget,
    ) -> Tuple[str, str]:
        return download_exception_detail(target.exc)

    def _log_download_exception(self, exc: Exception) -> None:
        self.log(f"   ❌ 下载异常: {exc}")

    def _remove_partial_download_after_exception(self, file_path: str) -> None:
        temp_path = partial_download_path(file_path)
        if remove_partial_download(temp_path):
            self.log(f"   🗑️ 删除不完整文件")

    def _wait_before_download_retry(self, attempt: int, download_retries: int) -> None:
        self._wait_before_download_retry_target(
            DownloadRetryWaitTarget(attempt, download_retries),
        )

    def _wait_before_download_retry_target(
        self,
        target: DownloadRetryWaitTarget,
    ) -> None:
        retry_delay, retry_message = download_retry_wait(target.attempt, target.download_retries)
        self.log(retry_message)
        time.sleep(retry_delay)

    def _request_download_response(self, download_url: str) -> Any:
        return self._request_download_response_target(
            DownloadFileResponseRequestTarget(download_url),
        )

    def _request_download_response_target(
        self,
        target: DownloadFileResponseRequestTarget,
    ) -> Any:
        self._log_download_response_request_start()
        return self._send_download_response_request(target)

    def _log_download_response_request_start(self) -> None:
        self.log(f"   🚀 开始下载...")

    def _send_download_response_request(
        self,
        target: DownloadFileResponseRequestTarget,
    ) -> Any:
        return self.session.get(
            target.download_url,
            timeout=DOWNLOAD_FILE_RESPONSE_TIMEOUT_SECONDS,
            stream=True,
        )

    def _successful_download_attempt_result(
        self,
        response: Any,
        target: DownloadFileTarget,
    ) -> DownloadAttemptResult:
        return self._successful_download_attempt_result_target(
            DownloadResponseTarget(response, target),
        )

    def _successful_download_attempt_result_target(
        self,
        target: DownloadResponseTarget,
    ) -> DownloadAttemptResult:
        file_target = target.file_target
        body_result = self._handle_successful_download_response_result_target(
            target,
        )
        return DownloadAttemptResult(
            body_result.success_result,
            body_result.failure_detail,
            file_target.file_name,
            file_target.safe_filename,
            file_target.file_path,
        )

    def _download_attempt_result_for_response_status(
        self,
        response: Any,
        target: DownloadFileTarget,
    ) -> DownloadAttemptResult:
        return self._download_attempt_result_for_response_status_target(
            DownloadResponseTarget(response, target),
        )

    def _download_attempt_result_for_response_status_target(
        self,
        target: DownloadResponseTarget,
    ) -> DownloadAttemptResult:
        response = target.response
        file_target = target.file_target
        if response.status_code == 200:
            return self._successful_download_attempt_result_target(
                DownloadResponseTarget(response, file_target),
            )

        return self._http_failure_download_attempt_result(target)

    def _http_failure_download_attempt_result(
        self,
        target: DownloadResponseTarget,
    ) -> DownloadAttemptResult:
        response = target.response
        file_target = target.file_target
        failure_detail = self._record_download_http_failure(response.status_code)
        return DownloadAttemptResult(
            None,
            failure_detail,
            file_target.file_name,
            file_target.safe_filename,
            file_target.file_path,
        )

    def _download_target_for_response(
        self,
        response: Any,
        target: DownloadFileTarget,
    ) -> DownloadFileTarget:
        return self._download_target_for_response_target(
            DownloadResponseTarget(response, target),
        )

    def _download_target_for_response_target(
        self,
        target: DownloadResponseTarget,
    ) -> DownloadFileTarget:
        file_target = target.file_target
        filename_override = self._apply_response_filename_override_target(
            ResponseFilenameOverrideTarget(
                file_target.file_name,
                file_target.file_id,
                target.response.headers,
            ),
        )
        if not filename_override:
            return file_target._replace()

        return file_target._replace(
            file_name=filename_override.file_name,
            safe_filename=filename_override.safe_filename,
            file_path=filename_override.file_path,
        )

    def _handle_download_response(
        self,
        response,
        file_id: int,
        file_name: str,
        file_size: int,
        safe_filename: str,
        file_path: str,
    ) -> DownloadAttemptResult:
        return self._handle_download_response_target(
            response,
            DownloadFileTarget(
                file_id,
                file_name,
                file_size,
                safe_filename,
                file_path,
            ),
        )

    def _handle_download_response_target(
        self,
        response: Any,
        target: DownloadFileTarget,
    ) -> DownloadAttemptResult:
        return self._handle_download_response_result_target(
            DownloadResponseTarget(response, target),
        )

    def _handle_download_response_result_target(
        self,
        target: DownloadResponseTarget,
    ) -> DownloadAttemptResult:
        response = target.response
        response_download_target = target.file_target
        try:
            response_download_target = self._download_target_for_response_target(
                target,
            )

            return self._download_attempt_result_for_response_status_target(
                DownloadResponseTarget(response, response_download_target),
            )
        except Exception as exc:
            return self._download_response_exception_result(
                exc,
                response_download_target,
            )

    def _download_response_exception_result(
        self,
        exc: Exception,
        response_download_target: DownloadFileTarget,
    ) -> DownloadAttemptResult:
        failure_detail = self._record_download_exception_target(
            DownloadExceptionTarget(
                exc,
                response_download_target.file_path,
            ),
        )
        return DownloadAttemptResult(
            None,
            failure_detail,
            response_download_target.file_name,
            response_download_target.safe_filename,
            response_download_target.file_path,
        )

    def _prepare_download_body_target(
        self,
        response_headers: Dict[str, Any],
        file_size: int,
        file_path: str,
    ) -> DownloadBodyTarget:
        return self._prepare_download_body_target_from_target(
            DownloadBodyPreparationTarget(
                response_headers,
                file_size,
                file_path,
            )
        )

    def _prepare_download_body_target_from_target(
        self,
        target: DownloadBodyPreparationTarget,
    ) -> DownloadBodyTarget:
        body_target = self._download_body_target_for_preparation(target)
        remove_partial_download(body_target.temp_path)
        return body_target

    def _download_body_target_for_preparation(
        self,
        target: DownloadBodyPreparationTarget,
    ) -> DownloadBodyTarget:
        total_size = download_total_size(target.response_headers)
        expected_size = download_expected_size(target.file_size, total_size)
        temp_path = partial_download_path(target.file_path)
        return DownloadBodyTarget(total_size, expected_size, temp_path)

    def _handle_successful_download_response(
        self,
        response,
        file_id: int,
        file_size: int,
        safe_filename: str,
        file_path: str,
    ) -> DownloadBodyResult:
        return self._handle_successful_download_response_target(
            response,
            DownloadFileTarget(
                file_id,
                safe_filename,
                file_size,
                safe_filename,
                file_path,
            ),
        )

    def _handle_successful_download_response_target(
        self,
        response: Any,
        target: DownloadFileTarget,
    ) -> DownloadBodyResult:
        return self._handle_successful_download_response_result_target(
            DownloadResponseTarget(response, target),
        )

    def _handle_successful_download_response_result_target(
        self,
        target: DownloadResponseTarget,
    ) -> DownloadBodyResult:
        body_target = self._download_body_target_for_response(target)
        return self._download_body_result_for_response_target(target, body_target)

    def _download_body_target_for_response(
        self,
        target: DownloadResponseTarget,
    ) -> DownloadBodyTarget:
        response = target.response
        file_target = target.file_target
        return self._prepare_download_body_target_from_target(
            DownloadBodyPreparationTarget(
                response.headers,
                file_target.file_size,
                file_target.file_path,
            ),
        )

    def _download_body_result_for_response_target(
        self,
        target: DownloadResponseTarget,
        body_target: DownloadBodyTarget,
    ) -> DownloadBodyResult:
        downloaded_size = self._downloaded_size_for_response_body_target(target, body_target)
        return self._finalize_download_body_result_decision_target(
            self._download_body_finalization_decision_target(
                downloaded_size,
                target,
                body_target,
            )
        )

    def _downloaded_size_for_response_body_target(
        self,
        target: DownloadResponseTarget,
        body_target: DownloadBodyTarget,
    ) -> Optional[int]:
        return self._write_download_response_body_result_target(
            self._download_body_write_response_target(target, body_target),
        )

    def _download_body_write_response_target(
        self,
        target: DownloadResponseTarget,
        body_target: DownloadBodyTarget,
    ) -> DownloadBodyResponseTarget:
        response = target.response
        file_target = target.file_target
        return DownloadBodyResponseTarget(
            response,
            DownloadBodyWriteTarget(
                body_target.temp_path,
                body_target.total_size,
                file_target.file_id,
            ),
        )

    def _download_body_finalization_decision_target(
        self,
        downloaded_size: Optional[int],
        target: DownloadResponseTarget,
        body_target: DownloadBodyTarget,
    ) -> DownloadBodyFinalizationDecisionTarget:
        file_target = target.file_target
        return DownloadBodyFinalizationDecisionTarget(
            downloaded_size,
            DownloadBodyFinalizationTarget(
                body_target.expected_size,
                body_target.temp_path,
                file_target.file_id,
                file_target.safe_filename,
                file_target.file_path,
            ),
        )

    def _finalize_download_body_result(
        self,
        downloaded_size: Optional[int],
        expected_size: int,
        temp_path: str,
        file_id: int,
        safe_filename: str,
        file_path: str,
    ) -> DownloadBodyResult:
        return self._finalize_download_body_result_target(
            downloaded_size,
            DownloadBodyFinalizationTarget(
                expected_size,
                temp_path,
                file_id,
                safe_filename,
                file_path,
            ),
        )

    def _finalize_download_body_result_target(
        self,
        downloaded_size: Optional[int],
        target: DownloadBodyFinalizationTarget,
    ) -> DownloadBodyResult:
        return self._finalize_download_body_result_decision_target(
            DownloadBodyFinalizationDecisionTarget(downloaded_size, target),
        )

    def _finalize_download_body_result_decision_target(
        self,
        target: DownloadBodyFinalizationDecisionTarget,
    ) -> DownloadBodyResult:
        downloaded_size = target.downloaded_size
        finalization_target = target.finalization_target
        if downloaded_size is None:
            return self._stopped_download_body_result()

        mismatch_detail = self._download_size_mismatch_detail_for_finalization(finalization_target)
        if mismatch_detail:
            return self._download_size_mismatch_result(mismatch_detail)

        return self._successful_download_body_result_target(finalization_target)

    def _stopped_download_body_result(self) -> DownloadBodyResult:
        return DownloadBodyResult(False, None)

    def _download_size_mismatch_result(
        self,
        mismatch_detail: DownloadFailureDetail,
    ) -> DownloadBodyResult:
        return DownloadBodyResult(None, mismatch_detail)

    def _download_size_mismatch_detail_for_finalization(
        self,
        finalization_target: DownloadBodyFinalizationTarget,
    ) -> Optional[DownloadFailureDetail]:
        return self._handle_download_size_mismatch_target(
            self._download_size_mismatch_target_for_finalization(finalization_target),
        )

    def _download_size_mismatch_target_for_finalization(
        self,
        finalization_target: DownloadBodyFinalizationTarget,
    ) -> DownloadSizeMismatchTarget:
        return DownloadSizeMismatchTarget(
            finalization_target.expected_size,
            finalization_target.temp_path,
        )

    def _successful_download_body_result_target(
        self,
        finalization_target: DownloadBodyFinalizationTarget,
    ) -> DownloadBodyResult:
        self._complete_successful_download_target(
            self._download_completion_target_for_finalization(finalization_target),
        )
        return self._successful_download_body_result()

    def _download_completion_target_for_finalization(
        self,
        finalization_target: DownloadBodyFinalizationTarget,
    ) -> DownloadCompletionTarget:
        return DownloadCompletionTarget(
            finalization_target.file_id,
            finalization_target.safe_filename,
            finalization_target.file_path,
            finalization_target.temp_path,
        )

    def _successful_download_body_result(self) -> DownloadBodyResult:
        return DownloadBodyResult(True, None)

    def _handle_download_size_mismatch(
        self,
        expected_size: int,
        temp_path: str,
    ) -> Optional[DownloadFailureDetail]:
        return self._handle_download_size_mismatch_target(
            DownloadSizeMismatchTarget(expected_size, temp_path),
        )

    def _handle_download_size_mismatch_target(
        self,
        target: DownloadSizeMismatchTarget,
    ) -> Optional[DownloadFailureDetail]:
        raw_mismatch_detail = self._raw_download_size_mismatch_detail_for_target(target)
        if not raw_mismatch_detail:
            return None

        return self._download_size_mismatch_failure_detail(target, raw_mismatch_detail)

    def _raw_download_size_mismatch_detail_for_target(
        self,
        target: DownloadSizeMismatchTarget,
    ) -> Optional[Tuple[str, str]]:
        final_size = os.path.getsize(target.temp_path)
        return download_size_mismatch_detail(target.expected_size, final_size)

    def _download_size_mismatch_failure_detail(
        self,
        target: DownloadSizeMismatchTarget,
        raw_mismatch_detail: Tuple[str, str],
    ) -> DownloadFailureDetail:
        mismatch_detail = self._download_failure_detail_from_raw_mismatch(raw_mismatch_detail)
        self._record_download_size_mismatch_failure(target, mismatch_detail)
        return mismatch_detail

    def _download_failure_detail_from_raw_mismatch(
        self,
        raw_mismatch_detail: Tuple[str, str],
    ) -> DownloadFailureDetail:
        return DownloadFailureDetail(*raw_mismatch_detail)

    def _record_download_size_mismatch_failure(
        self,
        target: DownloadSizeMismatchTarget,
        mismatch_detail: DownloadFailureDetail,
    ) -> None:
        self.log(f"   ⚠️ {mismatch_detail.error_message}")
        os.remove(target.temp_path)

    def _handle_download_stop(self, file_id: int, temp_path: str) -> None:
        self._handle_download_stop_target(DownloadStopTarget(file_id, temp_path))

    def _handle_download_stop_target(
        self,
        target: DownloadStopTarget,
    ) -> None:
        self._record_download_stop_target(target)

    def _record_download_stop_target(
        self,
        target: DownloadStopTarget,
    ) -> None:
        failure_detail = self._download_stop_failure_detail()
        self._log_download_stop(failure_detail)
        self._update_download_stop_status(target, failure_detail)
        self._cleanup_stopped_download(target)

    def _download_stop_failure_detail(self) -> DownloadFailureDetail:
        return DownloadFailureDetail("stopped", "下载过程中被停止")

    def _log_download_stop(self, failure_detail: DownloadFailureDetail) -> None:
        self.log(f"🛑 {failure_detail.error_message}")

    def _update_download_stop_status(
        self,
        target: DownloadStopTarget,
        failure_detail: DownloadFailureDetail,
    ) -> None:
        self.file_db.update_file_download_status(
            target.file_id,
            'failed',
            error_code=failure_detail.error_code,
            error_message=failure_detail.error_message,
        )

    def _cleanup_stopped_download(self, target: DownloadStopTarget) -> None:
        remove_partial_download(target.temp_path)

    def _download_interval_values(self) -> DownloadIntervalValues:
        download_interval = self.download_interval
        long_sleep_interval = self.long_sleep_interval
        if self._should_use_random_interval():
            if self._should_use_random_long_sleep_interval():
                long_sleep_interval = self._random_long_sleep_interval()
            elif self._has_random_download_interval_range():
                download_interval = self._random_download_interval()
        return DownloadIntervalValues(download_interval, long_sleep_interval)

    def _should_use_random_interval(self) -> bool:
        return bool(getattr(self, "use_random_interval", False))

    def _should_use_random_long_sleep_interval(self) -> bool:
        return (
            self.current_batch_count >= self.files_per_batch
            and self.long_sleep_interval_min is not None
            and self.long_sleep_interval_max is not None
        )

    def _has_random_download_interval_range(self) -> bool:
        return self.download_interval_min is not None and self.download_interval_max is not None

    def _random_long_sleep_interval(self) -> float:
        return random.uniform(
            self.long_sleep_interval_min,
            self.long_sleep_interval_max,
        )

    def _random_download_interval(self) -> float:
        return random.uniform(self.download_interval_min, self.download_interval_max)

    def _apply_download_interval_plan(
        self,
        interval_values: DownloadIntervalValues,
    ) -> None:
        self._apply_download_interval_plan_target(
            DownloadIntervalPlanTarget(
                self.current_batch_count,
                self.files_per_batch,
                interval_values,
            ),
        )

    def _apply_download_interval_plan_target(
        self,
        target: DownloadIntervalPlanTarget,
    ) -> None:
        delay, messages, should_reset_batch = self._download_interval_plan_for_target(target)
        self._apply_download_interval_delay(delay, messages, should_reset_batch)

    def _download_interval_plan_for_target(
        self,
        target: DownloadIntervalPlanTarget,
    ) -> Tuple[Optional[float], Tuple[str, ...], bool]:
        interval_values = target.interval_values
        return download_interval_plan(
            target.current_batch_count,
            target.files_per_batch,
            interval_values.download_interval,
            interval_values.long_sleep_interval,
        )

    def _apply_download_interval_delay(
        self,
        delay: Optional[float],
        messages: Tuple[str, ...],
        should_reset_batch: bool,
    ) -> None:
        if delay is None:
            return

        self.log(messages[0])
        time.sleep(delay)
        if should_reset_batch:
            self.current_batch_count = 0  # 重置批次计数
            self.log(messages[1])

    def _apply_download_intervals(self):
        """应用下载间隔控制"""
        self._apply_download_interval_plan_target(
            DownloadIntervalPlanTarget(
                self.current_batch_count,
                self.files_per_batch,
                self._download_interval_values(),
            ),
        )

    def _download_batch_file_item(
        self,
        file_info: Dict[str, Any],
        item_number: int,
        max_files: Optional[int],
        has_more_in_batch: bool,
        downloaded_in_batch: int,
        stats: Dict[str, int],
    ) -> int:
        return self._download_batch_file_item_target(
            BatchDownloadFileItemTarget(
                file_info,
                item_number,
                max_files,
                has_more_in_batch,
                downloaded_in_batch,
                stats,
            ),
        )

    def _download_batch_file_item_target(
        self,
        target: BatchDownloadFileItemTarget,
    ) -> int:
        self._log_batch_download_file_item(target)
        result = self.download_file(target.file_info)
        downloaded_in_batch = self._apply_batch_file_item_result(target, result)
        self._record_batch_file_item_attempt(target.stats)
        return downloaded_in_batch

    def _log_batch_download_file_item(self, target: BatchDownloadFileItemTarget) -> None:
        file_name = _batch_download_file_name(target.file_info)
        self.log(batch_download_item_message(target.item_number, target.max_files, file_name))

    def _apply_batch_file_item_result(
        self,
        target: BatchDownloadFileItemTarget,
        result: Any,
    ) -> int:
        return self._apply_batch_download_result_target(
            BatchDownloadResultTarget(
                result,
                target.has_more_in_batch,
                target.downloaded_in_batch,
                target.max_files,
                target.stats,
            ),
        )

    def _record_batch_file_item_attempt(self, stats: Dict[str, int]) -> None:
        stats['total_files'] += 1

    def _apply_batch_download_result(
        self,
        result: Any,
        has_more_in_batch: bool,
        downloaded_in_batch: int,
        max_files: Optional[int],
        stats: Dict[str, int],
    ) -> int:
        return self._apply_batch_download_result_target(
            BatchDownloadResultTarget(
                result,
                has_more_in_batch,
                downloaded_in_batch,
                max_files,
                stats,
            ),
        )

    def _apply_batch_download_result_target(
        self,
        target: BatchDownloadResultTarget,
    ) -> int:
        downloaded_in_batch = target.downloaded_in_batch
        result_status = _record_file_download_result(target.result, target.stats)
        if result_status == "skipped":
            self._log_batch_download_skipped()
        elif result_status == "downloaded":
            downloaded_in_batch = self._apply_successful_batch_download_result(target, downloaded_in_batch)

        return downloaded_in_batch

    def _log_batch_download_skipped(self) -> None:
        self.log(batch_download_skipped_message())

    def _apply_successful_batch_download_result(
        self,
        target: BatchDownloadResultTarget,
        downloaded_in_batch: int,
    ) -> int:
        downloaded_in_batch += 1
        self.check_long_delay()
        if self._should_delay_after_batch_download(target, downloaded_in_batch):
            self.download_delay()
        return downloaded_in_batch

    def _should_delay_after_batch_download(
        self,
        target: BatchDownloadResultTarget,
        downloaded_in_batch: int,
    ) -> bool:
        not_reached_limit = target.max_files is None or downloaded_in_batch < target.max_files
        return target.has_more_in_batch and not_reached_limit

    def _next_batch_download_index(
        self,
        next_index: Optional[str],
        downloaded_in_batch: int,
        max_files: Optional[int],
    ) -> Optional[str]:
        return self._next_batch_download_index_target(
            BatchDownloadNextIndexTarget(next_index, downloaded_in_batch, max_files),
        )

    def _next_batch_download_index_target(
        self,
        target: BatchDownloadNextIndexTarget,
    ) -> Optional[str]:
        next_page = self._batch_download_next_page_plan_for_target(target)
        return self._apply_batch_download_next_page(next_page)

    def _batch_download_next_page_plan_for_target(
        self,
        target: BatchDownloadNextIndexTarget,
    ) -> Dict[str, Any]:
        return batch_download_next_page_plan(
            target.next_index,
            target.downloaded_in_batch,
            target.max_files,
        )

    def _apply_batch_download_next_page(self, next_page: Dict[str, Any]) -> Optional[str]:
        if not next_page["should_continue"]:
            return None

        self.log(next_page["message"])
        time.sleep(next_page["delay"])  # 页面间短暂延迟
        return next_page["next_index"]

    def _download_batch_page_files(
        self,
        files: list[Dict[str, Any]],
        downloaded_in_batch: int,
        max_files: Optional[int],
        stats: Dict[str, int],
    ) -> int:
        return self._download_batch_page_files_target(
            BatchDownloadPageFilesTarget(files, downloaded_in_batch, max_files, stats),
        )

    def _download_batch_page_files_target(
        self,
        target: BatchDownloadPageFilesTarget,
    ) -> int:
        downloaded_in_batch = target.downloaded_in_batch

        for i, file_info in enumerate(target.files):
            # 检查是否需要停止
            if self.check_stop():
                self.log(batch_download_file_stop_message())
                break

            if target.max_files is not None and downloaded_in_batch >= target.max_files:
                break

            downloaded_in_batch = self._download_batch_file_item_target(
                self._batch_page_file_item_target(target, file_info, i, downloaded_in_batch),
            )

        return downloaded_in_batch

    def _batch_page_file_item_target(
        self,
        target: BatchDownloadPageFilesTarget,
        file_info: Dict[str, Any],
        file_index: int,
        downloaded_in_batch: int,
    ) -> BatchDownloadFileItemTarget:
        return BatchDownloadFileItemTarget(
            file_info,
            downloaded_in_batch + 1,
            target.max_files,
            (file_index + 1) < len(target.files),
            downloaded_in_batch,
            target.stats,
        )

    def _fetch_batch_download_page(self, current_index: Optional[str]) -> Optional[BatchDownloadPage]:
        return self._fetch_batch_download_page_target(BatchDownloadFetchTarget(current_index))

    def _fetch_batch_download_page_target(
        self,
        target: BatchDownloadFetchTarget,
    ) -> Optional[BatchDownloadPage]:
        data = self.fetch_file_list(count=20, index=target.current_index)
        if not data:
            self.log(batch_download_fetch_failed_message())
            return None

        files, next_index = file_list_response_page(data)

        if not files:
            self.log(batch_download_empty_page_message())
            return None

        self.log(batch_download_page_files_message(len(files)))
        return BatchDownloadPage(files, next_index)

    def _run_batch_download_page(
        self,
        step: BatchDownloadLoopStep,
        max_files: Optional[int],
        stats: Dict[str, int],
    ) -> Optional[BatchDownloadLoopStep]:
        return self._run_batch_download_page_target(
            BatchDownloadPageRunTarget(step, max_files, stats),
        )

    def _run_batch_download_page_target(
        self,
        target: BatchDownloadPageRunTarget,
    ) -> Optional[BatchDownloadLoopStep]:
        page = self._fetch_batch_download_page_target(
            BatchDownloadFetchTarget(target.step.next_index),
        )
        if page is None:
            return None

        downloaded_in_batch = self._download_batch_page_files_target(
            self._batch_page_files_target_for_page(target, page),
        )

        next_index = self._next_batch_download_index_target(
            BatchDownloadNextIndexTarget(
                page.next_index,
                downloaded_in_batch,
                target.max_files,
            ),
        )
        return BatchDownloadLoopStep(downloaded_in_batch, next_index)

    def _batch_page_files_target_for_page(
        self,
        target: BatchDownloadPageRunTarget,
        page: BatchDownloadPage,
    ) -> BatchDownloadPageFilesTarget:
        return BatchDownloadPageFilesTarget(
            page.files,
            target.step.downloaded_in_batch,
            target.max_files,
            target.stats,
        )

    def _run_batch_download_loop(
        self,
        stats: Dict[str, int],
        max_files: Optional[int],
        start_index: Optional[str],
    ) -> None:
        self._run_batch_download_loop_target(
            self._batch_download_loop_target(stats, max_files, start_index),
        )

    def _batch_download_loop_target(
        self,
        stats: Dict[str, int],
        max_files: Optional[int],
        start_index: Optional[str],
    ) -> BatchDownloadLoopTarget:
        return BatchDownloadLoopTarget(stats, max_files, start_index)

    def _run_batch_download_loop_target(
        self,
        target: BatchDownloadLoopTarget,
    ) -> None:
        step = self._initial_batch_download_loop_step(target)

        while self._should_continue_batch_download_loop(target, step):
            # 检查是否需要停止
            if self.check_stop():
                self.log(batch_download_loop_stop_message())
                break

            next_step = self._run_batch_download_page_target(
                self._batch_download_page_run_target(target, step),
            )
            if next_step is None:
                break

            step = next_step
            if step.next_index is None:
                break

    def _should_continue_batch_download_loop(
        self,
        target: BatchDownloadLoopTarget,
        step: BatchDownloadLoopStep,
    ) -> bool:
        return target.max_files is None or step.downloaded_in_batch < target.max_files

    def _initial_batch_download_loop_step(
        self,
        target: BatchDownloadLoopTarget,
    ) -> BatchDownloadLoopStep:
        return BatchDownloadLoopStep(0, target.start_index)

    def _batch_download_page_run_target(
        self,
        target: BatchDownloadLoopTarget,
        step: BatchDownloadLoopStep,
    ) -> BatchDownloadPageRunTarget:
        return BatchDownloadPageRunTarget(
            step,
            target.max_files,
            target.stats,
        )

    def download_files_batch(self, max_files: Optional[int] = None, start_index: Optional[str] = None) -> Dict[str, int]:
        return self._download_files_batch_target(
            self._batch_download_target(max_files, start_index),
        )

    def _batch_download_target(
        self,
        max_files: Optional[int],
        start_index: Optional[str],
    ) -> BatchDownloadTarget:
        return BatchDownloadTarget(max_files, start_index)

    def _download_files_batch_target(
        self,
        target: BatchDownloadTarget,
    ) -> Dict[str, int]:
        """批量下载文件"""
        self._log_batch_download_start(target.max_files)

        # 检查是否需要停止
        if self._is_initial_batch_download_stopped():
            return download_result_stats()

        stats = download_result_stats()
        self._run_batch_download_loop_target(
            self._batch_download_loop_target(stats, target.max_files, target.start_index),
        )

        self._log_batch_download_completion(stats)
        
        return stats

    def _is_initial_batch_download_stopped(self) -> bool:
        if not self.check_stop():
            return False

        self.log(batch_download_initial_stop_message())
        return True

    def _log_batch_download_start(self, max_files: Optional[int]) -> None:
        for message in batch_download_start_messages(max_files):
            self.log(message)

    def _log_batch_download_completion(self, stats: Dict[str, int]) -> None:
        for message in batch_download_completion_messages(stats):
            self.log(message)

    def _print_file_list_page(
        self,
        files: list[Dict[str, Any]],
        next_index: Any,
    ) -> None:
        print(f"\n📋 文件列表 ({len(files)} 个文件):")
        print("="*80)

        for i, file_info in enumerate(files, 1):
            for line in file_list_item_display_lines(i, file_info):
                print(line)

        print(file_list_next_index_message(next_index))

    def show_file_list(self, count: int = 20, index: Optional[str] = None) -> Optional[str]:
        """显示文件列表"""
        return self._show_file_list_target(ShowFileListTarget(count, index))

    def _show_file_list_target(self, target: ShowFileListTarget) -> Optional[str]:
        data = self.fetch_file_list(count=target.count, index=target.index)
        if not data:
            return None
        
        files, next_index = file_list_response_page(data)
        self._print_file_list_page(files, next_index)

        return next_index

    def _import_file_collection_page(
        self,
        data: Dict[str, Any],
        file_count: int,
        page_count: int,
        stats: Dict[str, int],
    ) -> bool:
        try:
            page_stats = self.file_db.import_file_response(data)

            add_file_collection_page_stats(stats, file_count, page_stats)

            for message in file_collection_page_import_messages(page_stats):
                print(message)

        except Exception as e:
            print(file_collection_storage_failed_message(page_count, e))
            return False

        print(file_collection_page_stored_message(page_count))
        return True

    def _next_file_collection_index(self, next_index: Any) -> Optional[Any]:
        next_page = file_collection_next_page_plan(next_index)
        if not next_page["has_next"]:
            return None

        time.sleep(random.uniform(next_page["delay_min"], next_page["delay_max"]))
        return next_page["next_index"]

    def _fetch_file_collection_page(
        self,
        page_count: int,
        current_index: Optional[Any],
    ) -> Optional[FileCollectionPage]:
        data = self.fetch_file_list(count=20, index=current_index)
        if not data:
            for message in file_collection_fetch_failed_messages(page_count):
                print(message)
            return None

        files, next_index = file_list_response_page(data)
        if not files:
            print(file_collection_empty_page_message())
            return None

        print(file_collection_page_files_message(len(files)))
        return FileCollectionPage(data, files, next_index)

    def _run_file_collection_page(
        self,
        page_count: int,
        current_index: Optional[Any],
        stats: Dict[str, int],
    ) -> Optional[Any]:
        page = self._fetch_file_collection_page(page_count, current_index)
        if page is None:
            return None

        if not self._import_file_collection_page(
            page.data,
            len(page.files),
            page_count,
            stats,
        ):
            return None

        return self._next_file_collection_index(page.next_index)

    def _run_file_collection_loop(self, stats: Dict[str, int]) -> int:
        current_index = None
        page_count = 0

        try:
            while True:
                page_count += 1
                print(file_collection_page_message(page_count))

                current_index = self._run_file_collection_page(
                    page_count,
                    current_index,
                    stats,
                )
                if current_index is None:
                    break

        except KeyboardInterrupt:
            print(file_collection_interrupted_message())
        except Exception as e:
            print(file_collection_exception_message(e))

        return page_count

    def _create_file_collection_log(self) -> Optional[Any]:
        insert_query, insert_params = file_collection_log_insert_query(
            datetime.datetime.now().isoformat()
        )
        self.file_db.cursor.execute(insert_query, insert_params)
        row = self.file_db.cursor.fetchone()
        log_id = _file_collection_log_id(row)
        self.file_db.conn.commit()
        return log_id

    def _update_file_collection_log(
        self,
        stats: Dict[str, int],
        log_id: Optional[Any],
    ) -> None:
        update_query, update_params = file_collection_log_update_query(
            datetime.datetime.now().isoformat(),
            stats,
            log_id,
        )
        self.file_db.cursor.execute(update_query, update_params)
        self.file_db.conn.commit()

    def collect_all_files_to_database(self) -> Dict[str, int]:
        """收集所有文件信息到数据库"""
        return self._collect_all_files_to_database_target(FileCollectionTarget())

    def _collect_all_files_to_database_target(
        self,
        target: FileCollectionTarget,
    ) -> Dict[str, int]:
        print(file_collection_start_message())

        # 创建收集记录
        log_id = self._create_file_collection_log()

        stats = file_collection_stats()
        page_count = self._run_file_collection_loop(stats)

        # 更新收集记录
        self._update_file_collection_log(stats, log_id)
        
        for message in file_collection_completion_messages(stats, page_count):
            print(message)
        
        return stats
    
    def get_database_time_range(self) -> Dict[str, Any]:
        """获取完整数据库中文件的时间范围信息"""
        return self._get_database_time_range_target(DatabaseTimeRangeTarget())

    def _get_database_time_range_target(
        self,
        target: DatabaseTimeRangeTarget,
    ) -> Dict[str, Any]:
        # 使用新数据库检查是否有数据
        stats = self.file_db.get_database_stats()
        total_files = stats.get('files', 0)
        
        if total_files == 0:
            return database_time_range_result(total_files, None)
        
        # 获取时间范围
        query, params = database_time_range_query(_query_group_id(self.group_id))
        self.file_db.cursor.execute(query, params)
        
        result = self.file_db.cursor.fetchone()
        
        return database_time_range_result(total_files, result)

    def _load_time_collection_latest_file_time(
        self,
        enable_time_dedupe: bool,
        initial_files: int,
    ) -> Optional[Any]:
        if not enable_time_dedupe or initial_files <= 0:
            return None

        query, params = latest_file_create_time_query(_query_group_id(self.group_id))
        self.file_db.cursor.execute(query, params)
        result = self.file_db.cursor.fetchone()
        db_latest_time = _latest_file_create_time(result)
        if db_latest_time:
            self.log(time_collection_latest_file_time_message(db_latest_time))
            return db_latest_time

        return None

    def _load_time_collection_database_state(
        self,
        enable_time_dedupe: bool,
    ) -> TimeCollectionDatabaseState:
        initial_stats = self.file_db.get_database_stats()
        initial_files = initial_stats.get('files', 0)
        self.log(time_collection_database_status_message(initial_files))
        db_latest_time = self._load_time_collection_latest_file_time(
            enable_time_dedupe,
            initial_files,
        )
        return TimeCollectionDatabaseState(initial_files, db_latest_time)

    def _time_collection_dedupe_result(
        self,
        should_stop_before_insert: bool = False,
        should_stop_after_insert: bool = False,
    ) -> Dict[str, bool]:
        return {
            "should_stop_before_insert": should_stop_before_insert,
            "should_stop_after_insert": should_stop_after_insert,
        }

    def _apply_time_collection_dedupe_plan(
        self,
        data: Dict[str, Any],
        files: list[Dict[str, Any]],
        enable_time_dedupe: bool,
        db_latest_time: Optional[Any],
    ) -> Dict[str, bool]:
        if not enable_time_dedupe or not db_latest_time:
            return self._time_collection_dedupe_result()

        dedupe_plan = time_dedupe_page_plan(files, db_latest_time)
        for message in time_dedupe_page_messages(dedupe_plan):
            self.log(message)

        if dedupe_plan["should_stop_before_insert"]:
            return self._time_collection_dedupe_result(
                should_stop_before_insert=True,
            )

        if dedupe_plan["should_filter_before_insert"]:
            data['resp_data']['files'] = dedupe_plan["newer_files"]
            return self._time_collection_dedupe_result(
                should_stop_after_insert=dedupe_plan["should_stop_after_insert"],
            )

        return self._time_collection_dedupe_result()

    def _import_time_collection_page(
        self,
        data: Dict[str, Any],
        page_count: int,
        should_stop_after_insert: bool,
        total_imported_stats: Dict[str, int],
    ) -> bool:
        try:
            page_stats = self.file_db.import_file_response(data)
            add_import_stats(total_imported_stats, page_stats)

            for message in time_collection_page_import_messages(
                page_count,
                page_stats,
                should_stop_after_insert,
            ):
                self.log(message)
            return True

        except Exception as e:
            self.log(time_collection_storage_failed_message(page_count, e))
            return False

    def _crossed_time_collection_stop_before(
        self,
        files: list[Dict[str, Any]],
        stop_before_time: Optional[datetime.datetime],
    ) -> bool:
        if not stop_before_time:
            return False

        crossed_stop_before, oldest_page_time = page_crosses_stop_before(files, stop_before_time)
        if crossed_stop_before and oldest_page_time:
            self.log(time_collection_stop_before_boundary_message(oldest_page_time, stop_before_time))
            return True

        return False

    def _next_time_collection_index(self, next_index: Optional[Any]) -> Optional[Any]:
        next_page = time_collection_next_page_plan(next_index)
        self.log(next_page["message"])
        if not next_page["has_next"]:
            return None

        time.sleep(random.uniform(2, 5))
        return next_page["next_index"]

    def _fetch_time_collection_page(
        self,
        page_count: int,
        current_index: Optional[Any],
        sort: str,
    ) -> Optional[TimeCollectionPage]:
        data = self.fetch_file_list(count=20, index=current_index, sort=sort)
        if not data:
            for message in time_collection_fetch_failed_messages(page_count):
                self.log(message)
            return None

        files, next_index = file_list_response_page(data)
        if not files:
            self.log(time_collection_empty_page_message())
            return None

        self.log(time_collection_page_files_message(len(files)))
        page_oldest, page_newest = summarize_page_time_range(files)
        time_range_message = time_collection_page_time_range_message(page_oldest, page_newest)
        if time_range_message:
            self.log(time_range_message)

        return TimeCollectionPage(data, files, next_index)

    def _next_time_collection_page_after_import(
        self,
        page: TimeCollectionPage,
        should_stop_after_insert: bool,
        stop_before_time: Optional[datetime.datetime],
    ) -> Optional[Any]:
        if should_stop_after_insert:
            return None

        if self._crossed_time_collection_stop_before(page.files, stop_before_time):
            return None

        return self._next_time_collection_index(page.next_index)

    def _collect_time_collection_page(
        self,
        page_count: int,
        current_index: Optional[Any],
        context: TimeCollectionLoopContext,
    ) -> Optional[Any]:
        self.log(time_collection_page_message(page_count))

        page = self._fetch_time_collection_page(page_count, current_index, context.sort)
        if page is None:
            return None

        import_result = self._dedupe_and_import_time_collection_page(
            page,
            page_count,
            context.enable_time_dedupe,
            context.db_latest_time,
            context.total_imported_stats,
        )
        if import_result is None:
            return None

        return self._next_time_collection_page_after_import(
            page,
            import_result.should_stop_after_insert,
            context.stop_before_time,
        )

    def _dedupe_and_import_time_collection_page(
        self,
        page: TimeCollectionPage,
        page_count: int,
        enable_time_dedupe: bool,
        db_latest_time: Optional[Any],
        total_imported_stats: Dict[str, int],
    ) -> Optional[TimeCollectionPageImportResult]:
        dedupe_result = self._apply_time_collection_dedupe_plan(
            page.data,
            page.files,
            enable_time_dedupe,
            db_latest_time,
        )
        if dedupe_result["should_stop_before_insert"]:
            return None
        should_stop_after_insert = dedupe_result["should_stop_after_insert"]

        if not self._import_time_collection_page(
            page.data,
            page_count,
            should_stop_after_insert,
            total_imported_stats,
        ):
            return None

        return TimeCollectionPageImportResult(should_stop_after_insert)

    def _run_time_collection_loop(
        self,
        start_time: Optional[str],
        context: TimeCollectionLoopContext,
    ) -> int:
        current_index = start_time
        page_count = 0

        try:
            while True:
                if self.check_stop():
                    self.log(time_collection_loop_stop_message())
                    break

                page_count += 1
                current_index = self._collect_time_collection_page(
                    page_count,
                    current_index,
                    context,
                )
                if current_index is None:
                    break

        except KeyboardInterrupt:
            self.log(time_collection_interrupted_message())
        except Exception as e:
            self.log(time_collection_exception_message(e))

        return page_count

    def _finalize_time_collection_result(
        self,
        initial_files: int,
        total_imported_stats: Dict[str, int],
        page_count: int,
    ) -> Dict[str, int]:
        final_stats = self.file_db.get_database_stats()
        summary = time_collection_final_summary(
            final_stats,
            initial_files,
            total_imported_stats,
            page_count,
        )

        for message in time_collection_summary_messages(summary, page_count):
            self.log(message)

        return summary["result"]

    def _collect_incremental_from_oldest_time(self, oldest_time: Any) -> Dict[str, int]:
        self.log(incremental_collection_target_message())

        try:
            start_index = incremental_start_index(oldest_time)
            self.log(incremental_collection_start_index_message(start_index))

            return self.collect_files_by_time(start_time=start_index)

        except Exception as e:
            for message in incremental_collection_timestamp_failure_messages(e):
                self.log(message)
            return self.collect_files_by_time()

    def _collect_incremental_from_time_info(self, time_info: Dict[str, Any]) -> Dict[str, int]:
        if not time_info['has_data']:
            self.log(incremental_collection_empty_database_message())
            return self.collect_files_by_time()

        oldest_time = time_info['oldest_time']
        # Preserve historical key validation before emitting status logs.
        _ = (time_info['newest_time'], time_info['total_files'])

        for message in incremental_collection_status_messages(time_info):
            self.log(message)

        if not oldest_time:
            self.log(incremental_collection_missing_time_message())
            return self.collect_files_by_time()

        return self._collect_incremental_from_oldest_time(oldest_time)

    def _collect_files_for_normalized_date_range(
        self,
        normalized_start: Optional[str],
        normalized_end: Optional[str],
        stop_before_dt: Optional[datetime.datetime],
    ) -> Dict[str, int]:
        for message in date_range_collection_start_messages(normalized_start, normalized_end):
            self.log(message)
        return self.collect_files_by_time(
            sort="by_create_time",
            start_time=None,
            stop_before_time=stop_before_dt,
        )

    def _initialize_time_collection_mode(
        self,
        sort: str,
        start_time: Optional[str],
        stop_before_time: Optional[datetime.datetime],
        force_refresh: bool,
    ) -> bool:
        for message in time_collection_start_messages(sort, start_time, stop_before_time):
            self.log(message)

        mode = time_collection_mode(sort, force_refresh, stop_before_time)
        if mode["mode_message"]:
            self.log(mode["mode_message"])
        return mode["enable_time_dedupe"]

    def _should_stop_time_collection_initially(self) -> bool:
        if self.check_stop():
            self.log(time_collection_initial_stop_message())
            return True

        return False

    def _run_time_collection_after_initial_stop(
        self,
        start_time: Optional[str],
        sort: str,
        enable_time_dedupe: bool,
        stop_before_time: Optional[datetime.datetime],
    ) -> Dict[str, int]:
        database_state = self._load_time_collection_database_state(
            enable_time_dedupe,
        )

        total_imported_stats = empty_import_stats()
        loop_context = TimeCollectionLoopContext(
            sort,
            enable_time_dedupe,
            database_state.db_latest_time,
            total_imported_stats,
            stop_before_time,
        )
        page_count = self._run_time_collection_loop(
            start_time,
            loop_context,
        )

        return self._finalize_time_collection_result(
            database_state.initial_files,
            total_imported_stats,
            page_count,
        )

    def _collect_files_by_time_target(
        self,
        target: TimeCollectionTarget,
    ) -> Dict[str, int]:
        enable_time_dedupe = self._initialize_time_collection_mode(
            target.sort,
            target.start_time,
            target.stop_before_time,
            target.force_refresh,
        )

        # 检查是否需要停止
        if self._should_stop_time_collection_initially():
            return {'total_files': 0, 'new_files': 0}

        # 使用完整数据库的统计信息
        return self._run_time_collection_after_initial_stop(
            target.start_time,
            target.sort,
            enable_time_dedupe,
            target.stop_before_time,
        )

    def collect_files_by_time(
        self,
        sort: str = "by_create_time",
        start_time: Optional[str] = None,
        stop_before_time: Optional[datetime.datetime] = None,
        **kwargs,
    ) -> Dict[str, int]:
        """按时间顺序收集文件列表到数据库（使用完整的数据库结构）"""
        return self._collect_files_by_time_target(
            TimeCollectionTarget(
                sort,
                start_time,
                stop_before_time,
                kwargs.get('force_refresh', False),
            )
        )
    
    def collect_incremental_files(self) -> Dict[str, int]:
        """增量收集：从数据库最老时间戳开始继续收集"""
        return self._collect_incremental_files_target(IncrementalCollectionTarget())

    def _collect_incremental_files_target(
        self,
        target: IncrementalCollectionTarget,
    ) -> Dict[str, int]:
        self.log(incremental_collection_start_message())

        # 检查是否需要停止
        if self._should_stop_time_collection_initially():
            return {'total_files': 0, 'new_files': 0}

        # 获取数据库时间范围
        time_info = self.get_database_time_range()

        return self._collect_incremental_from_time_info(time_info)
    
    def _collect_files_for_date_range_target(
        self,
        target: DateRangeCollectionTarget,
    ) -> Dict[str, int]:
        normalized_start, normalized_end, stop_before_dt = normalize_date_range(
            start_date=target.start_date,
            end_date=target.end_date,
            last_days=target.last_days,
        )
        return self._collect_files_for_normalized_date_range(
            normalized_start,
            normalized_end,
            stop_before_dt,
        )

    def collect_files_for_date_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        last_days: Optional[int] = None,
    ) -> Dict[str, int]:
        return self._collect_files_for_date_range_target(
            DateRangeCollectionTarget(
                start_date,
                end_date,
                last_days,
            )
        )

    def _download_database_file_row(
        self,
        file_row: DatabaseDownloadRow,
        position: int,
        total_files: int,
        stats: Dict[str, int],
    ) -> None:
        self.log(f"【{position}/{total_files}】{file_row.file_name}")
        self.log(
            f"   📊 文件ID: {file_row.file_id}, 大小: {file_row.file_size/1024:.1f}KB, "
            f"下载次数: {file_row.download_count}"
        )

        file_info = database_download_file_info(
            file_row.file_id,
            file_row.file_name,
            file_row.file_size,
            file_row.download_count,
        )

        result = self.download_file(file_info)
        self._apply_database_download_result(result, position, total_files, stats)

    def _apply_database_download_result(
        self,
        result: Any,
        position: int,
        total_files: int,
        stats: Dict[str, int],
    ) -> None:
        result_status = _record_file_download_result(result, stats)
        if result_status == "skipped":
            self.log(f"   ⚠️ 文件已跳过")
        elif result_status == "downloaded":
            self.check_long_delay()
            if position < total_files:
                self.download_delay()
        else:
            self.log(f"   ❌ 下载失败")

    def _fetch_database_download_rows(
        self,
        query_plan: Dict[str, Any],
    ) -> list[DatabaseDownloadRow]:
        self.file_db.cursor.execute(query_plan["query"], query_plan["params"])
        return [_database_download_row(row) for row in self.file_db.cursor.fetchall()]

    def _download_database_file_rows(
        self,
        files_to_download: list[DatabaseDownloadRow],
        stats: Dict[str, int],
    ) -> None:
        total_files = len(files_to_download)
        for i, file_row in enumerate(files_to_download, 1):
            # 检查是否需要停止
            if self.check_stop():
                self.log("🛑 下载任务被停止")
                break

            try:
                self._download_database_file_row(file_row, i, total_files, stats)
            except KeyboardInterrupt:
                self.log(f"⏹️ 用户中断下载")
                break
            except Exception as e:
                self.log(f"   ❌ 处理文件异常: {e}")
                stats['failed'] += 1
                continue

    def _should_stop_database_download_initially(self) -> bool:
        if self.check_stop():
            self.log("🛑 任务被停止")
            return True

        return False

    def _prepare_database_download_query_plan(
        self,
        max_files: Optional[int],
        status_filter: str,
        sort_by: str,
        start_date: Optional[str],
        end_date: Optional[str],
        last_days: Optional[int],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        last_days = database_download_effective_last_days(last_days, kwargs.get('recent_days'))

        query_plan = database_download_query_plan(
            _query_group_id(self.group_id),
            max_files=max_files,
            status_filter=status_filter,
            sort_by=sort_by,
            start_date=start_date,
            end_date=end_date,
            last_days=last_days,
            legacy_order_by=kwargs.get('order_by'),
        )
        normalized_start = query_plan["normalized_start"]
        normalized_end = query_plan["normalized_end"]
        sort_by = query_plan["sort_by"]

        for message in database_download_filter_messages(normalized_start, normalized_end, last_days, sort_by):
            self.log(message)

        return query_plan

    def _log_database_download_rows_summary(
        self,
        files_to_download: list[DatabaseDownloadRow],
        sort_by: str,
    ) -> None:
        if not files_to_download:
            self.log(f"📭 数据库中没有符合条件的文件可下载")
            return

        self.log(f"📋 找到 {len(files_to_download)} 个待下载文件")
        time_range_message = database_download_time_range_message(files_to_download, sort_by)
        if time_range_message:
            self.log(time_range_message)

    def _log_database_download_completion(self, stats: Dict[str, int]) -> None:
        for message in database_download_completion_messages(stats):
            self.log(message)

    def _log_database_download_start(self, max_files: Optional[int], status_filter: str) -> None:
        for message in database_download_start_messages(max_files, status_filter):
            self.log(message)

    def _run_database_download_rows(
        self,
        files_to_download: list[DatabaseDownloadRow],
    ) -> Dict[str, int]:
        return self._run_database_download_rows_target(
            DatabaseDownloadRowsTarget(files_to_download),
        )

    def _run_database_download_rows_target(
        self,
        target: DatabaseDownloadRowsTarget,
    ) -> Dict[str, int]:
        stats = download_result_stats(len(target.files_to_download))

        self._download_database_file_rows(target.files_to_download, stats)
        self._log_database_download_completion(stats)

        return stats

    def _run_database_download_after_initial_stop(
        self,
        query_plan: Dict[str, Any],
        sort_by: str,
    ) -> Dict[str, int]:
        return self._run_database_download_after_initial_stop_target(
            DatabaseDownloadAfterInitialStopTarget(query_plan, sort_by),
        )

    def _run_database_download_after_initial_stop_target(
        self,
        target: DatabaseDownloadAfterInitialStopTarget,
    ) -> Dict[str, int]:
        files_to_download = self._fetch_database_download_rows(target.query_plan)

        self._log_database_download_rows_summary(files_to_download, target.sort_by)
        if not files_to_download:
            return download_result_stats()

        return self._run_database_download_rows(files_to_download)

    def download_files_from_database(
        self,
        max_files: Optional[int] = None,
        status_filter: str = 'pending',
        sort_by: str = 'download_count',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        last_days: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, int]:
        """从完整数据库下载文件（使用file_id字段）"""
        return self._download_files_from_database_target(
            DatabaseDownloadTarget(
                max_files,
                status_filter,
                sort_by,
                start_date,
                end_date,
                last_days,
                kwargs,
            ),
        )

    def _download_files_from_database_target(
        self,
        target: DatabaseDownloadTarget,
    ) -> Dict[str, int]:
        self._log_database_download_start(target.max_files, target.status_filter)

        query_plan = self._prepare_database_download_query_plan(
            target.max_files,
            target.status_filter,
            target.sort_by,
            target.start_date,
            target.end_date,
            target.last_days,
            target.kwargs,
        )
        sort_by = query_plan["sort_by"]

        # 检查是否需要停止
        if self._should_stop_database_download_initially():
            return download_result_stats()

        return self._run_database_download_after_initial_stop(query_plan, sort_by)

    def _print_database_core_stats(self, stats: Dict[str, Any]) -> None:
        total_files = stats.get('files', 0)
        total_topics = stats.get('topics', 0)
        total_users = stats.get('users', 0)
        total_groups = stats.get('groups', 0)

        print(f"📈 核心数据:")
        print(f"   📄 文件数量: {total_files:,}")
        print(f"   💬 话题数量: {total_topics:,}")
        print(f"   👥 用户数量: {total_users:,}")
        print(f"   🏠 群组数量: {total_groups:,}")

    def _fetch_database_total_size(self) -> Any:
        query, params = database_stats_total_size_query(_query_group_id(self.group_id))
        self.file_db.cursor.execute(query, params)
        result = self.file_db.cursor.fetchone()
        return _database_stats_total_size(result)

    def _fetch_database_time_range(self) -> Optional[DatabaseStatsTimeRange]:
        query, params = database_stats_time_range_query(_query_group_id(self.group_id))
        self.file_db.cursor.execute(query, params)
        time_result = self.file_db.cursor.fetchone()
        return _database_stats_time_range(time_result)

    def _fetch_database_api_response_stats(self) -> Any:
        self.file_db.cursor.execute(database_stats_api_response_query())
        return self.file_db.cursor.fetchall()

    def _print_database_total_size(self) -> None:
        total_size = self._fetch_database_total_size()

        if total_size > 0:
            print(f"💾 总文件大小: {total_size/1024/1024:.2f} MB")

    def _print_database_table_stats(self, stats: Dict[str, Any]) -> None:
        print(f"\n📋 详细表统计:")
        for table_name, count in stats.items():
            if count > 0:
                emoji = database_stats_table_emoji(table_name)
                print(f"   {emoji} {table_name}: {count:,}")

    def _print_database_time_range(self) -> None:
        time_range = self._fetch_database_time_range()
        if time_range:
            print(f"\n⏰ 文件时间范围:")
            print(f"   最早文件: {time_range.min_time}")
            print(f"   最新文件: {time_range.max_time}")
            print(f"   有时间信息的文件: {time_range.time_count:,}")

    def _print_database_api_response_stats(self) -> None:
        api_stats = self._fetch_database_api_response_stats()

        if api_stats:
            print(f"\n📡 API响应统计:")
            for succeeded, count in api_stats:
                status = "成功" if succeeded else "失败"
                emoji = "✅" if succeeded else "❌"
                print(f"   {emoji} {status}: {count:,}")

    def show_database_stats(self):
        """显示完整数据库统计信息"""
        return self._show_database_stats_entry_target(ShowDatabaseStatsEntryTarget())

    def _show_database_stats_entry_target(
        self,
        target: ShowDatabaseStatsEntryTarget,
    ) -> None:
        print(f"\n📊 完整数据库统计信息:")
        print("="*60)
        print(f"📁 PostgreSQL schema: {CORE_SCHEMA}")

        # 使用新数据库的统计方法
        stats = self.file_db.get_database_stats()

        self._show_database_stats_target(ShowDatabaseStatsTarget(stats))

        print("="*60)

    def _show_database_stats_target(self, target: ShowDatabaseStatsTarget) -> None:
        # 主要数据统计
        self._print_database_core_stats(target.stats)

        # 文件大小统计
        self._print_database_total_size()

        # 详细表统计
        self._print_database_table_stats(target.stats)

        # 文件创建时间范围
        self._print_database_time_range()

        # API响应统计
        self._print_database_api_response_stats()
    
    def _print_download_settings(self) -> None:
        for line in download_settings_display_lines(
            self.download_interval_min,
            self.download_interval_max,
            self.long_delay_interval,
            self.long_delay_min,
            self.long_delay_max,
            self.download_dir,
        ):
            print(line)

    def _apply_adjusted_settings(self, new_interval: int, new_dir: str) -> None:
        self.long_delay_interval = max(new_interval, 1)

        if new_dir != self.download_dir:
            self.download_dir = new_dir
            os.makedirs(new_dir, exist_ok=True)
            print(f"📁 下载目录已更新: {os.path.abspath(new_dir)}")

        print(f"✅ 设置已更新")

    def adjust_settings(self):
        """调整下载设置"""
        return self._adjust_settings_target(AdjustSettingsTarget())

    def _adjust_settings_target(
        self,
        target: AdjustSettingsTarget,
    ) -> None:
        self._print_download_settings()

        try:
            new_interval = int(input(f"长休眠间隔 (当前每{self.long_delay_interval}个文件): ") or self.long_delay_interval)
            new_dir = input(f"下载目录 (当前: {self.download_dir}): ").strip() or self.download_dir
            self._apply_adjusted_settings(new_interval, new_dir)
            
        except ValueError:
            print("❌ 输入无效，保持原设置")
    
    def close(self):
        """关闭资源"""
        return self._close_target(CloseTarget())

    def _close_target(
        self,
        target: CloseTarget,
    ) -> None:
        if hasattr(self, 'file_db') and self.file_db:
            self.file_db.close()
            print("🔒 文件数据库连接已关闭")
