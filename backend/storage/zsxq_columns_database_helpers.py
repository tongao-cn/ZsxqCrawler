"""Helper functions for ZSXQ columns storage."""

from typing import Any, Dict, Optional


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


def _comment_image_row_to_dict(row) -> Dict[str, Any]:
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
        }
    }


def _topic_file_row_to_dict(row) -> Dict[str, Any]:
    return {
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
    }


def _topic_video_row_to_dict(row) -> Dict[str, Any]:
    return {
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
    }


def _pending_video_row_to_dict(row) -> Dict[str, Any]:
    return {
        'video_id': row[0],
        'topic_id': row[1],
        'size': row[2],
        'duration': row[3],
        'cover_url': row[4],
        'group_id': row[5]
    }


def _topic_detail_row_to_dict(row) -> Dict[str, Any]:
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

    if row[15]:
        result['owner'] = {
            'user_id': row[15],
            'name': row[16],
            'alias': row[17],
            'avatar_url': row[18],
            'description': row[19],
            'location': row[20]
        }

    return result


def _topic_comment_row_to_dict(row) -> Dict[str, Any]:
    comment = {
        'comment_id': row[0],
        'parent_comment_id': row[1],
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

    return comment


def _column_insert_params(group_id: int, column_data: Dict[str, Any]) -> tuple[Any, ...]:
    statistics = column_data.get('statistics', {})

    return (
        column_data.get('column_id'),
        group_id,
        column_data.get('name', ''),
        column_data.get('cover_url'),
        statistics.get('topics_count', 0),
        column_data.get('create_time'),
        column_data.get('last_topic_attach_time')
    )


def _column_topic_insert_params(
    column_id: int,
    group_id: int,
    topic_data: Dict[str, Any],
) -> tuple[Any, ...]:
    return (
        topic_data.get('topic_id'),
        column_id,
        group_id,
        topic_data.get('title'),
        topic_data.get('text'),
        topic_data.get('create_time'),
        topic_data.get('attached_to_column_time')
    )


def _user_insert_params(user_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        user_data.get('user_id'),
        user_data.get('name', ''),
        user_data.get('alias'),
        user_data.get('avatar_url'),
        user_data.get('description'),
        user_data.get('location')
    )


def _topic_detail_insert_params(
    group_id: int,
    topic_data: Dict[str, Any],
    raw_json: Optional[str],
) -> tuple[Any, ...]:
    talk = topic_data.get('talk', {})

    return (
        topic_data.get('topic_id'),
        group_id,
        topic_data.get('type'),
        topic_data.get('title'),
        talk.get('text', ''),
        topic_data.get('likes_count', 0),
        topic_data.get('comments_count', 0),
        topic_data.get('readers_count', 0),
        topic_data.get('digested', False),
        topic_data.get('sticky', False),
        topic_data.get('create_time'),
        topic_data.get('modify_time'),
        raw_json
    )


def _topic_owner_insert_params(topic_id: int, user_id: int) -> tuple[Any, ...]:
    return (topic_id, user_id)


def _topic_image_insert_params(topic_id: int, image_data: Dict[str, Any]) -> tuple[Any, ...]:
    thumbnail = image_data.get('thumbnail', {})
    large = image_data.get('large', {})
    original = image_data.get('original', {})

    return (
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
    )


def _topic_file_insert_params(topic_id: int, file_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        file_data.get('file_id'),
        topic_id,
        file_data.get('name', ''),
        file_data.get('hash'),
        file_data.get('size'),
        file_data.get('duration'),
        file_data.get('download_count', 0),
        file_data.get('create_time')
    )


def _topic_video_insert_params(topic_id: int, video_data: Dict[str, Any]) -> tuple[Any, ...]:
    cover = video_data.get('cover', {})

    return (
        video_data.get('video_id'),
        topic_id,
        video_data.get('size'),
        video_data.get('duration'),
        cover.get('url'),
        cover.get('width'),
        cover.get('height')
    )


def _topic_comment_insert_params(
    topic_id: int,
    group_id: Any,
    owner_id: Optional[Any],
    repliee_id: Optional[Any],
    comment_data: Dict[str, Any],
) -> tuple[Any, ...]:
    return (
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
    )


def _nest_topic_comments(comments: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    all_comments = {}
    parent_comments = []
    child_comments = []

    for comment in comments:
        comment_id = comment['comment_id']
        parent_comment_id = comment['parent_comment_id']

        all_comments[comment_id] = comment
        if parent_comment_id:
            child_comments.append(comment)
        else:
            parent_comments.append(comment)

    for child in child_comments:
        parent_id = child.get("parent_comment_id")
        if parent_id and parent_id in all_comments:
            parent = all_comments[parent_id]
            if "replied_comments" not in parent:
                parent["replied_comments"] = []
            parent["replied_comments"].append(child)

    return parent_comments


def _pending_file_row_to_dict(row) -> Dict[str, Any]:
    return {
        'file_id': row[0],
        'topic_id': row[1],
        'name': row[2],
        'size': row[3],
        'hash': row[4],
        'group_id': row[5]
    }


def _uncached_image_row_to_dict(row) -> Dict[str, Any]:
    return {
        'image_id': row[0],
        'topic_id': row[1],
        'original_url': row[2],
        'group_id': row[3]
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


def _stats_count_queries(group_id: int) -> tuple[tuple[str, str, tuple[Any, ...]], ...]:
    return (
        ('columns_count', 'SELECT COUNT(*) FROM columns WHERE group_id = ?', (group_id,)),
        ('topics_count', 'SELECT COUNT(*) FROM column_topics WHERE group_id = ?', (group_id,)),
        ('details_count', 'SELECT COUNT(*) FROM topic_details WHERE group_id = ?', (group_id,)),
        (
            'images_count',
            '''
                SELECT COUNT(*) FROM images i
                JOIN topic_details td ON i.topic_id = td.topic_id
                WHERE td.group_id = ?
            ''',
            (group_id,),
        ),
        (
            'files_count',
            '''
                SELECT COUNT(*) FROM files f
                JOIN topic_details td ON f.topic_id = td.topic_id
                WHERE td.group_id = ?
            ''',
            (group_id,),
        ),
        (
            'files_downloaded',
            '''
                SELECT COUNT(*) FROM files f
                JOIN topic_details td ON f.topic_id = td.topic_id
                WHERE td.group_id = ? AND f.download_status = 'completed'
            ''',
            (group_id,),
        ),
        (
            'videos_count',
            '''
                SELECT COUNT(*) FROM videos v
                JOIN topic_details td ON v.topic_id = td.topic_id
                WHERE td.group_id = ?
            ''',
            (group_id,),
        ),
        (
            'videos_downloaded',
            '''
                SELECT COUNT(*) FROM videos v
                JOIN topic_details td ON v.topic_id = td.topic_id
                WHERE td.group_id = ? AND v.download_status = 'completed'
            ''',
            (group_id,),
        ),
        (
            'comments_count',
            '''
                SELECT COUNT(*) FROM comments c
                JOIN topic_details td ON c.topic_id = td.topic_id
                WHERE td.group_id = ?
            ''',
            (group_id,),
        ),
    )


def _crawl_log_insert_statement() -> str:
    return '''
        INSERT INTO crawl_log (group_id, crawl_type)
        VALUES (?, ?)
        RETURNING id
    '''


def _crawl_log_update_parts(
    columns_count: int = 0,
    topics_count: int = 0,
    details_count: int = 0,
    files_count: int = 0,
    status: Optional[str] = None,
    error_message: Optional[str] = None,
) -> tuple[list[str], list[Any]]:
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

    return updates, values


def _crawl_log_update_statement(updates: list[str]) -> str:
    return f'''
        UPDATE crawl_log SET {', '.join(updates)}
        WHERE id = ?
    '''


def _empty_clear_data_stats() -> Dict[str, int]:
    return {
        'columns_deleted': 0,
        'topics_deleted': 0,
        'details_deleted': 0,
        'images_deleted': 0,
        'files_deleted': 0,
        'videos_deleted': 0,
        'comments_deleted': 0,
        'users_deleted': 0
    }


def _topic_child_delete_statements(placeholders: str) -> tuple[tuple[Optional[str], str], ...]:
    return (
        ('comments_deleted', f'DELETE FROM comments WHERE topic_id IN ({placeholders})'),
        ('videos_deleted', f'DELETE FROM videos WHERE topic_id IN ({placeholders})'),
        ('files_deleted', f'DELETE FROM files WHERE topic_id IN ({placeholders})'),
        ('images_deleted', f'DELETE FROM images WHERE topic_id IN ({placeholders})'),
        (None, f'DELETE FROM topic_owners WHERE topic_id IN ({placeholders})'),
    )


def _group_clear_delete_statements() -> tuple[tuple[Optional[str], str], ...]:
    return (
        ('details_deleted', 'DELETE FROM topic_details WHERE group_id = ?'),
        ('topics_deleted', 'DELETE FROM column_topics WHERE group_id = ?'),
        ('columns_deleted', 'DELETE FROM columns WHERE group_id = ?'),
        (None, 'DELETE FROM crawl_log WHERE group_id = ?'),
    )


def _topic_group_id_query(topic_id: int) -> tuple[str, tuple[Any, ...]]:
    return 'SELECT group_id FROM topic_details WHERE topic_id = ? LIMIT 1', (topic_id,)


def _topic_detail_exists_query(topic_id: int) -> tuple[str, tuple[Any, ...]]:
    return 'SELECT 1 FROM topic_details WHERE topic_id = ?', (topic_id,)


def _group_topic_ids_query(group_id: int) -> tuple[str, tuple[Any, ...]]:
    return 'SELECT topic_id FROM topic_details WHERE group_id = ?', (group_id,)


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


def _column_insert_statement() -> str:
    return '''
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
        '''


def _columns_query(group_id: int) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT column_id, group_id, name, cover_url, topics_count,
                   create_time, last_topic_attach_time, imported_at
            FROM columns
            WHERE group_id = ?
            ORDER BY create_time DESC
        ''',
        (group_id,),
    )


def _column_query(column_id: int, scope_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT column_id, group_id, name, cover_url, topics_count,
                   create_time, last_topic_attach_time, imported_at
            FROM columns
            WHERE column_id = ? AND (? IS NULL OR group_id = ?)
        ''',
        (column_id, scope_group_id, scope_group_id),
    )


def _column_topic_insert_statement() -> str:
    return '''
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
        '''


def _column_topics_query(column_id: int, scope_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT ct.topic_id, ct.column_id, ct.group_id, ct.title, ct.text,
                   ct.create_time, ct.attached_to_column_time, ct.imported_at,
                   CASE WHEN td.topic_id IS NOT NULL THEN 1 ELSE 0 END as has_detail
            FROM column_topics ct
            LEFT JOIN topic_details td ON ct.topic_id = td.topic_id AND ct.group_id = td.group_id
            WHERE ct.column_id = ? AND (? IS NULL OR ct.group_id = ?)
            ORDER BY ct.attached_to_column_time DESC
        ''',
        (column_id, scope_group_id, scope_group_id),
    )


def _user_insert_statement() -> str:
    return '''
            INSERT INTO users
            (user_id, name, alias, avatar_url, description, location)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                alias = excluded.alias,
                avatar_url = excluded.avatar_url,
                description = excluded.description,
                location = excluded.location
        '''


def _topic_detail_insert_statement() -> str:
    return '''
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
        '''


def _topic_owner_insert_statement() -> str:
    return '''
                INSERT INTO topic_owners (topic_id, user_id, owner_type)
                VALUES (?, ?, 'talk')
                ON CONFLICT(topic_id, owner_type) DO UPDATE SET
                    user_id = excluded.user_id
            '''


def _topic_image_insert_statement() -> str:
    return '''
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
        '''


def _topic_file_insert_statement() -> str:
    return '''
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
        '''


def _topic_video_insert_statement() -> str:
    return '''
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
        '''


def _topic_comment_insert_statement() -> str:
    return '''
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
        '''


def _topic_detail_query(topic_id: int, scope_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT td.topic_id, td.group_id, td.type, td.title, td.full_text,
                   td.likes_count, td.comments_count, td.readers_count,
                   td.digested, td.sticky, td.create_time, td.modify_time,
                   td.raw_json, td.imported_at, td.updated_at,
                   u.user_id, u.name, u.alias, u.avatar_url, u.description, u.location
            FROM topic_details td
            LEFT JOIN topic_owners tow ON td.topic_id = tow.topic_id AND tow.owner_type = 'talk'
            LEFT JOIN users u ON tow.user_id = u.user_id
            WHERE td.topic_id = ? AND (? IS NULL OR td.group_id = ?)
        ''',
        (topic_id, scope_group_id, scope_group_id),
    )


def _topic_images_query(topic_id: int, scope_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
                   large_url, large_width, large_height, original_url, original_width,
                   original_height, original_size, local_path
            FROM images
            WHERE topic_id = ?
              AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topic_details WHERE group_id = ?))
        ''',
        (topic_id, scope_group_id, scope_group_id),
    )


def _topic_files_query(topic_id: int, scope_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT file_id, name, hash, size, duration, download_count,
                   create_time, download_status, local_path, download_time
            FROM files
            WHERE topic_id = ?
              AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topic_details WHERE group_id = ?))
        ''',
        (topic_id, scope_group_id, scope_group_id),
    )


