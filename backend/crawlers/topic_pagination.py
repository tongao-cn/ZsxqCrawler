from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.core.console_output import safe_console_print as print
from backend.crawlers.topic_ingestion import _query_group_id


TOPIC_PAGINATION_MAX_RETRIES_PER_PAGE = 10


def _format_offset_zsxq_end_time(value: str, delta: Any) -> str:
    from datetime import datetime

    dt = datetime.fromisoformat(value.replace('+0800', '+08:00'))
    dt = dt - delta
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'


def _offset_zsxq_end_time(value: str, offset_ms: int) -> str:
    from datetime import timedelta

    return _format_offset_zsxq_end_time(value, timedelta(milliseconds=offset_ms))


def _offset_zsxq_end_time_by_hours(value: str, hours: int) -> str:
    from datetime import timedelta

    return _format_offset_zsxq_end_time(value, timedelta(hours=hours))


class TopicPaginationMixin:
    """Pagination strategies for ZSXQ topic crawlers."""
    def _topic_next_end_time(self, topics: List[Dict[str, Any]]) -> Optional[str]:
        if not topics:
            return None
        original_time = topics[-1].get('create_time')
        if not original_time:
            self.log("   ⚠️ 最后一条话题缺少 create_time，停止继续翻页")
            return None
        try:
            return _offset_zsxq_end_time(original_time, self.timestamp_offset_ms)
        except Exception as e:
            self.log(f"   ⚠️ 时间戳调整失败: {e}")
            return original_time

    def crawl_latest(self, count: int = 20) -> Dict[str, int]:
        """爬取最新话题"""
        print(f"\n🆕 爬取最新 {count} 个话题...")

        data = self.fetch_topics_safe(scope="all", count=count)
        if data:
            stats = self.store_batch_data(data)
            self.log(f"💾 存储结果: 新增{stats['new_topics']}, 更新{stats['updated_topics']}")
            return stats
        else:
            print("❌ 获取失败")
            return {'new_topics': 0, 'updated_topics': 0, 'errors': 1}

    def crawl_historical(self, pages: int = 10, per_page: int = 20) -> Dict[str, int]:
        """爬取历史数据"""
        print(f"\n📚 爬取历史数据: {pages}页 x {per_page}条/页")

        total_stats = {'new_topics': 0, 'updated_topics': 0, 'errors': 0, 'pages': 0}
        end_time = None
        completed_pages = 0
        max_retries_per_page = TOPIC_PAGINATION_MAX_RETRIES_PER_PAGE

        while completed_pages < pages:
            # 检查停止标志
            if self.is_stopped():
                self.log("🛑 任务已停止")
                break

            current_page = completed_pages + 1
            self.log(f"\n📄 页面 {current_page}/{pages}")
            retry_count = 0

            # 重试当前页直到成功或达到最大重试次数
            while retry_count < max_retries_per_page:
                # 在重试循环中也检查停止标志
                if self.is_stopped():
                    return total_stats

                if retry_count > 0:
                    self.log(f"   🔄 第{retry_count}次重试")

                # 获取数据
                if current_page == 1:
                    data = self.fetch_topics_safe(scope="all", count=per_page, is_historical=True)
                else:
                    data = self.fetch_topics_safe(scope="all", count=per_page, 
                                                end_time=end_time, is_historical=True)

                if data:
                    # 成功获取数据
                    topics = data.get('resp_data', {}).get('topics', [])
                    if not topics:
                        print(f"   📭 无更多数据，停止爬取")
                        return total_stats

                    # 存储数据
                    page_stats = self.store_batch_data(data)
                    self.log(f"   💾 页面存储: 新增{page_stats['new_topics']}, 更新{page_stats['updated_topics']}")

                    # 累计统计
                    total_stats['new_topics'] += page_stats['new_topics']
                    total_stats['updated_topics'] += page_stats['updated_topics']
                    total_stats['errors'] += page_stats['errors']
                    total_stats['pages'] += 1
                    completed_pages += 1

                    # 调试：显示所有话题的时间戳（只在调试模式下）
                    if self.debug_mode:
                        self.log(f"   🔍 调试信息:")
                        self.log(f"   📊 本页获取到 {len(topics)} 个话题")
                        for i, topic in enumerate(topics):
                            topic_time = topic.get('create_time', 'N/A')
                            topic_title = topic.get('title', '无标题')[:30]
                            self.log(f"   {i+1:2d}. {topic_time} - {topic_title}")

                    # 准备下一页的时间戳
                    next_end_time = self._topic_next_end_time(topics)
                    if not next_end_time:
                        return total_stats
                    end_time = next_end_time
                    print(f"   📅 原始时间戳: {topics[-1].get('create_time')}")
                    print(f"   ⏭️ 下一页时间戳: {end_time} (减去{self.timestamp_offset_ms}毫秒)")

                    # 检查是否已爬完
                    if len(topics) < per_page:
                        print(f"   📭 已爬取完毕 (返回{len(topics)}条)")
                        return total_stats

                    # 成功，跳出重试循环
                    self.check_page_long_delay()  # 页面成功处理后进行长休眠检查
                    break
                else:
                    # 失败，增加重试计数和错误计数
                    retry_count += 1
                    total_stats['errors'] += 1
                    print(f"   ❌ 页面 {current_page} 获取失败 (重试{retry_count}/{max_retries_per_page})")

                    # 调整时间戳用于重试
                    if end_time:
                        try:
                            end_time = _offset_zsxq_end_time(end_time, self.timestamp_offset_ms)
                            print(f"   🔄 调整时间戳: {end_time} (再次减去{self.timestamp_offset_ms}毫秒)")
                        except Exception as e:
                            print(f"   ⚠️ 时间戳调整失败: {e}")

            # 如果重试次数用完仍然失败
            if retry_count >= max_retries_per_page:
                print(f"   🚫 页面 {current_page} 达到最大重试次数，跳过此页")
                # 如果有时间戳，尝试大幅度调整跳过问题区域
                if end_time:
                    try:
                        # 大幅度跳过，减去1小时
                        end_time = _offset_zsxq_end_time_by_hours(end_time, 1)
                        print(f"   ⏰ 大幅度跳过时间段: {end_time} (减去1小时)")
                    except Exception as e:
                        print(f"   ⚠️ 大幅度时间戳调整失败: {e}")
                completed_pages += 1  # 跳过这一页

        print(f"\n🏁 历史爬取完成:")
        print(f"   📄 成功页数: {total_stats['pages']}")
        print(f"   ✅ 新增话题: {total_stats['new_topics']}")
        print(f"   🔄 更新话题: {total_stats['updated_topics']}")
        if total_stats['errors'] > 0:
            print(f"   ❌ 总错误数: {total_stats['errors']}")

        return total_stats

    def crawl_all_historical(self, per_page: int = 20, auto_confirm: bool = False) -> Dict[str, int]:
        """获取所有历史数据：无限爬取直到没有数据（使用增量爬取逻辑）"""
        self.log(f"\n🌊 获取所有历史数据模式 (每页{per_page}条)")
        self.log(f"⚠️ 警告：此模式将持续爬取直到没有数据，可能需要很长时间")

        # 检查数据库状态，如果有数据则使用增量爬取逻辑
        timestamp_info = self.db.get_timestamp_range_info()
        start_end_time = None

        if timestamp_info['has_data']:
            oldest_timestamp = timestamp_info['oldest_timestamp']
            total_existing = timestamp_info['total_topics']

            self.log(f"📊 数据库现状:")
            self.log(f"   现有话题数: {total_existing}")
            self.log(f"   最老时间戳: {oldest_timestamp}")
            self.log(f"   最新时间戳: {timestamp_info['newest_timestamp']}")
            self.log(f"🎯 将从最老时间戳开始继续向历史爬取（增量模式）...")

            # 准备增量爬取的起始时间戳
            try:
                start_end_time = _offset_zsxq_end_time(oldest_timestamp, self.timestamp_offset_ms)
                print(f"🚀 增量爬取起始时间戳: {start_end_time}")
            except Exception as e:
                print(f"⚠️ 时间戳处理失败，使用原时间戳: {e}")
                start_end_time = oldest_timestamp
        else:
            self.log(f"📊 数据库为空，将从最新数据开始爬取")

        # 用户确认（Web API调用时自动确认）
        if not auto_confirm:
            confirm = input("确认开始无限爬取？(y/N): ").lower().strip()
            if confirm != 'y':
                self.log("❌ 用户取消操作")
                return {'new_topics': 0, 'updated_topics': 0, 'errors': 0, 'pages': 0}

        self.log(f"🚀 开始无限历史爬取...")

        total_stats = {'new_topics': 0, 'updated_topics': 0, 'errors': 0, 'pages': 0}
        end_time = start_end_time  # 使用增量爬取的起始时间戳
        current_page = 0
        max_retries_per_page = TOPIC_PAGINATION_MAX_RETRIES_PER_PAGE
        consecutive_empty_pages = 0  # 连续空页面计数
        max_consecutive_empty = 3   # 最大连续空页面数

        while True:
            # 检查停止标志
            if self.is_stopped():
                self.log("🛑 任务已停止")
                break

            current_page += 1
            self.log(f"\n📄 页面 {current_page}")
            retry_count = 0
            page_success = False

            # 重试当前页直到成功或达到最大重试次数
            while retry_count < max_retries_per_page:
                # 在重试循环中也检查停止标志
                if self.is_stopped():
                    return total_stats
                if retry_count > 0:
                    self.log(f"   🔄 第{retry_count}次重试")

                # 获取数据 - 根据是否有起始时间戳决定请求方式
                if current_page == 1 and start_end_time is None:
                    # 数据库为空，从最新开始
                    data = self.fetch_topics_safe(scope="all", count=per_page, is_historical=True)
                else:
                    # 有数据或后续页面，使用 end_time 参数
                    data = self.fetch_topics_safe(scope="all", count=per_page,
                                                end_time=end_time, is_historical=True)

                # 检查是否是会员过期错误
                if data and data.get('expired'):
                    print(f"   ❌ 会员已过期，停止爬取")
                    return data  # 直接返回过期信息

                if data:
                    # 成功获取数据
                    topics = data.get('resp_data', {}).get('topics', [])

                    if not topics:
                        consecutive_empty_pages += 1
                        print(f"   📭 第{consecutive_empty_pages}个空页面")

                        if consecutive_empty_pages >= max_consecutive_empty:
                            print(f"   🏁 连续{max_consecutive_empty}个空页面，所有历史数据爬取完成")
                            print(f"\n🎉 无限爬取完成总结:")
                            print(f"   📄 总页数: {total_stats['pages']}")
                            print(f"   ✅ 新增话题: {total_stats['new_topics']}")
                            print(f"   🔄 更新话题: {total_stats['updated_topics']}")
                            if total_stats['errors'] > 0:
                                print(f"   ❌ 总错误数: {total_stats['errors']}")

                            # 显示最终数据库状态
                            final_db_stats = self.db.get_timestamp_range_info()
                            if final_db_stats['has_data']:
                                print(f"\n📊 最终数据库状态:")
                                print(f"   话题总数: {final_db_stats['total_topics']}")
                                if timestamp_info['has_data']:
                                    print(f"   新增话题: {final_db_stats['total_topics'] - timestamp_info['total_topics']}")
                                print(f"   时间范围: {final_db_stats['oldest_timestamp']} ~ {final_db_stats['newest_timestamp']}")

                            return total_stats

                        # 空页面也算成功，避免无限重试
                        page_success = True
                        break
                    else:
                        consecutive_empty_pages = 0  # 重置连续空页面计数

                    # 检查是否有新数据（避免重复爬取已有数据）
                    new_topics_count = 0
                    for topic in topics:
                        topic_id = topic.get('topic_id')
                        self.db.cursor.execute(
                            'SELECT topic_id FROM topics WHERE topic_id = ? AND group_id = ?',
                            (topic_id, _query_group_id(self.group_id)),
                        )
                        if not self.db.cursor.fetchone():
                            new_topics_count += 1

                    # 存储数据
                    page_stats = self.store_batch_data(data)
                    print(f"   💾 页面存储: 新增{page_stats['new_topics']}, 更新{page_stats['updated_topics']}")

                    # 累计统计
                    total_stats['new_topics'] += page_stats['new_topics']
                    total_stats['updated_topics'] += page_stats['updated_topics']
                    total_stats['errors'] += page_stats['errors']
                    total_stats['pages'] += 1

                    # 显示进度信息
                    print(f"   📊 获取到 {len(topics)} 个话题，其中 {new_topics_count} 个为新话题")
                    print(f"   📈 累计: 新增{total_stats['new_topics']}, 更新{total_stats['updated_topics']}, 页数{total_stats['pages']}")

                    # 调试：显示时间戳信息（简化版）
                    if topics:
                        first_time = topics[0].get('create_time', 'N/A')
                        last_time = topics[-1].get('create_time', 'N/A')
                        print(f"   ⏰ 时间范围: {first_time} ~ {last_time}")

                    # 准备下一页的时间戳
                    next_end_time = self._topic_next_end_time(topics)
                    if not next_end_time:
                        return total_stats
                    end_time = next_end_time

                    # 检查是否返回数据量小于预期（可能接近底部）
                    if len(topics) < per_page:
                        print(f"   ⚠️ 返回数据量({len(topics)})小于预期({per_page})，可能接近历史底部")

                    # 如果没有新话题且数据量不足，可能已达历史底部
                    if new_topics_count == 0 and len(topics) < per_page:
                        print(f"   📭 无新话题且数据量不足，可能已达历史底部")
                        return total_stats

                    # 成功，跳出重试循环
                    page_success = True
                    break
                else:
                    # 失败，增加重试计数和错误计数
                    retry_count += 1
                    total_stats['errors'] += 1
                    print(f"   ❌ 页面 {current_page} 获取失败 (重试{retry_count}/{max_retries_per_page})")

                    # 调整时间戳用于重试
                    if end_time:
                        try:
                            end_time = _offset_zsxq_end_time(end_time, self.timestamp_offset_ms)
                        except Exception as e:
                            print(f"   ⚠️ 时间戳调整失败: {e}")

            # 如果重试次数用完仍然失败
            if not page_success:
                print(f"   🚫 页面 {current_page} 达到最大重试次数")
                # 大幅度跳过问题区域
                if end_time:
                    try:
                        end_time = _offset_zsxq_end_time_by_hours(end_time, 1)
                        print(f"   ⏰ 大幅度跳过时间段: {end_time} (减去1小时)")
                    except Exception as e:
                        print(f"   ⚠️ 大幅度时间戳调整失败: {e}")
            else:
                # 页面成功处理后进行长休眠检查（基于页面数而非请求数）
                self.check_page_long_delay()

            # 每50页显示一次总体进度
            if current_page % 50 == 0:
                print(f"\n🎯 进度报告 (第{current_page}页):")
                print(f"   📊 累计新增: {total_stats['new_topics']}")
                print(f"   📊 累计更新: {total_stats['updated_topics']}")
                print(f"   📊 成功页数: {total_stats['pages']}")
                print(f"   📊 错误次数: {total_stats['errors']}")

                # 显示当前数据库状态
                current_db_stats = self.db.get_timestamp_range_info()
                if current_db_stats['has_data']:
                    print(f"   📊 数据库状态: {current_db_stats['total_topics']}个话题")
                    print(f"   📊 时间范围: {current_db_stats['oldest_timestamp']} ~ {current_db_stats['newest_timestamp']}")

        # 这里理论上不会到达，因为在循环内会return
        return total_stats

    def crawl_incremental(self, pages: int = 10, per_page: int = 20) -> Dict[str, int]:
        """增量爬取：基于数据库最老时间戳继续向历史爬取"""
        print(f"\n📈 增量爬取模式: {pages}页 x {per_page}条/页")

        # 获取数据库时间戳范围信息
        timestamp_info = self.db.get_timestamp_range_info()

        if not timestamp_info['has_data']:
            print("❌ 数据库中没有话题数据，请先进行历史爬取")
            return {'new_topics': 0, 'updated_topics': 0, 'errors': 1}

        oldest_timestamp = timestamp_info['oldest_timestamp']
        total_existing = timestamp_info['total_topics']

        print(f"📊 数据库状态:")
        print(f"   现有话题数: {total_existing}")
        print(f"   最老时间戳: {oldest_timestamp}")
        print(f"   最新时间戳: {timestamp_info['newest_timestamp']}")
        print(f"🎯 将从最老时间戳开始继续向历史爬取...")

        # 准备增量爬取的起始时间戳（在最老时间戳基础上减去偏移量）
        try:
            start_end_time = _offset_zsxq_end_time(oldest_timestamp, self.timestamp_offset_ms)
            print(f"🚀 增量爬取起始时间戳: {start_end_time}")
        except Exception as e:
            print(f"⚠️ 时间戳处理失败，使用原时间戳: {e}")
            start_end_time = oldest_timestamp

        # 执行增量爬取
        total_stats = {'new_topics': 0, 'updated_topics': 0, 'errors': 0, 'pages': 0}
        end_time = start_end_time
        completed_pages = 0
        max_retries_per_page = TOPIC_PAGINATION_MAX_RETRIES_PER_PAGE

        while completed_pages < pages:
            current_page = completed_pages + 1
            self.log(f"\n📄 增量页面 {current_page}/{pages}")
            retry_count = 0

            # 重试当前页直到成功或达到最大重试次数
            while retry_count < max_retries_per_page:
                if retry_count > 0:
                    print(f"   🔄 第{retry_count}次重试")

                # 获取数据 - 总是使用 end_time 参数
                data = self.fetch_topics_safe(scope="all", count=per_page,
                                            end_time=end_time, is_historical=True)

                # 检查是否是会员过期错误
                if data and data.get('expired'):
                    print(f"   ❌ 会员已过期，停止爬取")
                    return data  # 直接返回过期信息

                if data:
                    # 成功获取数据
                    topics = data.get('resp_data', {}).get('topics', [])
                    if not topics:
                        print(f"   📭 无更多历史数据，增量爬取完成")
                        return total_stats

                    # 检查是否有新数据（避免重复爬取已有数据）
                    new_topics_count = 0
                    for topic in topics:
                        topic_id = topic.get('topic_id')
                        self.db.cursor.execute(
                            'SELECT topic_id FROM topics WHERE topic_id = ? AND group_id = ?',
                            (topic_id, _query_group_id(self.group_id)),
                        )
                        if not self.db.cursor.fetchone():
                            new_topics_count += 1

                    print(f"   📊 获取到 {len(topics)} 个话题，其中 {new_topics_count} 个为新话题")

                    # 如果没有新话题且当前页话题数少于预期，可能已到达历史底部
                    if new_topics_count == 0 and len(topics) < per_page:
                        print(f"   📭 无新话题且数据量不足，可能已达历史底部")
                        return total_stats

                    # 存储数据
                    page_stats = self.store_batch_data(data)
                    print(f"   💾 页面存储: 新增{page_stats['new_topics']}, 更新{page_stats['updated_topics']}")

                    # 累计统计
                    total_stats['new_topics'] += page_stats['new_topics']
                    total_stats['updated_topics'] += page_stats['updated_topics']
                    total_stats['errors'] += page_stats['errors']
                    total_stats['pages'] += 1
                    completed_pages += 1

                    # 调试：显示话题时间戳信息
                    if self.debug_mode:
                        print(f"   🔍 调试信息:")
                        print(f"   📊 本页获取到 {len(topics)} 个话题")
                        for i, topic in enumerate(topics):
                            topic_time = topic.get('create_time', 'N/A')
                            topic_title = topic.get('title', '无标题')[:30]
                            print(f"   {i+1:2d}. {topic_time} - {topic_title}")

                    # 准备下一页的时间戳
                    next_end_time = self._topic_next_end_time(topics)
                    if not next_end_time:
                        return total_stats
                    end_time = next_end_time
                    print(f"   ⏭️ 下一页时间戳: {end_time}")

                    # 成功，跳出重试循环
                    self.check_page_long_delay()  # 页面成功处理后进行长休眠检查
                    break
                else:
                    # 失败，增加重试计数和错误计数
                    retry_count += 1
                    total_stats['errors'] += 1

                    # 如果任务已停止，不再打印错误信息和调整时间戳
                    if self.is_stopped():
                        return total_stats

                    print(f"   ❌ 页面 {current_page} 获取失败 (重试{retry_count}/{max_retries_per_page})")

                    # 调整时间戳用于重试
                    if end_time:
                        try:
                            end_time = _offset_zsxq_end_time(end_time, self.timestamp_offset_ms)
                            print(f"   🔄 调整时间戳: {end_time}")
                        except Exception as e:
                            print(f"   ⚠️ 时间戳调整失败: {e}")

            # 如果重试次数用完仍然失败
            if retry_count >= max_retries_per_page:
                # 如果任务已停止，不再打印信息
                if self.is_stopped():
                    return total_stats

                print(f"   🚫 页面 {current_page} 达到最大重试次数，跳过此页")
                # 大幅度跳过问题区域
                if end_time:
                    try:
                        end_time = _offset_zsxq_end_time_by_hours(end_time, 1)
                        print(f"   ⏰ 大幅度跳过时间段: {end_time} (减去1小时)")
                    except Exception as e:
                        print(f"   ⚠️ 大幅度时间戳调整失败: {e}")
                completed_pages += 1  # 跳过这一页

        print(f"\n🏁 增量爬取完成:")
        print(f"   📄 成功页数: {total_stats['pages']}")
        print(f"   ✅ 新增话题: {total_stats['new_topics']}")
        print(f"   🔄 更新话题: {total_stats['updated_topics']}")
        if total_stats['errors'] > 0:
            print(f"   ❌ 总错误数: {total_stats['errors']}")

        # 显示更新后的数据库状态
        updated_info = self.db.get_timestamp_range_info()
        print(f"\n📊 更新后数据库状态:")
        print(f"   话题总数: {updated_info['total_topics']} (+{updated_info['total_topics'] - total_existing})")
        print(f"   时间范围: {updated_info['oldest_timestamp']} ~ {updated_info['newest_timestamp']}")

        return total_stats

    def crawl_latest_until_complete(self, per_page: int = 20) -> Dict[str, int]:
        """获取最新记录：智能增量更新，爬取到与数据库完全衔接为止"""
        print(f"\n🔄 获取最新记录模式 (每页{per_page}条)")
        print(f"💡 智能逻辑：检查最新话题，如有新内容则向后爬取直到与数据库完全衔接")

        # 检查数据库状态
        timestamp_info = self.db.get_timestamp_range_info()
        if not timestamp_info['has_data']:
            self.log("📊 数据库为空，将从最新开始爬取")
            # 空库场景：直接从最新开始增量，直到与已存数据衔接或无更多数据

        print(f"📊 数据库状态:")
        print(f"   现有话题数: {timestamp_info['total_topics']}")
        print(f"   最新时间戳: {timestamp_info['newest_timestamp']}")

        total_stats = {'new_topics': 0, 'updated_topics': 0, 'errors': 0, 'pages': 0}
        end_time = None  # 从最新开始
        current_page = 0
        max_retries_per_page = TOPIC_PAGINATION_MAX_RETRIES_PER_PAGE

        while True:
            # 检查停止标志
            if self.is_stopped():
                break

            current_page += 1
            self.log(f"\n📄 检查页面 {current_page}")
            retry_count = 0
            page_success = False

            # 重试当前页直到成功或达到最大重试次数
            while retry_count < max_retries_per_page:
                # 在重试循环中也检查停止标志
                if self.is_stopped():
                    return total_stats
                if retry_count > 0:
                    print(f"   🔄 第{retry_count}次重试")

                # 获取数据
                if current_page == 1:
                    # 第一页：获取最新话题
                    data = self.fetch_topics_safe(scope="all", count=per_page, is_historical=False)
                else:
                    # 后续页面：使用 end_time 向历史爬取
                    data = self.fetch_topics_safe(scope="all", count=per_page, 
                                                end_time=end_time, is_historical=True)

                if data:
                    # 成功获取数据
                    topics = data.get('resp_data', {}).get('topics', [])

                    if not topics:
                        print(f"   📭 无更多数据，获取完成")
                        break

                    # 检查这一页的话题是否在数据库中全部存在
                    existing_count = 0
                    new_topics_list = []

                    for topic in topics:
                        topic_id = topic.get('topic_id')
                        self.db.cursor.execute(
                            'SELECT topic_id FROM topics WHERE topic_id = ? AND group_id = ?',
                            (topic_id, _query_group_id(self.group_id)),
                        )
                        if self.db.cursor.fetchone():
                            existing_count += 1
                        else:
                            new_topics_list.append(topic)

                    print(f"   📊 页面分析: {len(topics)}个话题，{existing_count}个已存在，{len(new_topics_list)}个新话题")
                    self.log(f"📊 页面分析: {len(topics)}个话题，{existing_count}个已存在，{len(new_topics_list)}个新话题")

                    # 判断是否需要停止
                    if existing_count == len(topics):
                        # 整页话题全部存在于数据库中
                        print(f"   ✅ 整页话题全部存在于数据库，增量更新完成")
                        print(f"\n🎉 获取最新记录完成总结:")
                        print(f"   📄 检查页数: {total_stats['pages']}")
                        print(f"   ✅ 新增话题: {total_stats['new_topics']}")
                        print(f"   🔄 更新话题: {total_stats['updated_topics']}")
                        if total_stats['errors'] > 0:
                            print(f"   ❌ 总错误数: {total_stats['errors']}")

                        # 显示更新后的数据库状态
                        final_db_stats = self.db.get_timestamp_range_info()
                        if final_db_stats['has_data']:
                            print(f"\n📊 数据库最终状态:")
                            print(f"   话题总数: {final_db_stats['total_topics']} (+{final_db_stats['total_topics'] - timestamp_info['total_topics']})")
                            print(f"   时间范围: {final_db_stats['oldest_timestamp']} ~ {final_db_stats['newest_timestamp']}")

                        return total_stats

                    elif existing_count == 0:
                        # 整页话题都是新的，全部存储
                        self.log(f"💾 开始整页入库: {len(topics)}个话题")
                        page_stats = self.store_batch_data(data)
                        print(f"   💾 整页存储: 新增{page_stats['new_topics']}, 更新{page_stats['updated_topics']}")
                        self.log(f"💾 整页入库完成: 新增{page_stats['new_topics']}, 更新{page_stats['updated_topics']}")

                    else:
                        # 部分话题是新的，只存储新话题
                        print(f"   💾 部分存储: 只处理{len(new_topics_list)}个新话题")
                        self.log(f"💾 开始部分入库: {len(new_topics_list)}个新话题")
                        new_topics_count = 0
                        updated_topics_count = 0

                        for new_topic in new_topics_list:
                            try:
                                topic_id = new_topic.get('topic_id')
                                # 检查是否已存在（双重检查）
                                self.db.cursor.execute(
                                    'SELECT topic_id FROM topics WHERE topic_id = ? AND group_id = ?',
                                    (topic_id, _query_group_id(self.group_id)),
                                )
                                exists = self.db.cursor.fetchone()

                                # 导入数据
                                if not self.db.import_topic_data(new_topic):
                                    total_stats['errors'] += 1
                                    print(f"   ⚠️ 话题 {topic_id} 导入失败，已回滚该话题写入")
                                    continue

                                if exists:
                                    updated_topics_count += 1
                                else:
                                    new_topics_count += 1

                            except Exception as e:
                                print(f"   ⚠️ 话题导入失败: {e}")

                        # 提交事务
                        self.log(f"💾 部分入库完成，准备提交: 新增{new_topics_count}, 更新{updated_topics_count}")
                        self.db.conn.commit()
                        self.log("✅ 数据库提交完成")
                        print(f"   💾 新话题存储: 新增{new_topics_count}, 更新{updated_topics_count}")

                        # 更新统计
                        total_stats['new_topics'] += new_topics_count
                        total_stats['updated_topics'] += updated_topics_count

                    # 累计统计（如果是整页存储）
                    if existing_count == 0:
                        total_stats['new_topics'] += page_stats['new_topics']
                        total_stats['updated_topics'] += page_stats['updated_topics']
                        total_stats['errors'] += page_stats['errors']

                    total_stats['pages'] += 1

                    # 显示当前进度
                    print(f"   📈 累计: 新增{total_stats['new_topics']}, 更新{total_stats['updated_topics']}, 页数{total_stats['pages']}")
                    self.log(f"📈 累计: 新增{total_stats['new_topics']}, 更新{total_stats['updated_topics']}, 页数{total_stats['pages']}")

                    # 显示时间戳信息
                    if topics:
                        first_time = topics[0].get('create_time', 'N/A')
                        last_time = topics[-1].get('create_time', 'N/A')
                        print(f"   ⏰ 时间范围: {first_time} ~ {last_time}")
                        self.log(f"⏰ 页面时间范围: {first_time} ~ {last_time}")

                    # 准备下一页的时间戳
                    next_end_time = self._topic_next_end_time(topics)
                    if not next_end_time:
                        return total_stats
                    end_time = next_end_time

                    # 成功，跳出重试循环
                    page_success = True
                    break
                else:
                    # 失败，增加重试计数和错误计数
                    retry_count += 1
                    total_stats['errors'] += 1

                    # 如果任务已停止，不再打印错误信息和调整时间戳
                    if self.is_stopped():
                        return total_stats

                    print(f"   ❌ 页面 {current_page} 获取失败 (重试{retry_count}/{max_retries_per_page})")

                    # 调整时间戳用于重试
                    if end_time:
                        try:
                            end_time = _offset_zsxq_end_time(end_time, self.timestamp_offset_ms)
                        except Exception as e:
                            print(f"   ⚠️ 时间戳调整失败: {e}")

            # 如果重试次数用完仍然失败
            if not page_success:
                # 如果任务已停止，不再打印信息
                if self.is_stopped():
                    break
                print(f"   🚫 页面 {current_page} 达到最大重试次数，停止获取")
                break
            else:
                # 页面成功处理后进行长休眠检查（基于页面数而非请求数）
                self.check_page_long_delay()

        return total_stats


