from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from backend.storage.db_compat import connect


TERMINAL_TASK_STATUSES = ("completed", "failed", "cancelled", "stopped")


def _chunk_values(values: List[Any], chunk_size: int) -> List[List[Any]]:
    return [values[start : start + chunk_size] for start in range(0, len(values), chunk_size)]


def _cleanup_result(tasks_deleted: int, logs_deleted: int, kept_latest: int) -> Dict[str, int]:
    return {
        "tasks_deleted": tasks_deleted,
        "logs_deleted": logs_deleted,
        "kept_latest": kept_latest,
    }


class TaskStore:
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
                    INSERT OR REPLACE INTO task_runs (
                        task_id, type, status, message, result_json,
                        metadata_json, created_at, updated_at, stopped
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                        (SELECT stopped FROM task_runs WHERE task_id = ?), 0
                    ))
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
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_runs (
                        task_id TEXT PRIMARY KEY,
                        type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        message TEXT NOT NULL,
                        result_json TEXT,
                        metadata_json TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        stopped INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        message TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_task_logs_task_id ON task_logs (task_id, id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_task_runs_created_at ON task_runs (created_at)"
                )
                conn.commit()
            finally:
                conn.close()

    def _connect(self):
        return connect(self.db_path, row_factory=True)

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
