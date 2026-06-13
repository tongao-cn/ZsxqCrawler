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
from typing import Dict, Optional, Any

import requests

from backend.core.console_output import safe_console_print as print
from backend.core.log_redaction import redact_json_like
from backend.crawlers.zsxq_file_downloader_helpers import (
    API_FAILURE_NON_RETRY,
    API_FAILURE_PERMISSION_DENIED_1030,
    API_FAILURE_RETRY,
    HTTP_FAILURE_NON_RETRY,
    HTTP_FAILURE_RETRY,
    api_failure_detail,
    add_import_stats,
    classify_api_failure,
    database_download_completion_messages,
    database_download_filter_messages,
    database_download_file_info,
    database_download_query_plan,
    database_download_start_messages,
    database_download_time_range_message,
    database_stats_table_emoji,
    date_range_collection_start_messages,
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
    download_url_failure_detail,
    download_url_success_plan,
    empty_import_stats,
    existing_file_matches,
    file_list_request_params,
    file_list_start_messages,
    http_failure_plan,
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
    risk_event_header_profile_label,
    risk_event_user_agent_label,
    should_log_full_response,
    summarize_page_time_range,
    time_collection_final_summary,
    time_collection_mode,
    time_collection_next_page_plan,
    time_dedupe_page_plan,
)
from backend.storage.postgres_core_schema import CORE_SCHEMA
from backend.storage.zsxq_file_database import ZSXQFileDatabase


