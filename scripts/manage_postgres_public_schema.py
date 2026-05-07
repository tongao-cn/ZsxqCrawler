from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

import psycopg2

from backend.storage.db_compat import get_postgres_dsn


PUBLIC_SCHEMA = "zsxq_public"
DEFAULT_READER_ROLE = "zsxq_reader"
DEFAULT_WRITER_ROLE = "zsxq_writer"
INTERNAL_SCHEMA_PREFIX = "zsxq_"
_BARE_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CASTED_COLUMN_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)::")


@dataclass(frozen=True)
class PublicViewSpec:
    name: str
    table: str
    columns: tuple[tuple[str, str], ...]
    required_columns: tuple[str, ...]


PUBLIC_VIEW_SPECS: tuple[PublicViewSpec, ...] = (
    PublicViewSpec(
        name="groups",
        table="groups",
        columns=(
            ("group_id", "group_id::text"),
            ("group_name", "name::text"),
            ("group_type", "type::text"),
            ("background_url", "background_url::text"),
            ("created_at", "NULL::text"),
            ("source_updated_at", "NULL::text"),
        ),
        required_columns=("group_id", "name"),
    ),
    PublicViewSpec(
        name="topics",
        table="topics",
        columns=(
            ("group_id", "group_id::text"),
            ("topic_id", "topic_id::text"),
            ("title", "title::text"),
            ("topic_type", "type::text"),
            ("create_time", "create_time::text"),
            ("updated_at", "updated_at::text"),
            ("source_updated_at", "COALESCE(updated_at::text, imported_at::text)"),
        ),
        required_columns=("group_id", "topic_id", "title"),
    ),
    PublicViewSpec(
        name="comments",
        table="comments",
        columns=(
            ("group_id", "NULL::text"),
            ("comment_id", "comment_id::text"),
            ("topic_id", "topic_id::text"),
            ("owner_user_id", "owner_user_id::text"),
            ("text", "text::text"),
            ("create_time", "create_time::text"),
            ("source_updated_at", "NULL::text"),
        ),
        required_columns=("comment_id", "topic_id", "text"),
    ),
    PublicViewSpec(
        name="files",
        table="files",
        columns=(
            ("group_id", "NULL::text"),
            ("file_id", "file_id::text"),
            ("name", "name::text"),
            ("size", "size"),
            ("download_status", "download_status::text"),
            ("local_path", "local_path::text"),
            ("create_time", "create_time::text"),
            ("source_updated_at", "updated_at::text"),
        ),
        required_columns=("file_id", "name"),
    ),
    PublicViewSpec(
        name="columns",
        table="columns",
        columns=(
            ("group_id", "group_id::text"),
            ("column_id", "column_id::text"),
            ("name", "name::text"),
            ("description", "description::text"),
            ("topics_count", "topics_count"),
            ("created_at", "NULL::text"),
            ("source_updated_at", "updated_at::text"),
        ),
        required_columns=("column_id", "name"),
    ),
    PublicViewSpec(
        name="column_topics",
        table="column_topics",
        columns=(
            ("group_id", "group_id::text"),
            ("column_id", "column_id::text"),
            ("topic_id", "topic_id::text"),
            ("title", "title::text"),
            ("create_time", "create_time::text"),
            ("source_updated_at", "updated_at::text"),
        ),
        required_columns=("column_id", "topic_id"),
    ),
    PublicViewSpec(
        name="daily_ai_reports",
        table="daily_ai_reports",
        columns=(
            ("group_id", "group_id::text"),
            ("report_date", "report_date::text"),
            ("topic_count", "topic_count"),
            ("summary", "summary::text"),
            ("created_at", "created_at::text"),
            ("source_updated_at", "updated_at::text"),
        ),
        required_columns=("group_id", "report_date", "summary"),
    ),
    PublicViewSpec(
        name="file_ai_analyses",
        table="file_ai_analyses",
        columns=(
            ("group_id", "NULL::text"),
            ("file_id", "file_id::text"),
            ("status", "status::text"),
            ("summary", "summary::text"),
            ("content_type", "content_type::text"),
            ("source_path", "source_path::text"),
            ("source_updated_at", "updated_at::text"),
        ),
        required_columns=("file_id", "status"),
    ),
)


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _public_schema_expr(expr: str, available_columns: set[str]) -> str:
    if _BARE_COLUMN_RE.fullmatch(expr):
        return quote_identifier(expr) if expr in available_columns else "NULL"

    def replace_cast(match: re.Match[str]) -> str:
        column = match.group(1)
        if column.upper() == "NULL":
            return match.group(0)
        if column in available_columns:
            return f"{quote_identifier(column)}::"
        return "NULL::"

    return _CASTED_COLUMN_RE.sub(replace_cast, expr)


