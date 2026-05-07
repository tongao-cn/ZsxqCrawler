from __future__ import annotations

import argparse

import psycopg2

from backend.storage.db_compat import get_postgres_dsn
from backend.storage.postgres_core_schema import build_core_schema_sql, execute_statements


def build_core_schema(*, apply: bool = False, build_indexes: bool = True) -> list[str]:
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")
    statements = build_core_schema_sql(include_indexes=build_indexes)
    if apply:
        conn = psycopg2.connect(dsn)
        try:
            execute_statements(conn, statements)
        finally:
            conn.close()
    return statements


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage ZsxqCrawler core PostgreSQL schema")
    parser.add_argument("--apply", action="store_true", help="Execute generated SQL instead of printing it.")
    parser.add_argument("--no-indexes", action="store_true", help="Skip core index creation statements.")
    args = parser.parse_args()

    statements = build_core_schema(apply=args.apply, build_indexes=not args.no_indexes)
    if not args.apply:
        for statement in statements:
            print(statement.rstrip(";") + ";")


if __name__ == "__main__":
    main()
