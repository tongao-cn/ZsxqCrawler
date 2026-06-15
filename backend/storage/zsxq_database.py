#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Callable, Dict, Any, Optional, List

from backend.storage.db_compat import connect
from backend.storage.zsxq_database_helpers import (
    answer_insert_statement,
    article_insert_statement,
    beijing_now_timestamp,
    build_pagination,
    comment_image_batch_from_comment,
    comment_insert_statement,
    database_stats_count_query,
    delete_latest_likes_statement,
    file_exists_query,
    format_tag_row,
    format_tag_topic_row,
    group_id_param,
    group_insert_statement,
    image_insert_statement,
    insert_tag_statement,
    insert_topic_tag_statement,
    iter_additional_comment_user_payloads,
    iter_topic_user_payloads_from_data,
    iter_valid_comment_image_payloads,
    iter_valid_latest_like_payloads,
    iter_valid_like_emoji_payloads,
    iter_valid_user_liked_emoji_keys,
    like_emoji_insert_statement,
    latest_like_insert_statement,
    like_insert_statement,
    like_insert_statement_pair,
    load_topic_detail_base,
    load_topic_detail_comments,
    load_topic_detail_latest_likes,
    load_topic_detail_likes_detail,
    load_topic_detail_qa,
    load_topic_detail_talk_payload,
    newest_topic_create_time_query,
    nullable_group_id_param,
    oldest_topic_create_time_query,
    question_insert_statement,
    refresh_tag_topic_count_statement,
    replace_file_topic_relation,
    tag_id_by_name_query,
    talk_insert_statement,
    tags_by_group_query,
    topic_create_time_by_id_query,
    topic_count_by_tag_query,
    topic_article_payload_from_data,
    topic_detail_scope,
    topic_count_query,
    topic_exists_query,
    topic_files_backfill_query,
    topic_file_backfill_ids_from_row,
    topic_file_group_payload_from_row,
    topic_file_payload_from_row,
    topic_file_insert_statement,
    topic_group_id_query,
    topic_image_payloads_from_data,
    topic_insert_statement,
    topic_stats_update_statement,
    topic_talk_files_from_data,
    topics_by_tag_query,
    topic_tags_from_data,
    update_tag_hid_statement,
    upsert_core_file,
    user_liked_emoji_insert_statement,
    user_insert_statement,
)


_DATABASE_STATS_TABLES = (
    'groups',
    'users',
    'topics',
    'talks',
    'articles',
    'images',
    'likes',
    'like_emojis',
    'user_liked_emojis',
    'comments',
    'questions',
    'answers',
)


def _beijing_now_timestamp() -> str:
    return beijing_now_timestamp()


def _build_pagination(page: int, per_page: int, total: int) -> Dict[str, int]:
    return build_pagination(page, per_page, total)


def _format_tag_row(row) -> Dict[str, Any]:
    return format_tag_row(row)


def _format_tag_topic_row(topic) -> Dict[str, Any]:
    return format_tag_topic_row(topic)


def _topic_tags_from_data(topic_data: Dict[str, Any]) -> set[tuple[str, str]]:
    return topic_tags_from_data(topic_data)


def _iter_topic_user_payloads_from_data(topic_data: Dict[str, Any]):
    return iter_topic_user_payloads_from_data(topic_data)


def _topic_image_payloads_from_data(topic_data: Dict[str, Any]) -> list[tuple[Any, Optional[Any]]]:
    return topic_image_payloads_from_data(topic_data)


def _iter_valid_like_emoji_payloads(emojis):
    return iter_valid_like_emoji_payloads(emojis)


def _iter_valid_user_liked_emoji_keys(emoji_keys):
    return iter_valid_user_liked_emoji_keys(emoji_keys)


def _iter_valid_latest_like_payloads(latest_likes):
    return iter_valid_latest_like_payloads(latest_likes)


def _iter_valid_comment_image_payloads(images):
    return iter_valid_comment_image_payloads(images)


def _comment_image_batch_from_comment(comment):
    return comment_image_batch_from_comment(comment)


def _iter_additional_comment_user_payloads(comment):
    return iter_additional_comment_user_payloads(comment)


def _tag_id_by_name_query(group_id: int, tag_name: str) -> tuple[str, tuple[Any, ...]]:
    return tag_id_by_name_query(group_id, tag_name)


def _tags_by_group_query(group_id: int) -> tuple[str, tuple[Any, ...]]:
    return tags_by_group_query(group_id)