def _schema_table_ref(schema_name: str, table_name: str) -> str:
    return f"{quote_identifier(schema_name)}.{quote_identifier(table_name)}"


def discover_internal_schemas(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE %s
              AND schema_name <> %s
            ORDER BY schema_name
            """,
            (f"{INTERNAL_SCHEMA_PREFIX}%", PUBLIC_SCHEMA),
        )
        return [str(row[0]) for row in cur.fetchall()]


def get_table_columns(conn, schema_name: str, table_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            """,
            (schema_name, table_name),
        )
        return {str(row[0]) for row in cur.fetchall()}


def build_public_view_sql(
    spec: PublicViewSpec,
    schema_columns: Sequence[tuple[str, set[str]]],
    public_schema: str = PUBLIC_SCHEMA,
) -> str:
    selects: list[str] = []
    for schema_name, available_columns in schema_columns:
        if not set(spec.required_columns).issubset(available_columns):
            continue
        column_sql = [
            f"{_public_schema_expr(expr, available_columns)} AS {quote_identifier(alias)}"
            for alias, expr in spec.columns
        ]
        column_sql.append(f"{schema_name!r}::text AS source_schema")
        selects.append(
            "SELECT "
            + ", ".join(column_sql)
            + f" FROM {_schema_table_ref(schema_name, spec.table)}"
        )

    view_name = f"{quote_identifier(public_schema)}.{quote_identifier(spec.name)}"
    if not selects:
        null_columns = [f"NULL::text AS {quote_identifier(alias)}" for alias, _expr in spec.columns]
        null_columns.append("NULL::text AS source_schema")
        return f"CREATE OR REPLACE VIEW {view_name} AS SELECT {', '.join(null_columns)} WHERE false"

    return f"CREATE OR REPLACE VIEW {view_name} AS " + " UNION ALL ".join(selects)


def build_all_public_view_sql(
    conn,
    public_schema: str = PUBLIC_SCHEMA,
) -> list[str]:
    schemas = discover_internal_schemas(conn)
    statements = [f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(public_schema)}"]
    for spec in PUBLIC_VIEW_SPECS:
        schema_columns = [
            (schema_name, get_table_columns(conn, schema_name, spec.table))
            for schema_name in schemas
        ]
        statements.append(build_public_view_sql(spec, schema_columns, public_schema))
    return statements


def build_role_sql(
    reader_role: str = DEFAULT_READER_ROLE,
    writer_role: str = DEFAULT_WRITER_ROLE,
    public_schema: str = PUBLIC_SCHEMA,
) -> list[str]:
    reader = quote_identifier(reader_role)
    writer = quote_identifier(writer_role)
    schema = quote_identifier(public_schema)
    return [
        (
            "DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {writer_role!r}) "
            f"THEN CREATE ROLE {writer} NOLOGIN; END IF; "
            "END $$"
        ),
        (
            "DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {reader_role!r}) "
            f"THEN CREATE ROLE {reader} NOLOGIN; END IF; "
            "END $$"
        ),
        f"GRANT USAGE ON SCHEMA {schema} TO {reader}",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {reader}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {reader}",
        f"GRANT USAGE, CREATE ON SCHEMA {schema} TO {writer}",
    ]


def _execute_statements(conn, statements: Iterable[str]) -> None:
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    conn.commit()


def build_public_schema(*, apply: bool = False) -> list[str]:
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")
    conn = psycopg2.connect(dsn)
    try:
        statements = build_all_public_view_sql(conn)
        statements.extend(build_role_sql())
        if apply:
            _execute_statements(conn, statements)
        return statements
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage ZsxqCrawler public PostgreSQL schema")
    parser.add_argument("--apply", action="store_true", help="Execute generated SQL instead of printing it.")
    args = parser.parse_args()

    statements = build_public_schema(apply=args.apply)
    if not args.apply:
        for statement in statements:
            print(statement.rstrip(";") + ";")


if __name__ == "__main__":
    main()
