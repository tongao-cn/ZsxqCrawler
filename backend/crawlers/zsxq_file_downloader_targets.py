from __future__ import annotations

import json
from typing import Any, Dict, NamedTuple, Optional

import requests

from backend.crawlers.file_download_transfer import DownloadFileTarget


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


class FileListResponseStatusTarget(NamedTuple):
    response: requests.Response
    attempt: int
    max_retries: int


class FileListOkResponseTarget(NamedTuple):
    response: requests.Response
    attempt: int
    max_retries: int


class FileListOkDataTarget(NamedTuple):
    data: Optional[Dict[str, Any]]
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


class FileListRequestContext(NamedTuple):
    url: str
    params: Dict[str, str]
    max_retries: int


class FileListRequestTarget(NamedTuple):
    url: str
    headers: Dict[str, str]
    params: Dict[str, str]


class FileListRequestAttemptTarget(NamedTuple):
    request_context: FileListRequestContext
    attempt: int


class StealthHeaderSelection(NamedTuple):
    user_agent: str
    sec_ch_ua: str
    accept_language: str
    platform: str


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


class DownloadRetryWaitTarget(NamedTuple):
    attempt: int
    download_retries: int


class DownloadFileResponseRequestTarget(NamedTuple):
    download_url: str


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


class DownloadUrlUnavailableTarget(NamedTuple):
    file_id: int
    last_download_url_error: Optional[Dict[str, Any]]


class DownloadFinalFailureTarget(NamedTuple):
    file_id: int
    download_retries: int
    last_error_code: Optional[str]
    last_error: Optional[str]


class DownloadStopTarget(NamedTuple):
    file_id: int
    temp_path: str


class DownloadAttemptResponseTarget(NamedTuple):
    download_url: str
    file_target: DownloadFileTarget


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


class ShowFileListTarget(NamedTuple):
    count: int
    index: Optional[str]


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
