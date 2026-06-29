from typing import Any, Dict, NamedTuple, Optional, Sequence


_IMPORT_STAT_KEYS = (
    'files',
    'topics',
    'users',
    'groups',
    'images',
    'comments',
    'likes',
    'columns',
    'solutions',
)

_STATS_TABLES = (
    'files', 'groups', 'users', 'topics', 'talks', 'images',
    'topic_files', 'latest_likes', 'comments', 'like_emojis',
    'user_liked_emojis', 'columns', 'topic_columns', 'solutions',
    'solution_files', 'file_topic_relations', 'api_responses', 'collection_log',
    'file_ai_analyses'
)

_FILE_AI_ANALYSIS_FIELDS = (
    'file_id',
    'status',
    'summary',
    'extracted_text',
    'extracted_text_preview',
    'content_type',
    'source_path',
    'source_size',
    'model',
    'api_base',
    'wire_api',
    'reasoning_effort',
    'error_message',
    'created_at',
    'updated_at',
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


def _new_import_stats() -> Dict[str, int]:
    return dict.fromkeys(_IMPORT_STAT_KEYS, 0)


def _record_imported_value(stats: Dict[str, int], key: str, value: Any, amount: int = 1) -> Any:
    if value:
        stats[key] += amount
    return value


def _record_imported_items(stats: Dict[str, int], key: str, items: Any) -> Any:
    if items:
        stats[key] += len(items)
    return items


def _row_to_file_ai_analysis(row: Any) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return dict(zip(_FILE_AI_ANALYSIS_FIELDS, row))


def _group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def _nullable_group_id_param(group_id: Optional[str]) -> Any:
    value = str(group_id or "").strip()
    if not value:
        return None
    return int(value) if value.isdigit() else value


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


class DownloadFileSelection(NamedTuple):
    records: list[DownloadFileRecord]
    missing: list[int]
    requested_count: int


class FileStatusRecord(NamedTuple):
    name: str
    size: Any
    download_status: Optional[str]

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "FileStatusRecord":
        return cls(row[0], row[1], row[2])


class FileAnalysisSourceRecord(NamedTuple):
    file_id: int
    name: str
    size: Any
    download_status: Optional[str]
    local_path: Optional[str]

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "FileAnalysisSourceRecord":
        file_id = int(row[0])
        return cls(file_id, str(row[1] or f"file_{file_id}"), row[2], row[3], row[4])


class FileDownloadStats(NamedTuple):
    total_files: int
    downloaded: int
    pending: int
    failed: int

    @classmethod
    def from_row(cls, row: Optional[Sequence[Any]]) -> "FileDownloadStats":
        if not row:
            return cls(0, 0, 0, 0)
        return cls(
            int(row[0] or 0),
            int(row[1] or 0),
            int(row[2] or 0),
            int(row[3] or 0),
        )


class FileListRecord(NamedTuple):
    file_id: Any
    name: Any
    size: Any
    download_count: Any
    create_time: Any
    download_status: Optional[str]
    local_path: Optional[str]
    download_error_code: Optional[str]
    download_error_message: Optional[str]
    last_download_attempt_at: Optional[str]
    analysis_updated_at: Optional[str]

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "FileListRecord":
        return cls(
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            row[8],
            row[9],
            row[10],
        )


class FileListPage(NamedTuple):
    records: list[FileListRecord]
    total: int


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


_FILE_LIST_FROM_CLAUSE = """
            FROM files f
            LEFT JOIN file_ai_analyses faa ON faa.file_id = f.file_id
        """


def _build_file_list_filters(
    group_id: Optional[Any],
    status: Optional[str],
    search: Optional[str],
    analysis_status: Optional[str],
) -> tuple[str, list[Any]]:
    conditions = []
    params_prefix = [_query_group_id(group_id)]
    conditions.append("f.group_id = ?")

    _add_file_download_status_condition(conditions, params_prefix, status)

    if analysis_status == "analyzed":
        conditions.append("faa.updated_at IS NOT NULL")
    elif analysis_status == "pending":
        conditions.append("faa.updated_at IS NULL")

    _add_file_search_condition(conditions, params_prefix, search)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, params_prefix


def _build_file_list_query(where_clause: str) -> str:
    return f"""
            SELECT
                f.file_id,
                f.name,
                f.size,
                f.download_count,
                f.create_time,
                f.download_status,
                f.local_path,
                f.download_error_code,
                f.download_error_message,
                f.last_download_attempt_at,
                faa.updated_at
            {_FILE_LIST_FROM_CLAUSE}
            {where_clause}
            ORDER BY f.create_time DESC
            LIMIT ? OFFSET ?
        """


def _build_file_count_query(where_clause: str) -> str:
    return f"SELECT COUNT(*) {_FILE_LIST_FROM_CLAUSE} {where_clause}"


def _normalize_file_list_record(row: Sequence[Any]) -> FileListRecord:
    return FileListRecord.from_row(row)


def _user_record_params(user_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        user_data.get('user_id'),
        user_data.get('name', ''),
        user_data.get('alias'),
        user_data.get('avatar_url'),
        user_data.get('description'),
        user_data.get('location'),
        user_data.get('ai_comment_url'),
    )


def _group_record_params(group_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        group_data.get('group_id'),
        group_data.get('name', ''),
        group_data.get('type'),
        group_data.get('background_url'),
    )


def _topic_record_params(topic_data: Dict[str, Any]) -> tuple[Any, ...]:
    user_specific = topic_data.get('user_specific', {})
    return (
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
        topic_data.get('modify_time'),
        user_specific.get('liked', False),
        user_specific.get('subscribed', False),
    )


def _talk_record_params(topic_id: int, owner_id: Optional[Any], talk_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        topic_id,
        owner_id,
        talk_data.get('text', ''),
    )


def _image_record_params(topic_id: int, image_data: Dict[str, Any]) -> tuple[Any, ...]:
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
        original.get('size'),
    )


