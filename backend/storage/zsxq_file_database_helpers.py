from typing import Any, Dict, Optional


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


def _new_import_stats() -> Dict[str, int]:
    return dict.fromkeys(_IMPORT_STAT_KEYS, 0)


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