def _topics_by_tag_query(tag_id: int, per_page: int, offset: int) -> tuple[str, tuple[Any, ...]]:
    return topics_by_tag_query(tag_id, per_page, offset)


def _topic_count_by_tag_query(tag_id: int) -> tuple[str, tuple[Any, ...]]:
    return topic_count_by_tag_query(tag_id)


def _group_insert_statement(group_data: Dict[str, Any], created_at: str) -> tuple[str, tuple[Any, ...]]:
    return group_insert_statement(group_data, created_at)


def _user_insert_statement(user_data: Dict[str, Any], created_at: str) -> tuple[str, tuple[Any, ...]]:
    return user_insert_statement(user_data, created_at)


def _topic_insert_statement(topic_data: Dict[str, Any], imported_at: str) -> tuple[str, tuple[Any, ...]]:
    return topic_insert_statement(topic_data, imported_at)


def _topic_stats_update_statement(
    topic_data: Dict[str, Any],
    topic_id: int,
    scoped_group_id: Any,
    imported_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return topic_stats_update_statement(topic_data, topic_id, scoped_group_id, imported_at)


def _talk_insert_statement(topic_id: int, talk_data: Dict[str, Any], created_at: str) -> tuple[str, tuple[Any, ...]]:
    return talk_insert_statement(topic_id, talk_data, created_at)


def _image_insert_statement(
    topic_id: int,
    image_data: Dict[str, Any],
    comment_id: Optional[int],
    created_at: str,
    *,
    missing_numeric_default: Any = None,
) -> tuple[str, tuple[Any, ...]]:
    return image_insert_statement(
        topic_id,
        image_data,
        comment_id,
        created_at,
        missing_numeric_default=missing_numeric_default,
    )


def _comment_image_insert_statement(
    topic_id: int,
    image_data: Dict[str, Any],
    comment_id: int,
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return _image_insert_statement(
        topic_id,
        image_data,
        comment_id,
        created_at,
        missing_numeric_default=0,
    )


def _delete_latest_likes_statement(topic_id: int) -> tuple[str, tuple[Any, ...]]:
    return delete_latest_likes_statement(topic_id)


def _like_insert_statement(
    topic_id: int,
    user_id: Any,
    like_data: Dict[str, Any],
    imported_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return like_insert_statement(topic_id, user_id, like_data, imported_at)


def _latest_like_insert_statement(
    topic_id: int,
    user_id: Any,
    like_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return latest_like_insert_statement(topic_id, user_id, like_data, created_at)


def _like_insert_statement_pair(
    topic_id: int,
    user_id: Any,
    like_data: Dict[str, Any],
    timestamp: str,
) -> tuple[tuple[str, tuple[Any, ...]], tuple[str, tuple[Any, ...]]]:
    return like_insert_statement_pair(topic_id, user_id, like_data, timestamp)


def _like_emoji_insert_statement(
    topic_id: int,
    emoji_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return like_emoji_insert_statement(topic_id, emoji_data, created_at)


def _user_liked_emoji_insert_statement(topic_id: int, emoji_key: str) -> tuple[str, tuple[Any, ...]]:
    return user_liked_emoji_insert_statement(topic_id, emoji_key)


def _comment_insert_statement(
    topic_id: int,
    comment_id: Any,
    group_id: Any,
    owner_user_id: Any,
    repliee_user_id: Any,
    comment_data: Dict[str, Any],
    imported_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return comment_insert_statement(
        topic_id,
        comment_id,
        group_id,
        owner_user_id,
        repliee_user_id,
        comment_data,
        imported_at,
    )


def _question_insert_statement(
    topic_id: int,
    owner_user_id: Any,
    questionee_user_id: Any,
    is_anonymous: bool,
    question_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return question_insert_statement(
        topic_id,
        owner_user_id,
        questionee_user_id,
        is_anonymous,
        question_data,
        created_at,
    )


def _answer_insert_statement(
    topic_id: int,
    owner_user_id: Any,
    answer_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return answer_insert_statement(topic_id, owner_user_id, answer_data, created_at)


def _article_insert_statement(
    topic_id: int,
    title: str,
    article_id: Any,
    article_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return article_insert_statement(topic_id, title, article_id, article_data, created_at)


def _topic_file_insert_statement(
    topic_id: int,
    file_data: Dict[str, Any],
    created_at: str,
) -> tuple[str, tuple[Any, ...]]:
    return topic_file_insert_statement(topic_id, file_data, created_at)


def _update_tag_hid_statement(tag_id: int, hid: str) -> tuple[str, tuple[Any, ...]]:
    return update_tag_hid_statement(tag_id, hid)


def _insert_tag_statement(
    group_id: int, tag_name: str, hid: Optional[str], created_at: str
) -> tuple[str, tuple[Any, ...]]:
    return insert_tag_statement(group_id, tag_name, hid, created_at)


def _insert_topic_tag_statement(
    topic_id: int, tag_id: int, created_at: str
) -> tuple[str, tuple[Any, ...]]:
    return insert_topic_tag_statement(topic_id, tag_id, created_at)


def _refresh_tag_topic_count_statement(tag_id: int) -> tuple[str, tuple[Any, ...]]:
    return refresh_tag_topic_count_statement(tag_id)


def _replace_file_topic_relation(file_db, file_id: int, topic_id: int) -> int:
    return replace_file_topic_relation(file_db, file_id, topic_id)


def _group_id_param(group_id: Optional[str]) -> Any:
    return group_id_param(group_id)


def _nullable_group_id_param(group_id: Optional[str]) -> Any:
    return nullable_group_id_param(group_id)


def _topic_detail_scope(topic_id: int, group_id: Optional[str]) -> tuple[Any, str, list[Any]]:
    return topic_detail_scope(topic_id, group_id)


def _topic_exists_query(topic_id: int, group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    return topic_exists_query(topic_id, group_id)


def _file_exists_query(file_id: int, group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    return file_exists_query(file_id, group_id)


def _topic_group_id_query(topic_id: int) -> tuple[str, tuple[Any, ...]]:
    return topic_group_id_query(topic_id)


def _topic_create_time_by_id_query(topic_id: int) -> tuple[str, tuple[Any, ...]]:
    return topic_create_time_by_id_query(topic_id)


def _newest_topic_create_time_query(
    group_id: Optional[str], *, nullable_scope: bool = False
) -> tuple[str, tuple[Any, ...]]:
    return newest_topic_create_time_query(group_id, nullable_scope=nullable_scope)


def _oldest_topic_create_time_query(
    group_id: Optional[str], *, nullable_scope: bool = False
) -> tuple[str, tuple[Any, ...]]:
    return oldest_topic_create_time_query(group_id, nullable_scope=nullable_scope)


def _topic_count_query(group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    return topic_count_query(group_id)


def _database_stats_count_query(table: str, group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    return database_stats_count_query(table, group_id)


def _upsert_core_file(cursor, group_id: Optional[int], topic_id: int, file_data: Dict[str, Any]) -> Optional[int]:
    return upsert_core_file(cursor, group_id, topic_id, file_data)


def _topic_files_backfill_query(group_id: Optional[str]) -> tuple[str, tuple[Any, ...]]:
    return topic_files_backfill_query(group_id)


def _topic_file_payload_from_row(row) -> Dict[str, Any]:
    return topic_file_payload_from_row(row)


def _topic_file_backfill_ids_from_row(row) -> tuple[Any, Any, Any]:
    return topic_file_backfill_ids_from_row(row)


def _topic_file_group_payload_from_row(row) -> Optional[Dict[str, Any]]:
    return topic_file_group_payload_from_row(row)


def _topic_talk_files_from_data(topic_data: Dict[str, Any]) -> tuple[bool, Any]:
    return topic_talk_files_from_data(topic_data)


def _topic_article_payload_from_data(topic_id: int, topic_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return topic_article_payload_from_data(topic_id, topic_data)


class ZSXQDatabase:
    """知识星球数据库管理器"""
    
    def __init__(self, group_id: Optional[str] = None):
        self.group_id = str(group_id) if group_id is not None else None
        self.file_db = None
        self.conn = connect()
        self.cursor = self.conn.cursor()
        self._init_database()
    
    def _init_database(self):
        """Schema is managed by manage-postgres-core-schema; runtime DDL is disabled."""
        return None

    def import_topic_data(self, topic_data: Dict[str, Any]) -> bool:
        """导入话题数据到数据库"""
        try:
            topic_id = topic_data.get('topic_id')
            group_info = topic_data.get('group', {})
            
            if not topic_id:
                return False

            # 如果话题已存在，直接跳过，避免重复写入或更新
            sql, params = _topic_exists_query(topic_id, self.group_id)
            self.cursor.execute(sql, params)
            if self.cursor.fetchone():
                self._sync_existing_topic_talk_files(topic_data)
                print(f"话题 {topic_id} 已存在，跳过导入")
                return True
            

            self._import_new_topic_payloads(topic_id, topic_data, group_info)

            return True
            
        except Exception as e:
            self.conn.rollback()
            print(f"导入话题数据失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _upsert_group(self, group_data: Dict[str, Any]):
        """插入或更新群组信息"""
        group_id = group_data.get('group_id')
        if not group_id:
            return

        self._execute_timestamped_statement(_group_insert_statement, group_data)
    
    def _upsert_user(self, user_data: Dict[str, Any]):
        """插入或更新用户信息"""
        user_id = user_data.get('user_id')
        if not user_id:
            return

        self._execute_timestamped_statement(_user_insert_statement, user_data)
    
    def _upsert_topic(self, topic_data: Dict[str, Any]):
        """插入或更新话题信息"""
        topic_id = topic_data.get('topic_id')
        if not topic_id:
            return

        self._execute_timestamped_statement(_topic_insert_statement, topic_data)

    def _import_new_topic_payloads(
        self,
        topic_id: int,
        topic_data: Dict[str, Any],
        group_info: Dict[str, Any],
    ):
        if group_info:
            self._upsert_group(group_info)

        self._import_all_users(topic_data)
        self._upsert_topic(topic_data)

        if 'talk' in topic_data and topic_data['talk']:
            self._upsert_talk(topic_id, topic_data['talk'])

        self._import_articles(topic_id, topic_data)
        self._import_images(topic_id, topic_data)
        self._import_likes(topic_id, topic_data)
        self._import_like_emojis(topic_id, topic_data)
        self._import_user_liked_emojis(topic_id, topic_data)

        if 'show_comments' in topic_data:
            self._import_comments(topic_id, topic_data['show_comments'])

        if 'question' in topic_data and topic_data['question']:
            self._upsert_question(topic_id, topic_data['question'])

        if 'answer' in topic_data and topic_data['answer']:
            self._upsert_answer(topic_id, topic_data['answer'])

        self._import_tags(topic_id, topic_data)
        self._import_new_topic_talk_files(topic_id, topic_data)

    def _sync_existing_topic_talk_files(self, topic_data: Dict[str, Any]):
        has_talk_files, talk_files = _topic_talk_files_from_data(topic_data)
        if has_talk_files:
            self._sync_topic_files_to_core_tables(topic_data, talk_files)

    def _import_new_topic_talk_files(self, topic_id: int, topic_data: Dict[str, Any]):
        has_talk_files, talk_files = _topic_talk_files_from_data(topic_data)
        if has_talk_files:
            self._import_files(topic_id, talk_files)
            self._sync_topic_files_to_core_tables(topic_data, talk_files)
    
    def update_topic_stats(self, topic_data: Dict[str, Any]) -> bool:
        """仅更新话题的统计信息，不导入其他相关数据"""
        try:
            topic_id = topic_data.get('topic_id')
            if not topic_id:
                return False

            # 只更新统计相关字段，不更新内容字段
            scoped_group_id = _group_id_param(self.group_id)
            self._execute_timestamped_statement(_topic_stats_update_statement, topic_data, topic_id, scoped_group_id)

            # 检查是否有行被更新
            if self.cursor.rowcount > 0:
                return True
            else:
                print(f"警告：话题 {topic_id} 不存在，无法更新")
                return False

        except Exception as e:
            print(f"❌ 更新话题统计信息失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _fetch_first_column(self, sql: str, params: Any) -> Any:
        self.cursor.execute(sql, params)
        return self.cursor.fetchone()[0]

    def _execute_timestamped_statement(
        self,
        statement_builder: Callable[..., tuple[str, tuple[Any, ...]]],
        *args: Any,
    ) -> None:
        sql, params = statement_builder(*args, _beijing_now_timestamp())
        self.cursor.execute(sql, params)

    def _execute_timestamped_statements(
        self,
        statement_builder: Callable[..., tuple[tuple[str, tuple[Any, ...]], ...]],
        *args: Any,
    ) -> None:
        for sql, params in statement_builder(*args, _beijing_now_timestamp()):
            self.cursor.execute(sql, params)

    def _fetch_first_column_or_default(self, sql: str, params: Any, default: Any) -> Any:
        self.cursor.execute(sql, params)
        row = self.cursor.fetchone()
        return row[0] if row else default

    def _fetch_optional_first_column(self, sql: str, params: Any) -> Any:
        return self._fetch_first_column_or_default(sql, params, None)

    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        stats = {}

        for table in _DATABASE_STATS_TABLES:
            try:
                stats[table] = self._fetch_database_stat(table)
            except Exception as e:
                print(f"获取表 {table} 统计信息失败: {e}")
                stats[table] = 0

        return stats

    def _fetch_database_stat(self, table: str) -> Any:
        sql, params = _database_stats_count_query(table, self.group_id)
        return self._fetch_first_column(sql, params)
    
    def get_timestamp_range_info(self) -> Dict[str, Any]:
        """获取话题时间戳范围信息"""
        try:
            newest_time, oldest_time, total_topics = self._fetch_timestamp_range_values()
            has_data = newest_time is not None and oldest_time is not None
            
            return {
                'newest_time': newest_time,
                'oldest_time': oldest_time,
                'newest_timestamp': newest_time,
                'oldest_timestamp': oldest_time,
                'total_topics': total_topics,
                'has_data': has_data
            }
            
        except Exception as e:
            print(f"获取时间戳范围信息失败: {e}")
            return {
                'newest_time': None,
                'oldest_time': None,
                'newest_timestamp': None,
                'oldest_timestamp': None,
                'total_topics': 0,
                'has_data': False
            }

    def _fetch_timestamp_range_values(self) -> tuple[Any, Any, int]:
        sql, params = _newest_topic_create_time_query(self.group_id, nullable_scope=True)
        newest_time = self._fetch_optional_first_column(sql, params)

        sql, params = _oldest_topic_create_time_query(self.group_id, nullable_scope=True)
        oldest_time = self._fetch_optional_first_column(sql, params)

        sql, params = _topic_count_query(self.group_id)
        total_topics = self._fetch_first_column(sql, params)
        return newest_time, oldest_time, total_topics
    
    def get_oldest_topic_timestamp(self) -> Optional[str]:
        """获取数据库中最老的话题时间戳"""
        try:
            return self._fetch_topic_create_time(_oldest_topic_create_time_query)
        except Exception as e:
            print(f"获取最老话题时间戳失败: {e}")
            return None
    
    def get_newest_topic_timestamp(self) -> Optional[str]:
        """获取数据库中最新的话题时间戳"""
        try:
            return self._fetch_topic_create_time(_newest_topic_create_time_query)
        except Exception as e:
            print(f"获取最新话题时间戳失败: {e}")
            return None

    def _fetch_topic_create_time(
        self,
        query_builder: Callable[[Any], tuple[str, tuple[Any, ...]]],
    ) -> Optional[str]:
        sql, params = query_builder(self.group_id)
        return self._fetch_optional_first_column(sql, params)
    
    def _import_all_users(self, topic_data: Dict[str, Any]):
        """导入话题相关的所有用户信息"""
        for user_data in _iter_topic_user_payloads_from_data(topic_data):
            self._upsert_user(user_data)
    
    def _upsert_talk(self, topic_id: int, talk_data: Dict[str, Any]):
        """插入或更新话题内容"""
        if not talk_data:
            return
        
        owner_user_id = talk_data.get('owner', {}).get('user_id')
        if not owner_user_id:
            return

        self._execute_timestamped_statement(_talk_insert_statement, topic_id, talk_data)

    
    def _import_images(self, topic_id: int, topic_data: Dict[str, Any]):
        """导入图片信息"""
        # 导入所有图片
        for img_data, comment_id in _topic_image_payloads_from_data(topic_data):
            self._upsert_image(topic_id, img_data, comment_id)
    
    def _upsert_image(self, topic_id: int, image_data: Dict[str, Any], comment_id: Optional[int] = None):
        """插入或更新图片信息"""
        image_id = image_data.get('image_id')
        if not image_id:
            return

        self._execute_timestamped_statement(_image_insert_statement, topic_id, image_data, comment_id)

    
    def _import_likes(self, topic_id: int, topic_data: Dict[str, Any]):
        """导入点赞信息"""
        if 'latest_likes' not in topic_data:
            return

        sql, params = _delete_latest_likes_statement(topic_id)
        self.cursor.execute(sql, params)

        for like, user_id in _iter_valid_latest_like_payloads(topic_data['latest_likes']):
            self._execute_timestamped_statements(
                _like_insert_statement_pair,
                topic_id,
                user_id,
                like,
            )

    def _import_like_emojis(self, topic_id: int, topic_data: Dict[str, Any]):
        """导入表情点赞信息"""
        if 'likes_detail' not in topic_data or 'emojis' not in topic_data['likes_detail']:
            return

        for emoji in _iter_valid_like_emoji_payloads(topic_data['likes_detail']['emojis']):
            self._execute_timestamped_statement(_like_emoji_insert_statement, topic_id, emoji)

    def _import_user_liked_emojis(self, topic_id: int, topic_data: Dict[str, Any]):
        """导入用户表情点赞信息"""
        if 'user_specific' not in topic_data or 'liked_emojis' not in topic_data['user_specific']:
            return

        for emoji_key in _iter_valid_user_liked_emoji_keys(topic_data['user_specific']['liked_emojis']):
            sql, params = _user_liked_emoji_insert_statement(topic_id, emoji_key)
            self.cursor.execute(sql, params)

    def _import_comments(self, topic_id: int, comments: List[Dict[str, Any]]):
        """导入评论信息"""
        for comment in comments:
            self._upsert_comment_with_images(topic_id, comment)

    def import_additional_comments(self, topic_id: int, comments: List[Dict[str, Any]]):
        """导入额外获取的评论信息（来自评论API）"""
        if not comments:
            return

        print(f"📝 导入话题 {topic_id} 的 {len(comments)} 条额外评论...")

        for comment in comments:
            for user_data in _iter_additional_comment_user_payloads(comment):
                self._upsert_user(user_data)

            self._upsert_comment_with_images(topic_id, comment)

        print(f"✅ 完成导入 {len(comments)} 条评论")

    def _upsert_comment_with_images(self, topic_id: int, comment_data: Dict[str, Any]):
        self._upsert_comment(topic_id, comment_data)
        image_batch = _comment_image_batch_from_comment(comment_data)
        if image_batch:
            comment_id, images = image_batch
            self._import_comment_images(topic_id, comment_id, images)

    def _upsert_comment(self, topic_id: int, comment_data: Dict[str, Any]):
        """插入或更新评论信息"""
        comment_id = comment_data.get('comment_id')
        if not comment_id:
            return
        
        owner_user_id = comment_data.get('owner', {}).get('user_id')
        repliee_user_id = comment_data.get('repliee', {}).get('user_id')
        
        group_id = self._resolve_topic_group_id(topic_id, comment_data.get('group_id'))

        self._execute_timestamped_statement(
            _comment_insert_statement,
            topic_id,
            comment_id,
            group_id,
            owner_user_id,
            repliee_user_id,
            comment_data,
        )

    def _resolve_topic_group_id(self, topic_id: int, explicit_group_id: Optional[Any] = None):
        """Resolve group_id for comments fetched separately from topic payloads."""
        group_id = explicit_group_id or self.group_id
        if group_id:
            return _nullable_group_id_param(str(group_id))
        try:
            sql, params = _topic_group_id_query(topic_id)
            return self._fetch_optional_first_column(sql, params)
        except Exception:
            return None

    def _import_comment_images(self, topic_id: int, comment_id: int, images: List[Dict[str, Any]]):
        """导入评论的图片信息"""
        for image in _iter_valid_comment_image_payloads(images):
            self._execute_timestamped_statement(
                _comment_image_insert_statement,
                topic_id,
                image,
                comment_id,
            )

    def _upsert_question(self, topic_id: int, question_data: Dict[str, Any]):
        """插入或更新问题信息"""
        owner_user_id = question_data.get('owner', {}).get('user_id')
        questionee_user_id = question_data.get('questionee', {}).get('user_id')
        is_anonymous = question_data.get('anonymous', False)

        # 对于匿名用户，owner_user_id 可能为 None，但仍需要存储问题信息
        # 只有在既没有 owner_user_id 又没有问题文本时才跳过
        if not owner_user_id and not question_data.get('text'):
            return

        self._execute_timestamped_statement(
            _question_insert_statement,
            topic_id,
            owner_user_id,
            questionee_user_id,
            is_anonymous,
            question_data,
        )

    
    def _upsert_answer(self, topic_id: int, answer_data: Dict[str, Any]):
        """插入或更新回答信息"""
        owner_user_id = answer_data.get('owner', {}).get('user_id')
        
        if not owner_user_id:
            return

        self._execute_timestamped_statement(
            _answer_insert_statement,
            topic_id,
            owner_user_id,
            answer_data,
        )

    
    def _import_articles(self, topic_id: int, topic_data: Dict[str, Any]):
        """导入文章信息"""
        article_data = _topic_article_payload_from_data(topic_id, topic_data)
        if article_data:
            self._upsert_article(topic_id, article_data)

    def _upsert_article(self, topic_id: int, article_data: Dict[str, Any]):
        """插入或更新文章信息"""
        title = article_data.get('title', '')
        article_id = article_data.get('article_id', '')
        
        if not title and not article_id:
            return
        
        created_at = self._fetch_topic_create_time_by_id(topic_id)
        
        sql, params = _article_insert_statement(
            topic_id,
            title,
            article_id,
            article_data,
            created_at,
        )
        self.cursor.execute(sql, params)

    def _fetch_topic_create_time_by_id(self, topic_id: int) -> Any:
        sql, params = _topic_create_time_by_id_query(topic_id)
        return self._fetch_first_column_or_default(sql, params, '')

    def _import_files(self, topic_id: int, files_data: List[Dict[str, Any]]):
        """导入话题文件信息"""
        if not files_data:
            return

        for file_data in files_data:
            if not file_data.get('file_id'):
                continue

            self._execute_timestamped_statement(_topic_file_insert_statement, topic_id, file_data)

    def _sync_topic_files_to_core_tables(self, topic_data: Dict[str, Any], files_data: List[Dict[str, Any]]):
        """把话题采集到的 talk.files 同步到核心 files/relations 表。"""
        if not files_data:
            return

        try:
            group_data = topic_data.get('group', {})
            topic_id = topic_data.get('topic_id')
            if not topic_id:
                return

            synced_files = 0
            for file_data in files_data:
                file_id = self._sync_topic_file_to_core_table(group_data, topic_id, file_data)
                if not file_id:
                    continue

                synced_files += 1

            if synced_files:
                print(f"同步话题文件到文件库: topic_id={topic_data.get('topic_id')}, files={synced_files}")
        except Exception as e:
            print(f"同步话题文件到文件库失败: {e}")
            raise

    def _sync_topic_file_to_core_table(
        self,
        group_data: Dict[str, Any],
        topic_id: Any,
        file_data: Dict[str, Any],
    ) -> Optional[int]:
        file_id = _upsert_core_file(
            self.cursor,
            group_data.get('group_id') if group_data else None,
            topic_id,
            file_data,
        )
        if not file_id:
            return None

        _replace_file_topic_relation(self, file_id, topic_id)
        return file_id

    def backfill_topic_files_to_core_tables(self, batch_size: int = 500) -> Dict[str, int]:
        """把当前 topic_files 回填到核心 files/file_topic_relations 表。"""
        stats = {'scanned': 0, 'new_files': 0, 'relations': 0, 'topic_files': 0}
        batch_size = max(1, batch_size)

        try:
            sql, params = _topic_files_backfill_query(self.group_id)
            self.cursor.execute(sql, params)
            for row in self.cursor.fetchall():
                stats['scanned'] += 1
                topic_id, file_id, group_id = _topic_file_backfill_ids_from_row(row)

                is_new_file = not self._core_file_exists(file_id)

                group_payload = _topic_file_group_payload_from_row(row)
                if group_payload:
                    self._upsert_group(group_payload)

                file_data = _topic_file_payload_from_row(row)
                if _upsert_core_file(self.cursor, group_id, topic_id, file_data):
                    stats['new_files'] += 1 if is_new_file else 0

                if topic_id and file_id:
                    stats['relations'] += _replace_file_topic_relation(self, file_id, topic_id)
                    stats['topic_files'] += 1

                if stats['scanned'] % batch_size == 0:
                    self.conn.commit()

            self.conn.commit()
            return stats
        except Exception:
            self.conn.rollback()
            raise

    def _core_file_exists(self, file_id: int) -> bool:
        sql, params = _file_exists_query(file_id, self.group_id)
        self.cursor.execute(sql, params)
        return self.cursor.fetchone() is not None

    def backfill_topic_files_to_file_database(self) -> Dict[str, int]:
        """兼容旧调用名：PostgreSQL 模式下回填到同一核心表。"""
        return self.backfill_topic_files_to_core_tables()


    def get_topic_detail(self, topic_id: int):
        """获取完整的话题详情"""
        try:
            scoped_group_id, topic_scope_sql, topic_scope_params = _topic_detail_scope(topic_id, self.group_id)

            # 1. 获取基本话题信息和群组信息
            topic_detail = load_topic_detail_base(self.cursor, topic_scope_sql, topic_scope_params)
            if topic_detail is None:
                return None

            # 2. 获取话题内容（talk）
            talk_payload = load_topic_detail_talk_payload(self.cursor, topic_id, scoped_group_id)
            if talk_payload is not None:
                topic_detail["talk"] = talk_payload

            # 3. 获取最新点赞
            topic_detail["latest_likes"] = load_topic_detail_latest_likes(self.cursor, topic_id, scoped_group_id)

            # 4. 获取评论 - 不再限制为10条，返回所有评论
            topic_detail["show_comments"] = load_topic_detail_comments(self.cursor, topic_id, scoped_group_id)

            # 5. 获取点赞详情（表情）
            topic_detail["likes_detail"] = load_topic_detail_likes_detail(self.cursor, topic_id, scoped_group_id)

            # 6. 获取问答数据（如果是问答类型话题）
            if topic_detail["type"] == "q&a":
                topic_detail.update(load_topic_detail_qa(self.cursor, topic_id, scoped_group_id))

            return topic_detail

        except Exception as e:
            print(f"获取话题详情失败: {e}")
            return None
    
    def _import_tags(self, topic_id: int, topic_data: Dict[str, Any]):
        """从话题数据中提取并导入标签信息"""
        group_id = topic_data.get('group', {}).get('group_id')
        if not group_id:
            return

        # 为每个标签创建或更新数据库记录
        for tag_name, hid in _topic_tags_from_data(topic_data):
            tag_id = self._upsert_tag(group_id, tag_name, hid)
            if tag_id:
                self._link_topic_tag(topic_id, tag_id)
    
    def _upsert_tag(self, group_id: int, tag_name: str, hid: str = None) -> Optional[int]:
        """插入或更新标签信息"""
        try:
            tag_id = self._fetch_tag_id_by_name(group_id, tag_name)
            if tag_id:
                self._update_tag_hid_if_present(tag_id, hid)
                return tag_id

            self._execute_timestamped_statement(_insert_tag_statement, group_id, tag_name, hid)
            row = self.cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"插入标签失败: {e}")
            return None

    def _fetch_tag_id_by_name(self, group_id: int, tag_name: str) -> Optional[int]:
        sql, params = _tag_id_by_name_query(group_id, tag_name)
        self.cursor.execute(sql, params)
        row = self.cursor.fetchone()
        return row[0] if row else None

    def _update_tag_hid_if_present(self, tag_id: int, hid: str = None):
        if not hid:
            return

        sql, params = _update_tag_hid_statement(tag_id, hid)
        self.cursor.execute(sql, params)
    
    def _link_topic_tag(self, topic_id: int, tag_id: int):
        """关联话题和标签"""
        try:
            self._insert_topic_tag_relation(topic_id, tag_id)
            self._refresh_tag_topic_count(tag_id)
        except Exception as e:
            print(f"关联话题标签失败: {e}")

    def _insert_topic_tag_relation(self, topic_id: int, tag_id: int):
        self._execute_timestamped_statement(_insert_topic_tag_statement, topic_id, tag_id)

    def _refresh_tag_topic_count(self, tag_id: int):
        sql, params = _refresh_tag_topic_count_statement(tag_id)
        self.cursor.execute(sql, params)

    def _fetch_mapped_rows(
        self,
        sql: str,
        params: Any,
        row_mapper: Callable[[Any], Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        self.cursor.execute(sql, params)
        return [row_mapper(row) for row in self.cursor.fetchall()]
    
    def get_tags_by_group(self, group_id: int) -> List[Dict[str, Any]]:
        """获取指定群组的所有标签"""
        try:
            return self._fetch_tags_by_group(group_id)
        except Exception as e:
            print(f"获取标签列表失败: {e}")
            return []

    def _fetch_tags_by_group(self, group_id: int) -> List[Dict[str, Any]]:
        sql, params = _tags_by_group_query(group_id)
        return self._fetch_mapped_rows(sql, params, _format_tag_row)
    
    def get_topics_by_tag(self, tag_id: int, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """根据标签获取话题列表"""
        try:
            offset = (page - 1) * per_page
            topics = self._fetch_topics_by_tag(tag_id, per_page, offset)
            total = self._fetch_topic_count_by_tag(tag_id)
            
            return {
                'topics': topics,
                'pagination': _build_pagination(page, per_page, total)
            }
        except Exception as e:
            print(f"根据标签获取话题失败: {e}")
            return {'topics': [], 'pagination': _build_pagination(page, per_page, 0)}

    def _fetch_topics_by_tag(self, tag_id: int, per_page: int, offset: int) -> List[Dict[str, Any]]:
        sql, params = _topics_by_tag_query(tag_id, per_page, offset)
        return self._fetch_mapped_rows(sql, params, _format_tag_topic_row)

    def _fetch_topic_count_by_tag(self, tag_id: int) -> int:
        sql, params = _topic_count_by_tag_query(tag_id)
        return self._fetch_first_column(sql, params)

    def close(self):
        """关闭数据库连接"""
        if hasattr(self, 'file_db') and self.file_db:
            self.file_db.close()
            self.file_db = None
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def __del__(self):
        """析构函数，确保数据库连接被关闭"""
        self.close()
