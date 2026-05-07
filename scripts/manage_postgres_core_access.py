from __future__ import annotations

import argparse
from dataclasses import dataclass

import psycopg2

from backend.storage.db_compat import get_postgres_dsn
from backend.storage.postgres_core_schema import CORE_SCHEMA, quote_identifier


DEFAULT_READER_ROLE = "zsxq_reader"
DEFAULT_WRITER_ROLE = "zsxq_writer"


@dataclass(frozen=True)
class CoreAccessSql:
    statements: list[str]

    def text(self) -> str:
        return ";\n".join(statement.rstrip(";") for statement in self.statements) + ";\n"


def _role_sql(role: str, *, login: bool, password: str | None) -> str:
    login_sql = "LOGIN" if login else "NOLOGIN"
    escaped_password = password.replace("'", "''") if password else ""
    password_sql = f" PASSWORD '{escaped_password}'" if login and password else ""
    quoted = quote_identifier(role)
    return f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {role!r}) THEN
        CREATE ROLE {quoted} {login_sql}{password_sql};
    ELSE
        ALTER ROLE {quoted} {login_sql}{password_sql};
    END IF;
END $$""".strip()


def build_core_access_sql(
    *,
    reader_role: str = DEFAULT_READER_ROLE,
    writer_role: str = DEFAULT_WRITER_ROLE,
    login_roles: bool = False,
    reader_password: str | None = None,
    writer_password: str | None = None,
) -> CoreAccessSql:
    core_schema = quote_identifier(CORE_SCHEMA)
    reader = quote_identifier(reader_role)
    writer = quote_identifier(writer_role)
    statements = [
        _role_sql(reader_role, login=login_roles, password=reader_password),
        _role_sql(writer_role, login=login_roles, password=writer_password),
        f"REVOKE CREATE ON SCHEMA {core_schema} FROM {reader}",
        f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA {core_schema} FROM {reader}",
        f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {core_schema} FROM {reader}",
        f"GRANT USAGE ON SCHEMA {core_schema} TO {reader}",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {core_schema} TO {reader}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {core_schema} GRANT SELECT ON TABLES TO {reader}",
        f"GRANT USAGE ON SCHEMA {core_schema} TO {writer}",
        f"GRANT CREATE ON SCHEMA {core_schema} TO {writer}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {core_schema} TO {writer}",
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {core_schema} TO {writer}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {core_schema} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {writer}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {core_schema} GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {writer}",
    ]
    return CoreAccessSql(statements)


def apply_sql(sql: CoreAccessSql) -> None:
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            for statement in sql.statements:
                cur.execute(statement)
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage zsxq_core PostgreSQL reader/writer roles")
    parser.add_argument("--apply", action="store_true", help="Execute generated SQL instead of printing it.")
    parser.add_argument("--login-roles", action="store_true", help="Allow zsxq_reader and zsxq_writer to log in.")
    parser.add_argument("--reader-password", default=None, help="Password to set for the reader role.")
    parser.add_argument("--writer-password", default=None, help="Password to set for the writer role.")
    args = parser.parse_args()

    sql = build_core_access_sql(
        login_roles=args.login_roles,
        reader_password=args.reader_password,
        writer_password=args.writer_password,
    )
    if args.apply:
        apply_sql(sql)
    else:
        print(sql.text(), end="")


if __name__ == "__main__":
    main()
