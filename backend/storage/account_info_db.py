#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import threading
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from backend.storage.db_compat import connect

_lock = threading.Lock()


def _safe_load_json(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _build_self_info_upsert_params(
    account_id: str,
    self_info: Dict[str, Any],
    raw_json: Optional[Dict[str, Any]],
    fetched_at: str,
) -> Tuple[Any, ...]:
    raw_json_str = json.dumps(raw_json or {}, ensure_ascii=False)
    return (
        account_id,
        self_info.get("uid"),
        self_info.get("name"),
        self_info.get("avatar_url"),
        self_info.get("location"),
        self_info.get("user_sid"),
        self_info.get("grade"),
        raw_json_str,
        fetched_at,
    )


def _self_info_row_to_dict(row) -> Dict[str, Any]:
    return {
        "account_id": row[0],
        "uid": row[1],
        "name": row[2],
        "avatar_url": row[3],
        "location": row[4],
        "user_sid": row[5],
        "grade": row[6],
        "raw_json": _safe_load_json(row[7]),
        "fetched_at": row[8],
    }


def _close_quietly(obj) -> None:
    try:
        obj.close()
    except Exception:
        pass


class AccountInfoDB:
    """
    账号信息数据库：持久化 /v3/users/self 的用户信息
    表：accounts_self
    """
    def __init__(self):
        self.conn = connect()
        self.cursor = self.conn.cursor()
        self._ensure_schema()

    def _ensure_schema(self):
        """Schema is managed by manage-postgres-core-schema; runtime DDL is disabled."""
        return None

    def upsert_self_info(
        self,
        account_id: str,
        self_info: Dict[str, Any],
        raw_json: Optional[Dict[str, Any]] = None,
    ):
        """
        保存/更新用户信息
        self_info 期望字段：uid, name, avatar_url, location, user_sid, grade
        """
        if not account_id:
            raise ValueError("account_id 不能为空")

        now = datetime.now().isoformat(timespec="seconds")
        params = _build_self_info_upsert_params(account_id, self_info, raw_json, now)

        with _lock:
            self.cursor.execute(
                """
                INSERT INTO accounts_self (account_id, uid, name, avatar_url, location, user_sid, grade, raw_json, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    uid=excluded.uid,
                    name=excluded.name,
                    avatar_url=excluded.avatar_url,
                    location=excluded.location,
                    user_sid=excluded.user_sid,
                    grade=excluded.grade,
                    raw_json=excluded.raw_json,
                    fetched_at=excluded.fetched_at
                """,
                params,
            )
            self.conn.commit()

    def get_self_info(self, account_id: str) -> Optional[Dict[str, Any]]:
        if not account_id:
            return None
        with _lock:
            self.cursor.execute(
                """
                SELECT account_id, uid, name, avatar_url, location, user_sid, grade, raw_json, fetched_at
                FROM accounts_self
                WHERE account_id = ?
                """,
                (account_id,),
            )
            row = self.cursor.fetchone()
            if not row:
                return None
            return _self_info_row_to_dict(row)

    def close(self):
        with _lock:
            _close_quietly(self.cursor)
            _close_quietly(self.conn)


_db_singleton: Optional[AccountInfoDB] = None
_db_lock = threading.Lock()


def get_account_info_db() -> AccountInfoDB:
    global _db_singleton
    if _db_singleton is None:
        with _db_lock:
            if _db_singleton is None:
                _db_singleton = AccountInfoDB()
    return _db_singleton
