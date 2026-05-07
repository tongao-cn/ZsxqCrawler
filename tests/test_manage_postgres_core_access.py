import unittest

from backend.storage.postgres_core_schema import CORE_SCHEMA, quote_identifier
from scripts.manage_postgres_core_access import build_core_access_sql


class ManagePostgresCoreAccessTests(unittest.TestCase):
    def test_quote_identifier_escapes_embedded_quotes(self):
        self.assertEqual('"plain"', quote_identifier("plain"))
        self.assertEqual('"has""quote"', quote_identifier('has"quote'))

    def test_build_core_access_sql_grants_reader_select_only_shape(self):
        sql = build_core_access_sql(reader_role="reader", writer_role="writer").statements
        joined = "\n".join(sql)

        self.assertIn('CREATE ROLE "reader" NOLOGIN', joined)
        self.assertIn('CREATE ROLE "writer" NOLOGIN', joined)
        self.assertIn(f'GRANT USAGE ON SCHEMA "{CORE_SCHEMA}" TO "reader"', sql)
        self.assertIn(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{CORE_SCHEMA}" TO "reader"', sql)
        self.assertIn("REVOKE INSERT, UPDATE, DELETE", joined)
        self.assertNotIn('GRANT INSERT ON ALL TABLES IN SCHEMA "zsxq_core" TO "reader"', joined)

    def test_build_core_access_sql_grants_writer_core_write_shape(self):
        sql = build_core_access_sql(reader_role="reader", writer_role="writer").statements

        self.assertIn(f'GRANT USAGE ON SCHEMA "{CORE_SCHEMA}" TO "writer"', sql)
        self.assertIn(f'GRANT CREATE ON SCHEMA "{CORE_SCHEMA}" TO "writer"', sql)
        self.assertIn(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{CORE_SCHEMA}" TO "writer"', sql)
        self.assertIn(f'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA "{CORE_SCHEMA}" TO "writer"', sql)

    def test_build_core_access_sql_can_emit_login_password_setup(self):
        sql = build_core_access_sql(
            reader_role="reader",
            writer_role="writer",
            login_roles=True,
            reader_password="reader'pw",
            writer_password="writer-pw",
        ).statements

        self.assertIn('ALTER ROLE "reader" LOGIN', "\n".join(sql))
        self.assertIn('ALTER ROLE "writer" LOGIN', "\n".join(sql))
        self.assertIn("ALTER ROLE \"reader\" LOGIN PASSWORD 'reader''pw'", "\n".join(sql))
        self.assertIn('ALTER ROLE "writer" LOGIN PASSWORD \'writer-pw\'', "\n".join(sql))


if __name__ == "__main__":
    unittest.main()
