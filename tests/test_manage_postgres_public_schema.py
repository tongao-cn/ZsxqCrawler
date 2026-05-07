import unittest

from backend.storage.postgres_core_schema import CORE_SCHEMA
from scripts.manage_postgres_public_schema import (
    PUBLIC_SCHEMA,
    PUBLIC_VIEW_SPECS,
    build_internal_index_sql,
    build_public_view_sql,
    build_role_sql,
    quote_identifier,
)


class ManagePostgresPublicSchemaTests(unittest.TestCase):
    def test_quote_identifier_escapes_embedded_quotes(self):
        self.assertEqual('"plain"', quote_identifier("plain"))
        self.assertEqual('"has""quote"', quote_identifier('has"quote'))

    def test_build_public_view_sql_reads_core_schema(self):
        topic_spec = next(spec for spec in PUBLIC_VIEW_SPECS if spec.name == "topics")

        sql = build_public_view_sql(
            topic_spec,
            [(CORE_SCHEMA, {"group_id", "topic_id", "title", "type", "create_time", "updated_at", "source_schema"})],
        )

        self.assertIn(f'CREATE OR REPLACE VIEW "{PUBLIC_SCHEMA}"."topics"', sql)
        self.assertIn(f'"{CORE_SCHEMA}"."topics" AS "src"', sql)
        self.assertIn('COALESCE("src"."source_schema"', sql)
        self.assertIn('"src"."group_id"::text AS "group_id"', sql)

    def test_build_public_view_sql_returns_empty_view_when_core_table_missing_columns(self):
        files_spec = next(spec for spec in PUBLIC_VIEW_SPECS if spec.name == "files")

        sql = build_public_view_sql(files_spec, [(CORE_SCHEMA, {"topic_id", "title"})])

        self.assertIn(f'CREATE OR REPLACE VIEW "{PUBLIC_SCHEMA}"."files"', sql)
        self.assertIn("WHERE false", sql)
        self.assertIn('NULL::text AS "group_id"', sql)

    def test_build_public_view_sql_uses_null_for_missing_optional_columns(self):
        topic_spec = next(spec for spec in PUBLIC_VIEW_SPECS if spec.name == "topics")

        sql = build_public_view_sql(
            topic_spec,
            [(CORE_SCHEMA, {"group_id", "topic_id", "title"})],
        )

        self.assertIn("NULL::text AS \"topic_type\"", sql)
        self.assertIn("COALESCE(NULL::text, NULL::text) AS \"source_updated_at\"", sql)
        self.assertNotIn("updated_at::text", sql)
        self.assertNotIn("imported_at::text", sql)

    def test_build_public_view_sql_fills_comment_group_id_from_topics(self):
        comment_spec = next(spec for spec in PUBLIC_VIEW_SPECS if spec.name == "comments")

        sql = build_public_view_sql(
            comment_spec,
            [(CORE_SCHEMA, {"comment_id", "topic_id", "text"})],
            schema_table_columns=[
                (
                    CORE_SCHEMA,
                    {
                        "comments": {"comment_id", "topic_id", "text"},
                        "topics": {"topic_id", "group_id"},
                    },
                )
            ],
        )

        self.assertIn(f'FROM "{CORE_SCHEMA}"."topics" AS "t"', sql)
        self.assertIn('"t"."topic_id"::text = "src"."topic_id"::text', sql)
        self.assertIn('AS "group_id"', sql)

    def test_build_role_sql_grants_reader_select_only_shape(self):
        sql = build_role_sql(reader_role="reader", writer_role="writer", public_schema="public_read")

        self.assertIn('CREATE ROLE "reader" NOLOGIN', "\n".join(sql))
        self.assertIn('CREATE ROLE "writer" NOLOGIN', "\n".join(sql))
        self.assertIn("IF NOT EXISTS", "\n".join(sql))
        self.assertIn('GRANT USAGE ON SCHEMA "public_read" TO "reader"', sql)
        self.assertIn('GRANT SELECT ON ALL TABLES IN SCHEMA "public_read" TO "reader"', sql)
        self.assertNotIn('GRANT INSERT', "\n".join(sql))

    def test_build_role_sql_can_emit_login_password_setup(self):
        sql = build_role_sql(
            reader_role="reader",
            writer_role="writer",
            public_schema="public_read",
            login_roles=True,
            reader_password="reader'pw",
            writer_password="writer-pw",
        )

        self.assertIn('ALTER ROLE "reader" LOGIN', sql)
        self.assertIn('ALTER ROLE "writer" LOGIN', sql)
        self.assertIn('ALTER ROLE "reader" LOGIN PASSWORD \'reader\'\'pw\'', sql)
        self.assertIn('ALTER ROLE "writer" LOGIN PASSWORD \'writer-pw\'', sql)

    def test_build_internal_index_sql_uses_core_schema(self):
        class FakeCursor:
            def __init__(self):
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                if "information_schema.columns" in sql:
                    columns = {
                        "topics": [("group_id",), ("topic_id",), ("create_time",)],
                        "files": [("file_id",)],
                    }.get(params[1], [])
                    self.rows = columns
                else:
                    self.rows = []

            def fetchall(self):
                return self.rows

        class FakeConn:
            def cursor(self):
                return FakeCursor()

        sql = "\n".join(build_internal_index_sql(FakeConn()))

        self.assertIn(f'ON "{CORE_SCHEMA}"."topics" ("group_id")', sql)
        self.assertIn(f'ON "{CORE_SCHEMA}"."topics" ("topic_id")', sql)
        self.assertIn(f'ON "{CORE_SCHEMA}"."files" ("file_id")', sql)
        self.assertNotIn('"updated_at"', sql)


if __name__ == "__main__":
    unittest.main()
