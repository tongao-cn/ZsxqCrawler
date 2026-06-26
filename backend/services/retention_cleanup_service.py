from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from backend.services.task_launch import TaskLaunchRecipe, launch_task_recipe
from backend.services.task_runtime import add_task_log, run_workflow
from backend.storage.db_compat import connect


DEFAULT_RETENTION_DAYS = 365
BJ_TZ = timezone(timedelta(hours=8))


LogCallback = Callable[[str], None]
ConnectFunc = Callable[[], Any]


@dataclass(frozen=True)
class RetentionCleanupTaskRequest:
    retention_days: int = DEFAULT_RETENTION_DAYS

    def __post_init__(self) -> None:
        object.__setattr__(self, "retention_days", _normalize_retention_days(self.retention_days))


@dataclass(frozen=True)
class DeleteSpec:
    name: str
    sql: str
    params: tuple[Any, ...]


def _normalize_retention_days(value: int) -> int:
    days = int(value)
    if days < 1:
        raise ValueError("retention_days must be at least 1")
    return days


def _retention_today(today: Optional[date] = None) -> date:
    return today or datetime.now(BJ_TZ).date()


def _cutoff_date(retention_days: int, today: Optional[date] = None) -> date:
    return _retention_today(today) - timedelta(days=_normalize_retention_days(retention_days))


def _old_topic_filter() -> str:
    return """
        group_id = ?
        AND create_time IS NOT NULL
        AND create_time <> ''
        AND SUBSTRING(create_time FROM 1 FOR 10) < ?
    """


def _old_topic_ids_sql(*, cast_to_text: bool = False) -> str:
    topic_id_expr = "topic_id::text" if cast_to_text else "topic_id"
    return f"SELECT {topic_id_expr} FROM topics WHERE {_old_topic_filter()}"


def _old_topic_params(group_id: str, cutoff: date) -> tuple[Any, ...]:
    return (str(group_id), cutoff.isoformat())


def _row_value(row: Any, key: str, index: int, default: Any = None) -> Any:
    if not row:
        return default
    try:
        return row[key]
    except Exception:
        try:
            return row[index]
        except Exception:
            return default


def _row_count(result: Any) -> int:
    return max(int(getattr(result, "rowcount", 0) or 0), 0)


def _fetch_row_count(conn: Any, sql: str, params: Iterable[Any]) -> int:
    row = conn.execute(sql, tuple(params)).fetchone()
    return int(_row_value(row, "row_count", 0, 0) or 0)


