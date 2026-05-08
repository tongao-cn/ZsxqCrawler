#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any, Optional, List

from backend.storage.db_compat import connect


def _build_pagination(page: int, per_page: int, total: int) -> Dict[str, int]:
    return {
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': (total + per_page - 1) // per_page
    }


def _format_tag_row(row) -> Dict[str, Any]:
    return {
        'tag_id': row[0],
        'tag_name': row[1],
        'hid': row[2],
        'topic_count': row[3],
        'created_at': row[4]
    }


def _format_tag_topic_row(topic) -> Dict[str, Any]:
    topic_data = {
        "topic_id": topic[0],
        "title": topic[1],
        "create_time": topic[2],
        "likes_count": topic[3],
        "comments_count": topic[4],
        "reading_count": topic[5],
        "type": topic[6],
        "digested": bool(topic[7]) if topic[7] is not None else False,
        "sticky": bool(topic[8]) if topic[8] is not None else False
    }

    if topic[6] == 'q&a':
        topic_data['question_text'] = topic[9] if topic[9] else ''
        topic_data['answer_text'] = topic[10] if topic[10] else ''
    else:
        topic_data['talk_text'] = topic[11] if topic[11] else ''
        if topic[12]:
            topic_data['author'] = {
                'user_id': topic[12],
                'name': topic[13],
                'avatar_url': topic[14]
            }

    return topic_data


def _replace_file_topic_relation(file_db, file_id: int, topic_id: int) -> int:
    file_db.cursor.execute('''
    DELETE FROM file_topic_relations
    WHERE file_id = ? AND topic_id = ?
    ''', (file_id, topic_id))
    file_db.cursor.execute('''
    INSERT OR IGNORE INTO file_topic_relations (file_id, topic_id)
    VALUES (?, ?)
    ''', (file_id, topic_id))
    return file_db.cursor.rowcount


def _group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def _nullable_group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    if not value:
        return None
    return int(value) if value.isdigit() else value


def _upsert_core_file(cursor, group_id: Optional[int], topic_id: int, file_data: Dict[str, Any]) -> Optional[int]:
    file_id = file_data.get('file_id')
    if not file_id:
        return None

    cursor.execute('''
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
    ''', (
        file_id,
        group_id,
        topic_id,
        file_data.get('name', ''),
        file_data.get('hash'),
        file_data.get('size'),
        file_data.get('duration'),
        file_data.get('download_count'),
        file_data.get('create_time'),
    ))
    return file_id


def _topic_file_payload_from_row(row) -> Dict[str, Any]:
    return {
        'file_id': row[1],
        'name': row[2] or '',
        'hash': row[3],
        'size': row[4],
        'duration': row[5],
        'download_count': row[6],
        'create_time': row[7],
    }


