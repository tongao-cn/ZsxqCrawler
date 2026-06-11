from typing import Dict, List, Any, Optional

from backend.storage.db_compat import connect
from backend.storage.zsxq_file_database_helpers import (
    _FILE_AI_ANALYSIS_FIELDS,
    _close_connection,
    _count_tables,
    _file_ai_analysis_params,
    _file_attachment_params,
    _file_download_status_params,
    _file_record_params,
    _group_id_param,
    _new_import_stats,
    _nullable_group_id_param,
    _row_to_file_ai_analysis,
)


class ZSXQFileDatabase:
    """知识星球文件列表数据库管理工具 - 完全匹配API响应结构"""
    
    def __init__(self, group_id: Optional[str] = None):
        """初始化数据库连接"""
        self.group_id = str(group_id) if group_id is not None else None
        self.conn = connect()
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        """Schema is managed by manage-postgres-core-schema; runtime DDL is disabled."""
        return None

    def insert_user(self, user_data: Dict[str, Any]) -> Optional[int]:
        """插入或更新用户信息"""
        if not user_data or not user_data.get('user_id'):
            return None
            
        self.cursor.execute('''
        INSERT INTO users 
        (user_id, name, alias, avatar_url, description, location, ai_comment_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            name = excluded.name,
            alias = excluded.alias,
            avatar_url = excluded.avatar_url,
            description = excluded.description,
            location = excluded.location,
            ai_comment_url = excluded.ai_comment_url
        ''', (
            user_data.get('user_id'),
            user_data.get('name', ''),
            user_data.get('alias'),
            user_data.get('avatar_url'),
            user_data.get('description'),
            user_data.get('location'),
            user_data.get('ai_comment_url')
        ))
        return user_data.get('user_id')
    
    def insert_group(self, group_data: Dict[str, Any]) -> Optional[int]:
        """插入或更新群组信息"""
        if not group_data or not group_data.get('group_id'):
            return None
            
        self.cursor.execute('''
        INSERT INTO groups 
        (group_id, name, type, background_url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(group_id) DO UPDATE SET
            name = excluded.name,
            type = excluded.type,
            background_url = excluded.background_url
        ''', (
            group_data.get('group_id'),
            group_data.get('name', ''),
            group_data.get('type'),
            group_data.get('background_url')
        ))
        return group_data.get('group_id')
    
    def insert_file(
        self,
        file_data: Dict[str, Any],
        group_id: Optional[Any] = None,
        topic_id: Optional[Any] = None,
    ) -> Optional[int]:
        """插入或更新文件信息"""
        if not file_data or not file_data.get('file_id'):
            return None
            
        self.cursor.execute('''
        INSERT INTO files
        (file_id, group_id, topic_id, name, hash, size, duration, download_count, create_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_id) DO UPDATE SET
            group_id = COALESCE(excluded.group_id, files.group_id),
            topic_id = COALESCE(excluded.topic_id, files.topic_id),
            name = excluded.name,
            hash = excluded.hash,
            size = excluded.size,
            duration = excluded.duration,
            download_count = excluded.download_count,
            create_time = excluded.create_time
        ''', _file_record_params(file_data, group_id, topic_id))
        return file_data.get('file_id')
    
    def insert_topic(self, topic_data: Dict[str, Any]) -> Optional[int]:
        """插入或更新话题信息"""
        if not topic_data or not topic_data.get('topic_id'):
            return None
        
        # 处理用户特定信息
        user_specific = topic_data.get('user_specific', {})
        
        self.cursor.execute('''
        INSERT INTO topics 
        (topic_id, group_id, type, title, annotation, likes_count, tourist_likes_count,
         rewards_count, comments_count, reading_count, readers_count, digested, sticky,
         create_time, modify_time, user_liked, user_subscribed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(topic_id) DO UPDATE SET
            group_id = excluded.group_id,
            type = excluded.type,
            title = excluded.title,
            annotation = excluded.annotation,
            likes_count = excluded.likes_count,
            tourist_likes_count = excluded.tourist_likes_count,
            rewards_count = excluded.rewards_count,
            comments_count = excluded.comments_count,
            reading_count = excluded.reading_count,
            readers_count = excluded.readers_count,
            digested = excluded.digested,
            sticky = excluded.sticky,
            create_time = excluded.create_time,
            modify_time = excluded.modify_time,
            user_liked = excluded.user_liked,
            user_subscribed = excluded.user_subscribed
        ''', (
            topic_data.get('topic_id'),
            topic_data.get('group', {}).get('group_id'),
            topic_data.get('type'),
            topic_data.get('title'),
            topic_data.get('annotation'),
            topic_data.get('likes_count', 0),
            topic_data.get('tourist_likes_count', 0),
            topic_data.get('rewards_count', 0),
            topic_data.get('comments_count', 0),
            topic_data.get('reading_count', 0),
            topic_data.get('readers_count', 0),
            topic_data.get('digested', False),
            topic_data.get('sticky', False),
            topic_data.get('create_time'),
            topic_data.get('modify_time'),  # 新增字段
            user_specific.get('liked', False),
            user_specific.get('subscribed', False)
        ))
        return topic_data.get('topic_id')

    def update_file_download_status(
        self,
        file_id: int,
        status: str,
        local_path: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """更新文件下载状态"""
        self.cursor.execute('''
        UPDATE files
        SET download_status = ?,
            local_path = COALESCE(?, local_path),
            download_time = CASE
                WHEN ? = 'completed' THEN CURRENT_TIMESTAMP::text
                ELSE download_time
            END,
            download_error_code = CASE
                WHEN ? = 'failed' THEN ?
                ELSE NULL
            END,
            download_error_message = CASE
                WHEN ? = 'failed' THEN ?
                ELSE NULL
            END,
            last_download_attempt_at = CURRENT_TIMESTAMP::text
        WHERE file_id = ?
          AND (? IS NULL OR group_id = ?)
        ''', _file_download_status_params(self.group_id, file_id, status, local_path, error_code, error_message))
        self.conn.commit()
    
    def insert_talk(self, topic_id: int, talk_data: Dict[str, Any]):
        """插入话题内容"""
        if not talk_data:
            return
            
        owner = talk_data.get('owner', {})
        owner_id = self.insert_user(owner)
        
        self.cursor.execute('''
        INSERT INTO talks (topic_id, owner_user_id, text)
        VALUES (?, ?, ?)
        ON CONFLICT(topic_id) DO UPDATE SET
            owner_user_id = excluded.owner_user_id,
            text = excluded.text
        ''', (topic_id, owner_id, talk_data.get('text', '')))
    
    def insert_images(self, topic_id: int, images_data: List[Dict[str, Any]]):
        """插入图片信息"""
        for image in images_data:
            if not image.get('image_id'):
                continue
                
            thumbnail = image.get('thumbnail', {})
            large = image.get('large', {})
            original = image.get('original', {})
            
            self.cursor.execute('''
            INSERT INTO images 
            (image_id, topic_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
             large_url, large_width, large_height, original_url, original_width, original_height, original_size)
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
            ''', (
                image.get('image_id'),
                topic_id,
                image.get('type'),
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
    
    def insert_topic_files(self, topic_id: int, files_data: List[Dict[str, Any]]):
        """插入话题关联的文件"""
        for file in files_data:
            if not file.get('file_id'):
                continue

            self.cursor.execute('''
            DELETE FROM topic_files
            WHERE topic_id = ? AND file_id = ?
            ''', (topic_id, file.get('file_id')))

            self.cursor.execute('''
            INSERT INTO topic_files 
            (topic_id, file_id, name, hash, size, duration, download_count, create_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_id, file_id) DO UPDATE SET
                name = excluded.name,
                hash = excluded.hash,
                size = excluded.size,
                duration = excluded.duration,
                download_count = excluded.download_count,
                create_time = excluded.create_time
            ''', _file_attachment_params(topic_id, file))
    
    def insert_latest_likes(self, topic_id: int, likes_data: List[Dict[str, Any]]):
        """插入最新点赞记录"""
        self.cursor.execute('''
        DELETE FROM latest_likes
        WHERE topic_id = ?
        ''', (topic_id,))

        for like in likes_data:
            owner = like.get('owner', {})
            owner_id = self.insert_user(owner)
            
            self.cursor.execute('''
            INSERT INTO latest_likes (topic_id, owner_user_id, create_time)
            VALUES (?, ?, ?)
            ON CONFLICT(topic_id, owner_user_id, create_time) DO NOTHING
            ''', (topic_id, owner_id, like.get('create_time')))
    
    def insert_comments(self, topic_id: int, comments_data: List[Dict[str, Any]]):
        """插入评论信息"""
        group_id = self._resolve_topic_group_id(topic_id)
        for comment in comments_data:
            if not comment.get('comment_id'):
                continue
                
            owner = comment.get('owner', {})
            owner_id = self.insert_user(owner)
            
            repliee = comment.get('repliee', {})
            repliee_id = self.insert_user(repliee) if repliee else None
            
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
            ''', (
                comment.get('comment_id'),
                group_id,
                topic_id,
                owner_id,
                comment.get('parent_comment_id'),
                repliee_id,
                comment.get('text', ''),
                comment.get('create_time'),
                comment.get('likes_count', 0),
                comment.get('rewards_count', 0),
                comment.get('replies_count', 0),
                comment.get('sticky', False)
            ))

    def _resolve_topic_group_id(self, topic_id: int):
        if self.group_id:
            return _nullable_group_id_param(self.group_id)
        try:
            self.cursor.execute('SELECT group_id FROM topics WHERE topic_id = ? LIMIT 1', (topic_id,))
            row = self.cursor.fetchone()
            return row[0] if row and row[0] is not None else None
        except Exception:
            return None
    
    def insert_like_emojis(self, topic_id: int, likes_detail: Dict[str, Any]):
        """插入点赞表情详情"""
        emojis = likes_detail.get('emojis', [])
        for emoji in emojis:
            self.cursor.execute('''
            INSERT INTO like_emojis (topic_id, emoji_key, likes_count)
            VALUES (?, ?, ?)
            ON CONFLICT(topic_id, emoji_key) DO UPDATE SET
                likes_count = excluded.likes_count
            ''', (topic_id, emoji.get('emoji_key'), emoji.get('likes_count', 0)))
    
    def insert_user_liked_emojis(self, topic_id: int, liked_emojis: List[str]):
        """插入用户点赞的表情"""
        for emoji_key in liked_emojis:
            self.cursor.execute('''
            INSERT INTO user_liked_emojis (topic_id, emoji_key)
            VALUES (?, ?)
            ON CONFLICT(topic_id, emoji_key) DO NOTHING
            ''', (topic_id, emoji_key))
    
    def insert_columns(self, topic_id: int, columns_data: List[Dict[str, Any]]):
        """插入栏目信息"""
        for column in columns_data:
            if not column.get('column_id'):
                continue
                
            # 插入栏目
            self.cursor.execute('''
            INSERT INTO columns (column_id, name)
            VALUES (?, ?)
            ON CONFLICT(column_id) DO UPDATE SET
                name = excluded.name
            ''', (column.get('column_id'), column.get('name', '')))
            
            # 插入话题-栏目关联
            self.cursor.execute('''
            INSERT INTO topic_columns (topic_id, column_id)
            VALUES (?, ?)
            ON CONFLICT(topic_id, column_id) DO NOTHING
            ''', (topic_id, column.get('column_id')))
    
    def insert_solution(self, topic_id: int, solution_data: Dict[str, Any]):
        """插入解决方案信息"""
        if not solution_data:
            return None
            
        owner = solution_data.get('owner', {})
        owner_id = self.insert_user(owner)
        
        self.cursor.execute('''
        INSERT INTO solutions (topic_id, task_id, owner_user_id, text)
        VALUES (?, ?, ?, ?)
        RETURNING id
        ''', (
            topic_id,
            solution_data.get('task_id'),
            owner_id,
            solution_data.get('text', '')
        ))
        
        row = self.cursor.fetchone()
        solution_id = row[0] if row else None
        
        # 插入解决方案文件
        files = solution_data.get('files', [])
        for file in files:
            self.cursor.execute('''
            INSERT INTO solution_files 
            (solution_id, file_id, name, hash, size, duration, download_count, create_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(solution_id, file_id) DO UPDATE SET
                name = excluded.name,
                hash = excluded.hash,
                size = excluded.size,
                duration = excluded.duration,
                download_count = excluded.download_count,
                create_time = excluded.create_time
            ''', _file_attachment_params(solution_id, file))
        
        return solution_id
    
    def import_file_response(self, response_data: Dict[str, Any]) -> Dict[str, int]:
        """导入文件API响应数据"""
        stats = _new_import_stats()
        
        try:
            # 记录API响应
            files_data = response_data.get('resp_data', {}).get('files', [])
            self.cursor.execute('''
            INSERT INTO api_responses (succeeded, index_value, files_count)
            VALUES (?, ?, ?)
            ''', (
                response_data.get('succeeded', False),
                response_data.get('resp_data', {}).get('index'),
                len(files_data)
            ))
            
            # 处理每个文件和关联的话题
            for item in files_data:
                file_data = item.get('file', {})
                topic_data = item.get('topic', {})
                
                if not file_data.get('file_id') or not topic_data.get('topic_id'):
                    continue

                # 统一 ingestion 写表顺序：groups/users/topics/content/files/relations
                group_data = topic_data.get('group', {})
                if group_data:
                    group_id = self.insert_group(group_data)
                    if group_id:
                        stats['groups'] += 1
                
                # 插入话题
                topic_id = self.insert_topic(topic_data)
                if topic_id:
                    stats['topics'] += 1

                    # 处理talk信息
                    talk_data = topic_data.get('talk', {})
                    topic_files = []
                    if talk_data:
                        self.insert_talk(topic_id, talk_data)
                        
                        # 处理talk中的图片
                        images = talk_data.get('images', [])
                        if images:
                            self.insert_images(topic_id, images)
                            stats['images'] += len(images)
                        
                        # 处理talk中的文件
                        topic_files = talk_data.get('files', [])
                    
                    # 处理最新点赞
                    latest_likes = topic_data.get('latest_likes', [])
                    if latest_likes:
                        self.insert_latest_likes(topic_id, latest_likes)
                        stats['likes'] += len(latest_likes)
                    
                    # 处理评论
                    comments = topic_data.get('show_comments', [])
                    if comments:
                        self.insert_comments(topic_id, comments)
                        stats['comments'] += len(comments)
                    
                    # 处理点赞详情
                    likes_detail = topic_data.get('likes_detail', {})
                    if likes_detail:
                        self.insert_like_emojis(topic_id, likes_detail)
                    
                    # 处理用户点赞表情
                    user_specific = topic_data.get('user_specific', {})
                    liked_emojis = user_specific.get('liked_emojis', [])
                    if liked_emojis:
                        self.insert_user_liked_emojis(topic_id, liked_emojis)
                    
                    # 处理栏目
                    columns = topic_data.get('columns', [])
                    if columns:
                        self.insert_columns(topic_id, columns)
                        stats['columns'] += len(columns)
                    
                    # 处理解决方案
                    solution = topic_data.get('solution', {})
                    if solution:
                        solution_id = self.insert_solution(topic_id, solution)
                        if solution_id:
                            stats['solutions'] += 1

                    group_id_for_file = (topic_data.get('group') or {}).get('group_id')
                    file_id = self.insert_file(file_data, group_id=group_id_for_file, topic_id=topic_id)
                    if file_id:
                        stats['files'] += 1

                    self.cursor.execute('''
                    DELETE FROM file_topic_relations
                    WHERE file_id = ? AND topic_id = ?
                    ''', (file_id, topic_id))

                    self.cursor.execute('''
                    INSERT INTO file_topic_relations (file_id, topic_id)
                    VALUES (?, ?)
                    ON CONFLICT(file_id, topic_id) DO NOTHING
                    ''', (file_id, topic_id))

                    if file_id:
                        self.insert_topic_files(topic_id, [file_data])
                    if topic_files:
                        self.insert_topic_files(topic_id, topic_files)
            
            self.conn.commit()
            print(f"数据导入成功: {stats}")
            return stats
            
        except Exception as e:
            self.conn.rollback()
            print(f"数据导入失败: {e}")
            raise e
    
    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        return _count_tables(self.cursor, group_id=self.group_id)

    def _migrate_database(self):
        """Schema is managed by manage-postgres-core-schema; runtime DDL is disabled."""
        return None

    def close(self):
        """关闭数据库连接"""
        _close_connection(self.conn)

    def upsert_file_ai_analysis(
        self,
        file_id: int,
        *,
        status: str = 'completed',
        summary: Optional[str] = None,
        extracted_text: Optional[str] = None,
        extracted_text_preview: Optional[str] = None,
        content_type: Optional[str] = None,
        source_path: Optional[str] = None,
        source_size: Optional[int] = None,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        wire_api: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        self.cursor.execute('''
        INSERT INTO file_ai_analyses (
            file_id, group_id, status, summary, extracted_text, extracted_text_preview, content_type,
            source_path, source_size, model, api_base, wire_api, reasoning_effort,
            error_message, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(file_id) DO UPDATE SET
            group_id=COALESCE(excluded.group_id, file_ai_analyses.group_id),
            status=excluded.status,
            summary=excluded.summary,
            extracted_text=excluded.extracted_text,
            extracted_text_preview=excluded.extracted_text_preview,
            content_type=excluded.content_type,
            source_path=excluded.source_path,
            source_size=excluded.source_size,
            model=excluded.model,
            api_base=excluded.api_base,
            wire_api=excluded.wire_api,
            reasoning_effort=excluded.reasoning_effort,
            error_message=excluded.error_message,
            updated_at=CURRENT_TIMESTAMP
        ''', _file_ai_analysis_params(
            self.group_id,
            file_id,
            status=status,
            summary=summary,
            extracted_text=extracted_text,
            extracted_text_preview=extracted_text_preview,
            content_type=content_type,
            source_path=source_path,
            source_size=source_size,
            model=model,
            api_base=api_base,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
            error_message=error_message,
        ))
        self.conn.commit()

    def get_file_ai_analysis(self, file_id: int) -> Optional[Dict[str, Any]]:
        self.cursor.execute('''
        SELECT
            file_id, status, summary, extracted_text, extracted_text_preview, content_type,
            source_path, source_size, model, api_base, wire_api, reasoning_effort,
            error_message, created_at, updated_at
        FROM file_ai_analyses
        WHERE file_id = ?
          AND (? IS NULL OR group_id = ?)
        ''', (file_id, _group_id_param(self.group_id), _group_id_param(self.group_id)))
        row = self.cursor.fetchone()
        return _row_to_file_ai_analysis(row)


def main():
    """测试数据库功能"""
    db = ZSXQFileDatabase()
    print("数据库统计:")
    stats = db.get_database_stats()
    for table, count in stats.items():
        print(f"  {table}: {count}")
    db.close()


if __name__ == "__main__":
    main() 