def _preview_with_conn(conn: Any, group_id: str, retention_days: int, today: Optional[date]) -> Dict[str, Any]:
    cutoff = _cutoff_date(retention_days, today)
    params = _old_topic_params(group_id, cutoff)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS topic_count,
               MIN(create_time) AS oldest_create_time,
               MAX(create_time) AS newest_create_time
        FROM topics
        WHERE {_old_topic_filter()}
        """,
        params,
    ).fetchone()
    matched_topics = int(_row_value(row, "topic_count", 0, 0) or 0)
    estimates = {
        name: _fetch_row_count(conn, sql, params)
        for name, sql, params in _count_specs(str(group_id), cutoff)
    }
    return {
        "group_id": str(group_id),
        "retention_days": _normalize_retention_days(retention_days),
        "cutoff_date": cutoff.isoformat(),
        "matched_topics": matched_topics,
        "oldest_topic_create_time": _row_value(row, "oldest_create_time", 1),
        "newest_topic_create_time": _row_value(row, "newest_create_time", 2),
        "estimated": estimates,
    }


def _count_specs(group_id: str, cutoff: date) -> tuple[tuple[str, str, tuple[Any, ...]], ...]:
    old_topic_ids = _old_topic_ids_sql()
    old_topic_text_ids = _old_topic_ids_sql(cast_to_text=True)
    old_topic_params = _old_topic_params(group_id, cutoff)
    dated_params = (group_id, cutoff.isoformat())
    return (
        ("topics", f"SELECT COUNT(*) AS row_count FROM topics WHERE {_old_topic_filter()}", old_topic_params),
        (
            "solution_files",
            f"SELECT COUNT(*) AS row_count FROM solution_files WHERE solution_id IN (SELECT id FROM solutions WHERE topic_id IN ({old_topic_ids}))",
            old_topic_params,
        ),
        (
            "file_ai_analyses",
            f"SELECT COUNT(*) AS row_count FROM file_ai_analyses WHERE group_id = ? AND file_id IN (SELECT file_id FROM files WHERE group_id = ? AND topic_id IN ({old_topic_ids}))",
            (group_id, group_id, *old_topic_params),
        ),
        ("files", f"SELECT COUNT(*) AS row_count FROM files WHERE group_id = ? AND topic_id IN ({old_topic_ids})", (group_id, *old_topic_params)),
        ("file_topic_relations", f"SELECT COUNT(*) AS row_count FROM file_topic_relations WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("topic_files", f"SELECT COUNT(*) AS row_count FROM topic_files WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("videos", f"SELECT COUNT(*) AS row_count FROM videos WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        (
            "images",
            f"""
            SELECT COUNT(*) AS row_count FROM images
            WHERE topic_id IN ({old_topic_ids})
               OR comment_id IN (SELECT comment_id FROM comments WHERE topic_id IN ({old_topic_ids}))
            """,
            (*old_topic_params, *old_topic_params),
        ),
        ("comments", f"SELECT COUNT(*) AS row_count FROM comments WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("user_liked_emojis", f"SELECT COUNT(*) AS row_count FROM user_liked_emojis WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("like_emojis", f"SELECT COUNT(*) AS row_count FROM like_emojis WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("latest_likes", f"SELECT COUNT(*) AS row_count FROM latest_likes WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("likes", f"SELECT COUNT(*) AS row_count FROM likes WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("answers", f"SELECT COUNT(*) AS row_count FROM answers WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("questions", f"SELECT COUNT(*) AS row_count FROM questions WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("articles", f"SELECT COUNT(*) AS row_count FROM articles WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("talks", f"SELECT COUNT(*) AS row_count FROM talks WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("topic_owners", f"SELECT COUNT(*) AS row_count FROM topic_owners WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("topic_columns", f"SELECT COUNT(*) AS row_count FROM topic_columns WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("topic_tags", f"SELECT COUNT(*) AS row_count FROM topic_tags WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("solutions", f"SELECT COUNT(*) AS row_count FROM solutions WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        ("daily_ai_reports", "SELECT COUNT(*) AS row_count FROM daily_ai_reports WHERE group_id = ? AND report_date < ?", dated_params),
        ("daily_stock_concepts", "SELECT COUNT(*) AS row_count FROM daily_stock_concepts WHERE group_id = ? AND report_date < ?", dated_params),
        (
            "zsxq_a_share_daily_mentions",
            "SELECT COUNT(*) AS row_count FROM zsxq_a_share_daily_mentions WHERE group_id = ? AND mention_date < ?::date",
            dated_params,
        ),
        (
            "zsxq_a_share_processed_state",
            "SELECT COUNT(*) AS row_count FROM zsxq_a_share_processed_state WHERE group_id = ? AND day < ?::date",
            dated_params,
        ),
        (
            "zsxq_a_share_topic_stock_extractions",
            "SELECT COUNT(*) AS row_count FROM zsxq_a_share_topic_stock_extractions WHERE group_id = ? AND topic_date < ?::date",
            dated_params,
        ),
        (
            "stock_topic_processed_states",
            f"SELECT COUNT(*) AS row_count FROM stock_topic_processed_states WHERE group_id = ? AND topic_id IN ({old_topic_text_ids})",
            (group_id, *old_topic_params),
        ),
        (
            "stock_topic_analysis_versions",
            "SELECT COUNT(*) AS row_count FROM stock_topic_analysis_versions WHERE group_id = ? AND analysis_date < ?",
            dated_params,
        ),
        (
            "stock_topic_analyses",
            "SELECT COUNT(*) AS row_count FROM stock_topic_analyses WHERE group_id = ? AND SUBSTRING(COALESCE(updated_at, created_at, '') FROM 1 FOR 10) < ?",
            dated_params,
        ),
    )


def preview_group_retention_cleanup(
    group_id: str,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    today: Optional[date] = None,
    connect_func: ConnectFunc = connect,
) -> Dict[str, Any]:
    conn = connect_func()
    try:
        return _preview_with_conn(conn, str(group_id), retention_days, today)
    finally:
        conn.close()


def _delete_specs(group_id: str, cutoff: date) -> tuple[DeleteSpec, ...]:
    old_topic_ids = _old_topic_ids_sql()
    old_topic_text_ids = _old_topic_ids_sql(cast_to_text=True)
    old_topic_params = _old_topic_params(group_id, cutoff)
    dated_params = (group_id, cutoff.isoformat())
    return (
        DeleteSpec(
            "solution_files",
            f"DELETE FROM solution_files WHERE solution_id IN (SELECT id FROM solutions WHERE topic_id IN ({old_topic_ids}))",
            old_topic_params,
        ),
        DeleteSpec(
            "file_ai_analyses",
            f"DELETE FROM file_ai_analyses WHERE group_id = ? AND file_id IN (SELECT file_id FROM files WHERE group_id = ? AND topic_id IN ({old_topic_ids}))",
            (group_id, group_id, *old_topic_params),
        ),
        DeleteSpec(
            "files",
            f"DELETE FROM files WHERE group_id = ? AND topic_id IN ({old_topic_ids})",
            (group_id, *old_topic_params),
        ),
        DeleteSpec("file_topic_relations", f"DELETE FROM file_topic_relations WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("topic_files", f"DELETE FROM topic_files WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("videos", f"DELETE FROM videos WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec(
            "images",
            f"""
            DELETE FROM images
            WHERE topic_id IN ({old_topic_ids})
               OR comment_id IN (SELECT comment_id FROM comments WHERE topic_id IN ({old_topic_ids}))
            """,
            (*old_topic_params, *old_topic_params),
        ),
        DeleteSpec("comments", f"DELETE FROM comments WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("user_liked_emojis", f"DELETE FROM user_liked_emojis WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("like_emojis", f"DELETE FROM like_emojis WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("latest_likes", f"DELETE FROM latest_likes WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("likes", f"DELETE FROM likes WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("answers", f"DELETE FROM answers WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("questions", f"DELETE FROM questions WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("articles", f"DELETE FROM articles WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("talks", f"DELETE FROM talks WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("topic_owners", f"DELETE FROM topic_owners WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("topic_columns", f"DELETE FROM topic_columns WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("topic_tags", f"DELETE FROM topic_tags WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("solutions", f"DELETE FROM solutions WHERE topic_id IN ({old_topic_ids})", old_topic_params),
        DeleteSpec("daily_ai_reports", "DELETE FROM daily_ai_reports WHERE group_id = ? AND report_date < ?", dated_params),
        DeleteSpec("daily_stock_concepts", "DELETE FROM daily_stock_concepts WHERE group_id = ? AND report_date < ?", dated_params),
        DeleteSpec("zsxq_a_share_daily_mentions", "DELETE FROM zsxq_a_share_daily_mentions WHERE group_id = ? AND mention_date < ?::date", dated_params),
        DeleteSpec("zsxq_a_share_processed_state", "DELETE FROM zsxq_a_share_processed_state WHERE group_id = ? AND day < ?::date", dated_params),
        DeleteSpec(
            "zsxq_a_share_topic_stock_extractions",
            "DELETE FROM zsxq_a_share_topic_stock_extractions WHERE group_id = ? AND topic_date < ?::date",
            dated_params,
        ),
        DeleteSpec(
            "stock_topic_processed_states",
            f"DELETE FROM stock_topic_processed_states WHERE group_id = ? AND topic_id IN ({old_topic_text_ids})",
            (group_id, *old_topic_params),
        ),
        DeleteSpec("stock_topic_analysis_versions", "DELETE FROM stock_topic_analysis_versions WHERE group_id = ? AND analysis_date < ?", dated_params),
        DeleteSpec(
            "stock_topic_analyses",
            "DELETE FROM stock_topic_analyses WHERE group_id = ? AND SUBSTRING(COALESCE(updated_at, created_at, '') FROM 1 FOR 10) < ?",
            dated_params,
        ),
        DeleteSpec("topics", f"DELETE FROM topics WHERE {_old_topic_filter()}", old_topic_params),
    )


def run_group_retention_cleanup(
    group_id: str,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    today: Optional[date] = None,
    connect_func: ConnectFunc = connect,
    log_callback: Optional[LogCallback] = None,
) -> Dict[str, Any]:
    conn = connect_func()
    try:
        preview = _preview_with_conn(conn, str(group_id), retention_days, today)
        cutoff = date.fromisoformat(preview["cutoff_date"])
        if log_callback:
            log_callback(f"保留窗口: {retention_days} 天，清理 {preview['cutoff_date']} 之前的话题")
            log_callback(f"匹配话题: {preview['matched_topics']} 条")
        deleted: Dict[str, int] = {}
        for spec in _delete_specs(str(group_id), cutoff):
            deleted[spec.name] = _row_count(conn.execute(spec.sql, spec.params))
        conn.commit()
        result = {**preview, "deleted": deleted}
        if log_callback:
            log_callback(f"删除完成: topics={deleted.get('topics', 0)}")
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_retention_cleanup_task(task_id: str, group_id: str, request: RetentionCleanupTaskRequest) -> None:
    def work() -> Dict[str, Any]:
        return run_group_retention_cleanup(
            group_id,
            retention_days=request.retention_days,
            log_callback=lambda message: add_task_log(task_id, message),
        )

    run_workflow(
        task_id,
        running_message="开始清理超期内容...",
        completed_message="超期内容清理完成",
        failure_label="超期内容清理",
        work=work,
    )


def create_retention_cleanup_task(
    group_id: str,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> Dict[str, str]:
    request = RetentionCleanupTaskRequest(retention_days=retention_days)
    return launch_task_recipe(
        TaskLaunchRecipe.ingestion(
            "retention_cleanup",
            f"清理超过 {request.retention_days} 天的内容 (群组: {group_id})",
            run_retention_cleanup_task,
            str(group_id),
            request,
        )
    )
