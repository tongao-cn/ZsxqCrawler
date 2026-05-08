#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识星球专栏数据库管理模块
用于存储专栏目录、文章和相关信息
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

from backend.storage.db_compat import connect


def _column_row_to_dict(row) -> Dict[str, Any]:
    return {
        'column_id': row[0],
        'group_id': row[1],
        'name': row[2],
        'cover_url': row[3],
        'topics_count': row[4],
        'create_time': row[5],
        'last_topic_attach_time': row[6],
        'imported_at': row[7]
    }


def _column_topic_row_to_dict(row) -> Dict[str, Any]:
    return {
        'topic_id': row[0],
        'column_id': row[1],
        'group_id': row[2],
        'title': row[3],
        'text': row[4],
        'create_time': row[5],
        'attached_to_column_time': row[6],
        'imported_at': row[7],
        'has_detail': bool(row[8])
    }


def _topic_image_row_to_dict(row) -> Dict[str, Any]:
    return {
        'image_id': row[0],
        'type': row[1],
        'thumbnail': {
            'url': row[2],
            'width': row[3],
            'height': row[4]
        },
        'large': {
            'url': row[5],
            'width': row[6],
            'height': row[7]
        },
        'original': {
            'url': row[8],
            'width': row[9],
            'height': row[10],
            'size': row[11]
        },
        'local_path': row[12]
    }


def _empty_stats() -> Dict[str, int]:
    return {
        'columns_count': 0,
        'topics_count': 0,
        'details_count': 0,
        'images_count': 0,
        'files_count': 0,
        'files_downloaded': 0,
        'videos_count': 0,
        'videos_downloaded': 0,
        'comments_count': 0
    }


def _group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def _nullable_group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    if not value:
        return None
    return int(value) if value.isdigit() else value


