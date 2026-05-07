from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Iterable

import psycopg2

from backend.storage.db_compat import (
    connect,
    get_database_backend,
    get_postgres_dsn,
    schema_name_for_path,
)
from scripts.manage_postgres_public_schema import build_public_schema


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _iter_sqlite_files(root: Path) -> Iterable[Path]:
    yield from sorted(root.rglob("*.db"))


def _sqlite_tables(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
          AND sql IS NOT NULL
        ORDER BY rowid
        """
    ).fetchall()
    return [(str(name), str(sql)) for name, sql in rows]


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()]


def _boolean_column_indexes(conn: sqlite3.Connection, table_name: str) -> set[int]:
    indexes: set[int] = set()
    for index, row in enumerate(conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()):
        declared_type = str(row[2] or "").upper()
        if "BOOL" in declared_type:
            indexes.add(index)
    return indexes


def _convert_row(row: tuple, boolean_indexes: set[int]) -> tuple:
    if not boolean_indexes:
        return row
    values = list(row)
    for index in boolean_indexes:
        if index < len(values) and values[index] is not None:
            values[index] = bool(values[index])
    return tuple(values)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _drop_schema(db_path: Path) -> None:
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")
    schema = schema_name_for_path(db_path)
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.commit()
    finally:
        conn.close()


def migrate_file(db_path: Path, *, replace_schema: bool = False) -> dict[str, int | str]:
    if replace_schema:
        _drop_schema(db_path)

    source = sqlite3.connect(db_path)
    target = connect(db_path)
    copied_rows = 0
    copied_tables = 0
    try:
        target_cursor = target.cursor()
        for table_name, create_sql in _sqlite_tables(source):
            target_cursor.execute(create_sql)
            columns = _table_columns(source, table_name)
            if not columns:
                continue
            col_sql = ", ".join(_quote_identifier(column) for column in columns)
            placeholders = ", ".join("?" for _ in columns)
            boolean_indexes = _boolean_column_indexes(source, table_name)
            rows = source.execute(f"SELECT {col_sql} FROM {_quote_identifier(table_name)}").fetchall()
            for row in rows:
                target_cursor.execute(
                    f"INSERT INTO {_quote_identifier(table_name)} ({col_sql}) VALUES ({placeholders})",
                    _convert_row(row, boolean_indexes),
                )
            copied_tables += 1
            copied_rows += len(rows)
        target.commit()
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()

    return {
        "path": str(db_path),
        "schema": schema_name_for_path(db_path),
        "tables": copied_tables,
        "rows": copied_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate ZsxqCrawler SQLite databases to PostgreSQL")
    parser.add_argument(
        "--root",
        default=None,
        help="Directory containing .db files. Defaults to output/databases.",
    )
    parser.add_argument(
        "--replace-schema",
        action="store_true",
        help="Drop each destination schema before importing it.",
    )
    parser.add_argument(
        "--build-public-views",
        action="store_true",
        help="Create or refresh zsxq_public views and read-only grants after migration.",
    )
    parser.add_argument(
        "--build-indexes",
        action="store_true",
        help="Create best-effort indexes on migrated PostgreSQL tables when refreshing public schema.",
    )
    args = parser.parse_args()
    if args.build_indexes:
        args.build_public_views = True

    if get_database_backend() != "postgres":
        raise RuntimeError("Set ZSXQ_DATABASE_BACKEND=postgres or config.toml [database].backend = 'postgres'")

    migrate_databases = bool(args.root or args.replace_schema or not args.build_public_views)

    if not migrate_databases:
        build_public_schema(apply=True, build_indexes=args.build_indexes)
        print("zsxq_public views refreshed")
        return

    root = Path(args.root) if args.root else _project_root() / "output" / "databases"
    if not root.exists():
        raise FileNotFoundError(f"SQLite database root not found: {root}")

    db_files = list(_iter_sqlite_files(root))
    if not db_files:
        print(f"No .db files found under {root}")
        return

    for db_file in db_files:
        result = migrate_file(db_file, replace_schema=args.replace_schema)
        print(
            f"{result['path']} -> schema {result['schema']}: "
            f"{result['tables']} tables, {result['rows']} rows"
        )

    if args.build_public_views:
        build_public_schema(apply=True, build_indexes=args.build_indexes)
        print("zsxq_public views refreshed")


if __name__ == "__main__":
    main()
