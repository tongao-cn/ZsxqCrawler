from typing import Any, Dict, List, NamedTuple, Optional, Sequence

from backend.storage.db_compat import connect
from backend.storage.zsxq_file_database_helpers import (
    _api_response_record_params,
    _close_connection,
    _column_record_params,
    _comment_record_params,
    _count_tables,
    _file_ai_analysis_params,
    _file_attachment_params,
    _file_download_status_params,
    _file_record_params,
    _file_topic_relation_params,
    _group_id_param,
    _image_record_params,
    _group_record_params,
    _latest_like_record_params,
    _like_emoji_record_params,
    _new_import_stats,
    _nullable_group_id_param,
    _record_imported_items,
    _record_imported_value,
    _row_to_file_ai_analysis,
    _solution_record_params,
    _talk_record_params,
    _topic_column_record_params,
    _topic_record_params,
    _user_liked_emoji_record_params,
    _user_record_params,
)


_COMPLETED_DOWNLOAD_STATUSES = ("completed", "downloaded", "skipped")

_FILE_SEARCH_CONDITION = """
        (
            LOWER(COALESCE(f.name, '')) LIKE ?
            OR EXISTS (
                SELECT 1
                FROM file_topic_relations fr
                LEFT JOIN topics t ON t.topic_id = fr.topic_id
                LEFT JOIN talks tk ON tk.topic_id = fr.topic_id
                LEFT JOIN articles ar ON ar.topic_id = fr.topic_id
                WHERE fr.file_id = f.file_id
                  AND (
                      LOWER(COALESCE(t.title, '')) LIKE ?
                      OR LOWER(COALESCE(t.annotation, '')) LIKE ?
                      OR LOWER(COALESCE(tk.text, '')) LIKE ?
                      OR LOWER(COALESCE(ar.title, '')) LIKE ?
                  )
            )
            OR EXISTS (
                SELECT 1
                FROM topic_files tf
                LEFT JOIN topics t2 ON t2.topic_id = tf.topic_id
                WHERE tf.file_id = f.file_id
                  AND (
                      LOWER(COALESCE(tf.name, '')) LIKE ?
                      OR LOWER(COALESCE(t2.title, '')) LIKE ?
                      OR LOWER(COALESCE(t2.annotation, '')) LIKE ?
                  )
            )
        )
        """


class DownloadFileRecord(NamedTuple):
    file_id: int
    name: str
    size: int
    download_count: int = 0

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "DownloadFileRecord":
        file_id = int(row[0])
        return cls(
            file_id=file_id,
            name=str(row[1] or f"file_{file_id}"),
            size=int(row[2] or 0),
            download_count=int(row[3] or 0),
        )

    def to_downloader_payload(self) -> Dict[str, Dict[str, Any]]:
        return {
            "file": {
                "id": self.file_id,
                "name": self.name,
                "size": self.size,
                "download_count": self.download_count,
            }
        }


def _query_group_id(group_id: Optional[Any]) -> Any:
    return _group_id_param(group_id)


def _unique_int_file_ids(file_ids: Sequence[int]) -> list[int]:
    return list(dict.fromkeys(int(file_id) for file_id in file_ids))


def _add_file_download_status_condition(
    conditions: list[str],
    params: list[Any],
    status: Optional[str],
    *,
    strip_status: bool = False,
    treat_all_as_empty: bool = False,
    exclude_completed_when_empty: bool = False,
) -> None:
    requested_status = str(status or "")
    if strip_status:
        requested_status = requested_status.strip()
    if treat_all_as_empty and requested_status == "all":
        requested_status = ""

    if requested_status:
        if requested_status == "completed":
            conditions.append("f.download_status IN (?, ?, ?)")
            params.extend(_COMPLETED_DOWNLOAD_STATUSES)
        else:
            conditions.append("f.download_status = ?")
            params.append(requested_status)
    elif exclude_completed_when_empty:
        conditions.append("(f.download_status IS NULL OR f.download_status NOT IN (?, ?, ?))")
        params.extend(_COMPLETED_DOWNLOAD_STATUSES)


