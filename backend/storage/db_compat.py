from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from backend.storage.postgres_core_schema import (
    CORE_SCHEMA,
    ensure_core_schema,
    is_schema_missing_error,
    quote_identifier,
    schema_not_ready_message,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


_CORE_SCHEMA_BOOTSTRAPPED_DSNS: set[str] = set()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_database_config() -> dict[str, Any]:
    if tomllib is None:
        return {}
    config_path = _project_root() / "config.toml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("rb") as f:
            config = tomllib.load(f)
    except Exception:
        return {}
    database = config.get("database", {})
    return database if isinstance(database, dict) else {}


def _strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_project_env_file() -> None:
    env_path = _project_root() / ".env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = _strip_env_value(value)


def get_database_backend() -> str:
    _load_project_env_file()
    backend = os.getenv("ZSXQ_DATABASE_BACKEND") or _load_database_config().get("backend")
    return str(backend or "postgres").strip().lower()


def get_postgres_dsn() -> Optional[str]:
    _load_project_env_file()
    env_dsn = os.getenv("ZSXQ_POSTGRES_DSN") or os.getenv("DATABASE_URL")
    if env_dsn:
        return env_dsn
    config = _load_database_config()
    dsn = config.get("postgres_dsn") or config.get("dsn")
    return str(dsn).strip() if dsn else None


def _should_bootstrap_schema_on_connect() -> bool:
    raw = os.getenv("ZSXQ_BOOTSTRAP_SCHEMA_ON_CONNECT", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def connect(*, row_factory: Any = None):
    """Open a PostgreSQL connection scoped to the fixed zsxq_core schema."""
    if get_database_backend() != "postgres":
        raise RuntimeError(
            "SQLite backend has been removed. Configure PostgreSQL with "
            "ZSXQ_DATABASE_BACKEND=postgres and ZSXQ_POSTGRES_DSN."
        )

    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError(
            "PostgreSQL backend is enabled but no DSN is configured. "
            "Set ZSXQ_POSTGRES_DSN or config.toml [database].postgres_dsn."
        )
    return PostgresCompatConnection(dsn)


class CompatRow(tuple):
    def __new__(cls, values: Iterable[Any], columns: Iterable[str]):
        obj = super().__new__(cls, values)
        obj._columns = list(columns)
        obj._index = {name: index for index, name in enumerate(obj._columns)}
        return obj

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            return super().__getitem__(self._index[key])
        return super().__getitem__(key)

    def keys(self) -> list[str]:
        return list(self._columns)


class PostgresCompatConnection:
    def __init__(self, dsn: str):
        import psycopg2

        self._conn = psycopg2.connect(dsn)
        self.schema_name = CORE_SCHEMA
        if _should_bootstrap_schema_on_connect() and dsn not in _CORE_SCHEMA_BOOTSTRAPPED_DSNS:
            ensure_core_schema(self._conn)
            _CORE_SCHEMA_BOOTSTRAPPED_DSNS.add(dsn)
        with self._conn.cursor() as cursor:
            cursor.execute(f"SET search_path TO {quote_identifier(CORE_SCHEMA)}")
        self._conn.commit()

    def cursor(self):
        return PostgresCompatCursor(self, self._conn.cursor())

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        cursor = self.cursor()
        return cursor.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class PostgresCompatCursor:
    def __init__(self, connection: PostgresCompatConnection, cursor: Any):
        self.connection = connection
        self._cursor = cursor
        self.rowcount = -1

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        translated = _translate_sql(sql)
        try:
            self._cursor.execute(translated, tuple(params or ()))
        except Exception as exc:
            if is_schema_missing_error(exc):
                raise RuntimeError(schema_not_ready_message(exc)) from exc
            raise
        self.rowcount = self._cursor.rowcount
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        return _to_compat_row(row, self._cursor.description)

    def fetchall(self):
        return [_to_compat_row(row, self._cursor.description) for row in self._cursor.fetchall()]

    def close(self) -> None:
        self._cursor.close()


def _to_compat_row(row: Any, description: Any) -> Any:
    if row is None or not description:
        return row
    return CompatRow(row, [col[0] for col in description])


def _translate_sql(sql: str) -> str:
    _reject_sqlite_only_sql(sql)
    translated = _replace_qmark_params(sql)
    translated = re.sub(r"\bLIMIT\s+-1\s+OFFSET\b", "OFFSET", translated, flags=re.I)
    return translated


def _reject_sqlite_only_sql(sql: str) -> None:
    unsupported_patterns = (
        (r"\bPRAGMA\b", "PRAGMA"),
        (r"\bINSERT\s+OR\s+REPLACE\b", "INSERT OR REPLACE"),
        (r"\bINSERT\s+OR\s+IGNORE\b", "INSERT OR IGNORE"),
        (r"\bAUTOINCREMENT\b", "AUTOINCREMENT"),
    )
    for pattern, label in unsupported_patterns:
        if re.search(pattern, sql, flags=re.I):
            raise RuntimeError(
                f"SQLite-only SQL is no longer translated by db_compat: {label}. "
                "Use explicit PostgreSQL SQL instead."
            )


def _replace_qmark_params(sql: str) -> str:
    result: list[str] = []
    in_single = False
    in_double = False
    for char in sql:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        if char == "?" and not in_single and not in_double:
            result.append("%s")
        else:
            result.append(char)
    return "".join(result)


