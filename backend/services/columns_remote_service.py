from __future__ import annotations

import asyncio
import json
import random
from typing import Any, Callable, Dict, List, Optional

import requests

from backend.core.log_redaction import redact_response_text


def redact_response_for_log(text: str | None, limit: int = 500) -> str:
    if not text:
        return "empty"
    return redact_response_text(text, limit=limit)


def retry_wait_seconds(retry: int) -> int:
    return 2 if retry < 3 else (5 if retry < 6 else 10)


async def _fetch_column_signed_resource_url(
    *,
    url: str,
    headers: Dict[str, str],
    response_field: str,
    action_label: str,
    retry_identity: str,
    failure_context: str,
    request_get: Callable[..., Any] = requests.get,
    log_error: Callable[[str], None] = lambda _message: None,
    log_exception: Callable[[str], None] = lambda _message: None,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> Optional[str]:
    max_retries = 10

    for retry in range(max_retries):
        try:
            resp = request_get(url, headers=headers, timeout=30)
        except Exception as req_err:
            if retry < max_retries - 1:
                await sleep(retry_wait_seconds(retry))
                continue
            log_exception(f"{action_label}请求异常: {retry_identity}")
            raise Exception(f"{action_label}请求异常: {req_err}")

        if resp.status_code != 200:
            if retry < max_retries - 1:
                await sleep(retry_wait_seconds(retry))
                continue
            error_msg = f"{action_label}失败: HTTP {resp.status_code}, URL={url}, Response={redact_response_for_log(resp.text)}"
            log_error(error_msg)
            raise Exception(error_msg)

        data = resp.json()
        if not data.get("succeeded"):
            error_code = data.get("code")
            error_message = data.get("error_message", "未知错误")

            if error_code == 1059:
                if retry < max_retries - 1:
                    await sleep(retry_wait_seconds(retry))
                    continue
                log_error(f"{action_label}重试{max_retries}次后仍失败: {retry_identity}, code={error_code}")
                raise Exception(f"{action_label}失败，重试{max_retries}次后仍遇到反爬限制")

            error_msg = f"{action_label}失败: code={error_code}, message={error_message}, {failure_context}"
            log_error(error_msg)
            raise Exception(f"{action_label}失败: {error_message} (code={error_code})")

        return data.get("resp_data", {}).get(response_field)

    return None


async def fetch_column_file_download_url(
    *,
    file_id: int,
    file_name: str,
    headers: Dict[str, str],
    request_get: Callable[..., Any] = requests.get,
    log_error: Callable[[str], None] = lambda _message: None,
    log_exception: Callable[[str], None] = lambda _message: None,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> Optional[str]:
    return await _fetch_column_signed_resource_url(
        url=f"https://api.zsxq.com/v2/files/{file_id}/download_url",
        headers=headers,
        response_field="download_url",
        action_label="获取下载链接",
        retry_identity=f"file_id={file_id}",
        failure_context=f"file_id={file_id}, file_name={file_name}",
        request_get=request_get,
        log_error=log_error,
        log_exception=log_exception,
        sleep=sleep,
    )


async def fetch_column_video_m3u8_url(
    *,
    video_id: int,
    topic_id: int,
    headers: Dict[str, str],
    request_get: Callable[..., Any] = requests.get,
    log_error: Callable[[str], None] = lambda _message: None,
    log_exception: Callable[[str], None] = lambda _message: None,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> Optional[str]:
    return await _fetch_column_signed_resource_url(
        url=f"https://api.zsxq.com/v2/videos/{video_id}/url",
        headers=headers,
        response_field="url",
        action_label="获取视频链接",
        retry_identity=f"video_id={video_id}",
        failure_context=f"video_id={video_id}, topic_id={topic_id}",
        request_get=request_get,
        log_error=log_error,
        log_exception=log_exception,
        sleep=sleep,
    )


def _request_column_json_once(
    task_id: str,
    url: str,
    headers: Dict[str, str],
    *,
    request_get: Callable[..., Any] = requests.get,
    add_task_log: Callable[[str, str], None] = lambda _task_id, _message: None,
    log_error: Callable[[str], None] = lambda _message: None,
    log_exception: Callable[[str], None] = lambda _message: None,
    context: str,
    log_action: str,
    parse_label: str,
    user_action: str,
    user_parse_label: str,
) -> tuple[Optional[Dict[str, Any]], int]:
    request_count = 0

    try:
        resp = request_get(url, headers=headers, timeout=30)
        request_count += 1
    except Exception as req_err:
        log_exception(f"{log_action}请求异常: {context}, url={url}")
        add_task_log(task_id, f"   ⚠️ {user_action}请求异常: {req_err}")
        return None, request_count

    if resp.status_code != 200:
        log_error(
            f"{log_action}失败: {context}, HTTP {resp.status_code}, "
            f"response={redact_response_for_log(resp.text)}"
        )
        add_task_log(task_id, f"   ⚠️ {user_action}失败: HTTP {resp.status_code}")
        return None, request_count

    try:
        return resp.json(), request_count
    except Exception as json_err:
        log_exception(f"解析{parse_label}JSON失败: {context}, response={redact_response_for_log(resp.text)}")
        add_task_log(task_id, f"   ⚠️ 解析{user_parse_label}失败: {json_err}")
        return None, request_count


async def fetch_columns_catalog(
    task_id: str,
    group_id: str,
    headers: Dict[str, str],
    *,
    request_get: Callable[..., Any] = requests.get,
    is_task_stopped: Callable[[str], bool] = lambda _task_id: False,
    add_task_log: Callable[[str, str], None] = lambda _task_id, _message: None,
    log_error: Callable[[str], None] = lambda _message: None,
    log_exception: Callable[[str], None] = lambda _message: None,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> tuple[List[Dict[str, Any]], int]:
    columns_url = f"https://api.zsxq.com/v2/groups/{group_id}/columns"
    max_retries = 10
    request_count = 0

    for retry in range(max_retries):
        if is_task_stopped(task_id):
            break

        try:
            resp = request_get(columns_url, headers=headers, timeout=30)
            request_count += 1
        except Exception as req_err:
            log_exception(f"获取专栏目录请求异常: group_id={group_id}, url={columns_url}")
            if retry < max_retries - 1:
                wait_time = retry_wait_seconds(retry)
                add_task_log(task_id, f"   ⚠️ 请求异常，等待{wait_time}秒后重试 ({retry+1}/{max_retries})")
                await sleep(wait_time)
                continue
            raise Exception(f"获取专栏目录请求异常: {req_err}")

        if resp.status_code != 200:
            log_error(
                f"获取专栏目录失败: group_id={group_id}, HTTP {resp.status_code}, "
                f"response={redact_response_for_log(resp.text)}"
            )
            if retry < max_retries - 1:
                wait_time = retry_wait_seconds(retry)
                add_task_log(task_id, f"   ⚠️ HTTP {resp.status_code}，等待{wait_time}秒后重试 ({retry+1}/{max_retries})")
                await sleep(wait_time)
                continue
            raise Exception(f"获取专栏目录失败: HTTP {resp.status_code}")

        try:
            data = resp.json()
        except Exception as json_err:
            log_exception(f"解析专栏目录JSON失败: group_id={group_id}, response={redact_response_for_log(resp.text)}")
            raise Exception(f"解析专栏目录失败: {json_err}")

        if not data.get("succeeded"):
            error_code = data.get("code")
            error_msg = data.get("error_message", "未知错误")

            if "expired" in error_msg.lower() or data.get("resp_data", {}).get("expired"):
                raise Exception(f"会员已过期: {error_msg}")

            if error_code == 1059:
                if retry < max_retries - 1:
                    wait_time = retry_wait_seconds(retry)
                    add_task_log(task_id, f"   ⚠️ 遇到反爬机制 (错误码1059)，等待{wait_time}秒后重试 ({retry+1}/{max_retries})")
                    await sleep(wait_time)
                    continue
                log_error(f"获取专栏目录重试{max_retries}次后仍失败: group_id={group_id}, code={error_code}")
                raise Exception(f"获取专栏目录失败，重试{max_retries}次后仍遇到反爬限制")

            log_error(
                f"获取专栏目录API失败: group_id={group_id}, code={error_code}, "
                f"message={error_msg}, response={json.dumps(data, ensure_ascii=False)[:500]}"
            )
            raise Exception(f"API返回失败: {error_msg} (code={error_code})")

        columns = data.get("resp_data", {}).get("columns", [])
        if retry > 0:
            add_task_log(task_id, f"   ✅ 重试成功 (第{retry+1}次尝试)")
        return columns, request_count

    raise Exception("获取专栏目录失败")


def fetch_column_topics(
    task_id: str,
    column_id: int,
    topics_url: str,
    headers: Dict[str, str],
    *,
    request_get: Callable[..., Any] = requests.get,
    add_task_log: Callable[[str, str], None] = lambda _task_id, _message: None,
    log_error: Callable[[str], None] = lambda _message: None,
    log_exception: Callable[[str], None] = lambda _message: None,
) -> tuple[Optional[List[Dict[str, Any]]], int]:
    topics_data, request_count = _request_column_json_once(
        task_id,
        topics_url,
        headers,
        request_get=request_get,
        add_task_log=add_task_log,
        log_error=log_error,
        log_exception=log_exception,
        context=f"column_id={column_id}",
        log_action="获取专栏文章列表",
        parse_label="专栏文章列表",
        user_action="获取文章列表",
        user_parse_label="文章列表",
    )
    if topics_data is None:
        return None, request_count

    if not topics_data.get("succeeded"):
        error_code = topics_data.get("code", "unknown")
        error_message = topics_data.get("error_message", "未知错误")
        log_error(f"获取专栏文章列表失败: column_id={column_id}, code={error_code}, message={error_message}")
        add_task_log(task_id, f"   ⚠️ 获取文章列表失败: {error_message} (code={error_code})")
        return None, request_count

    topics_list = topics_data.get("resp_data", {}).get("topics", [])
    add_task_log(task_id, f"   📝 获取到 {len(topics_list)} 篇文章")
    return topics_list, request_count


async def fetch_topic_detail(
    task_id: str,
    topic_id: int,
    headers: Dict[str, str],
    current_request_count: int,
    items_per_batch: int,
    long_sleep_min: float,
    long_sleep_max: float,
    crawl_interval_min: float,
    crawl_interval_max: float,
    *,
    request_get: Callable[..., Any] = requests.get,
    is_task_stopped: Callable[[str], bool] = lambda _task_id: False,
    add_task_log: Callable[[str, str], None] = lambda _task_id, _message: None,
    log_error: Callable[[str], None] = lambda _message: None,
    log_exception: Callable[[str], None] = lambda _message: None,
    sleep: Callable[[float], Any] = asyncio.sleep,
    random_uniform: Callable[[float, float], float] = random.uniform,
) -> tuple[Optional[Dict[str, Any]], int]:
    max_retries = 10
    request_count = current_request_count
    requests_made = 0

    for _ in range(max_retries):
        if is_task_stopped(task_id):
            break

        if request_count > 0 and request_count % items_per_batch == 0:
            sleep_time = random_uniform(long_sleep_min, long_sleep_max)
            add_task_log(task_id, f"      😴 已完成 {request_count} 次请求，休眠 {sleep_time:.1f} 秒...")
            await sleep(sleep_time)

        delay = random_uniform(crawl_interval_min, crawl_interval_max)
        await sleep(delay)

        detail_url = f"https://api.zsxq.com/v2/topics/{topic_id}/info"
        try:
            detail_resp = request_get(detail_url, headers=headers, timeout=30)
            request_count += 1
            requests_made += 1
        except Exception as req_err:
            log_exception(f"获取文章详情请求异常: topic_id={topic_id}, url={detail_url}")
            add_task_log(task_id, f"      ⚠️ 获取详情请求异常: {req_err}")
            continue

        if detail_resp.status_code != 200:
            log_error(
                f"获取文章详情失败: topic_id={topic_id}, HTTP {detail_resp.status_code}, "
                f"response={redact_response_for_log(detail_resp.text)}"
            )
            add_task_log(task_id, f"      ⚠️ 获取详情失败: HTTP {detail_resp.status_code}")
            continue

        try:
            topic_detail = detail_resp.json()
        except Exception as json_err:
            log_exception(f"解析文章详情JSON失败: topic_id={topic_id}, response={redact_response_for_log(detail_resp.text)}")
            add_task_log(task_id, f"      ⚠️ 解析详情失败: {json_err}")
            continue

        if topic_detail and topic_detail.get("succeeded"):
            return topic_detail, requests_made

        error_msg = (topic_detail or {}).get("error_message", "未知错误")
        log_error(f"获取文章详情API失败: topic_id={topic_id}, message={error_msg}")
        add_task_log(task_id, f"      ⚠️ 获取详情API失败: {error_msg}")

    return None, requests_made
