from __future__ import annotations

from typing import Any, Dict

from backend.core.console_output import safe_console_print as print
from backend.storage.zsxq_database import TopicImportResult


def _query_group_id(group_id: str):
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def _add_topic_import_result(stats: Dict[str, int], result: TopicImportResult) -> bool:
    if result.status == "created":
        stats["new_topics"] += 1
        return True
    if result.status == "existing":
        stats["updated_topics"] += 1
        return True
    stats["errors"] += 1
    return False


class TopicIngestionMixin:
    """Topic database ingestion behavior for ZSXQ topic crawlers."""
    def store_batch_data(self, data: Dict[str, Any]) -> Dict[str, int]:
        """批量存储数据到数据库"""
        # 在数据存储前检查停止标志
        if self.is_stopped():
            self.log("🛑 数据存储前检测到停止信号")
            return {'new_topics': 0, 'updated_topics': 0, 'errors': 0}

        if not data or not data.get('succeeded'):
            return {'new_topics': 0, 'updated_topics': 0, 'errors': 0}

        topics = data.get('resp_data', {}).get('topics', [])
        if not topics:
            return {'new_topics': 0, 'updated_topics': 0, 'errors': 0}

        stats = {'new_topics': 0, 'updated_topics': 0, 'errors': 0}

        for topic_data in topics:
            # 在处理每个话题前检查停止标志
            if self.is_stopped():
                self.log("🛑 话题处理过程中检测到停止信号")
                break

            try:
                topic_id = topic_data.get('topic_id')

                # 导入数据
                import_result = self.db.import_topic_data_with_result(topic_data)
                if not _add_topic_import_result(stats, import_result):
                    self.log(f"⚠️ 话题 {topic_id} 导入失败，已回滚该话题写入")
                    continue

                # 检查是否需要获取更多评论
                comments_count = topic_data.get('comments_count', 0)
                if comments_count > 8:
                    self.log(f"📝 话题 {topic_id} 有 {comments_count} 条评论，尝试获取完整评论列表...")
                    try:
                        additional_comments = self.fetch_all_comments(topic_id, comments_count)
                        if additional_comments:
                            self.db.import_additional_comments(topic_id, additional_comments)
                            self.log(f"✅ 成功获取并导入 {len(additional_comments)} 条额外评论")
                        else:
                            self.log(f"ℹ️ 话题 {topic_id} 无法获取更多评论，可能是权限限制")
                    except Exception as e:
                        self.log(f"⚠️ 话题 {topic_id} 获取评论时出错: {e}")
                        # 不影响话题本身的导入

            except Exception as e:
                stats['errors'] += 1
                print(f"   ⚠️ 话题导入失败: {e}")

        # 提交事务
        self.log(f"💾 批量入库完成，准备提交: 新增{stats['new_topics']}, 更新{stats['updated_topics']}, 错误{stats['errors']}")
        self.db.conn.commit()
        self.log("✅ 数据库提交完成")
        return stats


