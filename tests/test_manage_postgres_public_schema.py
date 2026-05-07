import unittest

from scripts.manage_postgres_public_schema import (
    PUBLIC_SCHEMA,
    PUBLIC_VIEW_SPECS,
    build_public_view_sql,
    build_role_sql,
    quote_identifier,
)


class ManagePostgresPublicSchemaTests(unittest.TestCase):
    def test_quote_identifier_escapes_embedded_quotes(self):
        self.assertEqual('"plain"', quote_identifier("plain"))
        self.assertEqual('"has""quote"', quote_identifier('has"quote'))

    def test_build_public_view_sql_unions_matching_schemas(self):
        topic_spec = next(spec for spec in PUBLIC_VIEW_SPECS if spec.name == "topics")

        sql = build_public_view_sql(
            topic_spec,
            [
                ("zsxq_topics_a", {"group_id", "topic_id", "title", "type", "create_time", "updated_at"}),
                ("zsxq_files_b", {"file_id", "name"}),
            ],
        )

        self.assertIn(f'CREATE OR REPLACE VIEW "{PUBLIC_SCHEMA}"."topics"', sql)
        self.assertIn('"zsxq_topics_a"."topics"', sql)
        self.assertNotIn('"zsxq_files_b"."topics"', sql)
        self.assertIn("'zsxq_topics_a'::text AS source_schema", sql)
        self.assertIn('"group_id"::text AS "group_id"', sql)

    def test_build_public_view_sql_returns_empty_view_when_no_schema_matches(self):
        files_spec = next(spec for spec in PUBLIC_VIEW_SPECS if spec.name == "files")

        sql = build_public_view_sql(files_spec, [("zsxq_topics_a", {"topic_id", "title"})])

        self.assertIn(f'CREATE OR REPLACE VIEW "{PUBLIC_SCHEMA}"."files"', sql)
        self.assertIn("WHERE false", sql)
        self.assertIn('NULL::text AS "group_id"', sql)

    def test_build_role_sql_grants_reader_select_only_shape(self):
        sql = build_role_sql(reader_role="reader", writer_role="writer", public_schema="public_read")

        self.assertIn('CREATE ROLE "reader" NOLOGIN', "\n".join(sql))
        self.assertIn('CREATE ROLE "writer" NOLOGIN', "\n".join(sql))
        self.assertIn("IF NOT EXISTS", "\n".join(sql))
        self.assertIn('GRANT USAGE ON SCHEMA "public_read" TO "reader"', sql)
        self.assertIn('GRANT SELECT ON ALL TABLES IN SCHEMA "public_read" TO "reader"', sql)
        self.assertNotIn('GRANT INSERT', "\n".join(sql))


if __name__ == "__main__":
    unittest.main()
