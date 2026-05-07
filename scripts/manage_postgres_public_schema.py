from __future__ import annotations

import argparse
import hashlib
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
SOURCE_ALIAS = "src"
TOPIC_GROUP_ID_EXPR = "$topic_group_id"
SINGLE_GROUP_ID_EXPR = "$single_group_id"


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
            ("group_id", TOPIC_GROUP_ID_EXPR),
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
            ("group_id", SINGLE_GROUP_ID_EXPR),
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
            ("group_id", SINGLE_GROUP_ID_EXPR),
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

INTERNAL_INDEX_SPECS: dict[str, tuple[tuple[str, ...], ...]] = {
    "groups": (("group_id",),),
    "topics": (("group_id",), ("topic_id",), ("create_time",), ("updated_at",)),
    "comments": (("topic_id",), ("comment_id",), ("create_time",)),
    "files": (("file_id",), ("download_status",), ("create_time",)),
    "columns": (("group_id",), ("column_id",)),
    "column_topics": (("group_id",), ("column_id",), ("topic_id",)),
    "daily_ai_reports": (("group_id", "report_date"),),
    "file_ai_analyses": (("file_id",), ("status",)),
}


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _source_column(column: str) -> str:
    return f"{quote_identifier(SOURCE_ALIAS)}.{quote_identifier(column)}"


def _single_group_id_expr(schema_name: str, table_columns: dict[str, set[str]]) -> str:
    if "group_id" in table_columns.get("groups", set()):
        return (
            f"(SELECT {quote_identifier('g')}.{quote_identifier('group_id')}::text "
            f"FROM {_schema_table_ref(schema_name, 'groups')} AS {quote_identifier('g')} LIMIT 1)"
        )
    return "NULL::text"


def _topic_group_id_expr(
    schema_name: str,
    available_columns: set[str],
    table_columns: dict[str, set[str]],
) -> str:
    if "group_id" in available_columns:
        return f"{_source_column('group_id')}::text"
    if {"topic_id", "group_id"}.issubset(table_columns.get("topics", set())) and "topic_id" in available_columns:
        return (
            f"(SELECT {quote_identifier('t')}.{quote_identifier('group_id')}::text "
            f"FROM {_schema_table_ref(schema_name, 'topics')} AS {quote_identifier('t')} "
            f"WHERE {quote_identifier('t')}.{quote_identifier('topic_id')}::text = "
            f"{_source_column('topic_id')}::text LIMIT 1)"
        )
    return _single_group_id_expr(schema_name, table_columns)


def _public_schema_expr(
    expr: str,
    available_columns: set[str],
    schema_name: str,
    table_columns: dict[str, set[str]],
) -> str:
    if expr == SINGLE_GROUP_ID_EXPR:
        if "group_id" in available_columns:
            return f"{_source_column('group_id')}::text"
        return _single_group_id_expr(schema_name, table_columns)
    if expr == TOPIC_GROUP_ID_EXPR:
        return _topic_group_id_expr(schema_name, available_columns, table_columns)

    if _BARE_COLUMN_RE.fullmatch(expr):
        return _source_column(expr) if expr in available_columns else "NULL"

    def replace_cast(match: re.Match[str]) -> str:
        column = match.group(1)
        if column.upper() == "NULL":
            return match.group(0)
        if column in available_columns:
            return f"{_source_column(column)}::"
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


def get_schema_table_columns(conn, schema_name: str, table_names: Iterable[str]) -> dict[str, set[str]]:
    return {
        table_name: get_table_columns(conn, schema_name, table_name)
        for table_name in sorted(set(table_names))
    }