def _scope_group_id_param(group_id: Optional[Any]) -> Any:
    return _nullable_group_id_param(group_id)


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
        
        statistics = column_data.get('statistics', {})
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO columns 
            (column_id, group_id, name, cover_url, topics_count, create_time, last_topic_attach_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            column_data.get('column_id'),
            group_id,
            column_data.get('name', ''),
            column_data.get('cover_url'),
            statistics.get('topics_count', 0),
            column_data.get('create_time'),
            column_data.get('last_topic_attach_time')
        ))
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
            INSERT OR REPLACE INTO column_topics 
            (topic_id, column_id, group_id, title, text, create_time, attached_to_column_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            topic_data.get('topic_id'),
            column_id,
            group_id,
            topic_data.get('title'),
            topic_data.get('text'),
            topic_data.get('create_time'),
            topic_data.get('attached_to_column_time')
        ))
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
            INSERT OR REPLACE INTO users 
            (user_id, name, alias, avatar_url, description, location)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user_data.get('user_id'),
            user_data.get('name', ''),
            user_data.get('alias'),
            user_data.get('avatar_url'),
            user_data.get('description'),
            user_data.get('location')
        ))
        return user_data.get('user_id')
    
    def insert_topic_detail(self, group_id: int, topic_data: Dict[str, Any], raw_json: str = None) -> Optional[int]:
        """插入或更新文章详情"""
        if not topic_data or not topic_data.get('topic_id'):
            return None
        
        topic_id = topic_data.get('topic_id')
        
        # 获取文本内容
        talk = topic_data.get('talk', {})
        full_text = talk.get('text', '')
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO topic_details 
            (topic_id, group_id, type, title, full_text, likes_count, comments_count,
             readers_count, digested, sticky, create_time, modify_time, raw_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            topic_id,
            group_id,
            topic_data.get('type'),
            topic_data.get('title'),
            full_text,
            topic_data.get('likes_count', 0),
            topic_data.get('comments_count', 0),
            topic_data.get('readers_count', 0),
            topic_data.get('digested', False),
            topic_data.get('sticky', False),
            topic_data.get('create_time'),
            topic_data.get('modify_time'),
            raw_json
        ))
        
        # 处理作者信息
        if talk and talk.get('owner'):
            owner = talk['owner']
            user_id = self.insert_user(owner)
            if user_id:
                self.cursor.execute('''
                    INSERT OR REPLACE INTO topic_owners (topic_id, user_id, owner_type)
                    VALUES (?, ?, 'talk')
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
        
        thumbnail = image_data.get('thumbnail', {})
        large = image_data.get('large', {})
        original = image_data.get('original', {})
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO images 
            (image_id, topic_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
             large_url, large_width, large_height, original_url, original_width, 
             original_height, original_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            image_data.get('image_id'),
            topic_id,
            image_data.get('type'),
            thumbnail.get('url'),
            thumbnail.get('width'),
            thumbnail.get('height'),
            large.get('url'),
            large.get('width'),
            large.get('height'),
            original.get('url'),
            original.get('width'),
            original.get('height'),
            original.get('size')
        ))
    
    def _insert_file(self, topic_id: int, file_data: Dict[str, Any]):
        """插入文件信息"""
        if not file_data or not file_data.get('file_id'):
            return
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO files 
            (file_id, topic_id, name, hash, size, duration, download_count, create_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            file_data.get('file_id'),
            topic_id,
            file_data.get('name', ''),
            file_data.get('hash'),
            file_data.get('size'),
            file_data.get('duration'),
            file_data.get('download_count', 0),
            file_data.get('create_time')
        ))
    
    def _insert_video(self, topic_id: int, video_data: Dict[str, Any]):
        """插入视频信息"""
        if not video_data or not video_data.get('video_id'):
            return
        
        cover = video_data.get('cover', {})
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO videos 
            (video_id, topic_id, size, duration, cover_url, cover_width, cover_height)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            video_data.get('video_id'),
            topic_id,
            video_data.get('size'),
            video_data.get('duration'),
            cover.get('url'),
            cover.get('width'),
            cover.get('height')
        ))
    
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
            INSERT OR REPLACE INTO comments 
            (comment_id, group_id, topic_id, owner_user_id, parent_comment_id, repliee_user_id,
             text, create_time, likes_count, rewards_count, replies_count, sticky)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            comment_data.get('comment_id'),
            group_id,
            topic_id,
            owner_id,
            comment_data.get('parent_comment_id'),
            repliee_id,
            comment_data.get('text', ''),
            comment_data.get('create_time'),
            comment_data.get('likes_count', 0),
            comment_data.get('rewards_count', 0),
            comment_data.get('replies_count', 0),
            comment_data.get('sticky', False)
        ))

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
        
        result = {
            'topic_id': row[0],
            'group_id': row[1],
            'type': row[2],
            'title': row[3],
            'full_text': row[4],
            'likes_count': row[5],
            'comments_count': row[6],
            'readers_count': row[7],
            'digested': bool(row[8]),
            'sticky': bool(row[9]),
            'create_time': row[10],
            'modify_time': row[11],
            'raw_json': row[12],
            'imported_at': row[13],
            'updated_at': row[14],
            'owner': None,
            'images': [],
            'files': [],
            'comments': []
        }
        
        # 设置作者信息
        if row[15]:
            result['owner'] = {
                'user_id': row[15],
                'name': row[16],
                'alias': row[17],
                'avatar_url': row[18],
                'description': row[19],
                'location': row[20]
            }
        
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
        
        files = []
        for row in self.cursor.fetchall():
            files.append({
                'file_id': row[0],
                'name': row[1],
                'hash': row[2],
                'size': row[3],
                'duration': row[4],
                'download_count': row[5],
                'create_time': row[6],
                'download_status': row[7],
                'local_path': row[8],
                'download_time': row[9]
            })
        return files
    
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
        
        videos = []
        for row in self.cursor.fetchall():
            videos.append({
                'video_id': row[0],
                'size': row[1],
                'duration': row[2],
                'cover': {
                    'url': row[3],
                    'width': row[4],
                    'height': row[5],
                    'local_path': row[6]
                },
                'video_url': row[7],
                'download_status': row[8],
                'local_path': row[9],
                'download_time': row[10]
            })
        return videos
    
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
        if group_id:
            self.cursor.execute('''
                SELECT v.video_id, v.topic_id, v.size, v.duration, v.cover_url, td.group_id
                FROM videos v
                JOIN topic_details td ON v.topic_id = td.topic_id
                WHERE v.download_status = 'pending' AND td.group_id = ?
            ''', (group_id,))
        else:
            self.cursor.execute('''
                SELECT v.video_id, v.topic_id, v.size, v.duration, v.cover_url, td.group_id
                FROM videos v
                JOIN topic_details td ON v.topic_id = td.topic_id
                WHERE v.download_status = 'pending'
            ''')
        
        videos = []
        for row in self.cursor.fetchall():
            videos.append({
                'video_id': row[0],
                'topic_id': row[1],
                'size': row[2],
                'duration': row[3],
                'cover_url': row[4],
                'group_id': row[5]
            })
        return videos
    
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

        # 先收集所有评论，然后构建嵌套结构
        all_comments = {}  # comment_id -> comment_data
        parent_comments = []  # 顶级评论
        child_comments = []   # 子评论（有parent_comment_id的）

        for row in self.cursor.fetchall():
            comment_id = row[0]
            parent_comment_id = row[1]

            comment = {
                'comment_id': comment_id,
                'parent_comment_id': parent_comment_id,
                'text': row[2],
                'create_time': row[3],
                'likes_count': row[4],
                'rewards_count': row[5],
                'replies_count': row[6],
                'sticky': bool(row[7]),
                'owner': None,
                'repliee': None
            }

            if row[8]:
                comment['owner'] = {
                    'user_id': row[8],
                    'name': row[9],
                    'alias': row[10],
                    'avatar_url': row[11],
                    'location': row[12]
                }

            if row[13]:
                comment['repliee'] = {
                    'user_id': row[13],
                    'name': row[14],
                    'alias': row[15],
                    'avatar_url': row[16]
                }

            # 获取评论图片
            self.cursor.execute('''
                SELECT image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
                       large_url, large_width, large_height, original_url, original_width,
                       original_height, original_size
                FROM images
                WHERE comment_id = ?
                  AND (? IS NULL OR topic_id = ?)
            ''', (comment_id, scope_group_id, topic_id))

            images = []
            for img_row in self.cursor.fetchall():
                images.append({
                    'image_id': img_row[0],
                    'type': img_row[1],
                    'thumbnail': {
                        'url': img_row[2],
                        'width': img_row[3],
                        'height': img_row[4]
                    },
                    'large': {
                        'url': img_row[5],
                        'width': img_row[6],
                        'height': img_row[7]
                    },
                    'original': {
                        'url': img_row[8],
                        'width': img_row[9],
                        'height': img_row[10],
                        'size': img_row[11]
                    }
                })
            if images:
                comment['images'] = images

            # 存储评论并分类
            all_comments[comment_id] = comment
            if parent_comment_id:
                child_comments.append(comment)
            else:
                parent_comments.append(comment)

        # 构建嵌套结构：将子评论附加到父评论的 replied_comments 中
        for child in child_comments:
            parent_id = child.get("parent_comment_id")
            if parent_id and parent_id in all_comments:
                parent = all_comments[parent_id]
                if "replied_comments" not in parent:
                    parent["replied_comments"] = []
                parent["replied_comments"].append(child)

        return parent_comments
    
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
        if group_id:
            self.cursor.execute('''
                SELECT f.file_id, f.topic_id, f.name, f.size, f.hash, td.group_id
                FROM files f
                JOIN topic_details td ON f.topic_id = td.topic_id
                WHERE f.download_status = 'pending' AND td.group_id = ?
            ''', (group_id,))
        else:
            self.cursor.execute('''
                SELECT f.file_id, f.topic_id, f.name, f.size, f.hash, td.group_id
                FROM files f
                JOIN topic_details td ON f.topic_id = td.topic_id
                WHERE f.download_status = 'pending'
            ''')
        
        files = []
        for row in self.cursor.fetchall():
            files.append({
                'file_id': row[0],
                'topic_id': row[1],
                'name': row[2],
                'size': row[3],
                'hash': row[4],
                'group_id': row[5]
            })
        return files
    
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
        if group_id:
            self.cursor.execute('''
                SELECT i.image_id, i.topic_id, i.original_url, td.group_id
                FROM images i
                JOIN topic_details td ON i.topic_id = td.topic_id
                WHERE i.local_path IS NULL AND i.original_url IS NOT NULL AND td.group_id = ?
            ''', (group_id,))
        else:
            self.cursor.execute('''
                SELECT i.image_id, i.topic_id, i.original_url, td.group_id
                FROM images i
                JOIN topic_details td ON i.topic_id = td.topic_id
                WHERE i.local_path IS NULL AND i.original_url IS NOT NULL
            ''')
        
        images = []
        for row in self.cursor.fetchall():
            images.append({
                'image_id': row[0],
                'topic_id': row[1],
                'original_url': row[2],
                'group_id': row[3]
            })
        return images
    
    # ==================== 统计信息 ====================
    
    def get_stats(self, group_id: int) -> Dict[str, Any]:
        """获取专栏数据库统计信息"""
        stats = _empty_stats()
        
        self.cursor.execute('SELECT COUNT(*) FROM columns WHERE group_id = ?', (group_id,))
        stats['columns_count'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('SELECT COUNT(*) FROM column_topics WHERE group_id = ?', (group_id,))
        stats['topics_count'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('SELECT COUNT(*) FROM topic_details WHERE group_id = ?', (group_id,))
        stats['details_count'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('''
            SELECT COUNT(*) FROM images i
            JOIN topic_details td ON i.topic_id = td.topic_id
            WHERE td.group_id = ?
        ''', (group_id,))
        stats['images_count'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('''
            SELECT COUNT(*) FROM files f
            JOIN topic_details td ON f.topic_id = td.topic_id
            WHERE td.group_id = ?
        ''', (group_id,))
        stats['files_count'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('''
            SELECT COUNT(*) FROM files f
            JOIN topic_details td ON f.topic_id = td.topic_id
            WHERE td.group_id = ? AND f.download_status = 'completed'
        ''', (group_id,))
        stats['files_downloaded'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('''
            SELECT COUNT(*) FROM videos v
            JOIN topic_details td ON v.topic_id = td.topic_id
            WHERE td.group_id = ?
        ''', (group_id,))
        stats['videos_count'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('''
            SELECT COUNT(*) FROM videos v
            JOIN topic_details td ON v.topic_id = td.topic_id
            WHERE td.group_id = ? AND v.download_status = 'completed'
        ''', (group_id,))
        stats['videos_downloaded'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('''
            SELECT COUNT(*) FROM comments c
            JOIN topic_details td ON c.topic_id = td.topic_id
            WHERE td.group_id = ?
        ''', (group_id,))
        stats['comments_count'] = self.cursor.fetchone()[0]
        
        return stats
    
    # ==================== 采集日志 ====================
    
    def start_crawl_log(self, group_id: int, crawl_type: str) -> int:
        """开始采集日志"""
        self.cursor.execute('''
            INSERT INTO crawl_log (group_id, crawl_type)
            VALUES (?, ?)
        ''', (group_id, crawl_type))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def update_crawl_log(self, log_id: int, columns_count: int = 0, topics_count: int = 0,
                         details_count: int = 0, files_count: int = 0,
                         status: str = None, error_message: str = None):
        """更新采集日志"""
        updates = []
        values = []
        
        if columns_count:
            updates.append('columns_count = ?')
            values.append(columns_count)
        if topics_count:
            updates.append('topics_count = ?')
            values.append(topics_count)
        if details_count:
            updates.append('details_count = ?')
            values.append(details_count)
        if files_count:
            updates.append('files_count = ?')
            values.append(files_count)
        if status:
            updates.append('status = ?')
            values.append(status)
            if status in ('completed', 'failed'):
                updates.append('end_time = CURRENT_TIMESTAMP')
        if error_message:
            updates.append('error_message = ?')
            values.append(error_message)
        
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
        stats = {
            'columns_deleted': 0,
            'topics_deleted': 0,
            'details_deleted': 0,
            'images_deleted': 0,
            'files_deleted': 0,
            'videos_deleted': 0,
            'comments_deleted': 0,
            'users_deleted': 0
        }
        
        try:
            # 获取该群组的所有topic_id
            self.cursor.execute('SELECT topic_id FROM topic_details WHERE group_id = ?', (group_id,))
            topic_ids = [row[0] for row in self.cursor.fetchall()]
            
            if topic_ids:
                placeholders = ','.join('?' * len(topic_ids))
                
                # 删除评论
                self.cursor.execute(f'DELETE FROM comments WHERE topic_id IN ({placeholders})', topic_ids)
                stats['comments_deleted'] = self.cursor.rowcount
                
                # 删除视频
                self.cursor.execute(f'DELETE FROM videos WHERE topic_id IN ({placeholders})', topic_ids)
                stats['videos_deleted'] = self.cursor.rowcount
                
                # 删除文件
                self.cursor.execute(f'DELETE FROM files WHERE topic_id IN ({placeholders})', topic_ids)
                stats['files_deleted'] = self.cursor.rowcount
                
                # 删除图片
                self.cursor.execute(f'DELETE FROM images WHERE topic_id IN ({placeholders})', topic_ids)
                stats['images_deleted'] = self.cursor.rowcount
                
                # 删除topic_owners
                self.cursor.execute(f'DELETE FROM topic_owners WHERE topic_id IN ({placeholders})', topic_ids)
            
            # 删除文章详情
            self.cursor.execute('DELETE FROM topic_details WHERE group_id = ?', (group_id,))
            stats['details_deleted'] = self.cursor.rowcount
            
            # 删除专栏文章
            self.cursor.execute('DELETE FROM column_topics WHERE group_id = ?', (group_id,))
            stats['topics_deleted'] = self.cursor.rowcount
            
            # 删除专栏目录
            self.cursor.execute('DELETE FROM columns WHERE group_id = ?', (group_id,))
            stats['columns_deleted'] = self.cursor.rowcount
            
            # 删除采集日志
            self.cursor.execute('DELETE FROM crawl_log WHERE group_id = ?', (group_id,))
            
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

