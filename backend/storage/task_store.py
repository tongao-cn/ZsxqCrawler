from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.storage.db_compat import connect


TERMINAL_TASK_STATUSES = ("completed", "failed", "cancelled", "stopped")
TASK_LOCK_LEASE_MINUTES = 30


def _chunk_values(values: List[Any], chunk_size: int) -> List[List[Any]]:
    return [values[start : start + chunk_size] for start in range(0, len(values), chunk_size)]


def _cleanup_result(tasks_deleted: int, logs_deleted: int, kept_latest: int) -> Dict[str, int]:
    return {
        "tasks_deleted": tasks_deleted,
        "logs_deleted": logs_deleted,
        "kept_latest": kept_latest,
    }


def _task_lock_key(category: str, group_id: str) -> str:
    return f"{category}:{group_id}"


class TaskStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._init_db()

    def create_task(
        self,
        task_id: str,
        task_type: str,
        status: str,
        message: str,
        result: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Any = None,
        updated_at: Any = None,
    ) -> Dict[str, Any]:
        created = self._iso(created_at)
        updated = self._iso(updated_at) if updated_at is not None else created
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO task_runs (
                        task_id, type, status, message, result_json,
                        metadata_json, created_at, updated_at, stopped
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                        (SELECT stopped FROM task_runs WHERE task_id = ?), 0
                    ))
                    ON CONFLICT(task_id) DO UPDATE SET
                        type = excluded.type,
                        status = excluded.status,
                        message = excluded.message,
                        result_json = excluded.result_json,
                        metadata_json = excluded.metadata_json,
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at,
                        stopped = excluded.stopped
                    """,
                    (
                        task_id,
                        task_type,
                        status,
                        message,
                        self._dump(result),
                        self._dump(metadata or {}),
                        created,
                        updated,
                        task_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        task = self.get_task(task_id)
        return task or {}

    def create_task_with_lock(
        self,
        task_id: str,
        task_type: str,
        message: str,
        group_id: str,
        category: str,
        metadata: Optional[Dict[str, Any]] = None,
        lease_minutes: int = TASK_LOCK_LEASE_MINUTES,
        created_at: Any = None,
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        created = self._iso(created_at)
        expires = self._iso(datetime.fromisoformat(created) + timedelta(minutes=lease_minutes))
        lock_key = _task_lock_key(category, str(group_id))
        lock_metadata = dict(metadata or {})
        lock_metadata.update({"group_id": str(group_id), "ingestion_lock_key": category})

        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO task_locks (
                        lock_key, group_id, category, owner_task_id, owner_task_type,
                        acquired_at, expires_at, heartbeat_at, released_at, release_reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                    ON CONFLICT(lock_key) DO UPDATE SET
                        group_id = excluded.group_id,
                        category = excluded.category,
                        owner_task_id = excluded.owner_task_id,
                        owner_task_type = excluded.owner_task_type,
                        acquired_at = excluded.acquired_at,
                        expires_at = excluded.expires_at,
                        heartbeat_at = excluded.heartbeat_at,
                        released_at = NULL,
                        release_reason = NULL
                    WHERE task_locks.released_at IS NOT NULL OR task_locks.expires_at < ?
                    """,
                    (
                        lock_key,
                        str(group_id),
                        category,
                        task_id,
                        task_type,
                        created,
                        expires,
                        created,
                        created,
                    ),
                )
                acquired = cursor.rowcount == 1
                if not acquired:
                    existing_task_row = cursor.execute(
                        """
                        SELECT tr.*
                        FROM task_locks tl
                        LEFT JOIN task_runs tr ON tr.task_id = tl.owner_task_id
                        WHERE tl.lock_key = ?
                        """,
                        (lock_key,),
                    ).fetchone()
                    existing_lock_row = cursor.execute(
                        """
                        SELECT owner_task_id, owner_task_type, group_id
                        FROM task_locks
                        WHERE lock_key = ?
                        """,
                        (lock_key,),
                    ).fetchone()
                    conn.rollback()
                    if existing_task_row and existing_task_row["task_id"]:
                        existing_task = self._task_from_row(existing_task_row)
                    elif existing_lock_row:
                        existing_task = {
                            "task_id": existing_lock_row["owner_task_id"],
                            "type": existing_lock_row["owner_task_type"],
                            "status": "running",
                            "group_id": existing_lock_row["group_id"],
                        }
                    else:
                        existing_task = None
                    return None, existing_task

                cursor.execute(
                    """
                    INSERT INTO task_runs (
                        task_id, type, status, message, result_json,
                        metadata_json, created_at, updated_at, stopped
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(task_id) DO UPDATE SET
                        type = excluded.type,
                        status = excluded.status,
                        message = excluded.message,
                        result_json = excluded.result_json,
                        metadata_json = excluded.metadata_json,
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at,
                        stopped = excluded.stopped
                    """,
                    (
                        task_id,
                        task_type,
                        "pending",
                        message,
                        self._dump(None),
                        self._dump(lock_metadata),
                        created,
                        created,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        task = self.get_task(task_id)
        return task, None

    def update_task(
        self,
        task_id: str,
        status: str,
        message: str,
        result: Optional[Dict[str, Any]] = None,
        updated_at: Any = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE task_runs
                    SET status = ?, message = ?, result_json = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (status, message, self._dump(result), self._iso(updated_at), task_id),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_task(task_id)

    def release_task_lock(self, task_id: str, reason: str, released_at: Any = None) -> None:
        released = self._iso(released_at)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE task_locks
                    SET released_at = ?, release_reason = ?
                    WHERE owner_task_id = ? AND released_at IS NULL
                    """,
                    (released, reason, task_id),
                )
                conn.commit()
            finally:
                conn.close()

    def heartbeat_task_lock(self, task_id: str, lease_minutes: int = TASK_LOCK_LEASE_MINUTES, heartbeat_at: Any = None) -> None:
        heartbeat = self._iso(heartbeat_at)
        expires = self._iso(datetime.fromisoformat(heartbeat) + timedelta(minutes=lease_minutes))
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE task_locks
                    SET heartbeat_at = ?, expires_at = ?
                    WHERE owner_task_id = ? AND released_at IS NULL
                    """,
                    (heartbeat, expires, task_id),
                )
                conn.commit()
            finally:
                conn.close()

    def get_task_lock(self, category: str, group_id: str) -> Optional[Dict[str, Any]]:
        lock_key = _task_lock_key(category, str(group_id))
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM task_locks WHERE lock_key = ?",
                    (lock_key,),
                ).fetchone()
            finally:
                conn.close()
        return {key: row[key] for key in row.keys()} if row else None

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM task_runs WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
            finally:
                conn.close()
        return self._task_from_row(row) if row else None

    def list_tasks(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM task_runs ORDER BY created_at DESC, task_id DESC"
        params: tuple[Any, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)

        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()
        return [self._task_from_row(row) for row in rows]

    def max_task_sequence(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT task_id FROM task_runs").fetchall()
            finally:
                conn.close()

        max_sequence = 0
        for row in rows:
            sequence = self._parse_task_sequence(row["task_id"])
            if sequence is not None and sequence > max_sequence:
                max_sequence = sequence
        return max_sequence

    def add_log(self, task_id: str, message: str, created_at: Any = None) -> str:
        created = self._iso(created_at)
        log_message = f"[{self._log_time(created)}] {message}"
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO task_logs (task_id, message, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (task_id, log_message, created),
                )
                conn.commit()
            finally:
                conn.close()
        return log_message

    def get_logs(self, task_id: str) -> List[str]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT message
                    FROM task_logs
                    WHERE task_id = ?
                    ORDER BY id
                    """,
                    (task_id,),
                ).fetchall()
            finally:
                conn.close()
        return [row["message"] for row in rows]

    def cleanup_completed(self, keep_latest: int = 500) -> Dict[str, int]:
        kept_latest = max(0, keep_latest)

        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT task_id
                    FROM task_runs
                    WHERE status IN (?, ?, ?, ?)
                    ORDER BY created_at DESC, task_id DESC
                    LIMIT -1 OFFSET ?
                    """,
                    TERMINAL_TASK_STATUSES + (kept_latest,),
                ).fetchall()
                task_ids = [row["task_id"] for row in rows]

                logs_deleted = 0
                tasks_deleted = 0
                chunk_size = 900
                for chunk in _chunk_values(task_ids, chunk_size):
                    placeholders = ",".join("?" for _ in chunk)
                    logs_deleted += conn.execute(
                        f"SELECT COUNT(*) FROM task_logs WHERE task_id IN ({placeholders})",
                        chunk,
                    ).fetchone()[0]
                    conn.execute(
                        f"DELETE FROM task_logs WHERE task_id IN ({placeholders})",
                        chunk,
                    )
                    cursor = conn.execute(
                        f"DELETE FROM task_runs WHERE task_id IN ({placeholders})",
                        chunk,
                    )
                    tasks_deleted += cursor.rowcount

                conn.commit()
            finally:
                conn.close()

        return _cleanup_result(tasks_deleted, logs_deleted, kept_latest)

    def set_stop_flag(self, task_id: str, stopped: bool = True) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE task_runs SET stopped = ? WHERE task_id = ?",
                    (1 if stopped else 0, task_id),
                )
                conn.commit()
            finally:
                conn.close()

    def is_stopped(self, task_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT stopped FROM task_runs WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
            finally:
                conn.close()
        return bool(row["stopped"]) if row else False

    def _init_db(self) -> None:
        """Schema is managed by manage-postgres-core-schema; runtime DDL is disabled."""
        return None

    def _connect(self):
        return connect(row_factory=True)

    def _task_from_row(self, row: Any) -> Dict[str, Any]:
        task = {
            "task_id": row["task_id"],
            "type": row["type"],
            "status": row["status"],
            "message": row["message"],
            "result": self._load(row["result_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        metadata = self._load(row["metadata_json"]) or {}
        if isinstance(metadata, dict):
            task.update(metadata)
        return task

    def _iso(self, value: Any = None) -> str:
        if value is None:
            return datetime.now().isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _log_time(self, value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%H:%M:%S")
        except ValueError:
            return datetime.now().strftime("%H:%M:%S")

    def _parse_task_sequence(self, task_id: str) -> Optional[int]:
        parts = task_id.split("_", 2)
        if len(parts) != 3 or parts[0] != "task" or not parts[1].isdigit() or not parts[2]:
            return None
        return int(parts[1])

    def _dump(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def _load(self, value: Optional[str]) -> Any:
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
