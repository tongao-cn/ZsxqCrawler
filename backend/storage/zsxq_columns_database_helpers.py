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
