from __future__ import annotations

import json
import random
import time
from typing import Any, Dict, List, Optional

import requests

from backend.core.console_output import safe_console_print as print
from backend.core.log_redaction import redact_json_like, redact_mapping, redact_response_text
from backend.crawlers.topic_ingestion import TopicIngestionMixin
from backend.crawlers.topic_pagination import TopicPaginationMixin
from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.storage.postgres_core_schema import CORE_SCHEMA
from backend.storage.zsxq_database import ZSXQDatabase


class ZSXQTopicCrawler(TopicIngestionMixin, TopicPaginationMixin):
    """知识星球话题采集器"""
    def __init__(self, cookie: str, group_id: str, log_callback=None):
        self.cookie = self.clean_cookie(cookie)
        self.group_id = group_id
        self.log_callback = log_callback  # 日志回调函数
        self.stop_flag = False  # 停止标志
        self.stop_check_func = None  # 停止检查函数

        self.db = ZSXQDatabase(group_id)
        self.session = requests.Session()

        # 文件下载器（懒加载）
        self.file_downloader = None

        # 基础API配置
        self.base_url = "https://api.zsxq.com"
        self.api_endpoint = f"/v2/groups/{group_id}/topics"

        # 反检测配置
        self.request_count = 0
        self.page_count = 0  # 成功处理的页面数
        self.last_request_time = 0
        self.min_delay = 2.0  # 最小延迟
        self.max_delay = 5.0  # 最大延迟
        self.long_delay_interval = 15  # 每15个页面进行长延迟
        self.debug_mode = False  # 调试模式
        self.timestamp_offset_ms = 1  # 时间戳减去的毫秒数

        # 可配置的间隔参数（用于API调用时覆盖默认值）
        self.use_custom_intervals = False
        self.custom_min_delay = None
        self.custom_max_delay = None
        self.custom_long_delay_min = None
        self.custom_long_delay_max = None
        self.custom_pages_per_batch = None

        self.log(f"🚀 知识星球交互式采集器初始化完成")
        self.log(f"📊 目标群组: {group_id}")
        self.log(f"💾 PostgreSQL schema: {CORE_SCHEMA}")

        # 显示当前数据库状态
        self.show_database_status()

    def set_custom_intervals(self, crawl_interval_min=None, crawl_interval_max=None,
                           long_sleep_interval_min=None, long_sleep_interval_max=None,
                           pages_per_batch=None):
        """设置自定义间隔参数"""
        if any([crawl_interval_min, crawl_interval_max, long_sleep_interval_min,
                long_sleep_interval_max, pages_per_batch]):
            self.use_custom_intervals = True
            self.custom_min_delay = crawl_interval_min
            self.custom_max_delay = crawl_interval_max
            self.custom_long_delay_min = long_sleep_interval_min
            self.custom_long_delay_max = long_sleep_interval_max
            self.custom_pages_per_batch = pages_per_batch

            self.log(f"🔧 使用自定义间隔设置:")
            if crawl_interval_min and crawl_interval_max:
                self.log(f"   页面间隔: {crawl_interval_min}-{crawl_interval_max}秒")
            if long_sleep_interval_min and long_sleep_interval_max:
                self.log(f"   长休眠: {long_sleep_interval_min}-{long_sleep_interval_max}秒")
            if pages_per_batch:
                self.log(f"   批次大小: {pages_per_batch}页")
        else:
            self.use_custom_intervals = False
            self.log(f"🔧 使用默认间隔设置")

    def log(self, message: str):
        """统一的日志输出方法"""
        print(message)  # 仍然输出到控制台
        if self.log_callback:
            self.log_callback(message)  # 同时推送到前端

    def set_stop_flag(self):
        """设置停止标志"""
        self.stop_flag = True
        self.log("🛑 收到停止信号，任务将在下一个检查点停止")

    def is_stopped(self):
        """检查是否被停止"""
        # 首先检查本地停止标志
        if self.stop_flag:
            return True
        # 然后检查外部停止检查函数
        if self.stop_check_func and self.stop_check_func():
            self.stop_flag = True  # 同步本地标志
            return True
        return False

    def _interruptible_sleep(self, duration: float):
        """可中断的睡眠，每0.1秒检查一次停止标志"""
        start_time = time.time()
        while time.time() - start_time < duration:
            if self.is_stopped():
                return
            time.sleep(0.1)  # 短暂睡眠，允许快速响应停止信号

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

    def get_file_downloader(self):
        """获取文件下载器（懒加载）"""
        if self.file_downloader is None:
            self.file_downloader = ZSXQFileDownloader(self.cookie, self.group_id)
        return self.file_downloader

    def show_database_status(self):
        """显示数据库当前状态"""
        stats = self.db.get_database_stats()
        total_topics = stats.get('topics', 0)
        total_users = stats.get('users', 0)
        total_comments = stats.get('comments', 0)

        print(f"\n📊 当前数据库状态:")
        print(f"   话题: {total_topics}, 用户: {total_users}, 评论: {total_comments}")

        # 显示时间戳范围信息
        if total_topics > 0:
            timestamp_info = self.db.get_timestamp_range_info()
            if timestamp_info['has_data']:
                print(f"   时间范围: {timestamp_info['oldest_timestamp']} ~ {timestamp_info['newest_timestamp']}")
            else:
                print(f"   ⚠️ 时间戳数据不完整")

    def get_stealth_headers(self) -> Dict[str, str]:
        """获取隐蔽性更强的请求头"""
        # 更多样化的User-Agent池
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ]

        # 基础头部
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
            "Cache-Control": "no-cache",
            "Cookie": self.cookie,
            "Origin": "https://wx.zsxq.com",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Referer": "https://wx.zsxq.com/",
            "Sec-Ch-Ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": random.choice(user_agents),
            "X-Aduid": "a3be07cd6-dd67-3912-0093-862d844e7fe",
            "X-Request-Id": f"dcc5cb6ab-1bc3-8273-cc26-{random.randint(100000000000, 999999999999)}",
            "X-Signature": "733fd672ddf6d4e367730d9622cdd1e28a4b6203",
            "X-Timestamp": str(int(time.time())),
            "X-Version": "2.77.0"
        }

        # 随机添加可选头部
        optional_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Sec-GPC": "1",
            "Upgrade-Insecure-Requests": "1"
        }

        for key, value in optional_headers.items():
            if random.random() > 0.4:  # 60%概率添加
                headers[key] = value

        return headers

    def smart_delay(self, is_historical: bool = False):
        """智能延迟机制 - 模拟人类行为（仅基础延迟）"""
        self.request_count += 1

        # 基础延迟时间
        if self.use_custom_intervals and self.custom_min_delay and self.custom_max_delay:
            # 使用自定义间隔
            min_delay = self.custom_min_delay
            max_delay = self.custom_max_delay
            if is_historical:
                delay = random.uniform(min_delay, max_delay + 1.0)  # 历史爬取稍长
            else:
                delay = random.uniform(min_delay, max_delay)
            self.log(f"⏱️ 页面间隔: {delay:.2f}秒 [自定义范围: {min_delay}-{max_delay}秒]")
        else:
            # 使用默认间隔
            if is_historical:
                delay = random.uniform(self.min_delay + 1.0, self.max_delay + 2.0)  # 历史爬取稍长
            else:
                delay = random.uniform(self.min_delay, self.max_delay)
            if self.debug_mode:
                self.log(f"   ⏱️ 延迟: {delay:.2f}秒 (请求#{self.request_count})")

        # 可中断的延迟
        self._interruptible_sleep(delay)
        self.last_request_time = time.time()

    def check_page_long_delay(self):
        """检查页面级长休眠：根据配置进行长休眠"""
        self.page_count += 1

        # 确定长休眠间隔
        if self.use_custom_intervals and self.custom_pages_per_batch:
            interval = self.custom_pages_per_batch
        else:
            interval = self.long_delay_interval

        if self.page_count % interval == 0:
            import datetime

            # 确定长休眠时间
            if self.use_custom_intervals and self.custom_long_delay_min and self.custom_long_delay_max:
                long_delay = random.uniform(self.custom_long_delay_min, self.custom_long_delay_max)
                self.log(f"🛌 长休眠开始: {long_delay:.1f}秒 ({long_delay/60:.1f}分钟) [自定义范围: {self.custom_long_delay_min/60:.1f}-{self.custom_long_delay_max/60:.1f}分钟]")
            else:
                long_delay = random.uniform(180, 300)  # 3-5分钟长休眠
                self.log(f"🛌 长休眠开始: {long_delay:.1f}秒 ({long_delay/60:.1f}分钟) [默认范围: 3-5分钟]")

            start_time = datetime.datetime.now()
            end_time = start_time + datetime.timedelta(seconds=long_delay)

            self.log(f"   已完成 {self.page_count} 个页面，进入长休眠模式...")
            self.log(f"   ⏰ 开始时间: {start_time.strftime('%H:%M:%S')}")
            self.log(f"   🕐 预计恢复: {end_time.strftime('%H:%M:%S')}")

            # 可中断的长延迟
            self._interruptible_sleep(long_delay)

            actual_end_time = datetime.datetime.now()
            self.log(f"😴 长休眠结束，继续爬取...")
            self.log(f"   🕐 实际结束: {actual_end_time.strftime('%H:%M:%S')}")

            # 调试信息
            if self.debug_mode:
                actual_duration = (actual_end_time - start_time).total_seconds()
                print(f"   💤 长休眠完成: 预计{long_delay:.1f}秒，实际{actual_duration:.1f}秒 (页面#{self.page_count})")

    def fetch_comments_safe(self, topic_id: int, begin_time: str = None, count: int = 30, max_retries: int = 10) -> Optional[Dict[str, Any]]:
        """安全获取话题评论，包含重试机制处理反爬"""
        for retry in range(max_retries):
            try:
                # 构建评论API URL
                url = f"https://api.zsxq.com/v2/topics/{topic_id}/comments"
                params = {
                    'sort': 'asc',
                    'count': count,
                    'with_sticky': 'true'
                }

                if begin_time:
                    params['begin_time'] = begin_time

                # 使用与主要API相同的隐蔽性请求头，包含完整的认证信息
                headers = self.get_stealth_headers()

                # 调试模式输出详细信息
                if self.debug_mode and retry == 0:  # 只在第一次尝试时输出
                    from urllib.parse import urlencode
                    full_url = f"{url}?{urlencode(params)}"
                    redacted_headers = redact_mapping(headers)
                    print(f"🔍 评论API调试信息:")
                    print(f"   🔗 完整URL: {full_url}")
                    print(f"   📊 参数: {params}")
                    print(f"   🔧 关键认证头:")
                    print(f"      X-Signature: {redacted_headers.get('X-Signature', 'N/A')}")
                    print(f"      X-Timestamp: {headers.get('X-Timestamp', 'N/A')}")
                    print(f"      X-Request-Id: {redacted_headers.get('X-Request-Id', 'N/A')}")
                    print(f"      X-Aduid: {redacted_headers.get('X-Aduid', 'N/A')}")

                # 发送请求
                response = self.session.get(url, params=params, headers=headers, timeout=30)

                if response.status_code == 200:
                    data = response.json()
                    if data.get('succeeded'):
                        if retry > 0:
                            self.log(f"✅ 评论API重试成功 (第{retry+1}次尝试)")
                        return data
                    else:
                        error_code = data.get('code')
                        error_msg = data.get('error', '未知错误')

                        # 检查是否是反爬错误码1059
                        if error_code == 1059:
                            if retry < max_retries - 1:
                                # 智能等待时间策略：前几次短等待，后面逐渐增加
                                if retry < 3:
                                    wait_time = 2  # 前3次等待2秒
                                elif retry < 6:
                                    wait_time = 5  # 第4-6次等待5秒
                                else:
                                    wait_time = 10  # 第7-10次等待10秒

                                self.log(f"⚠️ 遇到反爬机制 (错误码1059)，等待{wait_time}秒后重试 (第{retry+1}/{max_retries}次)")
                                time.sleep(wait_time)
                                continue
                            else:
                                self.log(f"❌ 评论API重试{max_retries}次后仍失败: 错误码{error_code} - {error_msg}")
                                return None
                        else:
                            self.log(f"❌ 评论API返回失败: 错误码{error_code} - {error_msg}")
                            return None
                else:
                    # 详细的错误日志
                    self.log(f"❌ 评论API请求失败: {response.status_code}")
                    self.log(f"🔗 请求URL: {response.url}")
                    self.log(f"📋 响应内容: {redact_response_text(response.text, limit=500)}")
                    return None

            except Exception as e:
                if retry < max_retries - 1:
                    # 使用与1059错误相同的等待策略
                    if retry < 3:
                        wait_time = 2
                    elif retry < 6:
                        wait_time = 5
                    else:
                        wait_time = 10

                    self.log(f"❌ 获取评论异常: {str(e)}，等待{wait_time}秒后重试 (第{retry+1}/{max_retries}次)")
                    time.sleep(wait_time)
                    continue
                else:
                    self.log(f"❌ 获取评论异常，重试{max_retries}次后仍失败: {str(e)}")
                    return None

        return None

    def fetch_all_comments(self, topic_id: int, comments_count: int) -> List[Dict[str, Any]]:
        """获取话题的所有评论（如果评论数量大于8）"""
        if comments_count <= 8:
            return []  # 不需要额外获取

        self.log(f"📝 话题 {topic_id} 有 {comments_count} 条评论，开始获取完整评论列表...")

        all_comments = []
        begin_time = None
        page = 1

        while True:
            # 检查停止标志
            if self.is_stopped():
                self.log("🛑 评论获取已停止")
                break

            self.log(f"   📄 获取第 {page} 页评论...")

            # 获取当前页评论
            data = self.fetch_comments_safe(topic_id, begin_time, count=30)
            if not data:
                self.log(f"   ❌ 第 {page} 页获取失败，可能是权限问题，跳过此话题")
                break

            comments = data.get('resp_data', {}).get('comments', [])
            if not comments:
                self.log(f"   📭 第 {page} 页无评论，停止获取")
                break

            self.log(f"   ✅ 第 {page} 页获取到 {len(comments)} 条评论")

            # 处理评论数据，包括回复评论
            for comment in comments:
                all_comments.append(comment)

                # 处理回复评论
                if 'replied_comments' in comment and comment['replied_comments']:
                    for reply in comment['replied_comments']:
                        all_comments.append(reply)

            # 如果返回的评论数量少于30，说明已经是最后一页
            if len(comments) < 30:
                self.log(f"   🏁 已获取完所有评论，共 {len(all_comments)} 条")
                break

            # 准备下一页的 begin_time（最后一条评论的时间 + 1毫秒）
            last_comment = comments[-1]
            last_time = last_comment.get('create_time')
            if last_time:
                begin_time = self._increment_time(last_time)
                self.log(f"   ⏭️ 下一页起始时间: {begin_time}")
            else:
                self.log("   ❌ 无法获取最后评论时间，停止获取")
                break

            page += 1

            # 添加延迟避免请求过快
            time.sleep(1)

        return all_comments

    def _increment_time(self, time_str: str) -> str:
        """将时间字符串增加1毫秒"""
        try:
            from datetime import datetime, timedelta
            import re

            # 解析时间字符串，例如: "2025-07-03T12:54:05.849+0800"
            # 提取毫秒部分
            match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d{3})(\+\d{4})', time_str)
            if match:
                base_time = match.group(1)
                milliseconds = int(match.group(2))
                timezone = match.group(3)

                # 增加1毫秒
                milliseconds += 1
                if milliseconds >= 1000:
                    # 需要进位到秒
                    dt = datetime.strptime(base_time, '%Y-%m-%dT%H:%M:%S')
                    dt += timedelta(seconds=1)
                    base_time = dt.strftime('%Y-%m-%dT%H:%M:%S')
                    milliseconds = 0

                return f"{base_time}.{milliseconds:03d}{timezone}"
            else:
                # 如果格式不匹配，直接返回原时间
                return time_str

        except Exception as e:
            self.log(f"❌ 时间增量失败: {e}")
            return time_str

    def fetch_topics_safe(self, scope: str = "all", count: int = 20,
                         begin_time: Optional[str] = None, end_time: Optional[str] = None,
                         is_historical: bool = False) -> Optional[Dict[str, Any]]:
        """安全的话题获取方法"""

        # 智能延迟
        self.smart_delay(is_historical)

        url = f"{self.base_url}{self.api_endpoint}"
        headers = self.get_stealth_headers()

        # 构建参数
        params = {
            "scope": scope,
            "count": str(count)
        }

        if begin_time:
            params["begin_time"] = begin_time
        if end_time:
            params["end_time"] = end_time

        # 不添加额外参数，保持与官网请求一致
        # random_params = {
        #     "_t": str(int(time.time() * 1000)),
        #     "v": "1.0",
        #     "_r": str(random.randint(1000, 9999))
        # }
        # 
        # for key, value in random_params.items():
        #     if random.random() > 0.3:  # 70%概率添加
        #         params[key] = value

        # 构造完整URL用于显示
        from urllib.parse import urlencode
        full_url = f"{url}?{urlencode(params)}"

        self.log(f"🌐 安全请求 #{self.request_count}")
        self.log(f"   🎯 参数: scope={scope}, count={count}")
        if begin_time or end_time:
            self.log(f"   📅 时间区间: {begin_time or '-'} ~ {end_time or '-'}")
        self.log(f"   🔗 完整链接: {full_url}")

        # 调试模式输出详细信息
        if self.debug_mode:
            print(f"   🔍 调试模式:")
            print(f"   📍 基础URL: {url}")
            print(f"   📊 所有参数: {params}")
            print(f"   🔧 请求头: {json.dumps(redact_mapping(headers), ensure_ascii=False, indent=4)}")
            print(f"   🍪 Cookie长度: {len(self.cookie)}字符")
            print(f"   ⏰ 当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 在发起请求前检查停止标志
        if self.is_stopped():
            # 停止时不再打印日志，直接返回
            return None

        try:
            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=10,  # 降低超时时间以便快速响应停止信号
                allow_redirects=True
            )

            self.log(f"   📊 状态: {response.status_code}, 大小: {len(response.content)}B")

            # 请求完成后立即检查停止标志
            if self.is_stopped():
                return None

            if response.status_code == 200:
                try:
                    # 在处理响应前检查停止标志
                    if self.is_stopped():
                        self.log("🛑 响应处理前检测到停止信号")
                        return None

                    data = response.json()
                    if data.get('succeeded'):
                        topics = data.get('resp_data', {}).get('topics', [])
                        self.log(f"   ✅ 获取成功: {len(topics)}个话题")
                        return data
                    else:
                        error_code = data.get('code')
                        error_message = data.get('error', data.get('message', '未知错误'))

                        # 检查是否是会员过期错误
                        if error_code == 14210:
                            print(f"   ❌ 会员已过期: {error_message}")
                            print(f"   📋 完整响应: {json.dumps(redact_json_like(data), ensure_ascii=False, indent=2)}")
                            # 设置过期标志，让调用方知道这是过期错误
                            return {"expired": True, "code": error_code, "message": error_message}
                        else:
                            print(f"   ❌ API失败: {error_message}")
                            print(f"   📋 完整响应: {json.dumps(redact_json_like(data), ensure_ascii=False, indent=2)}")
                            return None
                except json.JSONDecodeError as e:
                    print(f"   ❌ JSON解析失败: {e}")
                    print(f"   📄 响应内容: {redact_response_text(response.text, limit=500)}")
                    print(f"   📋 响应头: {redact_mapping(dict(response.headers))}")
                    return None
            else:
                print(f"   ❌ HTTP错误: {response.status_code}")
                print(f"   📄 响应内容: {redact_response_text(response.text, limit=500)}")
                print(f"   📋 响应头: {redact_mapping(dict(response.headers))}")
                if response.status_code == 429:
                    print("   🚨 触发频率限制，建议增加延迟时间")
                elif response.status_code == 403:
                    print("   🚨 访问被拒绝，可能需要更新Cookie或反检测策略")
                elif response.status_code == 401:
                    print("   🚨 认证失败，请检查Cookie是否过期")
                return None

        except requests.exceptions.Timeout as e:
            print(f"   ❌ 请求超时: {e}")
            print(f"   🔧 建议: 增加超时时间或检查网络连接")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"   ❌ 连接错误: {e}")
            print(f"   🔧 建议: 检查网络连接或DNS设置")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"   ❌ HTTP协议错误: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"   ❌ 请求异常: {e}")
            print(f"   🔧 异常类型: {type(e).__name__}")
            return None

    def close(self):
        """关闭资源"""
        self.db.close()
        print("🔒 数据库连接已关闭")