def _add_file_search_condition(conditions: list[str], params: list[Any], search: Optional[str]) -> None:
    search_text = (search or "").strip()
    if not search_text:
        return

    search_pattern = f"%{search_text.lower()}%"
    conditions.append(_FILE_SEARCH_CONDITION)
    params.extend([search_pattern] * 8)


def _build_selected_download_file_records_query(
    group_id: Optional[Any],
    ordered_ids: Sequence[int],
) -> tuple[str, tuple[Any, ...]]:
    placeholders = ", ".join("?" for _ in ordered_ids)
    return (
        f"""
        SELECT file_id, name, size, download_count
        FROM files
        WHERE group_id = ? AND file_id IN ({placeholders})
        """,
        (_query_group_id(group_id), *ordered_ids),
    )


def _fetch_download_file_rows(
    file_db: Any,
    query: str,
    params: Sequence[Any],
) -> Sequence[Sequence[Any]]:
    file_db.cursor.execute(query, params)
    return file_db.cursor.fetchall()


def _normalize_download_file_record(row: Sequence[Any]) -> DownloadFileRecord:
    return DownloadFileRecord.from_row(row)


def _build_filtered_download_file_records_query(
    group_id: Optional[Any],
    status: Optional[str],
    search: Optional[str],
    max_files: Optional[int],
) -> tuple[str, tuple[Any, ...]]:
    conditions = ["f.group_id = ?"]
    params: list[Any] = [_query_group_id(group_id)]
    _add_file_download_status_condition(
        conditions,
        params,
        status,
        strip_status=True,
        treat_all_as_empty=True,
        exclude_completed_when_empty=True,
    )

    _add_file_search_condition(conditions, params, search)
    limit_clause = "LIMIT ?" if max_files else ""
    if max_files:
        params.append(int(max_files))

    return (
        f"""
        SELECT f.file_id, f.name, f.size, f.download_count
        FROM files f
        WHERE {' AND '.join(conditions)}
        ORDER BY f.create_time DESC, f.download_count DESC
        {limit_clause}
        """,
        tuple(params),
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
        ''', _user_record_params(user_data))
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
        ''', _group_record_params(group_data))
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
        ''', _topic_record_params(topic_data))
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

    def count_files(self, group_id: Optional[Any] = None) -> int:
        scoped_group_id = self.group_id if group_id is None else group_id
        self.cursor.execute(
            "SELECT COUNT(*) FROM files WHERE group_id = ?",
            (_query_group_id(scoped_group_id),),
        )
        row = self.cursor.fetchone()
        return (row[0] or 0) if row else 0

    def get_download_file_record(
        self,
        file_id: int,
        group_id: Optional[Any] = None,
    ) -> Optional[DownloadFileRecord]:
        scoped_group_id = self.group_id if group_id is None else group_id
        self.cursor.execute(
            """
            SELECT file_id, name, size, download_count
            FROM files
            WHERE file_id = ? AND group_id = ?
            """,
            (file_id, _query_group_id(scoped_group_id)),
        )
        row = self.cursor.fetchone()
        return _normalize_download_file_record(row) if row else None

    def load_download_file_records(
        self,
        file_ids: Sequence[int],
        group_id: Optional[Any] = None,
    ) -> tuple[list[DownloadFileRecord], list[int]]:
        ordered_ids = _unique_int_file_ids(file_ids)
        query, params = _build_selected_download_file_records_query(
            self.group_id if group_id is None else group_id,
            ordered_ids,
        )
        rows = _fetch_download_file_rows(self, query, params)
        by_file_id = {int(row[0]): row for row in rows}
        records = [
            _normalize_download_file_record(row)
            for row in (by_file_id[file_id] for file_id in ordered_ids if file_id in by_file_id)
        ]
        missing = [file_id for file_id in ordered_ids if file_id not in by_file_id]
        return records, missing

    def load_filtered_download_file_records(
        self,
        *,
        status: Optional[str] = None,
        search: Optional[str] = None,
        max_files: Optional[int] = None,
        group_id: Optional[Any] = None,
    ) -> list[DownloadFileRecord]:
        query, params = _build_filtered_download_file_records_query(
            self.group_id if group_id is None else group_id,
            status,
            search,
            max_files,
        )
        rows = _fetch_download_file_rows(self, query, params)
        return [_normalize_download_file_record(row) for row in rows]
    
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
        ''', _talk_record_params(topic_id, owner_id, talk_data))
    
    def insert_images(self, topic_id: int, images_data: List[Dict[str, Any]]):
        """插入图片信息"""
        for image in images_data:
            if not image.get('image_id'):
                continue
            
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
            ''', _image_record_params(topic_id, image))
    
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
            ''', _latest_like_record_params(topic_id, owner_id, like))
    
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
            ''', _comment_record_params(group_id, topic_id, owner_id, repliee_id, comment))

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
            ''', _like_emoji_record_params(topic_id, emoji))
    
    def insert_user_liked_emojis(self, topic_id: int, liked_emojis: List[str]):
        """插入用户点赞的表情"""
        for emoji_key in liked_emojis:
            self.cursor.execute('''
            INSERT INTO user_liked_emojis (topic_id, emoji_key)
            VALUES (?, ?)
            ON CONFLICT(topic_id, emoji_key) DO NOTHING
            ''', _user_liked_emoji_record_params(topic_id, emoji_key))
    
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
            ''', _column_record_params(column))
            
            # 插入话题-栏目关联
            self.cursor.execute('''
            INSERT INTO topic_columns (topic_id, column_id)
            VALUES (?, ?)
            ON CONFLICT(topic_id, column_id) DO NOTHING
            ''', _topic_column_record_params(topic_id, column.get('column_id')))
    
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
        ''', _solution_record_params(topic_id, owner_id, solution_data))
        
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
            ''', _api_response_record_params(response_data, len(files_data)))
            
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
                    _record_imported_value(stats, 'groups', group_id)
                
                # 插入话题
                topic_id = self.insert_topic(topic_data)
                if topic_id:
                    _record_imported_value(stats, 'topics', topic_id)

                    # 处理talk信息
                    talk_data = topic_data.get('talk', {})
                    topic_files = []
                    if talk_data:
                        self.insert_talk(topic_id, talk_data)
                        
                        # 处理talk中的图片
                        images = talk_data.get('images', [])
                        if images:
                            self.insert_images(topic_id, images)
                            _record_imported_items(stats, 'images', images)
                        
                        # 处理talk中的文件
                        topic_files = talk_data.get('files', [])
                    
                    # 处理最新点赞
                    latest_likes = topic_data.get('latest_likes', [])
                    if latest_likes:
                        self.insert_latest_likes(topic_id, latest_likes)
                        _record_imported_items(stats, 'likes', latest_likes)
                    
                    # 处理评论
                    comments = topic_data.get('show_comments', [])
                    if comments:
                        self.insert_comments(topic_id, comments)
                        _record_imported_items(stats, 'comments', comments)
                    
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
                        _record_imported_items(stats, 'columns', columns)
                    
                    # 处理解决方案
                    solution = topic_data.get('solution', {})
                    if solution:
                        solution_id = self.insert_solution(topic_id, solution)
                        _record_imported_value(stats, 'solutions', solution_id)

                    group_id_for_file = (topic_data.get('group') or {}).get('group_id')
                    file_id = self.insert_file(file_data, group_id=group_id_for_file, topic_id=topic_id)
                    _record_imported_value(stats, 'files', file_id)

                    self.cursor.execute('''
                    DELETE FROM file_topic_relations
                    WHERE file_id = ? AND topic_id = ?
                    ''', _file_topic_relation_params(file_id, topic_id))

                    self.cursor.execute('''
                    INSERT INTO file_topic_relations (file_id, topic_id)
                    VALUES (?, ?)
                    ON CONFLICT(file_id, topic_id) DO NOTHING
                    ''', _file_topic_relation_params(file_id, topic_id))

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