def _comment_record_params(
    group_id: Any,
    topic_id: int,
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
        comment_data.get('sticky', False),
    )


def _latest_like_record_params(topic_id: int, owner_id: Optional[Any], like_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        topic_id,
        owner_id,
        like_data.get('create_time'),
    )


def _like_emoji_record_params(topic_id: int, emoji_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        topic_id,
        emoji_data.get('emoji_key'),
        emoji_data.get('likes_count', 0),
    )


def _user_liked_emoji_record_params(topic_id: int, emoji_key: str) -> tuple[Any, ...]:
    return (
        topic_id,
        emoji_key,
    )


def _column_record_params(column_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        column_data.get('column_id'),
        column_data.get('name', ''),
    )


def _topic_column_record_params(topic_id: int, column_id: Any) -> tuple[Any, ...]:
    return (
        topic_id,
        column_id,
    )


def _solution_record_params(topic_id: int, owner_id: Optional[Any], solution_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        topic_id,
        solution_data.get('task_id'),
        owner_id,
        solution_data.get('text', ''),
    )


def _api_response_record_params(response_data: Dict[str, Any], files_count: int) -> tuple[Any, ...]:
    return (
        response_data.get('succeeded', False),
        response_data.get('resp_data', {}).get('index'),
        files_count,
    )


def _file_topic_relation_params(file_id: Any, topic_id: Any) -> tuple[Any, ...]:
    return (
        file_id,
        topic_id,
    )


def _file_attachment_params(parent_id: Any, file_data: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        parent_id,
        file_data.get('file_id'),
        file_data.get('name', ''),
        file_data.get('hash'),
        file_data.get('size'),
        file_data.get('duration'),
        file_data.get('download_count'),
        file_data.get('create_time'),
    )


def _file_record_params(
    file_data: Dict[str, Any],
    group_id: Optional[Any] = None,
    topic_id: Optional[Any] = None,
) -> tuple[Any, ...]:
    return (
        file_data.get('file_id'),
        _nullable_group_id_param(str(group_id)) if group_id is not None else None,
        topic_id,
        file_data.get('name', ''),
        file_data.get('hash'),
        file_data.get('size'),
        file_data.get('duration'),
        file_data.get('download_count'),
        file_data.get('create_time'),
    )


def _file_download_status_params(
    group_id: Optional[str],
    file_id: int,
    status: str,
    local_path: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> tuple[Any, ...]:
    group_param = _group_id_param(group_id)
    return (
        status,
        local_path,
        status,
        status,
        error_code,
        status,
        error_message,
        file_id,
        group_param,
        group_param,
    )


def _file_ai_analysis_params(
    group_id: Optional[str],
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
) -> tuple[Any, ...]:
    return (
        file_id,
        _group_id_param(group_id),
        status,
        summary,
        extracted_text,
        extracted_text_preview,
        content_type,
        source_path,
        source_size,
        model,
        api_base,
        wire_api,
        reasoning_effort,
        error_message,
    )


def _count_tables(cursor: Any, tables: Any = _STATS_TABLES, group_id: Optional[str] = None) -> Dict[str, Any]:
    stats = {}
    scoped_topic_ids_sql = "SELECT topic_id FROM topics WHERE group_id = ?"
    group_param = _group_id_param(group_id)
    for table in tables:
        if group_id is None:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
        elif table in {"groups", "topics", "files", "columns", "column_topics", "topic_details", "comments", "file_ai_analyses"}:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE group_id = ?", (group_param,))
        elif table in {
            "talks",
            "articles",
            "images",
            "topic_files",
            "latest_likes",
            "likes",
            "like_emojis",
            "user_liked_emojis",
            "questions",
            "answers",
            "topic_tags",
            "topic_columns",
            "solutions",
        }:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE topic_id IN ({scoped_topic_ids_sql})", (group_param,))
        elif table == "file_topic_relations":
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE topic_id IN ({scoped_topic_ids_sql})", (group_param,))
        elif table == "solution_files":
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM solution_files sf
                JOIN solutions s ON s.id = sf.solution_id
                WHERE s.topic_id IN ({scoped_topic_ids_sql})
                """,
                (group_param,),
            )
        elif table == "users":
            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT user_id)
                FROM (
                    SELECT owner_user_id AS user_id FROM talks WHERE topic_id IN ({scoped_topic_ids_sql})
                    UNION
                    SELECT owner_user_id AS user_id FROM comments WHERE topic_id IN ({scoped_topic_ids_sql})
                    UNION
                    SELECT owner_user_id AS user_id FROM questions WHERE topic_id IN ({scoped_topic_ids_sql})
                    UNION
                    SELECT questionee_user_id AS user_id FROM questions WHERE topic_id IN ({scoped_topic_ids_sql})
                    UNION
                    SELECT owner_user_id AS user_id FROM answers WHERE topic_id IN ({scoped_topic_ids_sql})
                ) scoped_users
                WHERE user_id IS NOT NULL
                """,
                (group_param, group_param, group_param, group_param, group_param),
            )
        elif table == "api_responses":
            cursor.execute("SELECT COUNT(*) FROM api_responses")
        elif table == "collection_log":
            cursor.execute("SELECT COUNT(*) FROM collection_log")
        else:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
        stats[table] = cursor.fetchone()[0]
    return stats


def _close_connection(conn: Any) -> None:
    if conn:
        conn.close()