def _topic_videos_query(topic_id: int, scope_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT video_id, size, duration, cover_url, cover_width, cover_height,
                   cover_local_path, video_url, download_status, local_path, download_time
            FROM videos
            WHERE topic_id = ?
              AND (? IS NULL OR topic_id IN (SELECT topic_id FROM topic_details WHERE group_id = ?))
        ''',
        (topic_id, scope_group_id, scope_group_id),
    )


def _comment_images_query(
    comment_id: int,
    scope_group_id: Any,
    topic_id: int,
) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            SELECT image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
                   large_url, large_width, large_height, original_url, original_width,
                   original_height, original_size
            FROM images
            WHERE comment_id = ?
              AND (? IS NULL OR topic_id = ?)
        ''',
        (comment_id, scope_group_id, topic_id),
    )


def _topic_comments_query(topic_id: int, scope_group_id: Any) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
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
        ''',
        (topic_id, scope_group_id, scope_group_id),
    )


def _video_cover_path_update(video_id: int, local_path: str) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            UPDATE videos SET cover_local_path = ?
            WHERE video_id = ?
        ''',
        (local_path, video_id),
    )


def _video_download_status_update(
    video_id: int,
    status: str,
    video_url: Optional[str],
    local_path: Optional[str],
) -> tuple[str, tuple[Any, ...]]:
    if local_path:
        return (
            '''
                UPDATE videos SET download_status = ?, video_url = ?, local_path = ?, download_time = CURRENT_TIMESTAMP
                WHERE video_id = ?
            ''',
            (status, video_url, local_path, video_id),
        )
    if video_url:
        return (
            '''
                UPDATE videos SET download_status = ?, video_url = ?
                WHERE video_id = ?
            ''',
            (status, video_url, video_id),
        )
    return (
        '''
            UPDATE videos SET download_status = ?
            WHERE video_id = ?
        ''',
        (status, video_id),
    )