def build_public_view_sql(
    spec: PublicViewSpec,
    schema_columns: Sequence[tuple[str, set[str]]],
    public_schema: str = PUBLIC_SCHEMA,
    schema_table_columns: Sequence[tuple[str, dict[str, set[str]]]] | None = None,
) -> str:
    selects: list[str] = []
    table_columns_by_schema = dict(schema_table_columns or ())
    for schema_name, available_columns in schema_columns:
        if not set(spec.required_columns).issubset(available_columns):
            continue
        table_columns = table_columns_by_schema.get(schema_name, {spec.table: available_columns})
        table_columns.setdefault(spec.table, available_columns)
        column_sql = [
            f"{_public_schema_expr(expr, available_columns, schema_name, table_columns)} AS {quote_identifier(alias)}"
            for alias, expr in spec.columns
        ]
        column_sql.append(f"{schema_name!r}::text AS source_schema")
        selects.append(
            "SELECT "
            + ", ".join(column_sql)
            + f" FROM {_schema_table_ref(schema_name, spec.table)} AS {quote_identifier(SOURCE_ALIAS)}"
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
    table_names = {spec.table for spec in PUBLIC_VIEW_SPECS} | {"groups", "topics"}
    schema_table_columns = [
        (schema_name, get_schema_table_columns(conn, schema_name, table_names))
        for schema_name in schemas
    ]
    statements = [f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(public_schema)}"]
    for spec in PUBLIC_VIEW_SPECS:
        schema_columns = [
            (schema_name, table_columns.get(spec.table, set()))
            for schema_name, table_columns in schema_table_columns
        ]
        statements.append(build_public_view_sql(spec, schema_columns, public_schema, schema_table_columns))
    return statements


def build_role_sql(
    reader_role: str = DEFAULT_READER_ROLE,
    writer_role: str = DEFAULT_WRITER_ROLE,
    public_schema: str = PUBLIC_SCHEMA,
    *,
    login_roles: bool = False,
    reader_password: str | None = None,
    writer_password: str | None = None,
) -> list[str]:
    reader = quote_identifier(reader_role)
    writer = quote_identifier(writer_role)
    schema = quote_identifier(public_schema)
    statements = [
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
        (
            "DO $$ BEGIN "
            f"EXECUTE format('GRANT CREATE ON DATABASE %I TO %I', current_database(), {writer_role!r}); "
            "END $$"
        ),
    ]
    if login_roles:
        statements.extend(
            [
                f"ALTER ROLE {reader} LOGIN",
                f"ALTER ROLE {writer} LOGIN",
            ]
        )
    if reader_password:
        statements.append(f"ALTER ROLE {reader} LOGIN PASSWORD {quote_literal(reader_password)}")
    if writer_password:
        statements.append(f"ALTER ROLE {writer} LOGIN PASSWORD {quote_literal(writer_password)}")
    return statements


def build_internal_writer_grant_sql(conn, writer_role: str = DEFAULT_WRITER_ROLE) -> list[str]:
    writer = quote_identifier(writer_role)
    statements: list[str] = []
    for schema_name in discover_internal_schemas(conn):
        schema = quote_identifier(schema_name)
        statements.extend(
            [
                f"GRANT USAGE, CREATE ON SCHEMA {schema} TO {writer}",
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {writer}",
                f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {schema} TO {writer}",
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {writer}",
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {writer}",
            ]
        )
    return statements


def _index_name(table_name: str, columns: tuple[str, ...]) -> str:
    base = f"idx_{table_name}_{'_'.join(columns)}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"{base[:48]}_{digest}"


def build_internal_index_sql(conn) -> list[str]:
    statements: list[str] = []
    for schema_name in discover_internal_schemas(conn):
        for table_name, index_columns in INTERNAL_INDEX_SPECS.items():
            available_columns = get_table_columns(conn, schema_name, table_name)
            if not available_columns:
                continue
            for columns in index_columns:
                if not set(columns).issubset(available_columns):
                    continue
                col_sql = ", ".join(quote_identifier(column) for column in columns)
                index_name = quote_identifier(_index_name(table_name, columns))
                statements.append(
                    f"CREATE INDEX IF NOT EXISTS {index_name} "
                    f"ON {_schema_table_ref(schema_name, table_name)} ({col_sql})"
                )
    return statements


def _execute_statements(conn, statements: Iterable[str]) -> None:
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    conn.commit()


def build_public_schema(
    *,
    apply: bool = False,
    build_indexes: bool = False,
    login_roles: bool = False,
    reader_password: str | None = None,
    writer_password: str | None = None,
) -> list[str]:
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")
    conn = psycopg2.connect(dsn)
    try:
        statements = build_all_public_view_sql(conn)
        statements.extend(
            build_role_sql(
                login_roles=login_roles,
                reader_password=reader_password,
                writer_password=writer_password,
            )
        )
        statements.extend(build_internal_writer_grant_sql(conn))
        if build_indexes:
            statements.extend(build_internal_index_sql(conn))
        if apply:
            _execute_statements(conn, statements)
        return statements
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage ZsxqCrawler public PostgreSQL schema")
    parser.add_argument("--apply", action="store_true", help="Execute generated SQL instead of printing it.")
    parser.add_argument("--build-indexes", action="store_true", help="Create best-effort indexes on internal zsxq_* tables.")
    parser.add_argument("--login-roles", action="store_true", help="Allow zsxq_reader and zsxq_writer to log in.")
    parser.add_argument("--reader-password", help="Password to set for the reader role.")
    parser.add_argument("--writer-password", help="Password to set for the writer role.")
    args = parser.parse_args()

    statements = build_public_schema(
        apply=args.apply,
        build_indexes=args.build_indexes,
        login_roles=args.login_roles,
        reader_password=args.reader_password,
        writer_password=args.writer_password,
    )
    if not args.apply:
        for statement in statements:
            print(statement.rstrip(";") + ";")


if __name__ == "__main__":
    main()
