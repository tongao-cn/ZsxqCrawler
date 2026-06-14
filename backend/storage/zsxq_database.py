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
    topic_detail_scope,
    topic_count_query,
    topic_exists_query,
    topic_files_backfill_query,
    topic_file_payload_from_row,
    topic_file_insert_statement,
    topic_group_id_query,
    topic_image_payloads_from_data,
    topic_insert_statement,
    topic_stats_update_statement,
    topics_by_tag_query,
    topic_tags_from_data,
    update_tag_hid_statement,
    upsert_core_file,
    user_liked_emoji_insert_statement,
    user_insert_statement,
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
    return (
        _like_insert_statement(topic_id, user_id, like_data, timestamp),
        _latest_like_insert_statement(topic_id, user_id, like_data, timestamp),
    )


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
                if 'talk' in topic_data and topic_data['talk'] and 'files' in topic_data['talk']:
                    self._sync_topic_files_to_core_tables(topic_data, topic_data['talk']['files'])
                print(f"话题 {topic_id} 已存在，跳过导入")
                return True
            

            
            # 导入群组信息
            if group_info:
                self._upsert_group(group_info)
            
            # 导入话题相关的所有用户信息
            self._import_all_users(topic_data)
            
            # 导入话题信息
            self._upsert_topic(topic_data)
            
            # 导入话题内容(talk)
            if 'talk' in topic_data and topic_data['talk']:
                self._upsert_talk(topic_id, topic_data['talk'])
            
            # 导入文章信息（如果话题类型是文章）
            self._import_articles(topic_id, topic_data)
            
            # 导入图片信息
            self._import_images(topic_id, topic_data)
            
            # 导入点赞信息
            self._import_likes(topic_id, topic_data)
            
            # 导入表情点赞信息
            self._import_like_emojis(topic_id, topic_data)
            
            # 导入用户表情点赞信息
            self._import_user_liked_emojis(topic_id, topic_data)
            
            # 导入评论信息
            if 'show_comments' in topic_data:
                self._import_comments(topic_id, topic_data['show_comments'])
            
            # 导入问题信息
            if 'question' in topic_data and topic_data['question']:
                self._upsert_question(topic_id, topic_data['question'])
            
            # 导入回答信息
            if 'answer' in topic_data and topic_data['answer']:
                self._upsert_answer(topic_id, topic_data['answer'])
            
            # 导入标签信息
            self._import_tags(topic_id, topic_data)

            # 导入文件信息
            if 'talk' in topic_data and topic_data['talk'] and 'files' in topic_data['talk']:
                self._import_files(topic_id, topic_data['talk']['files'])
                self._sync_topic_files_to_core_tables(topic_data, topic_data['talk']['files'])

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

        tables = ['groups', 'users', 'topics', 'talks', 'articles', 'images',
                 'likes', 'like_emojis', 'user_liked_emojis', 'comments',
                 'questions', 'answers']

        for table in tables:
            try:
                sql, params = _database_stats_count_query(table, self.group_id)
                stats[table] = self._fetch_first_column(sql, params)
            except Exception as e:
                print(f"获取表 {table} 统计信息失败: {e}")
                stats[table] = 0

        return stats
    
    def get_timestamp_range_info(self) -> Dict[str, Any]:
        """获取话题时间戳范围信息"""
        try:
            # 获取最新话题时间
            sql, params = _newest_topic_create_time_query(self.group_id, nullable_scope=True)
            newest_time = self._fetch_optional_first_column(sql, params)
            
            # 获取最老话题时间
            sql, params = _oldest_topic_create_time_query(self.group_id, nullable_scope=True)
            oldest_time = self._fetch_optional_first_column(sql, params)
            
            # 获取话题总数
            sql, params = _topic_count_query(self.group_id)
            total_topics = self._fetch_first_column(sql, params)
            
            # 判断是否有数据
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
    
    def get_oldest_topic_timestamp(self) -> Optional[str]:
        """获取数据库中最老的话题时间戳"""
        try:
            sql, params = _oldest_topic_create_time_query(self.group_id)
            return self._fetch_optional_first_column(sql, params)
        except Exception as e:
            print(f"获取最老话题时间戳失败: {e}")
            return None
    
    def get_newest_topic_timestamp(self) -> Optional[str]:
        """获取数据库中最新的话题时间戳"""
        try:
            sql, params = _newest_topic_create_time_query(self.group_id)
            return self._fetch_optional_first_column(sql, params)
        except Exception as e:
            print(f"获取最新话题时间戳失败: {e}")
            return None
    
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
            self._upsert_comment(topic_id, comment)
            # 导入评论的图片
            image_batch = _comment_image_batch_from_comment(comment)
            if image_batch:
                comment_id, images = image_batch
                self._import_comment_images(topic_id, comment_id, images)

    def import_additional_comments(self, topic_id: int, comments: List[Dict[str, Any]]):
        """导入额外获取的评论信息（来自评论API）"""
        if not comments:
            return

        print(f"📝 导入话题 {topic_id} 的 {len(comments)} 条额外评论...")

        for comment in comments:
            for user_data in _iter_additional_comment_user_payloads(comment):
                self._upsert_user(user_data)

            # 导入评论
            self._upsert_comment(topic_id, comment)

            # 导入评论的图片
            image_batch = _comment_image_batch_from_comment(comment)
            if image_batch:
                comment_id, images = image_batch
                self._import_comment_images(topic_id, comment_id, images)

        print(f"✅ 完成导入 {len(comments)} 条评论")

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
        # 检查talk类型话题中的article字段
        if 'talk' in topic_data and topic_data['talk'] and 'article' in topic_data['talk']:
            article_data = topic_data['talk']['article']
            if article_data:
                self._upsert_article(topic_id, article_data)
                return
        
        # 检查顶层的article字段（如果存在）
        if 'article' in topic_data and topic_data['article']:
            article_data = topic_data['article']
            self._upsert_article(topic_id, article_data)
            return
        
        # 如果话题类型是article但没有article字段，从title等信息构建
        topic_type = topic_data.get('type', '')
        if topic_type == 'article' and topic_data.get('title'):
            article_data = {
                'title': topic_data.get('title', ''),
                'article_id': str(topic_id),  # 使用topic_id作为article_id
                'article_url': '',  # 暂时为空
                'inline_article_url': ''  # 暂时为空
            }
            self._upsert_article(topic_id, article_data)
    
    def _upsert_article(self, topic_id: int, article_data: Dict[str, Any]):
        """插入或更新文章信息"""
        title = article_data.get('title', '')
        article_id = article_data.get('article_id', '')
        
        if not title and not article_id:
            return
        
        # 获取话题的创建时间作为文章创建时间
        sql, params = _topic_create_time_by_id_query(topic_id)
        created_at = self._fetch_first_column_or_default(sql, params, '')
        
        sql, params = _article_insert_statement(
            topic_id,
            title,
            article_id,
            article_data,
            created_at,
        )
        self.cursor.execute(sql, params)

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
                file_id = _upsert_core_file(
                    self.cursor,
                    group_data.get('group_id') if group_data else None,
                    topic_id,
                    file_data,
                )
                if not file_id:
                    continue

                synced_files += 1
                _replace_file_topic_relation(self, file_id, topic_id)

            if synced_files:
                print(f"同步话题文件到文件库: topic_id={topic_data.get('topic_id')}, files={synced_files}")
        except Exception as e:
            print(f"同步话题文件到文件库失败: {e}")
            raise

    def backfill_topic_files_to_core_tables(self, batch_size: int = 500) -> Dict[str, int]:
        """把当前 topic_files 回填到核心 files/file_topic_relations 表。"""
        stats = {'scanned': 0, 'new_files': 0, 'relations': 0, 'topic_files': 0}
        batch_size = max(1, batch_size)

        try:
            sql, params = _topic_files_backfill_query(self.group_id)
            self.cursor.execute(sql, params)
            for row in self.cursor.fetchall():
                stats['scanned'] += 1
                (
                    topic_id, file_id, name, file_hash, size, duration, download_count, file_create_time,
                    group_id, topic_type, title, annotation, topic_create_time,
                    likes_count, tourist_likes_count, rewards_count, comments_count,
                    reading_count, readers_count, digested, sticky, user_liked, user_subscribed,
                    group_name, group_type, background_url,
                ) = row

                sql, params = _file_exists_query(file_id, self.group_id)
                self.cursor.execute(sql, params)
                is_new_file = self.cursor.fetchone() is None

                if group_id and group_name:
                    self._upsert_group({
                        'group_id': group_id,
                        'name': group_name or '',
                        'type': group_type,
                        'background_url': background_url,
                    })

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
            # 检查标签是否已存在
            sql, params = _tag_id_by_name_query(group_id, tag_name)
            self.cursor.execute(sql, params)
            
            result = self.cursor.fetchone()
            if result:
                tag_id = result[0]
                # 更新hid（如果提供了新的hid）
                if hid:
                    sql, params = _update_tag_hid_statement(tag_id, hid)
                    self.cursor.execute(sql, params)
                return tag_id
            else:
                # 插入新标签
                self._execute_timestamped_statement(_insert_tag_statement, group_id, tag_name, hid)

                row = self.cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            print(f"插入标签失败: {e}")
            return None
    
    def _link_topic_tag(self, topic_id: int, tag_id: int):
        """关联话题和标签"""
        try:
            self._execute_timestamped_statement(_insert_topic_tag_statement, topic_id, tag_id)
            
            # 更新标签的话题计数
            sql, params = _refresh_tag_topic_count_statement(tag_id)
            self.cursor.execute(sql, params)
            
        except Exception as e:
            print(f"关联话题标签失败: {e}")

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
            sql, params = _tags_by_group_query(group_id)
            return self._fetch_mapped_rows(sql, params, _format_tag_row)
        except Exception as e:
            print(f"获取标签列表失败: {e}")
            return []
    
    def get_topics_by_tag(self, tag_id: int, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """根据标签获取话题列表"""
        try:
            offset = (page - 1) * per_page
            
            # 获取话题列表 - 包含所有详细信息，与get_group_topics保持一致
            sql, params = _topics_by_tag_query(tag_id, per_page, offset)
            topics = self._fetch_mapped_rows(sql, params, _format_tag_topic_row)
            
            # 获取总数
            sql, params = _topic_count_by_tag_query(tag_id)
            total = self._fetch_first_column(sql, params)
            
            return {
                'topics': topics,
                'pagination': _build_pagination(page, per_page, total)
            }
        except Exception as e:
            print(f"根据标签获取话题失败: {e}")
            return {'topics': [], 'pagination': _build_pagination(page, per_page, 0)}

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