def _file_download_status_update(
    file_id: int,
    status: str,
    group_id: Any,
    local_path: Optional[str],
) -> tuple[str, tuple[Any, ...]]:
    if local_path:
        return (
            '''
                UPDATE files SET download_status = ?, local_path = ?, download_time = CURRENT_TIMESTAMP
                WHERE file_id = ? AND (? IS NULL OR group_id = ?)
            ''',
            (status, local_path, file_id, group_id, group_id),
        )
    return (
        '''
            UPDATE files SET download_status = ?
            WHERE file_id = ? AND (? IS NULL OR group_id = ?)
        ''',
        (status, file_id, group_id, group_id),
    )


def _image_local_path_update(image_id: int, local_path: str) -> tuple[str, tuple[Any, ...]]:
    return (
        '''
            UPDATE images SET local_path = ?
            WHERE image_id = ?
        ''',
        (local_path, image_id),
    )


def _pending_videos_query(group_id: Optional[int]) -> tuple[str, Optional[tuple[Any, ...]]]:
    if group_id:
        return (
            '''
                SELECT v.video_id, v.topic_id, v.size, v.duration, v.cover_url, td.group_id
                FROM videos v
                JOIN topic_details td ON v.topic_id = td.topic_id
                WHERE v.download_status = 'pending' AND td.group_id = ?
            ''',
            (group_id,),
        )
    return (
        '''
            SELECT v.video_id, v.topic_id, v.size, v.duration, v.cover_url, td.group_id
            FROM videos v
            JOIN topic_details td ON v.topic_id = td.topic_id
            WHERE v.download_status = 'pending'
        ''',
        None,
    )