def _query_group_id(group_id: str) -> Any:
    return download_query_group_id(group_id)


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

        # 下载间隔控制参数
        self.download_interval = download_interval
        self.long_sleep_interval = long_sleep_interval
        self.files_per_batch = files_per_batch
        self.current_batch_count = 0  # 当前批次已下载文件数

        # 随机间隔范围参数（如果提供了范围参数，则使用随机间隔）
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

        # 为每个群组创建专属的下载目录
        if download_dir == "downloads":  # 默认目录
            from backend.core.db_path_manager import get_db_path_manager
            path_manager = get_db_path_manager()
            group_dir = path_manager.get_group_dir(group_id)
            self.download_dir = os.path.join(group_dir, "downloads")
        else:
            # 如果指定了自定义目录，也在其下创建群组子目录
            self.download_dir = os.path.join(download_dir, f"group_{group_id}")

        print(f"📁 群组 {group_id} 下载目录: {self.download_dir}")
        self.base_url = "https://api.zsxq.com"

        # 日志回调和停止检查函数
        self.log_callback = None
        self.stop_check_func = None
        self.risk_event_log_path = None
        self.stop_flag = False  # 本地停止标志
        self.last_download_url_error = None

        # 反检测设置
        self.min_delay = 2.0  # 最小延迟（秒）
        self.max_delay = 5.0  # 最大延迟（秒）
        self.long_delay_interval = 5  # 每N个文件进行长休眠

        # 统计
        self.request_count = 0
        self.download_count = 0
        self.debug_mode = False

        # 创建session
        self.session = requests.Session()

        # 确保下载目录存在
        os.makedirs(self.download_dir, exist_ok=True)
        self.log(f"📁 下载目录: {os.path.abspath(self.download_dir)}")

        # 使用完整的文件数据库
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
        self.stop_flag = True
        self.log("🛑 收到停止信号，任务将在下一个检查点停止")

    def is_stopped(self):
        """检查是否被停止（综合检查本地标志和外部函数）"""
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
        return self.is_stopped()
    
    def clean_cookie(self, cookie: str) -> str:
        """清理Cookie字符串，去除不合法字符
        
        Args:
            cookie (str): 原始Cookie字符串
        
        Returns:
            str: 清理后的Cookie字符串
        """
        try:
            # 如果是bytes类型，先解码
            if isinstance(cookie, bytes):
                cookie = cookie.decode('utf-8')
            
            # 去除多余的空格和换行符
            cookie = cookie.strip()
            
            # 如果有多行，只取第一行
            if '\n' in cookie:
                cookie = cookie.split('\n')[0]
            
            # 去除末尾的反斜杠
            cookie = cookie.rstrip('\\')
            
            # 去除可能的前缀b和引号
            if cookie.startswith("b'") and cookie.endswith("'"):
                cookie = cookie[2:-1]
            elif cookie.startswith('b"') and cookie.endswith('"'):
                cookie = cookie[2:-1]
            elif cookie.startswith("'") and cookie.endswith("'"):
                cookie = cookie[1:-1]
            elif cookie.startswith('"') and cookie.endswith('"'):
                cookie = cookie[1:-1]
            
            # 处理转义字符
            cookie = cookie.replace('\\n', '')
            cookie = cookie.replace('\\"', '"')
            cookie = cookie.replace("\\'", "'")
            
            # 确保分号后有空格
            cookie = '; '.join(part.strip() for part in cookie.split(';'))
            
            return cookie
        except Exception as e:
            print(f"Cookie清理失败: {e}")
            return cookie  # 返回原始值
    
    def get_stealth_headers(self) -> Dict[str, str]:
        """获取反检测请求头（每次调用随机化）"""
        # 更丰富的User-Agent池
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
        ]
        
        # 随机选择User-Agent
        selected_ua = random.choice(user_agents)
        
        # 根据User-Agent生成对应的Sec-Ch-Ua
        if "Chrome" in selected_ua:
            if "131.0.0.0" in selected_ua:
                sec_ch_ua = '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
            elif "130.0.0.0" in selected_ua:
                sec_ch_ua = '"Google Chrome";v="130", "Chromium";v="130", "Not?A_Brand";v="99"'
            elif "129.0.0.0" in selected_ua:
                sec_ch_ua = '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"'
            else:
                sec_ch_ua = '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
        else:
            sec_ch_ua = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
        
        # 随机化其他头部
        accept_languages = [
            'zh-CN,zh;q=0.9,en;q=0.8',
            'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2'
        ]
        
        platforms = ['"Windows"', '"macOS"', '"Linux"']
        
        # 基础头部
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': random.choice(accept_languages),
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Cookie': self.cookie,
            'Host': 'api.zsxq.com',
            'Origin': 'https://wx.zsxq.com',
            'Pragma': 'no-cache',
            'Referer': f'https://wx.zsxq.com/dweb2/index/group/{self.group_id}',
            'Sec-Ch-Ua': sec_ch_ua,
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': random.choice(platforms),
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'User-Agent': selected_ua
        }
        
        # 随机添加可选头部
        optional_headers = {
            'DNT': '1',
            'Sec-GPC': '1',
            'Upgrade-Insecure-Requests': '1',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        for key, value in optional_headers.items():
            if random.random() > 0.5:  # 50%概率添加
                headers[key] = value
        
        # 随机调整时间戳相关头部
        if random.random() > 0.7:  # 30%概率添加
            headers['X-Timestamp'] = str(int(time.time()) + random.randint(-30, 30))
        
        if random.random() > 0.6:  # 40%概率添加
            headers['X-Request-Id'] = f"req-{random.randint(100000000000, 999999999999)}"
        
        return headers
    
    def smart_delay(self):
        """智能延迟"""
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
        if not getattr(self, "risk_event_log_path", None):
            return

        import csv
        from pathlib import Path

        path = Path(self.risk_event_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        user_agent = ""
        if headers:
            user_agent = headers.get("User-Agent") or headers.get("user-agent") or ""
        row = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "group_id": self.group_id,
            "file_id": file_id,
            "phase": phase,
            "attempt": attempt,
            "ua_label": self._user_agent_label(user_agent),
            "header_profile": self._header_profile_label(headers or {}),
            "status": status,
            "http_status": "" if http_status is None else http_status,
            "api_code": "" if api_code is None else api_code,
            "api_message": api_message or "",
        }
        fieldnames = tuple(row.keys())
        write_header = not path.exists()
        with path.open("a", encoding="utf-8-sig", newline="") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    def download_delay(self):
        """下载间隔延迟"""
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
        if attempt > 0:
            retry_delay = random.uniform(15, 30)
            print(f"   🔄 第{attempt}次重试，等待{retry_delay:.1f}秒...")
            time.sleep(retry_delay)

        self.smart_delay()
        self.request_count += 1
        headers = self.get_stealth_headers()
        if file_id is not None and getattr(self, "risk_event_log_path", None):
            user_agent = headers.get("User-Agent") or headers.get("user-agent") or ""
            self.log(f"   🧭 UA分类: {self._user_agent_label(user_agent)}")
        if file_id is not None:
            self._record_risk_event(
                file_id=file_id,
                phase="download_url_request",
                attempt=attempt,
                headers=headers,
            )

        if attempt > 0:
            print(f"   🔄 重试#{attempt}: 使用新的User-Agent: {headers.get('User-Agent', 'N/A')[:50]}...")
        return headers

    def _parse_api_json_response(
        self,
        response: requests.Response,
        attempt: int,
        max_retries: int,
    ) -> tuple[Optional[Dict[str, Any]], bool]:
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            decode_failure = json_decode_failure_plan(e, response.text, attempt, max_retries)
            for message in decode_failure["messages"]:
                print(message)
            return None, decode_failure["should_retry"]

        if should_log_full_response(attempt, max_retries, data.get('succeeded')):
            print(f"   📋 响应内容: {json.dumps(redact_json_like(data), ensure_ascii=False, indent=2)}")
        return data, False

    def fetch_file_list(self, count: int = 20, index: Optional[str] = None, sort: str = "by_download_count") -> Optional[Dict[str, Any]]:
        """获取文件列表（带重试机制）"""
        url = f"{self.base_url}/v2/groups/{self.group_id}/files"
        max_retries = 10

        params = file_list_request_params(count, sort, index)
        for message in file_list_start_messages(count, sort, index, url):
            self.log(message)
        
        for attempt in range(max_retries):
            headers = self._prepare_retry_api_request(attempt)
            
            try:
                response = self.session.get(url, headers=headers, params=params, timeout=30)
                
                print(f"   📊 响应状态: {response.status_code}")
                
                if response.status_code == 200:
                    data, should_retry_json = self._parse_api_json_response(response, attempt, max_retries)
                    if should_retry_json:
                        continue
                    if not data:
                        continue

                    if data.get('succeeded'):
                        files = data.get('resp_data', {}).get('files', [])
                        if attempt > 0:
                            print(f"   ✅ 重试成功！第{attempt}次重试获取到文件列表")
                        else:
                            print(f"   ✅ 获取成功: {len(files)}个文件")
                        return data

                    error_msg, error_code = api_failure_detail(data)
                    print(f"   ❌ API返回失败: {error_msg} (代码: {error_code})")
                    failure_class = classify_api_failure(error_code, attempt, max_retries)
                    if failure_class == API_FAILURE_RETRY:
                        print(f"   🔄 检测到可重试错误，准备重试...")
                        continue
                    if failure_class in {API_FAILURE_NON_RETRY, API_FAILURE_PERMISSION_DENIED_1030}:
                        print(f"   🚫 非可重试错误，停止重试")
                        return None
                        
                else:
                    http_failure = http_failure_plan(response.status_code, response.text, attempt, max_retries)
                    for message in http_failure["messages"]:
                        print(message)
                    http_failure_class = http_failure["failure_class"]
                    if http_failure_class == HTTP_FAILURE_RETRY:
                        continue
                    if http_failure_class == HTTP_FAILURE_NON_RETRY:
                        return None
                    
            except Exception as e:
                request_exception = request_exception_plan(e, attempt, max_retries)
                for message in request_exception["messages"]:
                    print(message)
                if request_exception["should_retry"]:
                    continue
        
        print(retry_exhausted_message(max_retries))
        return None
    
    def get_download_url(self, file_id: int) -> Optional[str]:
        """获取文件下载链接（带重试机制）
        
        注意：file_id 参数在不同场景下含义不同：
        - 边获取边下载时：传入的是真实的 file_id
        - 从数据库下载时：传入的是 topic_id
        """
        url = f"{self.base_url}/v2/files/{file_id}/download_url"
        max_retries = 10
        self.last_download_url_error = None
        
        self.log(f"   🔗 获取下载链接: ID={file_id}")
        self.log(f"   🌐 请求URL: {url}")
        
        for attempt in range(max_retries):
            headers = self._prepare_retry_api_request(attempt, file_id=file_id)
            
            try:
                response = self.session.get(url, headers=headers, timeout=30)
                
                print(f"   📊 响应状态: {response.status_code}")
                
                if response.status_code == 200:
                    data, should_retry_json = self._parse_api_json_response(response, attempt, max_retries)
                    if should_retry_json:
                        continue
                    if not data:
                        continue

                    if data.get('succeeded'):
                        download_url = data.get('resp_data', {}).get('download_url')
                        if download_url:
                            success_message, success_phase = download_url_success_plan(attempt)
                            print(success_message)
                            self._record_risk_event(
                                file_id=file_id,
                                phase=success_phase,
                                attempt=attempt,
                                headers=headers,
                                http_status=response.status_code,
                                status="api_success",
                            )
                            return download_url
                        print(f"   ❌ 响应中无下载链接字段")
                    else:
                        error_msg, error_code = api_failure_detail(data)
                        self.log(f"   ❌ API返回失败: {error_msg} (代码: {error_code})")
                        self._record_risk_event(
                            file_id=file_id,
                            phase="download_url_response",
                            attempt=attempt,
                            headers=headers,
                            http_status=response.status_code,
                            api_code=error_code,
                            api_message=error_msg,
                            status="api_failed",
                        )

                        failure_class = classify_api_failure(error_code, attempt, max_retries)

                        if failure_class == API_FAILURE_PERMISSION_DENIED_1030:
                            self.last_download_url_error = {
                                "code": error_code,
                                "message": error_msg,
                            }
                            self.log("   🚫 权限不足错误(1030)：此文件可能只能在手机端下载，已跳过当前文件")
                            return None

                        if failure_class == API_FAILURE_RETRY:
                            self.log(f"   🔄 检测到可重试错误，准备重试...")
                            continue
                        if failure_class == API_FAILURE_NON_RETRY:
                            self.log(f"   🚫 非可重试错误，停止重试")
                            return None
                        
                else:
                    http_failure = http_failure_plan(response.status_code, response.text, attempt, max_retries)
                    for message in http_failure["messages"]:
                        print(message)
                    http_failure_class = http_failure["failure_class"]
                    if http_failure_class == HTTP_FAILURE_RETRY:
                        continue
                    if http_failure_class == HTTP_FAILURE_NON_RETRY:
                        return None
                    
            except Exception as e:
                request_exception = request_exception_plan(e, attempt, max_retries)
                for message in request_exception["messages"]:
                    print(message)
                if request_exception["should_retry"]:
                    continue
        
        print(retry_exhausted_message(max_retries))
        return None
    
    def download_file(self, file_info: Dict[str, Any]) -> bool:
        """下载单个文件"""
        prepared_file = self._prepare_download_file_target(file_info)
        if not prepared_file:
            return False

        file_id, file_name, file_size, safe_filename, file_path = prepared_file

        # 🚀 优化：先检查本地文件，避免无意义的API请求
        existing_file_result = self._skip_existing_download_if_complete(file_id, file_path, file_size)
        if existing_file_result:
            return existing_file_result

        download_retries = 3
        last_error = None
        last_error_code = None

        for attempt in range(download_retries):
            try:
                if attempt > 0:
                    self._wait_before_download_retry(attempt, download_retries)

                download_url = self._get_download_url_or_mark_unavailable(file_id)
                if not download_url:
                    return False

                response = self._request_download_response(download_url)

                (
                    success_result,
                    failure_detail,
                    file_name,
                    safe_filename,
                    file_path,
                ) = self._handle_download_response(
                    response,
                    file_id,
                    file_name,
                    file_size,
                    safe_filename,
                    file_path,
                )
                if success_result is False:
                    return False
                if failure_detail:
                    last_error_code, last_error = failure_detail
                    continue
                return True

            except Exception as e:
                last_error_code, last_error = self._record_download_exception(e, file_path)

        self._mark_download_failed_after_retries(
            file_id,
            download_retries,
            last_error_code,
            last_error,
        )
        return False

    def _prepare_download_file_target(
        self,
        file_info: Dict[str, Any],
    ) -> Optional[tuple[int, str, int, str, str]]:
        file_data = download_file_data(file_info)
        file_id = file_data["file_id"]
        file_name = file_data["file_name"]
        file_size = file_data["file_size"]
        download_count = file_data["download_count"]

        self.log(f"📥 准备下载文件:")
        self.log(f"   📄 名称: {file_name}")
        self.log(f"   📊 大小: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        self.log(f"   📈 下载次数: {download_count}")
        if not file_id:
            self.log("   ❌ 文件缺少 file_id，无法下载")
            return None

        # 检查是否需要停止
        if self.check_stop():
            self.log("🛑 下载任务被停止")
            return None

        safe_filename, file_path = download_target_path(self.download_dir, file_name, file_id)
        return file_id, file_name, file_size, safe_filename, file_path

    def _skip_existing_download_if_complete(
        self,
        file_id: int,
        file_path: str,
        file_size: int,
    ) -> Optional[str]:
        file_exists, size_matches, _existing_size = existing_file_matches(file_path, file_size)
        if not file_exists:
            return None

        if size_matches:
            self.log(f"   ✅ 文件已存在且大小匹配，跳过下载")
            self.file_db.update_file_download_status(file_id, 'completed', file_path)
            return "skipped"  # 返回特殊值表示跳过

        self.log(f"   ⚠️ 文件已存在但大小不匹配，重新下载")
        return None

    def _get_download_url_or_mark_unavailable(self, file_id: int) -> Optional[str]:
        download_url = self.get_download_url(file_id)
        if download_url:
            return download_url

        self._mark_download_url_unavailable(file_id)
        return None

    def _mark_download_url_unavailable(self, file_id: int) -> None:
        self.log(f"   ❌ 无法获取下载链接")
        error_code, error_message = download_url_failure_detail(self.last_download_url_error)
        self.file_db.update_file_download_status(
            file_id,
            'failed',
            error_code=error_code,
            error_message=error_message,
        )

    def _mark_download_failed_after_retries(
        self,
        file_id: int,
        download_retries: int,
        last_error_code: Optional[str],
        last_error: Optional[str],
    ) -> None:
        self.log(f"   🚫 文件下载重试{download_retries}次仍失败: {last_error}")
        error_code, error_message = download_final_failure_detail(last_error_code, last_error)
        self.file_db.update_file_download_status(
            file_id,
            'failed',
            error_code=error_code,
            error_message=error_message,
        )

    def _complete_successful_download(
        self,
        file_id: int,
        safe_filename: str,
        file_path: str,
        temp_path: str,
    ) -> None:
        os.replace(temp_path, file_path)

        self.log(f"   ✅ 下载完成: {safe_filename}")
        self.log(f"   💾 保存路径: {file_path}")
        self.file_db.update_file_download_status(file_id, 'completed', file_path)

        self.download_count += 1
        self.current_batch_count += 1

        # 下载间隔控制
        self._apply_download_intervals()

    def _write_download_response_body(
        self,
        response,
        temp_path: str,
        total_size: int,
        file_id: int,
    ) -> Optional[int]:
        downloaded_size = 0
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)

                    progress_message = download_progress_message(downloaded_size, total_size)
                    if progress_message:
                        self.log(progress_message)

                    # 检查是否需要停止
                    if self.check_stop():
                        self._handle_download_stop(file_id, temp_path)
                        return None

        return downloaded_size

    def _apply_response_filename_override(
        self,
        file_name: str,
        file_id: int,
        response_headers: Dict[str, Any],
    ) -> Optional[tuple[str, str, str]]:
        filename_override = response_filename_override(
            file_name,
            file_id,
            self.download_dir,
            response_headers,
        )
        if not filename_override:
            return None

        real_filename, _safe_filename, _file_path = filename_override
        self.log(f"   📝 从响应头获取到真实文件名: {real_filename}")
        return filename_override

    def _record_download_http_failure(self, status_code: int) -> tuple[str, str]:
        error_code, error_message = download_http_failure_detail(status_code)
        self.log(f"   ❌ 下载失败: {error_message}")
        return error_code, error_message

    def _record_download_exception(self, exc: Exception, file_path: str) -> tuple[str, str]:
        error_code, error_message = download_exception_detail(exc)
        self.log(f"   ❌ 下载异常: {exc}")
        temp_path = partial_download_path(file_path)
        if remove_partial_download(temp_path):
            self.log(f"   🗑️ 删除不完整文件")
        return error_code, error_message

    def _wait_before_download_retry(self, attempt: int, download_retries: int) -> None:
        retry_delay, retry_message = download_retry_wait(attempt, download_retries)
        self.log(retry_message)
        time.sleep(retry_delay)

    def _request_download_response(self, download_url: str) -> Any:
        self.log(f"   🚀 开始下载...")
        return self.session.get(download_url, timeout=300, stream=True)

    def _handle_download_response(
        self,
        response,
        file_id: int,
        file_name: str,
        file_size: int,
        safe_filename: str,
        file_path: str,
    ) -> tuple[Optional[bool], Optional[tuple[str, str]], str, str, str]:
        try:
            filename_override = self._apply_response_filename_override(
                file_name,
                file_id,
                response.headers,
            )
            if filename_override:
                file_name, safe_filename, file_path = filename_override

            if response.status_code == 200:
                success_result, failure_detail = self._handle_successful_download_response(
                    response,
                    file_id,
                    file_size,
                    safe_filename,
                    file_path,
                )
                return success_result, failure_detail, file_name, safe_filename, file_path

            failure_detail = self._record_download_http_failure(response.status_code)
        except Exception as exc:
            failure_detail = self._record_download_exception(exc, file_path)
        return None, failure_detail, file_name, safe_filename, file_path

    def _prepare_download_body_target(
        self,
        response_headers: Dict[str, Any],
        file_size: int,
        file_path: str,
    ) -> tuple[int, int, str]:
        total_size = download_total_size(response_headers)
        expected_size = download_expected_size(file_size, total_size)
        temp_path = partial_download_path(file_path)
        remove_partial_download(temp_path)
        return total_size, expected_size, temp_path

    def _handle_successful_download_response(
        self,
        response,
        file_id: int,
        file_size: int,
        safe_filename: str,
        file_path: str,
    ) -> tuple[Optional[bool], Optional[tuple[str, str]]]:
        total_size, expected_size, temp_path = self._prepare_download_body_target(
            response.headers,
            file_size,
            file_path,
        )

        downloaded_size = self._write_download_response_body(
            response,
            temp_path,
            total_size,
            file_id,
        )
        if downloaded_size is None:
            return False, None

        mismatch_detail = self._handle_download_size_mismatch(expected_size, temp_path)
        if mismatch_detail:
            return None, mismatch_detail

        self._complete_successful_download(file_id, safe_filename, file_path, temp_path)
        return True, None

    def _handle_download_size_mismatch(
        self,
        expected_size: int,
        temp_path: str,
    ) -> Optional[tuple[str, str]]:
        final_size = os.path.getsize(temp_path)
        mismatch_detail = download_size_mismatch_detail(expected_size, final_size)
        if not mismatch_detail:
            return None

        _error_code, error_message = mismatch_detail
        self.log(f"   ⚠️ {error_message}")
        os.remove(temp_path)
        return mismatch_detail

    def _handle_download_stop(self, file_id: int, temp_path: str) -> None:
        self.log("🛑 下载过程中被停止")
        self.file_db.update_file_download_status(
            file_id,
            'failed',
            error_code='stopped',
            error_message='下载过程中被停止',
        )
        remove_partial_download(temp_path)

    def _apply_download_intervals(self):
        """应用下载间隔控制"""
        import time

        download_interval = self.download_interval
        long_sleep_interval = self.long_sleep_interval
        if getattr(self, "use_random_interval", False):
            should_long_sleep = self.current_batch_count >= self.files_per_batch
            if (
                should_long_sleep
                and self.long_sleep_interval_min is not None
                and self.long_sleep_interval_max is not None
            ):
                long_sleep_interval = random.uniform(
                    self.long_sleep_interval_min,
                    self.long_sleep_interval_max,
                )
            elif self.download_interval_min is not None and self.download_interval_max is not None:
                download_interval = random.uniform(self.download_interval_min, self.download_interval_max)

        delay, messages, should_reset_batch = download_interval_plan(
            self.current_batch_count,
            self.files_per_batch,
            download_interval,
            long_sleep_interval,
        )
        if delay is None:
            return

        self.log(messages[0])
        time.sleep(delay)
        if should_reset_batch:
            self.current_batch_count = 0  # 重置批次计数
            self.log(messages[1])

    def _download_batch_file_item(
        self,
        file_info: Dict[str, Any],
        item_number: int,
        max_files: Optional[int],
        has_more_in_batch: bool,
        downloaded_in_batch: int,
        stats: Dict[str, int],
    ) -> int:
        file_data = file_info.get('file', {})
        file_name = file_data.get('name', 'Unknown')

        if max_files is None:
            self.log(f"【第{item_number}个文件】{file_name}")
        else:
            self.log(f"【{item_number}/{max_files}】{file_name}")

        result = self.download_file(file_info)

        if result == "skipped":
            stats['skipped'] += 1
            self.log(f"   ⚠️ 文件已跳过，继续下一个")
        elif result:
            stats['downloaded'] += 1
            downloaded_in_batch += 1
            self.check_long_delay()

            not_reached_limit = max_files is None or downloaded_in_batch < max_files
            if has_more_in_batch and not_reached_limit:
                self.download_delay()
        else:
            stats['failed'] += 1

        stats['total_files'] += 1
        return downloaded_in_batch

    def download_files_batch(self, max_files: Optional[int] = None, start_index: Optional[str] = None) -> Dict[str, int]:
        """批量下载文件"""
        if max_files is None:
            self.log(f"📥 开始无限下载文件 (直到没有更多文件)")
        else:
            self.log(f"📥 开始批量下载文件 (最多{max_files}个)")

        # 检查是否需要停止
        if self.check_stop():
            self.log("🛑 任务被停止")
            return download_result_stats()

        stats = download_result_stats()
        current_index = start_index
        downloaded_in_batch = 0
        
        while max_files is None or downloaded_in_batch < max_files:
            # 检查是否需要停止
            if self.check_stop():
                self.log("🛑 批量下载任务被停止")
                break

            # 获取文件列表
            data = self.fetch_file_list(count=20, index=current_index)
            if not data:
                self.log("❌ 获取文件列表失败")
                break

            files = data.get('resp_data', {}).get('files', [])
            next_index = data.get('resp_data', {}).get('index')

            if not files:
                self.log("📭 没有更多文件")
                break

            self.log(f"📋 当前批次: {len(files)} 个文件")
            
            for i, file_info in enumerate(files):
                # 检查是否需要停止
                if self.check_stop():
                    self.log("🛑 文件下载过程中被停止")
                    break

                if max_files is not None and downloaded_in_batch >= max_files:
                    break

                downloaded_in_batch = self._download_batch_file_item(
                    file_info,
                    downloaded_in_batch + 1,
                    max_files,
                    (i + 1) < len(files),
                    downloaded_in_batch,
                    stats,
                )
            
            # 准备下一页
            should_continue = max_files is None or downloaded_in_batch < max_files
            if next_index and should_continue:
                current_index = next_index
                self.log(f"📄 准备获取下一页: {next_index}")
                time.sleep(2)  # 页面间短暂延迟
            else:
                break

        self.log(f"🎉 批量下载完成:")
        self.log(f"   📊 总文件数: {stats['total_files']}")
        self.log(f"   ✅ 下载成功: {stats['downloaded']}")
        self.log(f"   ⚠️ 跳过: {stats['skipped']}")
        self.log(f"   ❌ 失败: {stats['failed']}")
        
        return stats
    
    def show_file_list(self, count: int = 20, index: Optional[str] = None) -> Optional[str]:
        """显示文件列表"""
        data = self.fetch_file_list(count=count, index=index)
        if not data:
            return None
        
        files = data.get('resp_data', {}).get('files', [])
        next_index = data.get('resp_data', {}).get('index')
        
        print(f"\n📋 文件列表 ({len(files)} 个文件):")
        print("="*80)
        
        for i, file_info in enumerate(files, 1):
            file_data = file_info.get('file', {})
            topic_data = file_info.get('topic', {})
            
            file_name = file_data.get('name', 'Unknown')
            file_size = file_data.get('size', 0)
            download_count = file_data.get('download_count', 0)
            create_time = file_data.get('create_time', 'Unknown')
            
            topic_title = topic_data.get('talk', {}).get('text', '')[:50] if topic_data.get('talk') else ''
            
            print(f"{i:2d}. 📄 {file_name}")
            print(f"    📊 大小: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
            print(f"    📈 下载: {download_count} 次")
            print(f"    ⏰ 时间: {create_time}")
            if topic_title:
                print(f"    💬 话题: {topic_title}...")
            print()
        
        if next_index:
            print(f"📑 下一页索引: {next_index}")
        else:
            print("📭 没有更多文件")
        
        return next_index
    
    def collect_all_files_to_database(self) -> Dict[str, int]:
        """收集所有文件信息到数据库"""
        print(f"\n📊 开始收集文件列表到数据库...")
        
        # 创建收集记录
        self.file_db.cursor.execute(
            "INSERT INTO collection_log (start_time) VALUES (?) RETURNING id",
            (datetime.datetime.now().isoformat(),),
        )
        row = self.file_db.cursor.fetchone()
        log_id = row[0] if row else None
        self.file_db.conn.commit()
        
        stats = {'total_files': 0, 'new_files': 0, 'skipped_files': 0}
        current_index = None
        page_count = 0
        
        try:
            while True:
                page_count += 1
                print(f"\n📄 收集第{page_count}页文件列表...")
                
                # 获取文件列表
                data = self.fetch_file_list(count=20, index=current_index)
                if not data:
                    print(f"❌ 第{page_count}页获取失败，收集过程中断")
                    print(f"💾 已成功收集前{page_count-1}页的数据")
                    break
                
                files = data.get('resp_data', {}).get('files', [])
                next_index = data.get('resp_data', {}).get('index')
                
                if not files:
                    print("📭 没有更多文件")
                    break
                
                print(f"   📋 当前页面: {len(files)} 个文件")
                
                # 使用完整数据库导入整个API响应
                try:
                    page_stats = self.file_db.import_file_response(data)
                    
                    stats['new_files'] += page_stats.get('files', 0)
                    stats['total_files'] += len(files)
                    
                    print(f"      ✅ 新增文件: {page_stats.get('files', 0)}")
                    print(f"      📊 其他数据: 话题+{page_stats.get('topics', 0)}, 用户+{page_stats.get('users', 0)}")
                    
                except Exception as e:
                    print(f"   ❌ 第{page_count}页存储失败: {e}")
                    break
                
                print(f"   ✅ 第{page_count}页存储完成")
                
                # 准备下一页
                if next_index:
                    current_index = next_index
                    # 页面间短暂延迟
                    time.sleep(random.uniform(2, 5))
                else:
                    break
                    
        except KeyboardInterrupt:
            print(f"\n⏹️ 用户中断收集")
        except Exception as e:
            print(f"\n❌ 收集过程异常: {e}")
        
        # 更新收集记录
        self.file_db.cursor.execute('''
            UPDATE collection_log SET 
                end_time = ?, total_files = ?, new_files = ?, status = 'completed'
            WHERE id = ?
        ''', (datetime.datetime.now().isoformat(), stats['total_files'], 
              stats['new_files'], log_id))
        self.file_db.conn.commit()
        
        print(f"\n🎉 文件列表收集完成:")
        print(f"   📊 处理文件数: {stats['total_files']}")
        print(f"   ✅ 新增文件: {stats['new_files']}")
        print(f"   ⚠️ 跳过重复: {stats.get('skipped_files', 0)}")
        print(f"   📄 收集页数: {page_count}")
        
        return stats
    
    def get_database_time_range(self) -> Dict[str, Any]:
        """获取完整数据库中文件的时间范围信息"""
        # 使用新数据库检查是否有数据
        stats = self.file_db.get_database_stats()
        total_files = stats.get('files', 0)
        
        if total_files == 0:
            return {'has_data': False, 'total_files': 0}
        
        # 获取时间范围
        self.file_db.cursor.execute('''
            SELECT MIN(create_time) as oldest_time, 
                   MAX(create_time) as newest_time,
                   COUNT(*) as total_count
            FROM files 
            WHERE group_id = ?
              AND create_time IS NOT NULL AND create_time != ''
        ''', (_query_group_id(self.group_id),))
        
        result = self.file_db.cursor.fetchone()
        
        return {
            'has_data': True,
            'total_files': total_files,
            'oldest_time': result[0] if result else None,
            'newest_time': result[1] if result else None,
            'time_based_count': result[2] if result else 0
        }
    
    def collect_files_by_time(
        self,
        sort: str = "by_create_time",
        start_time: Optional[str] = None,
        stop_before_time: Optional[datetime.datetime] = None,
        **kwargs,
    ) -> Dict[str, int]:
        """按时间顺序收集文件列表到数据库（使用完整的数据库结构）"""
        self.log(f"📊 开始按时间顺序收集文件列表到完整数据库...")
        self.log(f"   📅 排序方式: {sort}")
        if start_time:
            self.log(f"   ⏰ 起始时间: {start_time}")
        if stop_before_time:
            self.log(f"   🎯 收集边界: 覆盖到 {stop_before_time.strftime('%Y-%m-%d')} 即停止")

        mode = time_collection_mode(sort, kwargs.get('force_refresh', False), stop_before_time)
        enable_time_dedupe = mode["enable_time_dedupe"]
        if mode["mode_message"]:
            self.log(mode["mode_message"])

        # 检查是否需要停止
        if self.check_stop():
            self.log("🛑 任务被停止")
            return {'total_files': 0, 'new_files': 0}

        # 使用完整数据库的统计信息
        initial_stats = self.file_db.get_database_stats()
        initial_files = initial_stats.get('files', 0)
        self.log(f"   📊 数据库初始状态: {initial_files} 个文件")
        
        db_latest_time = None
        if enable_time_dedupe and initial_files > 0:
            query, params = latest_file_create_time_query(_query_group_id(self.group_id))
            self.file_db.cursor.execute(query, params)
            result = self.file_db.cursor.fetchone()
            if result and result[0]:
                db_latest_time = result[0]
                self.log(f"   📅 数据库最新文件时间: {db_latest_time}")
        
        total_imported_stats = empty_import_stats()
        current_index = start_time  # 使用时间戳作为index
        page_count = 0
        
        try:
            while True:
                # 检查是否需要停止
                if self.check_stop():
                    self.log("🛑 文件收集任务被停止")
                    break

                page_count += 1
                self.log(f"📄 收集第{page_count}页文件列表...")

                # 获取文件列表（按时间排序）
                data = self.fetch_file_list(count=20, index=current_index, sort=sort)
                if not data:
                    self.log(f"❌ 第{page_count}页获取失败，收集过程中断")
                    self.log(f"💾 已成功收集前{page_count-1}页的数据")
                    break
                
                files = data.get('resp_data', {}).get('files', [])
                next_index = data.get('resp_data', {}).get('index')
                
                if not files:
                    self.log("📭 没有更多文件")
                    break

                self.log(f"   📋 当前页面: {len(files)} 个文件")
                page_oldest, page_newest = summarize_page_time_range(files)
                if page_oldest and page_newest:
                    self.log(f"   🗓️ 当前页文件时间范围: {page_newest} ~ {page_oldest}")

                should_stop_after_insert = False
                if enable_time_dedupe and db_latest_time:
                    dedupe_plan = time_dedupe_page_plan(files, db_latest_time)
                    newer_count = dedupe_plan["newer_count"]
                    older_count = dedupe_plan["older_count"]
                    
                    self.log(f"   📊 时间分析: 新于数据库{newer_count}个, 旧于或等于数据库{older_count}个")
                    
                    if dedupe_plan["should_stop_before_insert"]:
                        self.log(f"   ✅ 本页全部文件均已存在于数据库（时间不晚于数据库最新），停止收集")
                        self.log(f"   💡 提示: 如需强制重新收集，请传入 force_refresh=True 参数")
                        break
                    
                    if dedupe_plan["should_filter_before_insert"]:
                        self.log(f"   🔄 过滤掉{older_count}个旧数据，只插入{newer_count}个新数据")
                        data['resp_data']['files'] = dedupe_plan["newer_files"]
                        should_stop_after_insert = dedupe_plan["should_stop_after_insert"]

                # 使用完整数据库导入整个API响应
                try:
                    page_stats = self.file_db.import_file_response(data)

                    # 累计统计
                    add_import_stats(total_imported_stats, page_stats)

                    self.log(f"   ✅ 第{page_count}页存储完成: 文件+{page_stats.get('files', 0)}, 话题+{page_stats.get('topics', 0)}")
                    
                    # 如果本页有旧数据，插入新数据后停止
                    if should_stop_after_insert:
                        self.log(f"   ✅ 已插入本页新数据，后续页面均为旧数据，停止收集")
                        self.log(f"   💡 提示: 如需强制重新收集，请传入 force_refresh=True 参数")
                        break

                except Exception as e:
                    self.log(f"   ❌ 第{page_count}页存储失败: {e}")
                    break

                if stop_before_time:
                    crossed_stop_before, oldest_page_time = page_crosses_stop_before(files, stop_before_time)
                    if crossed_stop_before and oldest_page_time:
                        self.log(
                            f"🛑 当前页最老文件时间 {oldest_page_time.strftime('%Y-%m-%d %H:%M:%S')} "
                            f"早于目标起始时间 {stop_before_time.strftime('%Y-%m-%d')}，停止继续收集更早文件"
                        )
                        break
                
                next_page = time_collection_next_page_plan(next_index)
                self.log(next_page["message"])
                if next_page["has_next"]:
                    current_index = next_page["next_index"]
                    time.sleep(random.uniform(2, 5))
                else:
                    break

        except KeyboardInterrupt:
            self.log(f"⏹️ 用户中断收集")
        except Exception as e:
            self.log(f"❌ 收集过程异常: {e}")

        # 最终统计
        final_stats = self.file_db.get_database_stats()
        summary = time_collection_final_summary(
            final_stats,
            initial_files,
            total_imported_stats,
            page_count,
        )

        self.log(f"🎉 完整文件列表收集完成:")
        self.log(f"   📊 处理页数: {page_count}")
        self.log(f"   📁 新增文件: {summary['new_files']} (总计: {summary['final_files']})")
        self.log(f"   📋 累计导入统计:")
        for key, value in summary["imported_items"]:
            self.log(f"      {key}: +{value}")

        self.log("   📚 当前数据库状态:")
        for table, count in summary["database_items"]:
            self.log(f"      {table}: {count}")

        return summary["result"]
    
    def collect_incremental_files(self) -> Dict[str, int]:
        """增量收集：从数据库最老时间戳开始继续收集"""
        self.log(f"🔄 开始增量文件收集...")

        # 检查是否需要停止
        if self.check_stop():
            self.log("🛑 任务被停止")
            return {'total_files': 0, 'new_files': 0}

        # 获取数据库时间范围
        time_info = self.get_database_time_range()

        if not time_info['has_data']:
            self.log("📊 数据库为空，将进行全量收集")
            return self.collect_files_by_time()
        
        oldest_time = time_info['oldest_time']
        newest_time = time_info['newest_time']
        total_files = time_info['total_files']
        
        self.log(f"📊 数据库现状:")
        self.log(f"   现有文件数: {total_files}")
        self.log(f"   最老时间: {oldest_time}")
        self.log(f"   最新时间: {newest_time}")

        if not oldest_time:
            self.log("⚠️ 数据库中没有有效的时间信息，进行全量收集")
            return self.collect_files_by_time()

        # 从最老时间戳开始收集更早的文件
        self.log(f"🎯 将从最老时间戳开始收集更早的文件...")
        
        # 将时间戳转换为毫秒数用作index
        try:
            start_index = incremental_start_index(oldest_time)
            self.log(f"🚀 增量收集起始时间戳: {start_index}")

            return self.collect_files_by_time(start_time=start_index)

        except Exception as e:
            self.log(f"⚠️ 时间戳处理失败: {e}")
            self.log("🔄 改为全量收集")
            return self.collect_files_by_time()
    
    def collect_files_for_date_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        last_days: Optional[int] = None,
    ) -> Dict[str, int]:
        normalized_start, normalized_end, stop_before_dt = normalize_date_range(
            start_date=start_date,
            end_date=end_date,
            last_days=last_days,
        )
        for message in date_range_collection_start_messages(normalized_start, normalized_end):
            self.log(message)
        return self.collect_files_by_time(
            sort="by_create_time",
            start_time=None,
            stop_before_time=stop_before_dt,
        )

    def _download_database_file_row(
        self,
        file_row: tuple[Any, Any, Any, Any, Any],
        position: int,
        total_files: int,
        stats: Dict[str, int],
    ) -> None:
        file_id, file_name, file_size, download_count, _create_time = file_row
        self.log(f"【{position}/{total_files}】{file_name}")
        self.log(f"   📊 文件ID: {file_id}, 大小: {file_size/1024:.1f}KB, 下载次数: {download_count}")

        file_info = database_download_file_info(file_id, file_name, file_size, download_count)

        result = self.download_file(file_info)

        if result == "skipped":
            stats['skipped'] += 1
            self.log(f"   ⚠️ 文件已跳过")
        elif result:
            stats['downloaded'] += 1
            self.check_long_delay()
            if position < total_files:
                self.download_delay()
        else:
            stats['failed'] += 1
            self.log(f"   ❌ 下载失败")

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
        for message in database_download_start_messages(max_files, status_filter):
            self.log(message)
        legacy_recent_days = kwargs.get('recent_days')
        if last_days is None and legacy_recent_days is not None:
            last_days = legacy_recent_days

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

        # 检查是否需要停止
        if self.check_stop():
            self.log("🛑 任务被停止")
            return download_result_stats()
        self.file_db.cursor.execute(query_plan["query"], query_plan["params"])
        files_to_download = self.file_db.cursor.fetchall()
        
        if not files_to_download:
            self.log(f"📭 数据库中没有符合条件的文件可下载")
            return download_result_stats()

        self.log(f"📋 找到 {len(files_to_download)} 个待下载文件")
        time_range_message = database_download_time_range_message(files_to_download, sort_by)
        if time_range_message:
            self.log(time_range_message)

        stats = download_result_stats(len(files_to_download))

        for i, file_row in enumerate(files_to_download, 1):
            # 检查是否需要停止
            if self.check_stop():
                self.log("🛑 下载任务被停止")
                break

            try:
                self._download_database_file_row(file_row, i, len(files_to_download), stats)
            except KeyboardInterrupt:
                self.log(f"⏹️ 用户中断下载")
                break
            except Exception as e:
                self.log(f"   ❌ 处理文件异常: {e}")
                stats['failed'] += 1
                continue

        for message in database_download_completion_messages(stats):
            self.log(message)
        
        return stats
    
    def show_database_stats(self):
        """显示完整数据库统计信息"""
        print(f"\n📊 完整数据库统计信息:")
        print("="*60)
        print(f"📁 PostgreSQL schema: {CORE_SCHEMA}")
        
        # 使用新数据库的统计方法
        stats = self.file_db.get_database_stats()
        
        # 主要数据统计
        total_files = stats.get('files', 0)
        total_topics = stats.get('topics', 0)
        total_users = stats.get('users', 0)
        total_groups = stats.get('groups', 0)
        
        print(f"📈 核心数据:")
        print(f"   📄 文件数量: {total_files:,}")
        print(f"   💬 话题数量: {total_topics:,}")
        print(f"   👥 用户数量: {total_users:,}")
        print(f"   🏠 群组数量: {total_groups:,}")
        
        # 文件大小统计
        self.file_db.cursor.execute(
            "SELECT SUM(size) FROM files WHERE group_id = ? AND size IS NOT NULL",
            (_query_group_id(self.group_id),),
        )
        result = self.file_db.cursor.fetchone()
        total_size = result[0] if result and result[0] else 0
        
        if total_size > 0:
            print(f"💾 总文件大小: {total_size/1024/1024:.2f} MB")
        
        # 详细表统计
        print(f"\n📋 详细表统计:")
        for table_name, count in stats.items():
            if count > 0:
                emoji = database_stats_table_emoji(table_name)
                print(f"   {emoji} {table_name}: {count:,}")
        
        # 文件创建时间范围
        self.file_db.cursor.execute('''
            SELECT MIN(create_time), MAX(create_time), COUNT(*) 
            FROM files 
            WHERE group_id = ? AND create_time IS NOT NULL
        ''', (_query_group_id(self.group_id),))
        time_result = self.file_db.cursor.fetchone()
        
        if time_result and time_result[2] > 0:
            min_time, max_time, time_count = time_result
            print(f"\n⏰ 文件时间范围:")
            print(f"   最早文件: {min_time}")
            print(f"   最新文件: {max_time}")
            print(f"   有时间信息的文件: {time_count:,}")
        
        # API响应统计
        self.file_db.cursor.execute('''
            SELECT succeeded, COUNT(*) 
            FROM api_responses 
            GROUP BY succeeded
        ''')
        api_stats = self.file_db.cursor.fetchall()
        
        if api_stats:
            print(f"\n📡 API响应统计:")
            for succeeded, count in api_stats:
                status = "成功" if succeeded else "失败"
                emoji = "✅" if succeeded else "❌"
                print(f"   {emoji} {status}: {count:,}")
        
        print("="*60)
    
    def adjust_settings(self):
        """调整下载设置"""
        print(f"\n🔧 当前下载设置:")
        print(f"   下载间隔: {self.download_interval_min}-{self.download_interval_max}秒 ({self.download_interval_min/60:.1f}-{self.download_interval_max/60:.1f}分钟)")
        print(f"   长休眠间隔: 每{self.long_delay_interval}个文件")
        print(f"   长休眠时间: {self.long_delay_min}-{self.long_delay_max}秒 ({self.long_delay_min/60:.1f}-{self.long_delay_max/60:.1f}分钟)")
        print(f"   下载目录: {self.download_dir}")
        
        try:
            new_interval = int(input(f"长休眠间隔 (当前每{self.long_delay_interval}个文件): ") or self.long_delay_interval)
            new_dir = input(f"下载目录 (当前: {self.download_dir}): ").strip() or self.download_dir
            
            self.long_delay_interval = max(new_interval, 1)
            
            if new_dir != self.download_dir:
                self.download_dir = new_dir
                os.makedirs(new_dir, exist_ok=True)
                print(f"📁 下载目录已更新: {os.path.abspath(new_dir)}")
            
            print(f"✅ 设置已更新")
            
        except ValueError:
            print("❌ 输入无效，保持原设置")
    
    def close(self):
        """关闭资源"""
        if hasattr(self, 'file_db') and self.file_db:
            self.file_db.close()
            print("🔒 文件数据库连接已关闭")
