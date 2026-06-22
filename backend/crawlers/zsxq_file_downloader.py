#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识星球文件下载器
Author: AI Assistant
Date: 2024-12-19
Description: 专门用于下载知识星球文件的工具
"""

import datetime
import os
import random
import time
from typing import Dict, Optional, Any, Tuple

import requests

from backend.core.console_output import safe_console_print as print
from backend.crawlers.api_json_response_runner import (
    parse_api_json_response_target as run_parse_api_json_response_target,
)
from backend.crawlers.file_download_url import (
    DownloadUrlAttemptTarget,
    DownloadUrlResponseDecision,
    DownloadUrlRetryLoopStepDecision,
    DownloadUrlRetryLoopTarget,
    download_url_api_failure_data_decision as run_download_url_api_failure_data_decision,
    download_url_api_failure_decision as run_download_url_api_failure_decision,
    download_url_data_decision_target as run_download_url_data_decision_target,
    download_url_http_failure_decision as run_download_url_http_failure_decision,
    download_url_json_parse_decision as run_download_url_json_parse_decision,
    download_url_retry_loop_step_decision,
    download_url_status_decision as run_download_url_status_decision,
    download_url_success_data_decision as run_download_url_success_data_decision,
    handle_download_url_ok_response_target as run_handle_download_url_ok_response_target,
    handle_download_url_response_target as run_handle_download_url_response_target,
    run_download_url_attempt,
    run_download_url_retry_loop,
)
from backend.crawlers.file_download_transfer import (
    DownloadAttemptResult,
    DownloadAttemptTarget,
    DownloadBodyResponseTarget,
    DownloadBodyWriteTarget,
    DownloadCompletionTarget,
    DownloadExceptionTarget,
    DownloadFailureDetail,
    DownloadFileTarget,
    DownloadHttpFailureTarget,
    DownloadRetryDecision,
    DownloadRetryLoopAttemptTarget,
    DownloadRetryLoopFailureTarget,
    DownloadResponseTarget,
    DownloadSizeMismatchTarget,
    download_attempt_missing_url_result,
    download_attempt_result_for_response,
    run_download_retry_loop_attempt,
    run_download_retry_loop,
    write_download_response_body_stream,
)
from backend.crawlers.file_download_interval_runner import (
    apply_download_interval_delay as run_apply_download_interval_delay,
    apply_download_interval_plan as run_apply_download_interval_plan,
    apply_download_interval_plan_target as run_apply_download_interval_plan_target,
    apply_download_intervals as run_apply_download_intervals,
    download_interval_plan_for_target as run_download_interval_plan_for_target,
    download_interval_values as run_download_interval_values,
    has_random_download_interval_range as run_has_random_download_interval_range,
    random_download_interval as run_random_download_interval,
    random_long_sleep_interval as run_random_long_sleep_interval,
    should_use_random_interval as run_should_use_random_interval,
    should_use_random_long_sleep_interval as run_should_use_random_long_sleep_interval,
)
from backend.crawlers.file_download_outcome_runner import (
    cleanup_stopped_download as run_cleanup_stopped_download,
    complete_successful_download_target as run_complete_successful_download_target,
    download_exception_detail_for_target as run_download_exception_detail,
    download_failure_detail_from_raw_mismatch as run_download_failure_detail_from_raw_mismatch,
    download_final_failure_detail_for_target as run_download_final_failure_detail,
    download_http_failure_detail_for_target as run_download_http_failure_detail,
    download_size_mismatch_failure_detail as run_download_size_mismatch_failure_detail,
    download_stop_failure_detail as run_download_stop_failure_detail,
    download_url_unavailable_failure_detail as run_download_url_unavailable_failure_detail,
    handle_download_size_mismatch_target as run_handle_download_size_mismatch_target,
    handle_download_stop_target as run_handle_download_stop_target,
    increment_successful_download_counters as run_increment_successful_download_counters,
    log_download_exception as run_log_download_exception,
    log_download_http_failure as run_log_download_http_failure,
    log_download_stop as run_log_download_stop,
    log_successful_download_target as run_log_successful_download_target,
    mark_download_failed_after_retries_target as run_mark_download_failed_after_retries_target,
    mark_download_url_unavailable_target as run_mark_download_url_unavailable_target,
    mark_successful_download_completed as run_mark_successful_download_completed,
    raw_download_size_mismatch_detail_for_target as run_raw_download_size_mismatch_detail_for_target,
    record_download_exception_target as run_record_download_exception_target,
    record_download_http_failure_target as run_record_download_http_failure_target,
    record_download_size_mismatch_failure as run_record_download_size_mismatch_failure,
    record_download_stop_target as run_record_download_stop_target,
    remove_partial_download_after_exception as run_remove_partial_download_after_exception,
    replace_successful_download_file as run_replace_successful_download_file,
    update_download_final_failure_status as run_update_download_final_failure_status,
    update_download_stop_status as run_update_download_stop_status,
    update_download_url_unavailable_status as run_update_download_url_unavailable_status,
)
from backend.crawlers.file_runtime_state_runner import (
    check_long_delay_target as run_check_long_delay_target,
    check_stop_target as run_check_stop_target,
    download_delay_target as run_download_delay_target,
    is_stopped_target as run_is_stopped_target,
    set_stop_flag_target as run_set_stop_flag_target,
    smart_delay_target as run_smart_delay_target,
)
from backend.crawlers.file_risk_event_runner import (
    header_profile_label as run_risk_event_header_profile_label,
    prepare_risk_event_log_path as run_prepare_risk_event_log_path,
    record_risk_event as run_record_risk_event,
    risk_event_row_for_runtime as run_risk_event_row,
    user_agent_label as run_risk_event_user_agent_label,
    write_risk_event_row as run_write_risk_event_row,
)
from backend.crawlers.file_database_download_runner import (
    DatabaseDownloadTarget,
    run_database_file_download,
)
from backend.crawlers.file_database_time_range_runner import (
    get_database_time_range as run_get_database_time_range,
)
from backend.crawlers.file_database_stats_runner import (
    database_stats_time_range as _database_stats_time_range,
    database_stats_total_size as _database_stats_total_size,
    fetch_database_api_response_stats as run_fetch_database_api_response_stats,
    fetch_database_time_range as run_fetch_database_time_range,
    fetch_database_total_size as run_fetch_database_total_size,
    print_database_api_response_stats as run_print_database_api_response_stats,
    print_database_core_stats as run_print_database_core_stats,
    print_database_table_stats as run_print_database_table_stats,
    print_database_time_range as run_print_database_time_range,
    print_database_total_size as run_print_database_total_size,
    show_database_stats_entry as run_show_database_stats_entry,
    show_database_stats_target as run_show_database_stats_target,
)
from backend.crawlers.file_collection_runner import (
    collect_all_files_to_database as run_collect_all_files_to_database,
    create_file_collection_log as run_create_file_collection_log,
    fetch_file_collection_page as run_fetch_file_collection_page,
    file_collection_log_id as _file_collection_log_id,
    import_file_collection_page as run_import_file_collection_page,
    next_file_collection_index as run_next_file_collection_index,
    run_file_collection_loop,
    run_file_collection_page,
    update_file_collection_log as run_update_file_collection_log,
)
from backend.crawlers.file_incremental_collection_runner import (
    collect_files_for_date_range as run_collect_files_for_date_range,
    collect_files_for_normalized_date_range as run_collect_files_for_normalized_date_range,
    collect_incremental_files as run_collect_incremental_files,
    collect_incremental_from_oldest_time as run_collect_incremental_from_oldest_time,
    collect_incremental_from_time_info as run_collect_incremental_from_time_info,
)
from backend.crawlers.file_list_display_runner import (
    print_file_list_page as run_print_file_list_page,
    show_file_list as run_show_file_list,
)
from backend.crawlers.file_stealth_headers_runner import (
    apply_dynamic_stealth_headers as run_apply_dynamic_stealth_headers,
    apply_optional_stealth_headers as run_apply_optional_stealth_headers,
    get_stealth_headers as run_get_stealth_headers,
    select_stealth_header_values as run_select_stealth_header_values,
)
from backend.crawlers.file_batch_download_runner import (
    apply_batch_download_next_page as run_apply_batch_download_next_page,
    apply_batch_download_result as run_apply_batch_download_result,
    apply_batch_download_result_target as run_apply_batch_download_result_target,
    apply_batch_file_item_result as run_apply_batch_file_item_result,
    apply_successful_batch_download_result as run_apply_successful_batch_download_result,
    advance_batch_download_loop_step as run_advance_batch_download_loop_step,
    batch_download_loop_step_from_page as run_batch_download_loop_step_from_page,
    batch_download_next_page_plan_for_target as run_batch_download_next_page_plan_for_target,
    batch_download_page_from_response as run_batch_download_page_from_response,
    batch_page_file_item_target as run_batch_page_file_item_target,
    batch_page_files_target_for_page as run_batch_page_files_target_for_page,
    download_batch_file_item_target as run_download_batch_file_item_target,
    download_batch_page_file_for_target as run_download_batch_page_file_for_target,
    download_batch_page_files_for_run_target as run_download_batch_page_files_for_run_target,
    download_batch_page_files_target as run_download_batch_page_files_target,
    fetch_batch_download_page_data as run_fetch_batch_download_page_data,
    fetch_batch_download_page_for_run_target as run_fetch_batch_download_page_for_run_target,
    fetch_batch_download_page_target as run_fetch_batch_download_page_target,
    handle_batch_download_page_fetch_failure as run_handle_batch_download_page_fetch_failure,
    handle_empty_batch_download_page as run_handle_empty_batch_download_page,
    has_reached_batch_page_file_download_limit as run_has_reached_batch_page_file_download_limit,
    initial_batch_download_loop_step as run_initial_batch_download_loop_step,
    is_batch_download_loop_stopped as run_is_batch_download_loop_stopped,
    is_batch_page_file_download_stopped as run_is_batch_page_file_download_stopped,
    is_initial_batch_download_stopped as run_is_initial_batch_download_stopped,
    is_missing_batch_download_loop_step as run_is_missing_batch_download_loop_step,
    is_terminal_batch_download_loop_step as run_is_terminal_batch_download_loop_step,
    log_batch_download_completion as run_log_batch_download_completion,
    log_batch_download_file_item as run_log_batch_download_file_item,
    log_batch_download_skipped as run_log_batch_download_skipped,
    log_batch_download_start as run_log_batch_download_start,
    next_batch_download_index_for_run_target as run_next_batch_download_index_for_run_target,
    next_batch_download_index_target as run_next_batch_download_index_target,
    record_batch_file_item_attempt as run_record_batch_file_item_attempt,
    run_batch_download_loop_iteration,
    run_batch_download_loop_target,
    run_batch_download_page_target,
    run_batch_file_download,
    run_next_batch_download_loop_step,
    should_continue_batch_download_loop as run_should_continue_batch_download_loop,
    should_delay_after_batch_download as run_should_delay_after_batch_download,
)
from backend.crawlers.file_list_request_runner import (
    fetch_file_list_target as run_fetch_file_list_target,
    file_list_request_attempt_decision as run_file_list_request_attempt_decision,
    file_list_request_attempt_headers as run_file_list_request_attempt_headers,
    file_list_request_exception_decision as run_file_list_request_exception_decision,
    file_list_request_target_for_attempt as run_file_list_request_target_for_attempt,
    handle_file_list_request_attempt_exception as run_handle_file_list_request_attempt_exception,
    handle_file_list_request_attempt_response as run_handle_file_list_request_attempt_response,
    request_file_list_attempt_response as run_request_file_list_attempt_response,
    request_file_list_response_target as run_request_file_list_response_target,
    run_file_list_request_attempt,
    run_file_list_request_loop,
    start_file_list_request as run_start_file_list_request,
)
from backend.crawlers.file_list_response_runner import (
    file_list_api_failure_decision as run_file_list_api_failure_decision,
    file_list_http_failure_decision as run_file_list_http_failure_decision,
    file_list_ok_data_decision_target as run_file_list_ok_data_decision_target,
    file_list_response_status_decision_target as run_file_list_response_status_decision_target,
    handle_file_list_api_failure_response as run_handle_file_list_api_failure_response,
    handle_file_list_api_failure_response_target as run_handle_file_list_api_failure_response_target,
    handle_file_list_http_failure_response as run_handle_file_list_http_failure_response,
    handle_file_list_http_failure_response_target as run_handle_file_list_http_failure_response_target,
    handle_file_list_ok_response as run_handle_file_list_ok_response,
    handle_file_list_ok_response_target as run_handle_file_list_ok_response_target,
    handle_file_list_response as run_handle_file_list_response,
    handle_file_list_response_target as run_handle_file_list_response_target,
    handle_file_list_success_response as run_handle_file_list_success_response,
    handle_file_list_success_response_target as run_handle_file_list_success_response_target,
)
from backend.crawlers.file_time_collection_runner import (
    TimeCollectionDatabaseState,
    TimeCollectionLoopContext,
    TimeCollectionPage,
    TimeCollectionPageImportResult,
    TimeCollectionTarget,
    _latest_file_create_time,
    apply_time_collection_dedupe_plan as run_time_collection_dedupe_plan,
    collect_time_collection_page as run_time_collection_page,
    crossed_time_collection_stop_before as run_crossed_time_collection_stop_before,
    dedupe_and_import_time_collection_page as run_dedupe_and_import_time_collection_page,
    fetch_time_collection_page as run_fetch_time_collection_page,
    finalize_time_collection_result as run_finalize_time_collection_result,
    import_time_collection_page as run_import_time_collection_page,
    initialize_time_collection_mode as run_initialize_time_collection_mode,
    load_time_collection_database_state as run_load_time_collection_database_state,
    load_time_collection_latest_file_time as run_load_time_collection_latest_file_time,
    next_time_collection_index as run_next_time_collection_index,
    next_time_collection_page_after_import as run_next_time_collection_page_after_import,
    prepare_time_collection_loop_context as run_prepare_time_collection_loop_context,
    run_file_time_collection,
    run_time_collection_after_initial_stop,
    run_time_collection_loop,
    should_stop_time_collection_initially as run_should_stop_time_collection_initially,
    should_stop_time_collection_loop as run_should_stop_time_collection_loop,
    time_collection_dedupe_result as run_time_collection_dedupe_result,
    time_collection_page_import_result as run_time_collection_page_import_result,
)
from backend.crawlers.zsxq_file_downloader_helpers import (
    API_FAILURE_PERMISSION_DENIED_1030,
    api_retry_user_agent_message,
    api_retry_wait_message,
    add_import_stats,
    clean_cookie_result,
    download_settings_display_lines,
    download_file_data,
    download_progress_message,
    download_query_group_id,
    download_result_stats,
    download_retry_wait,
    download_target_path,
    download_url_api_failure_plan,
    download_url_from_response_data,
    download_url_success_plan,
    empty_import_stats,
    existing_file_matches,
    http_failure_plan,
    latest_file_create_time_query,
    page_crosses_stop_before,
    remove_partial_download,
    response_filename_override,
    request_exception_plan,
    retry_exhausted_message,
    risk_event_header_user_agent,
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
from backend.crawlers.zsxq_file_downloader_targets import (
    AdjustSettingsTarget,
    ApiJsonParseResult,
    BatchDownloadFetchTarget,
    BatchDownloadFileItemTarget,
    BatchDownloadLoopStep,
    BatchDownloadLoopTarget,
    BatchDownloadNextIndexTarget,
    BatchDownloadPage,
    BatchDownloadPageFilesTarget,
    BatchDownloadPageRunTarget,
    BatchDownloadResultTarget,
    BatchDownloadTarget,
    CheckLongDelayTarget,
    CheckStopTarget,
    CleanCookieTarget,
    CloseTarget,
    DatabaseStatsTimeRange,
    DatabaseTimeRangeTarget,
    DateRangeCollectionTarget,
    DownloadAttemptResponseTarget,
    DownloadDelayTarget,
    DownloadFilePreparationData,
    DownloadFileResponseRequestTarget,
    DownloadFilenameOverride,
    DownloadFinalFailureTarget,
    DownloadIntervalPlanTarget,
    DownloadIntervalValues,
    DownloadRetryWaitTarget,
    DownloadStopTarget,
    DownloadUrlApiFailureEventTarget,
    DownloadUrlApiFailureResponseTarget,
    DownloadUrlDataDecisionTarget,
    DownloadUrlEntryTarget,
    DownloadUrlHttpFailureResponseTarget,
    DownloadUrlOkResponseTarget,
    DownloadUrlRequestExceptionTarget,
    DownloadUrlResponseTarget,
    DownloadUrlSuccessEventTarget,
    DownloadUrlSuccessResponseTarget,
    DownloadUrlUnavailableTarget,
    ExistingDownloadMatch,
    ExistingDownloadTarget,
    FetchFileListTarget,
    FileCollectionPage,
    FileCollectionTarget,
    FileListApiFailureResponseTarget,
    FileListHttpFailureResponseTarget,
    FileListOkDataTarget,
    FileListOkResponseTarget,
    FileListRequestAttemptTarget,
    FileListRequestContext,
    FileListRequestExceptionTarget,
    FileListRequestTarget,
    FileListResponseDecision,
    FileListResponseStatusTarget,
    FileListResponseTarget,
    FileListSuccessResponseTarget,
    HttpFailureOutputTarget,
    IncrementalCollectionTarget,
    IsStoppedTarget,
    ParseApiJsonResponseTarget,
    PrepareRetryApiRequestTarget,
    RequestExceptionOutputTarget,
    ResponseFilenameOverrideTarget,
    SetStopFlagTarget,
    ShowDatabaseStatsEntryTarget,
    ShowDatabaseStatsTarget,
    ShowFileListTarget,
    SmartDelayTarget,
    StealthHeaderSelection,
)
from backend.storage.postgres_core_schema import CORE_SCHEMA
from backend.storage.zsxq_file_database import ZSXQFileDatabase


DOWNLOAD_URL_MAX_RETRIES = 10
DOWNLOAD_FILE_MAX_RETRIES = 3
DOWNLOAD_FILE_RESPONSE_TIMEOUT_SECONDS = 300


def _query_group_id(group_id: str) -> Any:
    return download_query_group_id(group_id)


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
        run_set_stop_flag_target(self, target)

    def is_stopped(self):
        """检查是否被停止（综合检查本地标志和外部函数）"""
        return self._is_stopped_target(IsStoppedTarget())

    def _is_stopped_target(
        self,
        target: IsStoppedTarget,
    ) -> bool:
        return run_is_stopped_target(self, target)

    def check_stop(self):
        """检查是否需要停止（兼容旧方法名）"""
        return self._check_stop_target(CheckStopTarget())

    def _check_stop_target(
        self,
        target: CheckStopTarget,
    ) -> Any:
        return run_check_stop_target(self, target)

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
        return run_select_stealth_header_values()

    def _apply_optional_stealth_headers(self, headers: Dict[str, str]) -> None:
        run_apply_optional_stealth_headers(headers)

    def _apply_dynamic_stealth_headers(self, headers: Dict[str, str]) -> None:
        run_apply_dynamic_stealth_headers(headers)

    def get_stealth_headers(self) -> Dict[str, str]:
        """获取反检测请求头（每次调用随机化）"""
        return run_get_stealth_headers(self)

    def smart_delay(self):
        """智能延迟"""
        return self._smart_delay_target(SmartDelayTarget())

    def _smart_delay_target(
        self,
        target: SmartDelayTarget,
    ) -> None:
        run_smart_delay_target(self, target)

    @staticmethod
    def _user_agent_label(user_agent: str) -> str:
        return run_risk_event_user_agent_label(user_agent)

    @staticmethod
    def _header_profile_label(headers: Dict[str, str]) -> str:
        return run_risk_event_header_profile_label(headers)

    def _prepare_risk_event_log_path(self) -> Optional[Any]:
        return run_prepare_risk_event_log_path(self)

    def _write_risk_event_row(self, path: Any, row: Dict[str, Any]) -> None:
        run_write_risk_event_row(path, row)

    def _risk_event_row(
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
    ) -> Dict[str, Any]:
        return run_risk_event_row(
            self,
            file_id=file_id,
            phase=phase,
            attempt=attempt,
            headers=headers,
            http_status=http_status,
            api_code=api_code,
            api_message=api_message,
            status=status,
        )

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
        run_record_risk_event(
            self,
            file_id=file_id,
            phase=phase,
            attempt=attempt,
            headers=headers,
            http_status=http_status,
            api_code=api_code,
            api_message=api_message,
            status=status,
        )

    def download_delay(self):
        """下载间隔延迟"""
        return self._download_delay_target(DownloadDelayTarget())

    def _download_delay_target(
        self,
        target: DownloadDelayTarget,
    ) -> None:
        run_download_delay_target(self, target)

    def check_long_delay(self):
        """检查是否需要长休眠"""
        return self._check_long_delay_target(CheckLongDelayTarget())

    def _check_long_delay_target(
        self,
        target: CheckLongDelayTarget,
    ) -> None:
        run_check_long_delay_target(self, target)

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
        return run_parse_api_json_response_target(target)

    def _handle_file_list_success_response(self, data: Dict[str, Any], attempt: int) -> Dict[str, Any]:
        return run_handle_file_list_success_response(self, data, attempt)

    def _handle_file_list_success_response_target(
        self,
        target: FileListSuccessResponseTarget,
    ) -> Dict[str, Any]:
        return run_handle_file_list_success_response_target(target)

    def _handle_file_list_api_failure_response(
        self,
        data: Dict[str, Any],
        attempt: int,
        max_retries: int,
    ) -> str:
        return run_handle_file_list_api_failure_response(self, data, attempt, max_retries)

    def _handle_file_list_api_failure_response_target(
        self,
        target: FileListApiFailureResponseTarget,
    ) -> str:
        return run_handle_file_list_api_failure_response_target(target)

    def _handle_file_list_http_failure_response(
        self,
        response: requests.Response,
        attempt: int,
        max_retries: int,
    ) -> str:
        return run_handle_file_list_http_failure_response(self, response, attempt, max_retries)

    def _handle_file_list_http_failure_response_target(
        self,
        target: FileListHttpFailureResponseTarget,
    ) -> str:
        return run_handle_file_list_http_failure_response_target(target)

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
        return run_file_list_api_failure_decision(failure_class)

    def _file_list_http_failure_decision(self, failure_class: str) -> FileListResponseDecision:
        return run_file_list_http_failure_decision(failure_class)

    def _handle_file_list_ok_response(
        self,
        response: requests.Response,
        attempt: int,
        max_retries: int,
    ) -> FileListResponseDecision:
        return run_handle_file_list_ok_response(self, response, attempt, max_retries)

    def _handle_file_list_ok_response_target(
        self,
        target: FileListOkResponseTarget,
    ) -> FileListResponseDecision:
        return run_handle_file_list_ok_response_target(self, target)

    def _file_list_ok_data_decision_target(
        self,
        target: FileListOkDataTarget,
    ) -> FileListResponseDecision:
        return run_file_list_ok_data_decision_target(target)

    def _handle_file_list_response(
        self,
        response: requests.Response,
        attempt: int,
        max_retries: int,
    ) -> FileListResponseDecision:
        return run_handle_file_list_response(self, response, attempt, max_retries)

    def _handle_file_list_response_target(
        self,
        target: FileListResponseTarget,
    ) -> FileListResponseDecision:
        return run_handle_file_list_response_target(self, target)

    def _file_list_response_status_decision_target(
        self,
        target: FileListResponseStatusTarget,
    ) -> FileListResponseDecision:
        return run_file_list_response_status_decision_target(self, target)

    def fetch_file_list(self, count: int = 20, index: Optional[str] = None, sort: str = "by_download_count") -> Optional[Dict[str, Any]]:
        """获取文件列表（带重试机制）"""
        return self._fetch_file_list_target(FetchFileListTarget(count, index, sort))

    def _fetch_file_list_target(self, target: FetchFileListTarget) -> Optional[Dict[str, Any]]:
        return run_fetch_file_list_target(self, target)

    def _run_file_list_request_loop(
        self,
        request_context: FileListRequestContext,
    ) -> Optional[Dict[str, Any]]:
        return run_file_list_request_loop(self, request_context)

    def _start_file_list_request(self, target: FetchFileListTarget) -> FileListRequestContext:
        return run_start_file_list_request(self, target)

    def _request_file_list_response_target(
        self,
        target: FileListRequestTarget,
    ) -> Any:
        return run_request_file_list_response_target(self, target)

    def _run_file_list_request_attempt(
        self,
        target: FileListRequestAttemptTarget,
    ) -> FileListResponseDecision:
        return run_file_list_request_attempt(self, target)

    def _file_list_request_attempt_headers(
        self,
        target: FileListRequestAttemptTarget,
    ) -> Dict[str, str]:
        return run_file_list_request_attempt_headers(self, target)

    def _file_list_request_attempt_decision(
        self,
        target: FileListRequestAttemptTarget,
        headers: Dict[str, str],
    ) -> FileListResponseDecision:
        return run_file_list_request_attempt_decision(self, target, headers)

    def _request_file_list_attempt_response(
        self,
        target: FileListRequestAttemptTarget,
        headers: Dict[str, str],
    ) -> Any:
        return run_request_file_list_attempt_response(self, target, headers)

    def _file_list_request_target_for_attempt(
        self,
        target: FileListRequestAttemptTarget,
        headers: Dict[str, str],
    ) -> FileListRequestTarget:
        return run_file_list_request_target_for_attempt(target, headers)

    def _handle_file_list_request_attempt_response(
        self,
        target: FileListRequestAttemptTarget,
        response: Any,
    ) -> FileListResponseDecision:
        return run_handle_file_list_request_attempt_response(self, target, response)

    def _handle_file_list_request_attempt_exception(
        self,
        target: FileListRequestAttemptTarget,
        exc: Exception,
    ) -> FileListResponseDecision:
        return run_handle_file_list_request_attempt_exception(self, target, exc)

    def _file_list_request_exception_decision(
        self,
        should_retry: bool,
    ) -> FileListResponseDecision:
        return run_file_list_request_exception_decision(should_retry)

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
        return run_download_url_http_failure_decision(failure_class)

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
        return run_download_url_api_failure_decision(failure_class)

    def _handle_download_url_ok_response_target(
        self,
        target: DownloadUrlOkResponseTarget,
    ) -> DownloadUrlResponseDecision:
        return run_handle_download_url_ok_response_target(self, target)

    def _download_url_json_parse_decision(
        self,
        target: DownloadUrlOkResponseTarget,
        json_parse: ApiJsonParseResult,
    ) -> DownloadUrlResponseDecision:
        return run_download_url_json_parse_decision(self, target, json_parse)

    def _download_url_data_decision_target(
        self,
        target: DownloadUrlDataDecisionTarget,
    ) -> DownloadUrlResponseDecision:
        return run_download_url_data_decision_target(self, target)

    def _download_url_success_data_decision(
        self,
        target: DownloadUrlDataDecisionTarget,
    ) -> DownloadUrlResponseDecision:
        return run_download_url_success_data_decision(self, target)

    def _download_url_api_failure_data_decision(
        self,
        target: DownloadUrlDataDecisionTarget,
    ) -> DownloadUrlResponseDecision:
        return run_download_url_api_failure_data_decision(self, target)

    def _handle_download_url_response_target(
        self,
        target: DownloadUrlResponseTarget,
    ) -> DownloadUrlResponseDecision:
        return run_handle_download_url_response_target(self, target)

    def _download_url_status_decision(
        self,
        target: DownloadUrlResponseTarget,
    ) -> DownloadUrlResponseDecision:
        return run_download_url_status_decision(self, target)

    def _start_download_url_request(self, file_id: int) -> str:
        url = f"{self.base_url}/v2/files/{file_id}/download_url"
        self.last_download_url_error = None
        self.log(f"   🔗 获取下载链接: ID={file_id}")
        self.log(f"   🌐 请求URL: {url}")
        return url

    def _run_download_url_attempt_target(
        self,
        target: DownloadUrlAttemptTarget,
    ) -> DownloadUrlResponseDecision:
        return run_download_url_attempt(self, target)

    def _download_url_retry_loop_step_decision(
        self,
        decision: DownloadUrlResponseDecision,
    ) -> DownloadUrlRetryLoopStepDecision:
        return download_url_retry_loop_step_decision(decision)

    def _run_download_url_retry_loop_target(
        self,
        target: DownloadUrlRetryLoopTarget,
    ) -> Optional[str]:
        return run_download_url_retry_loop(
            target,
            run_attempt=self._run_download_url_attempt_target,
            finish_exhausted=self._finish_download_url_retry_loop_exhausted_target,
        )

    def _finish_download_url_retry_loop_exhausted_target(
        self,
        target: DownloadUrlRetryLoopTarget,
    ) -> None:
        print(retry_exhausted_message(target.max_retries))

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
        prepared_file = self._prepare_download_file_target(file_info)
        if not prepared_file:
            return False
        return self._download_prepared_file(prepared_file)

    def _download_prepared_file(self, prepared_file: DownloadFileTarget) -> bool:
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
        return run_download_retry_loop(
            prepared_file,
            download_retries=DOWNLOAD_FILE_MAX_RETRIES,
            run_attempt=self._run_download_retry_loop_attempt_target,
            finish_failure=self._finish_download_retry_loop_failure_target,
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

    def _run_download_retry_loop_attempt_target(
        self,
        target: DownloadRetryLoopAttemptTarget,
    ) -> DownloadRetryDecision:
        return run_download_retry_loop_attempt(
            target,
            run_download_attempt=self._run_download_attempt_target,
            record_exception=self._record_download_exception_target,
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
            return download_attempt_missing_url_result(file_target)

        return self._run_download_attempt_response_target(
            DownloadAttemptResponseTarget(download_url, file_target),
        )

    def _run_download_attempt_response_target(
        self,
        target: DownloadAttemptResponseTarget,
    ) -> DownloadAttemptResult:
        response = self._request_download_response_target(
            DownloadFileResponseRequestTarget(target.download_url),
        )
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

    def _mark_download_url_unavailable_target(
        self,
        target: DownloadUrlUnavailableTarget,
    ) -> None:
        run_mark_download_url_unavailable_target(self, target)

    def _download_url_unavailable_failure_detail(
        self,
        target: DownloadUrlUnavailableTarget,
    ) -> DownloadFailureDetail:
        return run_download_url_unavailable_failure_detail(target)

    def _update_download_url_unavailable_status(
        self,
        file_id: int,
        failure_detail: DownloadFailureDetail,
    ) -> None:
        run_update_download_url_unavailable_status(self, file_id, failure_detail)

    def _mark_download_failed_after_retries_target(
        self,
        target: DownloadFinalFailureTarget,
    ) -> None:
        run_mark_download_failed_after_retries_target(self, target)

    def _download_final_failure_detail(
        self,
        target: DownloadFinalFailureTarget,
    ) -> DownloadFailureDetail:
        return run_download_final_failure_detail(target)

    def _update_download_final_failure_status(
        self,
        file_id: int,
        failure_detail: DownloadFailureDetail,
    ) -> None:
        run_update_download_final_failure_status(self, file_id, failure_detail)

    def _complete_successful_download_target(
        self,
        target: DownloadCompletionTarget,
    ) -> None:
        run_complete_successful_download_target(self, target)

    def _replace_successful_download_file(
        self,
        target: DownloadCompletionTarget,
    ) -> None:
        run_replace_successful_download_file(target)

    def _log_successful_download_target(
        self,
        target: DownloadCompletionTarget,
    ) -> None:
        run_log_successful_download_target(self, target)

    def _mark_successful_download_completed(
        self,
        target: DownloadCompletionTarget,
    ) -> None:
        run_mark_successful_download_completed(self, target)

    def _increment_successful_download_counters(self) -> None:
        run_increment_successful_download_counters(self)

    def _write_download_response_body_result_target(
        self,
        target: DownloadBodyResponseTarget,
    ) -> Optional[int]:
        return write_download_response_body_stream(
            target,
            log_progress=self._log_download_body_progress,
            stop_requested=self._stop_download_body_if_requested,
        )

    def _write_download_body_response_stream(
        self,
        response: Any,
        body_target: DownloadBodyWriteTarget,
    ) -> Optional[int]:
        return write_download_response_body_stream(
            DownloadBodyResponseTarget(response, body_target),
            log_progress=self._log_download_body_progress,
            stop_requested=self._stop_download_body_if_requested,
        )

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

    def _record_download_http_failure_target(
        self,
        target: DownloadHttpFailureTarget,
    ) -> DownloadFailureDetail:
        return run_record_download_http_failure_target(self, target)

    def _download_http_failure_detail(
        self,
        target: DownloadHttpFailureTarget,
    ) -> Tuple[str, str]:
        return run_download_http_failure_detail(target)

    def _log_download_http_failure(self, error_message: str) -> None:
        run_log_download_http_failure(self, error_message)

    def _record_download_exception_target(
        self,
        target: DownloadExceptionTarget,
    ) -> DownloadFailureDetail:
        return run_record_download_exception_target(self, target)

    def _download_exception_detail(
        self,
        target: DownloadExceptionTarget,
    ) -> Tuple[str, str]:
        return run_download_exception_detail(target)

    def _log_download_exception(self, exc: Exception) -> None:
        run_log_download_exception(self, exc)

    def _remove_partial_download_after_exception(self, file_path: str) -> None:
        run_remove_partial_download_after_exception(self, file_path)

    def _wait_before_download_retry_target(
        self,
        target: DownloadRetryWaitTarget,
    ) -> None:
        retry_delay, retry_message = download_retry_wait(target.attempt, target.download_retries)
        self.log(retry_message)
        time.sleep(retry_delay)

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

    def _handle_download_response_result_target(
        self,
        target: DownloadResponseTarget,
    ) -> DownloadAttemptResult:
        return download_attempt_result_for_response(
            target,
            resolve_response_target=self._download_target_for_response_target,
            remove_partial_download=remove_partial_download,
            write_response_body=self._write_download_response_body_result_target,
            find_mismatch_detail=self._handle_download_size_mismatch_target,
            complete_successful_download=self._complete_successful_download_target,
            record_http_failure=self._record_download_http_failure_target,
            record_exception=self._record_download_exception_target,
        )

    def _handle_download_size_mismatch_target(
        self,
        target: DownloadSizeMismatchTarget,
    ) -> Optional[DownloadFailureDetail]:
        return run_handle_download_size_mismatch_target(self, target)

    def _raw_download_size_mismatch_detail_for_target(
        self,
        target: DownloadSizeMismatchTarget,
    ) -> Optional[Tuple[str, str]]:
        return run_raw_download_size_mismatch_detail_for_target(target)

    def _download_size_mismatch_failure_detail(
        self,
        target: DownloadSizeMismatchTarget,
        raw_mismatch_detail: Tuple[str, str],
    ) -> DownloadFailureDetail:
        return run_download_size_mismatch_failure_detail(self, target, raw_mismatch_detail)

    def _download_failure_detail_from_raw_mismatch(
        self,
        raw_mismatch_detail: Tuple[str, str],
    ) -> DownloadFailureDetail:
        return run_download_failure_detail_from_raw_mismatch(raw_mismatch_detail)

    def _record_download_size_mismatch_failure(
        self,
        target: DownloadSizeMismatchTarget,
        mismatch_detail: DownloadFailureDetail,
    ) -> None:
        run_record_download_size_mismatch_failure(self, target, mismatch_detail)

    def _handle_download_stop_target(
        self,
        target: DownloadStopTarget,
    ) -> None:
        run_handle_download_stop_target(self, target)

    def _record_download_stop_target(
        self,
        target: DownloadStopTarget,
    ) -> None:
        run_record_download_stop_target(self, target)

    def _download_stop_failure_detail(self) -> DownloadFailureDetail:
        return run_download_stop_failure_detail()

    def _log_download_stop(self, failure_detail: DownloadFailureDetail) -> None:
        run_log_download_stop(self, failure_detail)

    def _update_download_stop_status(
        self,
        target: DownloadStopTarget,
        failure_detail: DownloadFailureDetail,
    ) -> None:
        run_update_download_stop_status(self, target, failure_detail)

    def _cleanup_stopped_download(self, target: DownloadStopTarget) -> None:
        run_cleanup_stopped_download(target)

    def _download_interval_values(self) -> DownloadIntervalValues:
        return run_download_interval_values(self)

    def _should_use_random_interval(self) -> bool:
        return run_should_use_random_interval(self)

    def _should_use_random_long_sleep_interval(self) -> bool:
        return run_should_use_random_long_sleep_interval(self)

    def _has_random_download_interval_range(self) -> bool:
        return run_has_random_download_interval_range(self)

    def _random_long_sleep_interval(self) -> float:
        return run_random_long_sleep_interval(self)

    def _random_download_interval(self) -> float:
        return run_random_download_interval(self)

    def _apply_download_interval_plan(
        self,
        interval_values: DownloadIntervalValues,
    ) -> None:
        run_apply_download_interval_plan(self, interval_values)

    def _apply_download_interval_plan_target(
        self,
        target: DownloadIntervalPlanTarget,
    ) -> None:
        run_apply_download_interval_plan_target(self, target)

    def _download_interval_plan_for_target(
        self,
        target: DownloadIntervalPlanTarget,
    ) -> Tuple[Optional[float], Tuple[str, ...], bool]:
        return run_download_interval_plan_for_target(target)

    def _apply_download_interval_delay(
        self,
        delay: Optional[float],
        messages: Tuple[str, ...],
        should_reset_batch: bool,
    ) -> None:
        run_apply_download_interval_delay(self, delay, messages, should_reset_batch)

    def _apply_download_intervals(self):
        """应用下载间隔控制"""
        run_apply_download_intervals(self)

    def _download_batch_file_item_target(
        self,
        target: BatchDownloadFileItemTarget,
    ) -> int:
        return run_download_batch_file_item_target(self, target)

    def _log_batch_download_file_item(self, target: BatchDownloadFileItemTarget) -> None:
        run_log_batch_download_file_item(self, target)

    def _apply_batch_file_item_result(
        self,
        target: BatchDownloadFileItemTarget,
        result: Any,
    ) -> int:
        return run_apply_batch_file_item_result(self, target, result)

    def _record_batch_file_item_attempt(self, stats: Dict[str, int]) -> None:
        run_record_batch_file_item_attempt(stats)

    def _apply_batch_download_result(
        self,
        result: Any,
        has_more_in_batch: bool,
        downloaded_in_batch: int,
        max_files: Optional[int],
        stats: Dict[str, int],
    ) -> int:
        return run_apply_batch_download_result(
            self,
            result,
            has_more_in_batch,
            downloaded_in_batch,
            max_files,
            stats,
        )

    def _apply_batch_download_result_target(
        self,
        target: BatchDownloadResultTarget,
    ) -> int:
        return run_apply_batch_download_result_target(self, target)

    def _log_batch_download_skipped(self) -> None:
        run_log_batch_download_skipped(self)

    def _apply_successful_batch_download_result(
        self,
        target: BatchDownloadResultTarget,
        downloaded_in_batch: int,
    ) -> int:
        return run_apply_successful_batch_download_result(self, target, downloaded_in_batch)

    def _should_delay_after_batch_download(
        self,
        target: BatchDownloadResultTarget,
        downloaded_in_batch: int,
    ) -> bool:
        return run_should_delay_after_batch_download(target, downloaded_in_batch)

    def _next_batch_download_index_target(
        self,
        target: BatchDownloadNextIndexTarget,
    ) -> Optional[str]:
        return run_next_batch_download_index_target(self, target)

    def _batch_download_next_page_plan_for_target(
        self,
        target: BatchDownloadNextIndexTarget,
    ) -> Dict[str, Any]:
        return run_batch_download_next_page_plan_for_target(target)

    def _apply_batch_download_next_page(self, next_page: Dict[str, Any]) -> Optional[str]:
        return run_apply_batch_download_next_page(self, next_page)

    def _download_batch_page_files_target(
        self,
        target: BatchDownloadPageFilesTarget,
    ) -> int:
        return run_download_batch_page_files_target(self, target)

    def _is_batch_page_file_download_stopped(self) -> bool:
        return run_is_batch_page_file_download_stopped(self)

    def _has_reached_batch_page_file_download_limit(
        self,
        target: BatchDownloadPageFilesTarget,
        downloaded_in_batch: int,
    ) -> bool:
        return run_has_reached_batch_page_file_download_limit(target, downloaded_in_batch)

    def _download_batch_page_file_for_target(
        self,
        target: BatchDownloadPageFilesTarget,
        file_info: Dict[str, Any],
        file_index: int,
        downloaded_in_batch: int,
    ) -> int:
        return run_download_batch_page_file_for_target(
            self,
            target,
            file_info,
            file_index,
            downloaded_in_batch,
        )

    def _batch_page_file_item_target(
        self,
        target: BatchDownloadPageFilesTarget,
        file_info: Dict[str, Any],
        file_index: int,
        downloaded_in_batch: int,
    ) -> BatchDownloadFileItemTarget:
        return run_batch_page_file_item_target(target, file_info, file_index, downloaded_in_batch)

    def _fetch_batch_download_page_target(
        self,
        target: BatchDownloadFetchTarget,
    ) -> Optional[BatchDownloadPage]:
        return run_fetch_batch_download_page_target(self, target)

    def _fetch_batch_download_page_data(
        self,
        target: BatchDownloadFetchTarget,
    ) -> Optional[Dict[str, Any]]:
        return run_fetch_batch_download_page_data(self, target)

    def _handle_batch_download_page_fetch_failure(self) -> Optional[BatchDownloadPage]:
        return run_handle_batch_download_page_fetch_failure(self)

    def _batch_download_page_from_response(
        self,
        data: Dict[str, Any],
    ) -> Optional[BatchDownloadPage]:
        return run_batch_download_page_from_response(self, data)

    def _handle_empty_batch_download_page(self) -> Optional[BatchDownloadPage]:
        return run_handle_empty_batch_download_page(self)

    def _run_batch_download_page_target(
        self,
        target: BatchDownloadPageRunTarget,
    ) -> Optional[BatchDownloadLoopStep]:
        return run_batch_download_page_target(self, target)

    def _batch_download_loop_step_from_page(
        self,
        target: BatchDownloadPageRunTarget,
        page: BatchDownloadPage,
    ) -> BatchDownloadLoopStep:
        return run_batch_download_loop_step_from_page(self, target, page)

    def _fetch_batch_download_page_for_run_target(
        self,
        target: BatchDownloadPageRunTarget,
    ) -> Optional[BatchDownloadPage]:
        return run_fetch_batch_download_page_for_run_target(self, target)

    def _download_batch_page_files_for_run_target(
        self,
        target: BatchDownloadPageRunTarget,
        page: BatchDownloadPage,
    ) -> int:
        return run_download_batch_page_files_for_run_target(self, target, page)

    def _next_batch_download_index_for_run_target(
        self,
        target: BatchDownloadPageRunTarget,
        page: BatchDownloadPage,
        downloaded_in_batch: int,
    ) -> Optional[str]:
        return run_next_batch_download_index_for_run_target(self, target, page, downloaded_in_batch)

    def _batch_page_files_target_for_page(
        self,
        target: BatchDownloadPageRunTarget,
        page: BatchDownloadPage,
    ) -> BatchDownloadPageFilesTarget:
        return run_batch_page_files_target_for_page(target, page)

    def _run_batch_download_loop_target(
        self,
        target: BatchDownloadLoopTarget,
    ) -> None:
        run_batch_download_loop_target(self, target)

    def _should_continue_batch_download_loop(
        self,
        target: BatchDownloadLoopTarget,
        step: BatchDownloadLoopStep,
    ) -> bool:
        return run_should_continue_batch_download_loop(target, step)

    def _run_batch_download_loop_iteration(
        self,
        target: BatchDownloadLoopTarget,
        step: BatchDownloadLoopStep,
    ) -> Optional[BatchDownloadLoopStep]:
        return run_batch_download_loop_iteration(self, target, step)

    def _is_batch_download_loop_stopped(self) -> bool:
        return run_is_batch_download_loop_stopped(self)

    def _run_next_batch_download_loop_step(
        self,
        target: BatchDownloadLoopTarget,
        step: BatchDownloadLoopStep,
    ) -> Optional[BatchDownloadLoopStep]:
        return run_next_batch_download_loop_step(self, target, step)

    def _advance_batch_download_loop_step(
        self,
        target: BatchDownloadLoopTarget,
        step: BatchDownloadLoopStep,
    ) -> Optional[BatchDownloadLoopStep]:
        return run_advance_batch_download_loop_step(self, target, step)

    def _is_missing_batch_download_loop_step(
        self,
        step: Optional[BatchDownloadLoopStep],
    ) -> bool:
        return run_is_missing_batch_download_loop_step(step)

    def _is_terminal_batch_download_loop_step(self, step: BatchDownloadLoopStep) -> bool:
        return run_is_terminal_batch_download_loop_step(step)

    def _initial_batch_download_loop_step(
        self,
        target: BatchDownloadLoopTarget,
    ) -> BatchDownloadLoopStep:
        return run_initial_batch_download_loop_step(target)

    def download_files_batch(self, max_files: Optional[int] = None, start_index: Optional[str] = None) -> Dict[str, int]:
        return self._download_files_batch_target(
            BatchDownloadTarget(max_files, start_index),
        )

    def _download_files_batch_target(
        self,
        target: BatchDownloadTarget,
    ) -> Dict[str, int]:
        """批量下载文件"""
        return run_batch_file_download(self, target)

    def _is_initial_batch_download_stopped(self) -> bool:
        return run_is_initial_batch_download_stopped(self)

    def _log_batch_download_start(self, max_files: Optional[int]) -> None:
        run_log_batch_download_start(self, max_files)

    def _log_batch_download_completion(self, stats: Dict[str, int]) -> None:
        run_log_batch_download_completion(self, stats)

    def _print_file_list_page(
        self,
        files: list[Dict[str, Any]],
        next_index: Any,
    ) -> None:
        run_print_file_list_page(files, next_index)

    def show_file_list(self, count: int = 20, index: Optional[str] = None) -> Optional[str]:
        """显示文件列表"""
        return self._show_file_list_target(ShowFileListTarget(count, index))

    def _show_file_list_target(self, target: ShowFileListTarget) -> Optional[str]:
        return run_show_file_list(self, target)

    def _import_file_collection_page(
        self,
        data: Dict[str, Any],
        file_count: int,
        page_count: int,
        stats: Dict[str, int],
    ) -> bool:
        return run_import_file_collection_page(self, data, file_count, page_count, stats)

    def _next_file_collection_index(self, next_index: Any) -> Optional[Any]:
        return run_next_file_collection_index(next_index)

    def _fetch_file_collection_page(
        self,
        page_count: int,
        current_index: Optional[Any],
    ) -> Optional[FileCollectionPage]:
        return run_fetch_file_collection_page(self, page_count, current_index)

    def _run_file_collection_page(
        self,
        page_count: int,
        current_index: Optional[Any],
        stats: Dict[str, int],
    ) -> Optional[Any]:
        return run_file_collection_page(self, page_count, current_index, stats)

    def _run_file_collection_loop(self, stats: Dict[str, int]) -> int:
        return run_file_collection_loop(self, stats)

    def _create_file_collection_log(self) -> Optional[Any]:
        return run_create_file_collection_log(self)

    def _update_file_collection_log(
        self,
        stats: Dict[str, int],
        log_id: Optional[Any],
    ) -> None:
        run_update_file_collection_log(self, stats, log_id)

    def collect_all_files_to_database(self) -> Dict[str, int]:
        """收集所有文件信息到数据库"""
        return self._collect_all_files_to_database_target(FileCollectionTarget())

    def _collect_all_files_to_database_target(
        self,
        target: FileCollectionTarget,
    ) -> Dict[str, int]:
        return run_collect_all_files_to_database(self, target)

    def get_database_time_range(self) -> Dict[str, Any]:
        """获取完整数据库中文件的时间范围信息"""
        return self._get_database_time_range_target(DatabaseTimeRangeTarget())

    def _get_database_time_range_target(
        self,
        target: DatabaseTimeRangeTarget,
    ) -> Dict[str, Any]:
        return run_get_database_time_range(self, target)

    def _load_time_collection_latest_file_time(
        self,
        enable_time_dedupe: bool,
        initial_files: int,
    ) -> Optional[Any]:
        return run_load_time_collection_latest_file_time(self, enable_time_dedupe, initial_files)

    def _load_time_collection_database_state(
        self,
        enable_time_dedupe: bool,
    ) -> TimeCollectionDatabaseState:
        return run_load_time_collection_database_state(self, enable_time_dedupe)

    def _time_collection_dedupe_result(
        self,
        should_stop_before_insert: bool = False,
        should_stop_after_insert: bool = False,
    ) -> Dict[str, bool]:
        return run_time_collection_dedupe_result(should_stop_before_insert, should_stop_after_insert)

    def _apply_time_collection_dedupe_plan(
        self,
        data: Dict[str, Any],
        files: list[Dict[str, Any]],
        enable_time_dedupe: bool,
        db_latest_time: Optional[Any],
    ) -> Dict[str, bool]:
        return run_time_collection_dedupe_plan(self, data, files, enable_time_dedupe, db_latest_time)

    def _import_time_collection_page(
        self,
        data: Dict[str, Any],
        page_count: int,
        should_stop_after_insert: bool,
        total_imported_stats: Dict[str, int],
    ) -> bool:
        return run_import_time_collection_page(self, data, page_count, should_stop_after_insert, total_imported_stats)

    def _crossed_time_collection_stop_before(
        self,
        files: list[Dict[str, Any]],
        stop_before_time: Optional[datetime.datetime],
    ) -> bool:
        return run_crossed_time_collection_stop_before(self, files, stop_before_time)

    def _next_time_collection_index(self, next_index: Optional[Any]) -> Optional[Any]:
        return run_next_time_collection_index(self, next_index)

    def _fetch_time_collection_page(
        self,
        page_count: int,
        current_index: Optional[Any],
        sort: str,
    ) -> Optional[TimeCollectionPage]:
        return run_fetch_time_collection_page(self, page_count, current_index, sort)

    def _next_time_collection_page_after_import(
        self,
        page: TimeCollectionPage,
        should_stop_after_insert: bool,
        stop_before_time: Optional[datetime.datetime],
    ) -> Optional[Any]:
        return run_next_time_collection_page_after_import(self, page, should_stop_after_insert, stop_before_time)

    def _collect_time_collection_page(
        self,
        page_count: int,
        current_index: Optional[Any],
        context: TimeCollectionLoopContext,
    ) -> Optional[Any]:
        return run_time_collection_page(self, page_count, current_index, context)

    def _time_collection_page_import_result(
        self,
        page: TimeCollectionPage,
        page_count: int,
        should_stop_after_insert: bool,
        total_imported_stats: Dict[str, int],
    ) -> Optional[TimeCollectionPageImportResult]:
        return run_time_collection_page_import_result(
            self,
            page,
            page_count,
            should_stop_after_insert,
            total_imported_stats,
        )

    def _dedupe_and_import_time_collection_page(
        self,
        page: TimeCollectionPage,
        page_count: int,
        enable_time_dedupe: bool,
        db_latest_time: Optional[Any],
        total_imported_stats: Dict[str, int],
    ) -> Optional[TimeCollectionPageImportResult]:
        return run_dedupe_and_import_time_collection_page(
            self,
            page,
            page_count,
            enable_time_dedupe,
            db_latest_time,
            total_imported_stats,
        )

    def _should_stop_time_collection_loop(self) -> bool:
        return run_should_stop_time_collection_loop(self)

    def _run_time_collection_loop(
        self,
        start_time: Optional[str],
        context: TimeCollectionLoopContext,
    ) -> int:
        return run_time_collection_loop(self, start_time, context)

    def _finalize_time_collection_result(
        self,
        initial_files: int,
        total_imported_stats: Dict[str, int],
        page_count: int,
    ) -> Dict[str, int]:
        return run_finalize_time_collection_result(self, initial_files, total_imported_stats, page_count)

    def _collect_incremental_from_oldest_time(self, oldest_time: Any) -> Dict[str, int]:
        return run_collect_incremental_from_oldest_time(self, oldest_time)

    def _collect_incremental_from_time_info(self, time_info: Dict[str, Any]) -> Dict[str, int]:
        return run_collect_incremental_from_time_info(self, time_info)

    def _collect_files_for_normalized_date_range(
        self,
        normalized_start: Optional[str],
        normalized_end: Optional[str],
        stop_before_dt: Optional[datetime.datetime],
    ) -> Dict[str, int]:
        return run_collect_files_for_normalized_date_range(
            self,
            normalized_start,
            normalized_end,
            stop_before_dt,
        )

    def _initialize_time_collection_mode(
        self,
        sort: str,
        start_time: Optional[str],
        stop_before_time: Optional[datetime.datetime],
        force_refresh: bool,
    ) -> bool:
        return run_initialize_time_collection_mode(self, sort, start_time, stop_before_time, force_refresh)

    def _should_stop_time_collection_initially(self) -> bool:
        return run_should_stop_time_collection_initially(self)

    def _prepare_time_collection_loop_context(
        self,
        sort: str,
        enable_time_dedupe: bool,
        db_latest_time: Optional[Any],
        stop_before_time: Optional[datetime.datetime],
    ) -> tuple[Dict[str, int], TimeCollectionLoopContext]:
        return run_prepare_time_collection_loop_context(
            sort,
            enable_time_dedupe,
            db_latest_time,
            stop_before_time,
        )

    def _run_time_collection_after_initial_stop(
        self,
        start_time: Optional[str],
        sort: str,
        enable_time_dedupe: bool,
        stop_before_time: Optional[datetime.datetime],
    ) -> Dict[str, int]:
        return run_time_collection_after_initial_stop(
            self,
            start_time,
            sort,
            enable_time_dedupe,
            stop_before_time,
        )

    def _collect_files_by_time_target(
        self,
        target: TimeCollectionTarget,
    ) -> Dict[str, int]:
        return run_file_time_collection(self, target)

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
        return run_collect_incremental_files(self, target)

    def _collect_files_for_date_range_target(
        self,
        target: DateRangeCollectionTarget,
    ) -> Dict[str, int]:
        return run_collect_files_for_date_range(self, target)

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
        return run_database_file_download(self, target)

    def _print_database_core_stats(self, stats: Dict[str, Any]) -> None:
        run_print_database_core_stats(stats)

    def _fetch_database_total_size(self) -> Any:
        return run_fetch_database_total_size(self)

    def _fetch_database_time_range(self) -> Optional[DatabaseStatsTimeRange]:
        return run_fetch_database_time_range(self)

    def _fetch_database_api_response_stats(self) -> Any:
        return run_fetch_database_api_response_stats(self)

    def _print_database_total_size(self) -> None:
        run_print_database_total_size(self)

    def _print_database_table_stats(self, stats: Dict[str, Any]) -> None:
        run_print_database_table_stats(stats)

    def _print_database_time_range(self) -> None:
        run_print_database_time_range(self)

    def _print_database_api_response_stats(self) -> None:
        run_print_database_api_response_stats(self)

    def show_database_stats(self):
        """显示完整数据库统计信息"""
        return self._show_database_stats_entry_target(ShowDatabaseStatsEntryTarget())

    def _show_database_stats_entry_target(
        self,
        target: ShowDatabaseStatsEntryTarget,
    ) -> None:
        run_show_database_stats_entry(self, target)

    def _show_database_stats_target(self, target: ShowDatabaseStatsTarget) -> None:
        run_show_database_stats_target(self, target)

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