class ZSXQDatabase:
    """知识星球数据库管理器"""
    
    def __init__(self, group_id: Optional[str] = None):
        self.group_id = str(group_id) if group_id is not None else None
        self.file_db = None
        self.conn = connect()
        self.cursor = self.conn.cursor()
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        
        # 群组表 - 适配现有结构
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                group_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT,
                background_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 用户表 - 适配现有结构
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                alias TEXT,
                avatar_url TEXT,
                location TEXT,
                description TEXT,
                ai_comment_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 话题表 - 适配现有结构
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS topics (
                topic_id INTEGER PRIMARY KEY,
                group_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                title TEXT,
                create_time TEXT,
                digested BOOLEAN DEFAULT FALSE,
                sticky BOOLEAN DEFAULT FALSE,
                likes_count INTEGER DEFAULT 0,
                tourist_likes_count INTEGER DEFAULT 0,
                rewards_count INTEGER DEFAULT 0,
                comments_count INTEGER DEFAULT 0,
                reading_count INTEGER DEFAULT 0,
                readers_count INTEGER DEFAULT 0,
                answered BOOLEAN DEFAULT FALSE,
                silenced BOOLEAN DEFAULT FALSE,
                annotation TEXT,
                user_liked BOOLEAN DEFAULT FALSE,
                user_subscribed BOOLEAN DEFAULT FALSE,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES groups (group_id)
            )
        ''')
        
        # 话题内容表（talks）
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS talks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                owner_user_id INTEGER,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id),
                FOREIGN KEY (owner_user_id) REFERENCES users (user_id)
            )
        ''')
        
        # 文章表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                title TEXT,
                article_id TEXT,
                article_url TEXT,
                inline_article_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id)
            )
        ''')
        
        # 图片表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                image_id INTEGER PRIMARY KEY,
                topic_id INTEGER,
                comment_id INTEGER,
                type TEXT,
                thumbnail_url TEXT,
                thumbnail_width INTEGER,
                thumbnail_height INTEGER,
                large_url TEXT,
                large_width INTEGER,
                large_height INTEGER,
                original_url TEXT,
                original_width INTEGER,
                original_height INTEGER,
                original_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id)
            )
        ''')
        
        # 点赞表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                user_id INTEGER,
                create_time TEXT,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # 表情点赞表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS like_emojis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                emoji_key TEXT,
                likes_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id)
            )
        ''')
        
        # 用户表情点赞表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_liked_emojis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                emoji_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id)
            )
        ''')
        
        # 评论表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                comment_id INTEGER PRIMARY KEY,
                group_id INTEGER,
                topic_id INTEGER,
                owner_user_id INTEGER,
                parent_comment_id INTEGER,
                repliee_user_id INTEGER,
                text TEXT,
                create_time TEXT,
                likes_count INTEGER DEFAULT 0,
                rewards_count INTEGER DEFAULT 0,
                replies_count INTEGER DEFAULT 0,
                sticky BOOLEAN DEFAULT FALSE,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id),
                FOREIGN KEY (owner_user_id) REFERENCES users (user_id),
                FOREIGN KEY (parent_comment_id) REFERENCES comments (comment_id),
                FOREIGN KEY (repliee_user_id) REFERENCES users (user_id)
            )
        ''')
        self.cursor.execute("PRAGMA table_info(comments)")
        comment_columns = [row[1] for row in self.cursor.fetchall()]
        if 'group_id' not in comment_columns:
            self.cursor.execute('ALTER TABLE comments ADD COLUMN group_id INTEGER')
        
        # 问题表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                owner_user_id INTEGER,
                questionee_user_id INTEGER,
                text TEXT,
                expired BOOLEAN DEFAULT FALSE,
                anonymous BOOLEAN DEFAULT FALSE,
                owner_questions_count INTEGER,
                owner_join_time TEXT,
                owner_status TEXT,
                owner_location TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id),
                FOREIGN KEY (owner_user_id) REFERENCES users (user_id),
                FOREIGN KEY (questionee_user_id) REFERENCES users (user_id)
            )
        ''')
        
        # 回答表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                owner_user_id INTEGER,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id),
                FOREIGN KEY (owner_user_id) REFERENCES users (user_id)
            )
        ''')
        
        # 标签表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                tag_name TEXT NOT NULL,
                hid TEXT,
                topic_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(group_id, tag_name),
                FOREIGN KEY (group_id) REFERENCES groups (group_id)
            )
        ''')
        
        # 话题标签关联表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS topic_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(topic_id, tag_id),
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id),
                FOREIGN KEY (tag_id) REFERENCES tags (tag_id)
            )
        ''')

        # 话题文件表 (talk.files数组)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS topic_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                file_id INTEGER,
                name TEXT,
                hash TEXT,
                size INTEGER,
                duration INTEGER,
                download_count INTEGER,
                create_time TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (topic_id)
            )
        ''')

        # 索引 - 覆盖当前高频查询和排序路径
        index_sqls = [
            'CREATE INDEX IF NOT EXISTS idx_topics_group_create_time ON topics (group_id, create_time DESC)',
            'CREATE INDEX IF NOT EXISTS idx_topics_create_time ON topics (create_time)',
            'CREATE INDEX IF NOT EXISTS idx_talks_topic_id ON talks (topic_id)',
            'CREATE INDEX IF NOT EXISTS idx_articles_topic_id ON articles (topic_id)',
            'CREATE INDEX IF NOT EXISTS idx_images_topic_comment_image_id ON images (topic_id, comment_id, image_id)',
            'CREATE INDEX IF NOT EXISTS idx_images_comment_image_id ON images (comment_id, image_id)',
            'CREATE INDEX IF NOT EXISTS idx_likes_topic_create_time ON likes (topic_id, create_time DESC)',
            'CREATE INDEX IF NOT EXISTS idx_like_emojis_topic_id ON like_emojis (topic_id)',
            'CREATE INDEX IF NOT EXISTS idx_user_liked_emojis_topic_id ON user_liked_emojis (topic_id)',
            'CREATE INDEX IF NOT EXISTS idx_comments_topic_create_time ON comments (topic_id, create_time ASC)',
            'CREATE INDEX IF NOT EXISTS idx_comments_group_topic_create_time ON comments (group_id, topic_id, create_time ASC)',
            'CREATE INDEX IF NOT EXISTS idx_questions_topic_id ON questions (topic_id)',
            'CREATE INDEX IF NOT EXISTS idx_answers_topic_id ON answers (topic_id)',
            'CREATE INDEX IF NOT EXISTS idx_topic_files_topic_file_id ON topic_files (topic_id, file_id)',
            'CREATE INDEX IF NOT EXISTS idx_topic_tags_tag_topic ON topic_tags (tag_id, topic_id)',
            'CREATE INDEX IF NOT EXISTS idx_tags_group_topic_count_name ON tags (group_id, topic_count DESC, tag_name ASC)',
        ]
        for sql in index_sqls:
            self.cursor.execute(sql)

        self.conn.commit()
    
    def import_topic_data(self, topic_data: Dict[str, Any]) -> bool:
        """导入话题数据到数据库"""
        try:
            topic_id = topic_data.get('topic_id')
            group_info = topic_data.get('group', {})
            
            if not topic_id:
                return False

            # 如果话题已存在，直接跳过，避免重复写入或更新
            self.cursor.execute(
                'SELECT 1 FROM topics WHERE topic_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1',
                (topic_id, _group_id_param(self.group_id), _group_id_param(self.group_id)),
            )
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
        
        # 获取当前时间作为created_at（使用东八区时间格式）
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO groups 
            (group_id, name, type, background_url, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            group_id,
            group_data.get('name', ''),
            group_data.get('type', ''),
            group_data.get('background_url', ''),
            current_time
        ))
    
    def _upsert_user(self, user_data: Dict[str, Any]):
        """插入或更新用户信息"""
        user_id = user_data.get('user_id')
        if not user_id:
            return
        
        # 获取当前时间作为created_at（使用东八区时间格式）
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, name, alias, avatar_url, location, description, ai_comment_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            user_data.get('name', ''),
            user_data.get('alias', ''),
            user_data.get('avatar_url', ''),
            user_data.get('location', ''),
            user_data.get('description', ''),
            user_data.get('ai_comment_url', ''),
            current_time
        ))
    
    def _upsert_topic(self, topic_data: Dict[str, Any]):
        """插入或更新话题信息"""
        topic_id = topic_data.get('topic_id')
        if not topic_id:
            return
        
        # 获取当前时间作为imported_at（使用东八区时间格式）
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO topics 
            (topic_id, group_id, type, title, create_time, digested, sticky, 
             likes_count, tourist_likes_count, rewards_count, comments_count, 
             reading_count, readers_count, answered, silenced, annotation, 
             user_liked, user_subscribed, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            topic_id,
            topic_data.get('group', {}).get('group_id', ''),
            topic_data.get('type', ''),
            topic_data.get('title', ''),
            topic_data.get('create_time', ''),
            topic_data.get('digested', False),
            topic_data.get('sticky', False),
            topic_data.get('likes_count', 0),
            topic_data.get('tourist_likes_count', 0),
            topic_data.get('rewards_count', 0),
            topic_data.get('comments_count', 0),
            topic_data.get('reading_count', 0),
            topic_data.get('readers_count', 0),
            topic_data.get('answered', False),
            topic_data.get('silenced', False),
            topic_data.get('annotation', ''),
            topic_data.get('user_liked', False),
            topic_data.get('user_subscribed', False),
            current_time
        ))
    
    def update_topic_stats(self, topic_data: Dict[str, Any]) -> bool:
        """仅更新话题的统计信息，不导入其他相关数据"""
        try:
            topic_id = topic_data.get('topic_id')
            if not topic_id:
                return False

            # 获取当前时间作为imported_at（使用东八区时间格式）
            from datetime import datetime, timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'

            # 只更新统计相关字段，不更新内容字段
            self.cursor.execute('''
                UPDATE topics
                SET likes_count = ?, tourist_likes_count = ?, rewards_count = ?,
                    comments_count = ?, reading_count = ?, readers_count = ?,
                    digested = ?, sticky = ?, user_liked = ?, user_subscribed = ?,
                    imported_at = ?
                WHERE topic_id = ?
                  AND (? IS NULL OR group_id = ?)
            ''', (
                topic_data.get('likes_count', 0),
                topic_data.get('tourist_likes_count', 0),
                topic_data.get('rewards_count', 0),
                topic_data.get('comments_count', 0),
                topic_data.get('reading_count', 0),
                topic_data.get('readers_count', 0),
                topic_data.get('digested', False),
                topic_data.get('sticky', False),
                topic_data.get('user_specific', {}).get('liked', False),
                topic_data.get('user_specific', {}).get('subscribed', False),
                current_time,
                topic_id,
                _group_id_param(self.group_id),
                _group_id_param(self.group_id),
            ))

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

    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        stats = {}

        tables = ['groups', 'users', 'topics', 'talks', 'articles', 'images',
                 'likes', 'like_emojis', 'user_liked_emojis', 'comments',
                 'questions', 'answers']

        for table in tables:
            try:
                if self.group_id is None:
                    self.cursor.execute(f'SELECT COUNT(*) FROM {table}')
                elif table in {'groups', 'topics', 'comments'}:
                    self.cursor.execute(f'SELECT COUNT(*) FROM {table} WHERE group_id = ?', (_group_id_param(self.group_id),))
                elif table == 'users':
                    self.cursor.execute(
                        '''
                        SELECT COUNT(DISTINCT user_id)
                        FROM (
                            SELECT owner_user_id AS user_id FROM talks WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                            UNION
                            SELECT owner_user_id AS user_id FROM comments WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                            UNION
                            SELECT owner_user_id AS user_id FROM questions WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                            UNION
                            SELECT questionee_user_id AS user_id FROM questions WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                            UNION
                            SELECT owner_user_id AS user_id FROM answers WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                        ) scoped_users
                        WHERE user_id IS NOT NULL
                        ''',
                        (
                            _group_id_param(self.group_id),
                            _group_id_param(self.group_id),
                            _group_id_param(self.group_id),
                            _group_id_param(self.group_id),
                            _group_id_param(self.group_id),
                        ),
                    )
                else:
                    self.cursor.execute(
                        f'SELECT COUNT(*) FROM {table} WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)',
                        (_group_id_param(self.group_id),),
                    )
                stats[table] = self.cursor.fetchone()[0]
            except Exception as e:
                print(f"获取表 {table} 统计信息失败: {e}")
                stats[table] = 0

        return stats
    
    def get_timestamp_range_info(self) -> Dict[str, Any]:
        """获取话题时间戳范围信息"""
        try:
            # 获取最新话题时间
            self.cursor.execute('''
                SELECT create_time FROM topics 
                WHERE (? IS NULL OR group_id = ?)
                  AND create_time IS NOT NULL AND create_time != ''
                ORDER BY create_time DESC LIMIT 1
            ''', (_group_id_param(self.group_id), _group_id_param(self.group_id)))
            newest_result = self.cursor.fetchone()
            newest_time = newest_result[0] if newest_result else None
            
            # 获取最老话题时间
            self.cursor.execute('''
                SELECT create_time FROM topics 
                WHERE (? IS NULL OR group_id = ?)
                  AND create_time IS NOT NULL AND create_time != ''
                ORDER BY create_time ASC LIMIT 1
            ''', (_group_id_param(self.group_id), _group_id_param(self.group_id)))
            oldest_result = self.cursor.fetchone()
            oldest_time = oldest_result[0] if oldest_result else None
            
            # 获取话题总数
            self.cursor.execute(
                'SELECT COUNT(*) FROM topics WHERE (? IS NULL OR group_id = ?)',
                (_group_id_param(self.group_id), _group_id_param(self.group_id)),
            )
            total_topics = self.cursor.fetchone()[0]
            
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
            self.cursor.execute('''
                SELECT create_time FROM topics 
                WHERE (? IS NULL OR group_id = ?)
                  AND create_time IS NOT NULL AND create_time != ''
                ORDER BY create_time ASC LIMIT 1
            ''', (_group_id_param(self.group_id), _group_id_param(self.group_id)))
            result = self.cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"获取最老话题时间戳失败: {e}")
            return None
    
    def get_newest_topic_timestamp(self) -> Optional[str]:
        """获取数据库中最新的话题时间戳"""
        try:
            self.cursor.execute('''
                SELECT create_time FROM topics 
                WHERE (? IS NULL OR group_id = ?)
                  AND create_time IS NOT NULL AND create_time != ''
                ORDER BY create_time DESC LIMIT 1
            ''', (_group_id_param(self.group_id), _group_id_param(self.group_id)))
            result = self.cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"获取最新话题时间戳失败: {e}")
            return None
    
    def _import_all_users(self, topic_data: Dict[str, Any]):
        """导入话题相关的所有用户信息"""
        # 导入talk中的用户
        if 'talk' in topic_data and topic_data['talk'] and 'owner' in topic_data['talk']:
            self._upsert_user(topic_data['talk']['owner'])

        # 导入question中的用户
        if 'question' in topic_data and topic_data['question']:
            # 对于非匿名用户，导入提问者信息
            if 'owner' in topic_data['question'] and not topic_data['question'].get('anonymous', False):
                self._upsert_user(topic_data['question']['owner'])
            # 导入被提问者信息（无论是否匿名都有）
            if 'questionee' in topic_data['question']:
                self._upsert_user(topic_data['question']['questionee'])

        # 导入answer中的用户
        if 'answer' in topic_data and topic_data['answer'] and 'owner' in topic_data['answer']:
            self._upsert_user(topic_data['answer']['owner'])
        
        # 导入latest_likes中的用户
        if 'latest_likes' in topic_data:
            for like in topic_data['latest_likes']:
                if 'owner' in like:
                    self._upsert_user(like['owner'])
        
        # 导入comments中的用户
        if 'show_comments' in topic_data:
            for comment in topic_data['show_comments']:
                if 'owner' in comment:
                    self._upsert_user(comment['owner'])
                if 'repliee' in comment:
                    self._upsert_user(comment['repliee'])
    
    def _upsert_talk(self, topic_id: int, talk_data: Dict[str, Any]):
        """插入或更新话题内容"""
        if not talk_data:
            return
        
        owner_user_id = talk_data.get('owner', {}).get('user_id')
        if not owner_user_id:
            return
        
        # 获取当前时间作为created_at（使用东八区时间格式）
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO talks 
            (topic_id, owner_user_id, text, created_at)
            VALUES (?, ?, ?, ?)
        ''', (
            topic_id,
            owner_user_id,
            talk_data.get('text', ''),
            current_time
        ))

    
    def _import_images(self, topic_id: int, topic_data: Dict[str, Any]):
        """导入图片信息"""
        images_to_import = []
        
        # 从talk中获取图片
        if 'talk' in topic_data and topic_data['talk'] and 'images' in topic_data['talk']:
            for img in topic_data['talk']['images']:
                images_to_import.append((img, None))  # (image_data, comment_id)
        
        # 从comments中获取图片
        if 'show_comments' in topic_data:
            for comment in topic_data['show_comments']:
                if 'images' in comment:
                    comment_id = comment.get('comment_id')
                    for img in comment['images']:
                        images_to_import.append((img, comment_id))
        
        # 导入所有图片
        for img_data, comment_id in images_to_import:
            self._upsert_image(topic_id, img_data, comment_id)
    
    def _upsert_image(self, topic_id: int, image_data: Dict[str, Any], comment_id: Optional[int] = None):
        """插入或更新图片信息"""
        image_id = image_data.get('image_id')
        if not image_id:
            return
        
        thumbnail = image_data.get('thumbnail', {})
        large = image_data.get('large', {})
        original = image_data.get('original', {})
        
        # 获取当前时间作为created_at（使用东八区时间格式）
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO images 
            (image_id, topic_id, comment_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
             large_url, large_width, large_height, original_url, original_width, original_height, original_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            image_id,
            topic_id,
            comment_id,
            image_data.get('type', ''),
            thumbnail.get('url', ''),
            thumbnail.get('width'),
            thumbnail.get('height'),
            large.get('url', ''),
            large.get('width'),
            large.get('height'),
            original.get('url', ''),
            original.get('width'),
            original.get('height'),
            original.get('size'),
            current_time
        ))

    
    def _import_likes(self, topic_id: int, topic_data: Dict[str, Any]):
        """导入点赞信息"""
        if 'latest_likes' not in topic_data:
            return
        
        for like in topic_data['latest_likes']:
            owner = like.get('owner', {})
            user_id = owner.get('user_id')
            if user_id:
                # 获取当前时间作为imported_at（使用东八区时间格式）
                from datetime import datetime, timezone, timedelta
                beijing_tz = timezone(timedelta(hours=8))
                current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
                
                self.cursor.execute('''
                    INSERT OR IGNORE INTO likes 
                    (topic_id, user_id, create_time, imported_at)
                    VALUES (?, ?, ?, ?)
                ''', (
                    topic_id,
                    user_id,
                    like.get('create_time', ''),
                    current_time
                ))
        
        if topic_data['latest_likes']:
            pass  # 数据已导入，无需额外日志

    def _import_like_emojis(self, topic_id: int, topic_data: Dict[str, Any]):
        """导入表情点赞信息"""
        if 'likes_detail' not in topic_data or 'emojis' not in topic_data['likes_detail']:
            return
        
        for emoji in topic_data['likes_detail']['emojis']:
            emoji_key = emoji.get('emoji_key')
            likes_count = emoji.get('likes_count', 0)
            if emoji_key:
                # 获取当前时间作为created_at（使用东八区时间格式）
                from datetime import datetime, timezone, timedelta
                beijing_tz = timezone(timedelta(hours=8))
                current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
                
                self.cursor.execute('''
                    INSERT OR REPLACE INTO like_emojis 
                    (topic_id, emoji_key, likes_count, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (
                    topic_id,
                    emoji_key,
                    likes_count,
                    current_time
                ))
        
        if topic_data['likes_detail']['emojis']:
            pass  # 数据已导入，无需额外日志

    def _import_user_liked_emojis(self, topic_id: int, topic_data: Dict[str, Any]):
        """导入用户表情点赞信息"""
        if 'user_specific' not in topic_data or 'liked_emojis' not in topic_data['user_specific']:
            return
        
        for emoji_key in topic_data['user_specific']['liked_emojis']:
            if emoji_key:
                self.cursor.execute('''
                    INSERT OR IGNORE INTO user_liked_emojis 
                    (topic_id, emoji_key)
                    VALUES (?, ?)
                ''', (
                    topic_id,
                    emoji_key
                ))
        
        if topic_data['user_specific']['liked_emojis']:
            pass  # 数据已导入，无需额外日志

    def _import_comments(self, topic_id: int, comments: List[Dict[str, Any]]):
        """导入评论信息"""
        for comment in comments:
            self._upsert_comment(topic_id, comment)
            # 导入评论的图片
            if 'images' in comment and comment['images']:
                self._import_comment_images(topic_id, comment['comment_id'], comment['images'])

        if comments:
            pass  # 数据已导入，无需额外日志

    def import_additional_comments(self, topic_id: int, comments: List[Dict[str, Any]]):
        """导入额外获取的评论信息（来自评论API）"""
        if not comments:
            return

        print(f"📝 导入话题 {topic_id} 的 {len(comments)} 条额外评论...")

        for comment in comments:
            # 导入评论作者
            if 'owner' in comment and comment['owner']:
                self._upsert_user(comment['owner'])

            # 导入回复人（如果存在）
            if 'repliee' in comment and comment['repliee']:
                self._upsert_user(comment['repliee'])

            # 导入评论
            self._upsert_comment(topic_id, comment)

            # 导入评论的图片
            if 'images' in comment and comment['images']:
                self._import_comment_images(topic_id, comment['comment_id'], comment['images'])

        print(f"✅ 完成导入 {len(comments)} 条评论")

    def _upsert_comment(self, topic_id: int, comment_data: Dict[str, Any]):
        """插入或更新评论信息"""
        comment_id = comment_data.get('comment_id')
        if not comment_id:
            return
        
        owner_user_id = comment_data.get('owner', {}).get('user_id')
        repliee_user_id = comment_data.get('repliee', {}).get('user_id')
        
        # 获取当前时间作为imported_at（使用东八区时间格式）
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
        group_id = self._resolve_topic_group_id(topic_id, comment_data.get('group_id'))
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO comments
            (comment_id, group_id, topic_id, owner_user_id, parent_comment_id, repliee_user_id,
             text, create_time, likes_count, rewards_count, replies_count, sticky, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            comment_id,
            group_id,
            topic_id,
            owner_user_id,
            comment_data.get('parent_comment_id'),
            repliee_user_id,
            comment_data.get('text', ''),
            comment_data.get('create_time', ''),
            comment_data.get('likes_count', 0),
            comment_data.get('rewards_count', 0),
            comment_data.get('replies_count', 0),
            comment_data.get('sticky', False),
            current_time
        ))

    def _resolve_topic_group_id(self, topic_id: int, explicit_group_id: Optional[Any] = None):
        """Resolve group_id for comments fetched separately from topic payloads."""
        group_id = explicit_group_id or self.group_id
        if group_id:
            return _nullable_group_id_param(str(group_id))
        try:
            self.cursor.execute('SELECT group_id FROM topics WHERE topic_id = ? LIMIT 1', (topic_id,))
            row = self.cursor.fetchone()
            return row[0] if row and row[0] is not None else None
        except Exception:
            return None

    def _import_comment_images(self, topic_id: int, comment_id: int, images: List[Dict[str, Any]]):
        """导入评论的图片信息"""
        for image in images:
            if not image.get('image_id'):
                continue

            # 获取当前时间作为created_at（使用东八区时间格式）
            from datetime import datetime, timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'

            self.cursor.execute('''
                INSERT OR REPLACE INTO images
                (image_id, topic_id, comment_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
                 large_url, large_width, large_height, original_url, original_width, original_height,
                 original_size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                image.get('image_id'),
                topic_id,
                comment_id,
                image.get('type', ''),
                image.get('thumbnail', {}).get('url', ''),
                image.get('thumbnail', {}).get('width', 0),
                image.get('thumbnail', {}).get('height', 0),
                image.get('large', {}).get('url', ''),
                image.get('large', {}).get('width', 0),
                image.get('large', {}).get('height', 0),
                image.get('original', {}).get('url', ''),
                image.get('original', {}).get('width', 0),
                image.get('original', {}).get('height', 0),
                image.get('original', {}).get('size', 0),
                current_time
            ))

    def _upsert_question(self, topic_id: int, question_data: Dict[str, Any]):
        """插入或更新问题信息"""
        owner_user_id = question_data.get('owner', {}).get('user_id')
        questionee_user_id = question_data.get('questionee', {}).get('user_id')
        is_anonymous = question_data.get('anonymous', False)

        # 对于匿名用户，owner_user_id 可能为 None，但仍需要存储问题信息
        # 只有在既没有 owner_user_id 又没有问题文本时才跳过
        if not owner_user_id and not question_data.get('text'):
            return

        owner_detail = question_data.get('owner_detail', {})

        # 获取当前时间作为created_at（使用东八区时间格式）
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'

        self.cursor.execute('''
            INSERT OR REPLACE INTO questions
            (topic_id, owner_user_id, questionee_user_id, text, expired, anonymous,
             owner_questions_count, owner_join_time, owner_status, owner_location, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            topic_id,
            owner_user_id,  # 对于匿名用户可能为 None
            questionee_user_id,
            question_data.get('text', ''),
            question_data.get('expired', False),
            is_anonymous,
            owner_detail.get('questions_count'),
            owner_detail.get('join_time', owner_detail.get('estimated_join_time', '')),  # 支持 estimated_join_time
            owner_detail.get('status', ''),
            question_data.get('owner_location', ''),
            current_time
        ))

    
    def _upsert_answer(self, topic_id: int, answer_data: Dict[str, Any]):
        """插入或更新回答信息"""
        owner_user_id = answer_data.get('owner', {}).get('user_id')
        
        if not owner_user_id:
            return
        
        # 获取当前时间作为created_at（使用东八区时间格式）
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO answers 
            (topic_id, owner_user_id, text, created_at)
            VALUES (?, ?, ?, ?)
        ''', (
            topic_id,
            owner_user_id,
            answer_data.get('text', ''),
            current_time
        ))

    
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
        self.cursor.execute('''
            SELECT create_time FROM topics WHERE topic_id = ?
        ''', (topic_id,))
        result = self.cursor.fetchone()
        created_at = result[0] if result else ''
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO articles
            (topic_id, title, article_id, article_url, inline_article_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            topic_id,
            title,
            article_id,
            article_data.get('article_url', ''),
            article_data.get('inline_article_url', ''),
            created_at
        ))

    def _import_files(self, topic_id: int, files_data: List[Dict[str, Any]]):
        """导入话题文件信息"""
        if not files_data:
            return

        for file_data in files_data:
            if not file_data.get('file_id'):
                continue

            # 获取当前时间作为created_at（使用东八区时间格式）
            from datetime import datetime, timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'

            self.cursor.execute('''
                INSERT OR REPLACE INTO topic_files
                (topic_id, file_id, name, hash, size, duration, download_count, create_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                topic_id,
                file_data.get('file_id'),
                file_data.get('name', ''),
                file_data.get('hash', ''),
                file_data.get('size', 0),
                file_data.get('duration', 0),
                file_data.get('download_count', 0),
                file_data.get('create_time', ''),
                current_time
            ))

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
            self.cursor.execute('''
                SELECT
                    tf.topic_id, tf.file_id, tf.name, tf.hash, tf.size, tf.duration,
                    tf.download_count, tf.create_time,
                    t.group_id, t.type, t.title, t.annotation, t.create_time,
                    t.likes_count, t.tourist_likes_count, t.rewards_count,
                    t.comments_count, t.reading_count, t.readers_count,
                    t.digested, t.sticky, t.user_liked, t.user_subscribed,
                    g.name, g.type, g.background_url
                FROM topic_files tf
                LEFT JOIN topics t ON t.topic_id = tf.topic_id
                LEFT JOIN groups g ON g.group_id = t.group_id
                WHERE tf.file_id IS NOT NULL
                  AND (? IS NULL OR t.group_id = ?)
                ORDER BY tf.topic_id ASC, tf.file_id ASC
            ''', (_group_id_param(self.group_id), _group_id_param(self.group_id)))
            for row in self.cursor.fetchall():
                stats['scanned'] += 1
                (
                    topic_id, file_id, name, file_hash, size, duration, download_count, file_create_time,
                    group_id, topic_type, title, annotation, topic_create_time,
                    likes_count, tourist_likes_count, rewards_count, comments_count,
                    reading_count, readers_count, digested, sticky, user_liked, user_subscribed,
                    group_name, group_type, background_url,
                ) = row

                self.cursor.execute(
                    'SELECT 1 FROM files WHERE file_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1',
                    (file_id, _group_id_param(self.group_id), _group_id_param(self.group_id)),
                )
                is_new_file = self.cursor.fetchone() is None

                if group_id and group_name:
                    self._upsert_group({
                        'group_id': group_id,
                        'name': group_name or '',
                        'type': group_type,
                        'background_url': background_url,
                    })

                if topic_id and group_id and topic_type:
                    file_db.insert_topic({
                        'topic_id': topic_id,
                        'group': {'group_id': group_id},
                        'type': topic_type,
                        'title': title,
                        'annotation': annotation,
                        'create_time': topic_create_time,
                        'likes_count': likes_count or 0,
                        'tourist_likes_count': tourist_likes_count or 0,
                        'rewards_count': rewards_count or 0,
                        'comments_count': comments_count or 0,
                        'reading_count': reading_count or 0,
                        'readers_count': readers_count or 0,
                        'digested': bool(digested),
                        'sticky': bool(sticky),
                        'user_specific': {
                            'liked': bool(user_liked),
                            'subscribed': bool(user_subscribed),
                        },
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
            # 1. 获取基本话题信息和群组信息
            self.cursor.execute('''
                SELECT
                    t.topic_id, t.type, t.title, t.create_time, t.digested, t.sticky,
                    t.likes_count, t.tourist_likes_count, t.rewards_count, t.comments_count,
                    t.reading_count, t.readers_count, t.answered, t.silenced, t.annotation,
                    t.user_liked, t.user_subscribed,
                    g.group_id, g.name as group_name, g.type as group_type, g.background_url
                FROM topics t
                LEFT JOIN groups g ON t.group_id = g.group_id
                WHERE t.topic_id = ?
            ''', (topic_id,))

            topic_row = self.cursor.fetchone()
            if not topic_row:
                return None

            # 构建基本话题信息
            topic_detail = {
                "topic_id": topic_row[0],
                "type": topic_row[1],
                "title": topic_row[2],
                "create_time": topic_row[3],
                "digested": bool(topic_row[4]),
                "sticky": bool(topic_row[5]),
                "likes_count": topic_row[6],
                "tourist_likes_count": topic_row[7],
                "rewards_count": topic_row[8],
                "comments_count": topic_row[9],
                "reading_count": topic_row[10],
                "readers_count": topic_row[11],
                "answered": bool(topic_row[12]),
                "silenced": bool(topic_row[13]),
                "annotation": topic_row[14],
                "group": {
                    "group_id": topic_row[17],
                    "name": topic_row[18],
                    "type": topic_row[19],
                    "background_url": topic_row[20]
                },
                "user_specific": {
                    "liked": bool(topic_row[15]),
                    "liked_emojis": [],
                    "subscribed": bool(topic_row[16])
                }
            }

            # 2. 获取话题内容（talk）
            self.cursor.execute('''
                SELECT
                    t.text,
                    u.user_id, u.name, u.alias, u.avatar_url, u.location, u.description
                FROM talks t
                LEFT JOIN users u ON t.owner_user_id = u.user_id
                WHERE t.topic_id = ?
                LIMIT 1
            ''', (topic_id,))

            talk_row = self.cursor.fetchone()
            if talk_row:
                talk_data = {
                    "text": talk_row[0],
                    "owner": {
                        "user_id": talk_row[1],
                        "name": talk_row[2],
                        "alias": talk_row[3],
                        "avatar_url": talk_row[4],
                        "location": talk_row[5],
                        "description": talk_row[6]
                    }
                }

                # 获取话题图片
                self.cursor.execute('''
                    SELECT
                        image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
                        large_url, large_width, large_height,
                        original_url, original_width, original_height, original_size
                    FROM images
                    WHERE topic_id = ? AND comment_id IS NULL
                    ORDER BY image_id
                ''', (topic_id,))

                images = []
                for img_row in self.cursor.fetchall():
                    images.append({
                        "image_id": img_row[0],
                        "type": img_row[1],
                        "thumbnail": {
                            "url": img_row[2],
                            "width": img_row[3],
                            "height": img_row[4]
                        },
                        "large": {
                            "url": img_row[5],
                            "width": img_row[6],
                            "height": img_row[7]
                        },
                        "original": {
                            "url": img_row[8],
                            "width": img_row[9],
                            "height": img_row[10],
                            "size": img_row[11]
                        }
                    })

                if images:
                    talk_data["images"] = images

                # 获取话题文件
                self.cursor.execute('''
                    SELECT
                        file_id, name, hash, size, duration, download_count, create_time
                    FROM topic_files
                    WHERE topic_id = ?
                    ORDER BY file_id
                ''', (topic_id,))

                files = []
                for file_row in self.cursor.fetchall():
                    files.append({
                        "file_id": file_row[0],
                        "name": file_row[1],
                        "hash": file_row[2],
                        "size": file_row[3],
                        "duration": file_row[4],
                        "download_count": file_row[5],
                        "create_time": file_row[6]
                    })

                if files:
                    talk_data["files"] = files

                # 读取文章信息（如有）
                self.cursor.execute('''
                    SELECT title, article_id, article_url, inline_article_url
                    FROM articles
                    WHERE topic_id = ?
                    LIMIT 1
                ''', (topic_id,))
                article_row = self.cursor.fetchone()
                if article_row:
                    talk_data["article"] = {
                        "title": article_row[0],
                        "article_id": article_row[1],
                        "article_url": article_row[2],
                        "inline_article_url": article_row[3]
                    }

                topic_detail["talk"] = talk_data

            # 3. 获取最新点赞
            self.cursor.execute('''
                SELECT
                    l.create_time,
                    u.user_id, u.name, u.avatar_url
                FROM likes l
                LEFT JOIN users u ON l.user_id = u.user_id
                WHERE l.topic_id = ?
                ORDER BY l.create_time DESC
                LIMIT 5
            ''', (topic_id,))

            latest_likes = []
            for like_row in self.cursor.fetchall():
                latest_likes.append({
                    "create_time": like_row[0],
                    "owner": {
                        "user_id": like_row[1],
                        "name": like_row[2],
                        "avatar_url": like_row[3]
                    }
                })
            topic_detail["latest_likes"] = latest_likes

            # 4. 获取评论 - 不再限制为10条，返回所有评论
            self.cursor.execute('''
                SELECT
                    c.comment_id, c.text, c.create_time, c.likes_count, c.rewards_count, c.sticky,
                    c.parent_comment_id, c.replies_count,
                    u.user_id, u.name, u.alias, u.avatar_url, u.location, u.description,
                    r.user_id as repliee_user_id, r.name as repliee_name, r.avatar_url as repliee_avatar_url
                FROM comments c
                LEFT JOIN users u ON c.owner_user_id = u.user_id
                LEFT JOIN users r ON c.repliee_user_id = r.user_id
                WHERE c.topic_id = ?
                ORDER BY c.create_time ASC
            ''', (topic_id,))

            comment_rows = self.cursor.fetchall()
            comment_ids = [row[0] for row in comment_rows]
            comment_images_map = {}

            # 批量获取评论图片，避免按评论逐条查询造成 N+1
            if comment_ids:
                chunk_size = 500
                for start in range(0, len(comment_ids), chunk_size):
                    chunk_ids = comment_ids[start:start + chunk_size]
                    placeholders = ','.join('?' for _ in chunk_ids)
                    self.cursor.execute(f'''
                        SELECT
                            comment_id, image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
                            large_url, large_width, large_height,
                            original_url, original_width, original_height, original_size
                        FROM images
                        WHERE comment_id IN ({placeholders})
                        ORDER BY comment_id ASC, image_id ASC
                    ''', chunk_ids)

                    for img_row in self.cursor.fetchall():
                        comment_images_map.setdefault(img_row[0], []).append({
                            "image_id": img_row[1],
                            "type": img_row[2],
                            "thumbnail": {
                                "url": img_row[3],
                                "width": img_row[4],
                                "height": img_row[5]
                            },
                            "large": {
                                "url": img_row[6],
                                "width": img_row[7],
                                "height": img_row[8]
                            },
                            "original": {
                                "url": img_row[9],
                                "width": img_row[10],
                                "height": img_row[11],
                                "size": img_row[12]
                            }
                        })

            # 先收集所有评论，然后构建嵌套结构
            all_comments = {}  # comment_id -> comment_data
            parent_comments = []  # 顶级评论
            child_comments = []   # 子评论（有parent_comment_id的）

            for comment_row in comment_rows:
                comment_id = comment_row[0]
                parent_comment_id = comment_row[6]

                comment_data = {
                    "comment_id": comment_id,
                    "text": comment_row[1],
                    "create_time": comment_row[2],
                    "likes_count": comment_row[3],
                    "rewards_count": comment_row[4],
                    "sticky": bool(comment_row[5]),
                    "parent_comment_id": parent_comment_id,
                    "replies_count": comment_row[7],
                    "owner": {
                        "user_id": comment_row[8],
                        "name": comment_row[9],
                        "alias": comment_row[10],
                        "avatar_url": comment_row[11],
                        "location": comment_row[12],
                        "description": comment_row[13]
                    }
                }

                # 添加回复人信息（如果存在）
                if comment_row[14]:  # repliee_user_id
                    comment_data["repliee"] = {
                        "user_id": comment_row[14],
                        "name": comment_row[15],
                        "avatar_url": comment_row[16]
                    }

                images = comment_images_map.get(comment_id, [])
                if images:
                    comment_data["images"] = images

                # 存储评论并分类
                all_comments[comment_id] = comment_data
                if parent_comment_id:
                    child_comments.append(comment_data)
                else:
                    parent_comments.append(comment_data)

            # 构建嵌套结构：将子评论附加到父评论的 replied_comments 中
            for child in child_comments:
                parent_id = child.get("parent_comment_id")
                if parent_id and parent_id in all_comments:
                    parent = all_comments[parent_id]
                    if "replied_comments" not in parent:
                        parent["replied_comments"] = []
                    parent["replied_comments"].append(child)

            topic_detail["show_comments"] = parent_comments

            # 5. 获取点赞详情（表情）
            self.cursor.execute('''
                SELECT emoji_key, likes_count
                FROM like_emojis
                WHERE topic_id = ?
            ''', (topic_id,))

            emojis = []
            for emoji_row in self.cursor.fetchall():
                emojis.append({
                    "emoji_key": emoji_row[0],
                    "likes_count": emoji_row[1]
                })

            topic_detail["likes_detail"] = {
                "emojis": emojis
            }

            # 6. 获取问答数据（如果是问答类型话题）
            if topic_detail["type"] == "q&a":
                # 获取问题信息
                self.cursor.execute('''
                    SELECT
                        q.text, q.expired, q.anonymous, q.owner_questions_count,
                        q.owner_join_time, q.owner_status, q.owner_location,
                        owner.user_id as owner_user_id, owner.name as owner_name,
                        owner.alias as owner_alias, owner.avatar_url as owner_avatar_url,
                        owner.location as owner_location_detail, owner.description as owner_description,
                        questionee.user_id as questionee_user_id, questionee.name as questionee_name,
                        questionee.alias as questionee_alias, questionee.avatar_url as questionee_avatar_url,
                        questionee.location as questionee_location, questionee.description as questionee_description
                    FROM questions q
                    LEFT JOIN users owner ON q.owner_user_id = owner.user_id
                    LEFT JOIN users questionee ON q.questionee_user_id = questionee.user_id
                    WHERE q.topic_id = ?
                    LIMIT 1
                ''', (topic_id,))

                question_row = self.cursor.fetchone()
                if question_row:
                    question_data = {
                        "text": question_row[0],
                        "expired": bool(question_row[1]),
                        "anonymous": bool(question_row[2]),
                        "owner_detail": {
                            "questions_count": question_row[3],
                            "estimated_join_time": question_row[4],
                            "status": question_row[5]
                        },
                        "owner_location": question_row[6]
                    }

                    # 添加被提问者信息
                    if question_row[12]:  # questionee_user_id
                        question_data["questionee"] = {
                            "user_id": question_row[12],
                            "name": question_row[13],
                            "alias": question_row[14],
                            "avatar_url": question_row[15],
                            "location": question_row[16],
                            "description": question_row[17]
                        }

                    # 如果不是匿名且有提问者信息，添加提问者信息
                    if not question_data["anonymous"] and question_row[7]:  # owner_user_id
                        question_data["owner"] = {
                            "user_id": question_row[7],
                            "name": question_row[8],
                            "alias": question_row[9],
                            "avatar_url": question_row[10],
                            "location": question_row[11],
                            "description": question_row[11]
                        }

                    topic_detail["question"] = question_data

                # 获取回答信息
                self.cursor.execute('''
                    SELECT
                        a.text,
                        u.user_id, u.name, u.alias, u.avatar_url, u.location, u.description
                    FROM answers a
                    LEFT JOIN users u ON a.owner_user_id = u.user_id
                    WHERE a.topic_id = ?
                    LIMIT 1
                ''', (topic_id,))

                answer_row = self.cursor.fetchone()
                if answer_row:
                    answer_data = {
                        "text": answer_row[0],
                        "owner": {
                            "user_id": answer_row[1],
                            "name": answer_row[2],
                            "alias": answer_row[3],
                            "avatar_url": answer_row[4],
                            "location": answer_row[5],
                            "description": answer_row[6]
                        }
                    }
                    topic_detail["answer"] = answer_data

            return topic_detail

        except Exception as e:
            print(f"获取话题详情失败: {e}")
            return None
    
    def _import_tags(self, topic_id: int, topic_data: Dict[str, Any]):
        """从话题数据中提取并导入标签信息"""
        import re
        
        group_id = topic_data.get('group', {}).get('group_id')
        if not group_id:
            return
        
        # 收集所有可能包含标签的文本内容
        text_contents = []
        
        # 从talk内容中提取
        if 'talk' in topic_data and topic_data['talk'] and 'text' in topic_data['talk']:
            text_contents.append(topic_data['talk']['text'])
        
        # 从question内容中提取
        if 'question' in topic_data and topic_data['question'] and 'text' in topic_data['question']:
            text_contents.append(topic_data['question']['text'])
        
        # 从answer内容中提取
        if 'answer' in topic_data and topic_data['answer'] and 'text' in topic_data['answer']:
            text_contents.append(topic_data['answer']['text'])
        
        # 从评论中提取
        if 'show_comments' in topic_data:
            for comment in topic_data['show_comments']:
                if 'text' in comment:
                    text_contents.append(comment['text'])
        
        # 提取所有标签
        all_tags = set()
        for text in text_contents:
            if text:
                # 使用正则表达式提取标签 <e type="hashtag" hid="..." title="..." />
                tag_pattern = r'<e\s+type="hashtag"\s+hid="([^"]+)"\s+title="([^"]+)"\s*/>'
                matches = re.findall(tag_pattern, text)
                for hid, encoded_title in matches:
                    try:
                        # 解码标签名称
                        import urllib.parse
                        tag_name = urllib.parse.unquote(encoded_title)
                        # 移除可能的#符号
                        tag_name = tag_name.strip('#')
                        if tag_name:
                            all_tags.add((tag_name, hid))
                    except Exception as e:
                        print(f"解码标签失败: {e}")
        
        # 为每个标签创建或更新数据库记录
        for tag_name, hid in all_tags:
            tag_id = self._upsert_tag(group_id, tag_name, hid)
            if tag_id:
                self._link_topic_tag(topic_id, tag_id)
    
    def _upsert_tag(self, group_id: int, tag_name: str, hid: str = None) -> Optional[int]:
        """插入或更新标签信息"""
        try:
            # 检查标签是否已存在
            self.cursor.execute('''
                SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?
            ''', (group_id, tag_name))
            
            result = self.cursor.fetchone()
            if result:
                tag_id = result[0]
                # 更新hid（如果提供了新的hid）
                if hid:
                    self.cursor.execute('''
                        UPDATE tags SET hid = ? WHERE tag_id = ?
                    ''', (hid, tag_id))
                return tag_id
            else:
                # 插入新标签
                from datetime import datetime, timezone, timedelta
                beijing_tz = timezone(timedelta(hours=8))
                current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
                
                self.cursor.execute('''
                    INSERT INTO tags (group_id, tag_name, hid, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (group_id, tag_name, hid, current_time))
                
                return self.cursor.lastrowid
        except Exception as e:
            print(f"插入标签失败: {e}")
            return None
    
    def _link_topic_tag(self, topic_id: int, tag_id: int):
        """关联话题和标签"""
        try:
            from datetime import datetime, timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0800'
            
            self.cursor.execute('''
                INSERT OR IGNORE INTO topic_tags (topic_id, tag_id, created_at)
                VALUES (?, ?, ?)
            ''', (topic_id, tag_id, current_time))
            
            # 更新标签的话题计数
            self.cursor.execute('''
                UPDATE tags SET topic_count = (
                    SELECT COUNT(*) FROM topic_tags WHERE tag_id = ?
                ) WHERE tag_id = ?
            ''', (tag_id, tag_id))
            
        except Exception as e:
            print(f"关联话题标签失败: {e}")
    
    def get_tags_by_group(self, group_id: int) -> List[Dict[str, Any]]:
        """获取指定群组的所有标签"""
        try:
            self.cursor.execute('''
                SELECT tag_id, tag_name, hid, topic_count, created_at
                FROM tags
                WHERE group_id = ?
                ORDER BY topic_count DESC, tag_name ASC
            ''', (group_id,))
            
            return [_format_tag_row(row) for row in self.cursor.fetchall()]
        except Exception as e:
            print(f"获取标签列表失败: {e}")
            return []
    
    def get_topics_by_tag(self, tag_id: int, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """根据标签获取话题列表"""
        try:
            offset = (page - 1) * per_page
            
            # 获取话题列表 - 包含所有详细信息，与get_group_topics保持一致
            self.cursor.execute('''
                SELECT
                    t.topic_id, t.title, t.create_time, t.likes_count, t.comments_count,
                    t.reading_count, t.type, t.digested, t.sticky,
                    q.text as question_text,
                    a.text as answer_text,
                    tk.text as talk_text,
                    u.user_id, u.name, u.avatar_url
                FROM topics t
                INNER JOIN topic_tags tt ON t.topic_id = tt.topic_id
                LEFT JOIN questions q ON t.topic_id = q.topic_id
                LEFT JOIN answers a ON t.topic_id = a.topic_id
                LEFT JOIN talks tk ON t.topic_id = tk.topic_id
                LEFT JOIN users u ON tk.owner_user_id = u.user_id
                WHERE tt.tag_id = ?
                ORDER BY t.create_time DESC
                LIMIT ? OFFSET ?
            ''', (tag_id, per_page, offset))
            
            topics = [_format_tag_topic_row(topic) for topic in self.cursor.fetchall()]
            
            # 获取总数
            self.cursor.execute('''
                SELECT COUNT(*)
                FROM topic_tags
                WHERE tag_id = ?
            ''', (tag_id,))
            total = self.cursor.fetchone()[0]
            
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