def _pending_files_query(group_id: Optional[int]) -> tuple[str, Optional[tuple[Any, ...]]]:
    if group_id:
        return (
            '''
                SELECT f.file_id, f.topic_id, f.name, f.size, f.hash, td.group_id
                FROM files f
                JOIN topic_details td ON f.topic_id = td.topic_id
                WHERE f.download_status = 'pending' AND td.group_id = ?
            ''',
            (group_id,),
        )
    return (
        '''
            SELECT f.file_id, f.topic_id, f.name, f.size, f.hash, td.group_id
            FROM files f
            JOIN topic_details td ON f.topic_id = td.topic_id
            WHERE f.download_status = 'pending'
        ''',
        None,
    )


def _uncached_images_query(group_id: Optional[int]) -> tuple[str, Optional[tuple[Any, ...]]]:
    if group_id:
        return (
            '''
                SELECT i.image_id, i.topic_id, i.original_url, td.group_id
                FROM images i
                JOIN topic_details td ON i.topic_id = td.topic_id
                WHERE i.local_path IS NULL AND i.original_url IS NOT NULL AND td.group_id = ?
            ''',
            (group_id,),
        )
    return (
        '''
            SELECT i.image_id, i.topic_id, i.original_url, td.group_id
            FROM images i
            JOIN topic_details td ON i.topic_id = td.topic_id
            WHERE i.local_path IS NULL AND i.original_url IS NOT NULL
        ''',
        None,
    )
