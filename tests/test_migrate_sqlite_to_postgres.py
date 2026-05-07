import sqlite3
import unittest
from unittest.mock import patch

from scripts.migrate_sqlite_to_postgres import (
    _boolean_column_indexes,
    _convert_row,
    _quote_identifier,
    _sqlite_tables,
    _table_columns,
    main,
)


class MigrateSqliteToPostgresHelperTests(unittest.TestCase):
    def test_quote_identifier_escapes_embedded_quotes(self):
        self.assertEqual(_quote_identifier("plain"), '"plain"')
        self.assertEqual(_quote_identifier('has"quote'), '"has""quote"')

    def test_convert_row_converts_boolean_indexes_only(self):
        row = (1, 0, None, "text")

        self.assertEqual(_convert_row(row, {0, 1, 2, 9}), (True, False, None, "text"))
        self.assertIs(_convert_row(row, set()), row)

    def test_sqlite_tables_returns_user_tables_in_creation_order(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE TABLE first_table (id INTEGER)")
            conn.execute("CREATE TABLE second_table (id INTEGER)")
            conn.execute("CREATE INDEX second_idx ON second_table (id)")

            tables = _sqlite_tables(conn)

            self.assertEqual([name for name, _sql in tables], ["first_table", "second_table"])
            self.assertTrue(all("CREATE TABLE" in sql.upper() for _name, sql in tables))
        finally:
            conn.close()

    def test_table_columns_handles_quoted_table_and_column_names(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute('CREATE TABLE "topic "" files" ("id" INTEGER, "file "" name" TEXT)')

            self.assertEqual(_table_columns(conn, 'topic " files'), ["id", 'file " name'])
        finally:
            conn.close()

    def test_boolean_column_indexes_detects_declared_bool_columns(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                'CREATE TABLE "topic "" flags" ('
                "id INTEGER, "
                "is_active BOOLEAN, "
                "title TEXT, "
                "has_file bool"
                ")"
            )

            self.assertEqual(_boolean_column_indexes(conn, 'topic " flags'), {1, 3})
        finally:
            conn.close()

    def test_build_public_views_only_skips_sqlite_migration(self):
        with (
            patch("scripts.migrate_sqlite_to_postgres.get_database_backend", return_value="postgres"),
            patch("scripts.migrate_sqlite_to_postgres.build_public_schema") as build_public_schema,
            patch("scripts.migrate_sqlite_to_postgres.migrate_file") as migrate_file,
            patch("sys.argv", ["migrate-sqlite-to-postgres", "--build-public-views"]),
        ):
            main()

        build_public_schema.assert_called_once_with(apply=True)
        migrate_file.assert_not_called()


if __name__ == "__main__":
    unittest.main()
