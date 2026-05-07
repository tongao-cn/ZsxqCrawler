from __future__ import annotations

import os
import re
import hashlib
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


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


def connect(db_path: str | Path, *, row_factory: Any = None):
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
    return PostgresCompatConnection(dsn, schema_name=schema_name_for_path(db_path))


def schema_name_for_path(db_path: str | Path) -> str:
    path = str(db_path).replace("\\", "/")
    stem = Path(path).stem or "default"
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", stem).strip("_").lower() or "default"
    digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:8]
    return f"zsxq_{slug}_{digest}"


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
    def __init__(self, dsn: str, schema_name: str):
        import psycopg2

        self._conn = psycopg2.connect(dsn)
        self.schema_name = schema_name
        with self._conn.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
            cursor.execute(f'SET search_path TO "{schema_name}"')
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
        self.lastrowid: Optional[int] = None
        self.rowcount = -1
        self._rows: Optional[list[Any]] = None

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        self.lastrowid = None
        self._rows = None

        pragma = _parse_pragma_table_info(sql)
        if pragma:
            self._execute_table_info(pragma)
            return self
        if re.match(r"\s*PRAGMA\b", sql, flags=re.I):
            self._rows = []
            self.rowcount = 0
            return self

        translated = _translate_sql(sql)
        returning_id = _should_return_id(translated)
        if returning_id:
            translated = f"{translated.rstrip().rstrip(';')} RETURNING id"

        self._cursor.execute(translated, tuple(params or ()))
        self.rowcount = self._cursor.rowcount
        if returning_id:
            row = self._cursor.fetchone()
            self.lastrowid = row[0] if row else None
        return self

    def fetchone(self):
        if self._rows is not None:
            return self._rows.pop(0) if self._rows else None
        row = self._cursor.fetchone()
        return _to_compat_row(row, self._cursor.description)

    def fetchall(self):
        if self._rows is not None:
            rows = self._rows
            self._rows = []
            return rows
        return [_to_compat_row(row, self._cursor.description) for row in self._cursor.fetchall()]

    def close(self) -> None:
        self._cursor.close()

    def _execute_table_info(self, table_name: str) -> None:
        self._cursor.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        rows = []
        for index, row in enumerate(self._cursor.fetchall()):
            name, data_type, is_nullable, default = row
            rows.append((index, name, data_type, 0 if is_nullable == "YES" else 1, default, 0))
        self._rows = rows
        self.rowcount = len(rows)


def _to_compat_row(row: Any, description: Any) -> Any:
    if row is None or not description:
        return row
    return CompatRow(row, [col[0] for col in description])


def _parse_pragma_table_info(sql: str) -> Optional[str]:
    match = re.fullmatch(r"\s*PRAGMA\s+table_info\(([^)]+)\)\s*;?\s*", sql, flags=re.I)
    return match.group(1).strip("\"'") if match else None


def _translate_sql(sql: str) -> str:
    translated = _strip_foreign_key_lines(sql)
    translated = re.sub(
        r"\b(\w+)\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        r"\1 BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
        translated,
        flags=re.I,
    )
    translated = re.sub(r"\bINTEGER\b", "BIGINT", translated, flags=re.I)
    translated = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", translated, flags=re.I)
    translated = re.sub(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", "INSERT INTO", translated, flags=re.I)
    translated = _add_do_nothing_for_ignore(sql, translated)
    translated = _add_upsert_for_replace(sql, translated)
    translated = _replace_qmark_params(translated)
    translated = re.sub(r"\bLIMIT\s+-1\s+OFFSET\b", "OFFSET", translated, flags=re.I)
    return translated


def _strip_foreign_key_lines(sql: str) -> str:
    if not re.match(r"\s*CREATE\s+TABLE\b", sql, flags=re.I):
        return sql
    lines = sql.splitlines()
    kept = [line for line in lines if "FOREIGN KEY" not in line.upper()]
    for index in range(len(kept) - 1):
        if kept[index].rstrip().endswith(",") and re.match(r"\s*\)\s*;?\s*$", kept[index + 1]):
            kept[index] = kept[index].rstrip().rstrip(",")
    return "\n".join(kept)


def _add_do_nothing_for_ignore(original: str, translated: str) -> str:
    if not re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", original, flags=re.I):
        return translated
    if re.search(r"\bON\s+CONFLICT\b", translated, flags=re.I):
        return translated
    return f"{translated.rstrip().rstrip(';')} ON CONFLICT DO NOTHING"


def _add_upsert_for_replace(original: str, translated: str) -> str:
    if not re.search(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", original, flags=re.I):
        return translated
    if re.search(r"\bON\s+CONFLICT\b", translated, flags=re.I):
        return translated

    match = re.search(
        r'INSERT\s+INTO\s+(?:"([^"]+)"|(\w+))\s*\((.*?)\)\s*VALUES',
        translated,
        flags=re.I | re.S,
    )
    if not match:
        return translated
    table_name = match.group(1) or match.group(2)
    columns = [col.strip().strip('"') for col in match.group(3).split(",")]
    conflict_target = _pick_conflict_target(table_name, columns)
    if not conflict_target:
        return translated
    target_cols = [col.strip() for col in conflict_target.strip("()").split(",")]
    update_cols = [col for col in columns if col not in target_cols]
    if not update_cols:
        return f"{translated.rstrip().rstrip(';')} ON CONFLICT {conflict_target} DO NOTHING"
    updates = ", ".join(f"{col} = EXCLUDED.{col}" for col in update_cols)
    return f"{translated.rstrip().rstrip(';')} ON CONFLICT {conflict_target} DO UPDATE SET {updates}"


def _pick_conflict_target(table_name: str, columns: list[str]) -> Optional[str]:
    preferred: dict[str, str] = {
        "accounts": "id",
        "accounts_self": "account_id",
        "groups": "group_id",
        "users": "user_id",
        "topics": "topic_id",
        "comments": "comment_id",
        "images": "image_id",
        "files": "file_id",
        "columns": "column_id",
        "column_topics": "topic_id",
        "topic_details": "topic_id",
        "videos": "video_id",
        "task_runs": "task_id",
        "file_ai_analyses": "file_id",
        "topic_owners": "topic_id, owner_type",
    }.get(table_name)
    if not preferred:
        return None
    target_cols = [col.strip() for col in preferred.split(",")]
    if all(col in columns for col in target_cols):
        return f"({preferred})"
    return None


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


def _should_return_id(sql: str) -> bool:
    if re.search(r"\bRETURNING\b", sql, flags=re.I):
        return False
    match = re.match(r'\s*INSERT\s+INTO\s+(?:"([^"]+)"|(\w+))\s*\(', sql, flags=re.I)
    if not match:
        return False
    table_name = match.group(1) or match.group(2)
    return table_name in {"crawl_log", "solutions"}
