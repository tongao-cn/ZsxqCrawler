#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识星球专栏数据库管理模块
用于存储专栏目录、文章和相关信息
"""

from typing import Dict, List, Any, Optional

from backend.storage.db_compat import connect
from backend.storage.zsxq_columns_database_helpers import (
    _column_insert_params,
    _column_row_to_dict,
    _column_topic_insert_params,
    _column_topic_row_to_dict,
    _comment_image_row_to_dict,
    _empty_clear_data_stats,
    _crawl_log_update_parts,
    _empty_stats,
    _group_clear_delete_statements,
    _group_id_param,
    _nullable_group_id_param,
    _pending_file_row_to_dict,
    _pending_files_query,
    _pending_video_row_to_dict,
    _pending_videos_query,
    _scope_group_id_param,
    _stats_count_queries,
    _nest_topic_comments,
    _topic_comment_insert_params,
    _topic_comment_row_to_dict,
    _topic_detail_insert_params,
    _topic_detail_row_to_dict,
    _topic_file_insert_params,
    _topic_file_row_to_dict,
    _topic_image_insert_params,
    _topic_image_row_to_dict,
    _topic_video_insert_params,
    _topic_video_row_to_dict,
    _topic_child_delete_statements,
    _uncached_image_row_to_dict,
    _uncached_images_query,
    _user_insert_params,
)


class ZSXQColumnsDatabase:
    """知识星球专栏数据库管理器"""
    
    def __init__(self, group_id: Optional[str] = None):
        """初始化数据库连接"""
        self.group_id = str(group_id) if group_id is not None else None
        self.conn = connect()
        self.cursor = self.conn.cursor()
        self._init_database()
    
    def _init_database(self):
        """Schema is managed by manage-postgres-core-schema; runtime DDL is disabled."""
        return None

    def insert_column(self, group_id: int, column_data: Dict[str, Any]) -> Optional[int]:
        """插入或更新专栏目录"""
        if not column_data or not column_data.get('column_id'):
            return None
        
        self.cursor.execute('''
            INSERT INTO columns 
            (column_id, group_id, name, cover_url, topics_count, create_time, last_topic_attach_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(column_id) DO UPDATE SET
                group_id = excluded.group_id,
                name = excluded.name,
                cover_url = excluded.cover_url,
                topics_count = excluded.topics_count,
                create_time = excluded.create_time,
                last_topic_attach_time = excluded.last_topic_attach_time
        ''', _column_insert_params(group_id, column_data))
        self.conn.commit()
        return column_data.get('column_id')
    
    def get_columns(self, group_id: int) -> List[Dict[str, Any]]:
        """获取群组的所有专栏目录"""
        self.cursor.execute('''
            SELECT column_id, group_id, name, cover_url, topics_count, 
                   create_time, last_topic_attach_time, imported_at
            FROM columns 
            WHERE group_id = ?
            ORDER BY create_time DESC
        ''', (group_id,))
        
        return [_column_row_to_dict(row) for row in self.cursor.fetchall()]
    
    def get_column(self, column_id: int, group_id: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """获取单个专栏目录"""
        scope_group_id = _scope_group_id_param(group_id if group_id is not None else self.group_id)
        self.cursor.execute('''
            SELECT column_id, group_id, name, cover_url, topics_count,
                   create_time, last_topic_attach_time, imported_at
            FROM columns
            WHERE column_id = ? AND (? IS NULL OR group_id = ?)
        ''', (column_id, scope_group_id, scope_group_id))
        
        row = self.cursor.fetchone()
        return _column_row_to_dict(row) if row else None
    
    # ==================== 专栏文章操作 ====================
    
    def insert_column_topic(self, column_id: int, group_id: int, topic_data: Dict[str, Any]) -> Optional[int]:
        """插入或更新专栏文章列表项"""
        if not topic_data or not topic_data.get('topic_id'):
            return None
        
        self.cursor.execute('''
            INSERT INTO column_topics 
            (topic_id, column_id, group_id, title, text, create_time, attached_to_column_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_id) DO UPDATE SET
                column_id = excluded.column_id,
                group_id = excluded.group_id,
                title = excluded.title,
                text = excluded.text,
                create_time = excluded.create_time,
                attached_to_column_time = excluded.attached_to_column_time
        ''', _column_topic_insert_params(column_id, group_id, topic_data))
        self.conn.commit()
        return topic_data.get('topic_id')
    
    def get_column_topics(self, column_id: int, group_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        """获取专栏下的所有文章列表"""
        scope_group_id = _scope_group_id_param(group_id if group_id is not None else self.group_id)
        self.cursor.execute('''
            SELECT ct.topic_id, ct.column_id, ct.group_id, ct.title, ct.text, 
                   ct.create_time, ct.attached_to_column_time, ct.imported_at,
                   CASE WHEN td.topic_id IS NOT NULL THEN 1 ELSE 0 END as has_detail
            FROM column_topics ct
            LEFT JOIN topic_details td ON ct.topic_id = td.topic_id AND ct.group_id = td.group_id
            WHERE ct.column_id = ? AND (? IS NULL OR ct.group_id = ?)
            ORDER BY ct.attached_to_column_time DESC
        ''', (column_id, scope_group_id, scope_group_id))
        
        return [_column_topic_row_to_dict(row) for row in self.cursor.fetchall()]
    
    # ==================== 文章详情操作 ====================
    
    def insert_user(self, user_data: Dict[str, Any]) -> Optional[int]:
        """插入或更新用户信息"""
        if not user_data or not user_data.get('user_id'):
            return None
        
        self.cursor.execute('''
            INSERT INTO users 
            (user_id, name, alias, avatar_url, description, location)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                alias = excluded.alias,
                avatar_url = excluded.avatar_url,
                description = excluded.description,
                location = excluded.location
        ''', _user_insert_params(user_data))
        return user_data.get('user_id')
    
    def insert_topic_detail(self, group_id: int, topic_data: Dict[str, Any], raw_json: str = None) -> Optional[int]:
        """插入或更新文章详情"""
        if not topic_data or not topic_data.get('topic_id'):
            return None
        
        topic_id = topic_data.get('topic_id')
        
        talk = topic_data.get('talk', {})
        
        self.cursor.execute('''
            INSERT INTO topic_details 
            (topic_id, group_id, type, title, full_text, likes_count, comments_count,
             readers_count, digested, sticky, create_time, modify_time, raw_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(topic_id) DO UPDATE SET
                group_id = excluded.group_id,
                type = excluded.type,
                title = excluded.title,
                full_text = excluded.full_text,
                likes_count = excluded.likes_count,
                comments_count = excluded.comments_count,
                readers_count = excluded.readers_count,
                digested = excluded.digested,
                sticky = excluded.sticky,
                create_time = excluded.create_time,
                modify_time = excluded.modify_time,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
        ''', _topic_detail_insert_params(group_id, topic_data, raw_json))
        
        # 处理作者信息
        if talk and talk.get('owner'):
            owner = talk['owner']
            user_id = self.insert_user(owner)
            if user_id:
                self.cursor.execute('''
                    INSERT INTO topic_owners (topic_id, user_id, owner_type)
                    VALUES (?, ?, 'talk')
                    ON CONFLICT(topic_id, owner_type) DO UPDATE SET
                        user_id = excluded.user_id
                ''', (topic_id, user_id))
        
        # 处理图片
        images = talk.get('images', [])
        for image in images:
            self._insert_image(topic_id, image)
        
        # 处理文件
        files = talk.get('files', [])
        for file in files:
            self._insert_file(topic_id, file)
        
        # 处理语音文件 (content_voice)
        content_voice = topic_data.get('content_voice')
        if content_voice:
            self._insert_file(topic_id, content_voice)
        
        # 处理视频 (talk.video)
        video = talk.get('video')
        if video:
            self._insert_video(topic_id, video)
        
        # 处理评论
        comments = topic_data.get('show_comments', [])
        for comment in comments:
            self._insert_comment(topic_id, comment)
        
        self.conn.commit()
        return topic_id
    
    def _insert_image(self, topic_id: int, image_data: Dict[str, Any]):
        """插入图片信息"""
        if not image_data or not image_data.get('image_id'):
            return
        
        self.cursor.execute('''
            INSERT INTO images 
            (image_id, topic_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
             large_url, large_width, large_height, original_url, original_width, 
             original_height, original_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(image_id) DO UPDATE SET
                topic_id = excluded.topic_id,
                type = excluded.type,
                thumbnail_url = excluded.thumbnail_url,
                thumbnail_width = excluded.thumbnail_width,
                thumbnail_height = excluded.thumbnail_height,
                large_url = excluded.large_url,
                large_width = excluded.large_width,
                large_height = excluded.large_height,
                original_url = excluded.original_url,
                original_width = excluded.original_width,
                original_height = excluded.original_height,
                original_size = excluded.original_size
        ''', _topic_image_insert_params(topic_id, image_data))
    
    def _insert_file(self, topic_id: int, file_data: Dict[str, Any]):
        """插入文件信息"""
        if not file_data or not file_data.get('file_id'):
            return
        
        self.cursor.execute('''
            INSERT INTO files 
            (file_id, topic_id, name, hash, size, duration, download_count, create_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                topic_id = excluded.topic_id,
                name = excluded.name,
                hash = excluded.hash,
                size = excluded.size,
                duration = excluded.duration,
                download_count = excluded.download_count,
                create_time = excluded.create_time
        ''', _topic_file_insert_params(topic_id, file_data))
    
    def _insert_video(self, topic_id: int, video_data: Dict[str, Any]):
        """插入视频信息"""
        if not video_data or not video_data.get('video_id'):
            return
        
        self.cursor.execute('''
            INSERT INTO videos 
            (video_id, topic_id, size, duration, cover_url, cover_width, cover_height)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                topic_id = excluded.topic_id,
                size = excluded.size,
                duration = excluded.duration,
                cover_url = excluded.cover_url,
                cover_width = excluded.cover_width,
                cover_height = excluded.cover_height
        ''', _topic_video_insert_params(topic_id, video_data))
    
    def _insert_comment(self, topic_id: int, comment_data: Dict[str, Any]):
        """插入评论信息"""
        if not comment_data or not comment_data.get('comment_id'):
            return
        
        # 处理评论作者
        owner = comment_data.get('owner', {})
        owner_id = self.insert_user(owner) if owner else None
        
        # 处理被回复者
        repliee = comment_data.get('repliee', {})
        repliee_id = self.insert_user(repliee) if repliee else None
        group_id = self._resolve_topic_group_id(topic_id)
        
        self.cursor.execute('''
            INSERT INTO comments 
            (comment_id, group_id, topic_id, owner_user_id, parent_comment_id, repliee_user_id,
             text, create_time, likes_count, rewards_count, replies_count, sticky)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(comment_id) DO UPDATE SET
                group_id = excluded.group_id,
                topic_id = excluded.topic_id,
                owner_user_id = excluded.owner_user_id,
                parent_comment_id = excluded.parent_comment_id,
                repliee_user_id = excluded.repliee_user_id,
                text = excluded.text,
                create_time = excluded.create_time,
                likes_count = excluded.likes_count,
                rewards_count = excluded.rewards_count,
                replies_count = excluded.replies_count,
                sticky = excluded.sticky
        ''', _topic_comment_insert_params(topic_id, group_id, owner_id, repliee_id, comment_data))

    def _resolve_topic_group_id(self, topic_id: int):
        if self.group_id:
            return _nullable_group_id_param(self.group_id)
        try:
            self.cursor.execute('SELECT group_id FROM topic_details WHERE topic_id = ? LIMIT 1', (topic_id,))
            row = self.cursor.fetchone()
            return row[0] if row and row[0] is not None else None
        except Exception:
            return None

    def import_comments(self, topic_id: int, comments: List[Dict[str, Any]]):
        """导入评论列表（包括嵌套回复），用于持久化从API获取的完整评论"""
        if not comments:
            return 0

        count = 0
        for comment in comments:
            # 插入主评论
            self._insert_comment(topic_id, comment)
            count += 1

            # 插入嵌套的回复评论
            replied_comments = comment.get('replied_comments', [])
            for reply in replied_comments:
                # 确保子评论有正确的 parent_comment_id
                if not reply.get('parent_comment_id'):
                    reply['parent_comment_id'] = comment.get('comment_id')
                self._insert_comment(topic_id, reply)
                count += 1

        self.conn.commit()
        return count

    def get_topic_detail(self, topic_id: int, group_id: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """获取文章详情"""
        scope_group_id = _scope_group_id_param(group_id if group_id is not None else self.group_id)
        self.cursor.execute('''
            SELECT td.topic_id, td.group_id, td.type, td.title, td.full_text,
                   td.likes_count, td.comments_count, td.readers_count,
                   td.digested, td.sticky, td.create_time, td.modify_time,
                   td.raw_json, td.imported_at, td.updated_at,
                   u.user_id, u.name, u.alias, u.avatar_url, u.description, u.location
            FROM topic_details td
            LEFT JOIN topic_owners tow ON td.topic_id = tow.topic_id AND tow.owner_type = 'talk'
            LEFT JOIN users u ON tow.user_id = u.user_id
            WHERE td.topic_id = ? AND (? IS NULL OR td.group_id = ?)
        ''', (topic_id, scope_group_id, scope_group_id))
        
        row = self.cursor.fetchone()
        if not row:
            return None
        
        result = _topic_detail_row_to_dict(row)
        
        # 获取图片
        result['images'] = self.get_topic_images(topic_id, scope_group_id)
        
        # 获取文件
        result['files'] = self.get_topic_files(topic_id, scope_group_id)
        
        # 获取视频
        result['videos'] = self.get_topic_videos(topic_id, scope_group_id)
        
        # 获取评论
        result['comments'] = self.get_topic_comments(topic_id, scope_group_id)
        
        return result
    
    def get_topic_images(self, topic_id: int, group_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        """获取文章的所有图片"""
        scope_group_id = _scope_group_id_param(group_id if group_id is not None else self.group_id)
        self.cursor.execute('''
            SELECT image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
                   large_url, large_width, large_height, original_url, original_width,
                   original_height, original_size, local_path
            FROM images
            WHERE topic_id = ?
              AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topic_details WHERE group_id = ?))
        ''', (topic_id, scope_group_id, scope_group_id))
        
        return [_topic_image_row_to_dict(row) for row in self.cursor.fetchall()]
    
    def get_topic_files(self, topic_id: int, group_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        """获取文章的所有文件"""
        scope_group_id = _scope_group_id_param(group_id if group_id is not None else self.group_id)
        self.cursor.execute('''
            SELECT file_id, name, hash, size, duration, download_count, 
                   create_time, download_status, local_path, download_time
            FROM files
            WHERE topic_id = ?
              AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topic_details WHERE group_id = ?))
        ''', (topic_id, scope_group_id, scope_group_id))
        
        return [_topic_file_row_to_dict(row) for row in self.cursor.fetchall()]
    
    def get_topic_videos(self, topic_id: int, group_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        """获取文章的所有视频"""
        scope_group_id = _scope_group_id_param(group_id if group_id is not None else self.group_id)
        self.cursor.execute('''
            SELECT video_id, size, duration, cover_url, cover_width, cover_height,
                   cover_local_path, video_url, download_status, local_path, download_time
            FROM videos
            WHERE topic_id = ?
              AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topic_details WHERE group_id = ?))
        ''', (topic_id, scope_group_id, scope_group_id))
        
        return [_topic_video_row_to_dict(row) for row in self.cursor.fetchall()]
    
    def update_video_cover_path(self, video_id: int, local_path: str):
        """更新视频封面本地缓存路径"""
        self.cursor.execute('''
            UPDATE videos SET cover_local_path = ?
            WHERE video_id = ?
        ''', (local_path, video_id))
        self.conn.commit()
    
    def update_video_download_status(self, video_id: int, status: str, video_url: str = None, local_path: str = None):
        """更新视频下载状态"""
        if local_path:
            self.cursor.execute('''
                UPDATE videos SET download_status = ?, video_url = ?, local_path = ?, download_time = CURRENT_TIMESTAMP
                WHERE video_id = ?
            ''', (status, video_url, local_path, video_id))
        elif video_url:
            self.cursor.execute('''
                UPDATE videos SET download_status = ?, video_url = ?
                WHERE video_id = ?
            ''', (status, video_url, video_id))
        else:
            self.cursor.execute('''
                UPDATE videos SET download_status = ?
                WHERE video_id = ?
            ''', (status, video_id))
        self.conn.commit()
    
    def get_pending_videos(self, group_id: int = None) -> List[Dict[str, Any]]:
        """获取待下载的视频列表"""
        sql, params = _pending_videos_query(group_id)
        if params:
            self.cursor.execute(sql, params)
        else:
            self.cursor.execute(sql)
        
        return [_pending_video_row_to_dict(row) for row in self.cursor.fetchall()]
    
    def get_topic_comments(self, topic_id: int, group_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        """获取文章的所有评论（支持嵌套结构）"""
        scope_group_id = _scope_group_id_param(group_id if group_id is not None else self.group_id)
        self.cursor.execute('''
            SELECT c.comment_id, c.parent_comment_id, c.text, c.create_time,
                   c.likes_count, c.rewards_count, c.replies_count, c.sticky,
                   u.user_id, u.name, u.alias, u.avatar_url, u.location,
                   r.user_id, r.name, r.alias, r.avatar_url
            FROM comments c
            LEFT JOIN users u ON c.owner_user_id = u.user_id
            LEFT JOIN users r ON c.repliee_user_id = r.user_id
            WHERE c.topic_id = ?
              AND (? IS NULL OR c.group_id = ?)
            ORDER BY c.create_time ASC
        ''', (topic_id, scope_group_id, scope_group_id))

        comments = []

        for row in self.cursor.fetchall():
            comment = _topic_comment_row_to_dict(row)
            comment_id = comment['comment_id']

            # 获取评论图片
            self.cursor.execute('''
                SELECT image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
                       large_url, large_width, large_height, original_url, original_width,
                       original_height, original_size
                FROM images
                WHERE comment_id = ?
                  AND (? IS NULL OR topic_id = ?)
            ''', (comment_id, scope_group_id, topic_id))

            images = [_comment_image_row_to_dict(img_row) for img_row in self.cursor.fetchall()]
            if images:
                comment['images'] = images

            comments.append(comment)

        return _nest_topic_comments(comments)
    
    # ==================== 文件下载状态 ====================
    
    def update_file_download_status(self, file_id: int, status: str, local_path: str = None):
        """更新文件下载状态"""
        group_id = _group_id_param(self.group_id)
        if local_path:
            self.cursor.execute('''
                UPDATE files SET download_status = ?, local_path = ?, download_time = CURRENT_TIMESTAMP
                WHERE file_id = ? AND (? IS NULL OR group_id = ?)
            ''', (status, local_path, file_id, group_id, group_id))
        else:
            self.cursor.execute('''
                UPDATE files SET download_status = ?
                WHERE file_id = ? AND (? IS NULL OR group_id = ?)
            ''', (status, file_id, group_id, group_id))
        self.conn.commit()
    
    def get_pending_files(self, group_id: int = None) -> List[Dict[str, Any]]:
        """获取待下载的文件列表"""
        sql, params = _pending_files_query(group_id)
        if params:
            self.cursor.execute(sql, params)
        else:
            self.cursor.execute(sql)
        
        return [_pending_file_row_to_dict(row) for row in self.cursor.fetchall()]
    
    # ==================== 图片缓存 ====================
    
    def update_image_local_path(self, image_id: int, local_path: str):
        """更新图片本地缓存路径"""
        self.cursor.execute('''
            UPDATE images SET local_path = ?
            WHERE image_id = ?
        ''', (local_path, image_id))
        self.conn.commit()
    
    def get_uncached_images(self, group_id: int = None) -> List[Dict[str, Any]]:
        """获取未缓存的图片列表"""
        sql, params = _uncached_images_query(group_id)
        if params:
            self.cursor.execute(sql, params)
        else:
            self.cursor.execute(sql)
        
        return [_uncached_image_row_to_dict(row) for row in self.cursor.fetchall()]
    
    # ==================== 统计信息 ====================
    
    def get_stats(self, group_id: int) -> Dict[str, Any]:
        """获取专栏数据库统计信息"""
        stats = _empty_stats()

        for key, sql, params in _stats_count_queries(group_id):
            self.cursor.execute(sql, params)
            stats[key] = self.cursor.fetchone()[0]
        
        return stats
    
    # ==================== 采集日志 ====================
    
    def start_crawl_log(self, group_id: int, crawl_type: str) -> int:
        """开始采集日志"""
        self.cursor.execute('''
            INSERT INTO crawl_log (group_id, crawl_type)
            VALUES (?, ?)
            RETURNING id
        ''', (group_id, crawl_type))
        row = self.cursor.fetchone()
        self.conn.commit()
        return row[0] if row else None
    
    def update_crawl_log(self, log_id: int, columns_count: int = 0, topics_count: int = 0,
                         details_count: int = 0, files_count: int = 0,
                         status: str = None, error_message: str = None):
        """更新采集日志"""
        updates, values = _crawl_log_update_parts(
            columns_count=columns_count,
            topics_count=topics_count,
            details_count=details_count,
            files_count=files_count,
            status=status,
            error_message=error_message,
        )
        
        if updates:
            values.append(log_id)
            self.cursor.execute(f'''
                UPDATE crawl_log SET {', '.join(updates)}
                WHERE id = ?
            ''', values)
            self.conn.commit()
    
    # ==================== 增量爬取支持 ====================
    
    def topic_detail_exists(self, topic_id: int) -> bool:
        """检查文章详情是否已存在"""
        self.cursor.execute('SELECT 1 FROM topic_details WHERE topic_id = ?', (topic_id,))
        return self.cursor.fetchone() is not None
    
    def get_existing_topic_ids(self, group_id: int) -> set:
        """获取已存在的文章ID集合"""
        self.cursor.execute('SELECT topic_id FROM topic_details WHERE group_id = ?', (group_id,))
        return {row[0] for row in self.cursor.fetchall()}
    
    # ==================== 数据清理 ====================
    
    def clear_all_data(self, group_id: int) -> Dict[str, int]:
        """清空指定群组的所有专栏数据"""
        stats = _empty_clear_data_stats()
        
        try:
            # 获取该群组的所有topic_id
            self.cursor.execute('SELECT topic_id FROM topic_details WHERE group_id = ?', (group_id,))
            topic_ids = [row[0] for row in self.cursor.fetchall()]
            
            if topic_ids:
                placeholders = ','.join('?' * len(topic_ids))
                
                for stat_key, sql in _topic_child_delete_statements(placeholders):
                    self.cursor.execute(sql, topic_ids)
                    if stat_key:
                        stats[stat_key] = self.cursor.rowcount
            
            for stat_key, sql in _group_clear_delete_statements():
                self.cursor.execute(sql, (group_id,))
                if stat_key:
                    stats[stat_key] = self.cursor.rowcount
            
            self.conn.commit()
            print(f"✅ 清空专栏数据完成: {stats}")
            return stats
            
        except Exception as e:
            self.conn.rollback()
            print(f"❌ 清空数据失败: {e}")
            raise
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()


def main():
    """测试专栏数据库"""
    db = ZSXQColumnsDatabase()
    print("📊 专栏数据库测试完成")
    db.close()


if __name__ == "__main__":
    main()

