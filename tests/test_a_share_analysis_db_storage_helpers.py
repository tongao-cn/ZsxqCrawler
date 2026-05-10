import unittest
from datetime import datetime
from importlib.util import find_spec
from unittest.mock import patch


HAS_STORAGE_DEPS = find_spec("psycopg2") is not None


class AShareAnalysisDbStorageHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_tdx_export_block_payload_normalizes_row_values(self):
        from backend.services.a_share_analysis_db_storage import _tdx_export_block_payload

        payload = _tdx_export_block_payload((3, "3日推荐池", "block3", r"C:\tdx\block3.blk", 5, 2, '["A", "B"]'))

        self.assertEqual(
            {
                "window_days": 3,
                "block_name": "3日推荐池",
                "block_code": "block3",
                "block_path": r"C:\tdx\block3.blk",
                "written_count": 5,
                "skipped_count": 2,
                "skipped_companies": ["A", "B"],
            },
            payload,
        )

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_latest_tdx_export_payload_keeps_existing_shape(self):
        from backend.services.a_share_analysis_db_storage import _latest_tdx_export_payload

        exported_at = datetime(2026, 5, 7, 10, 30)
        row = (
            12,
            exported_at,
            "2026-05-01",
            "2026-05-07",
            r"C:\new_tdx",
            20,
            8,
            3,
            "cache",
            "cache.json",
            '["backup.blk"]',
        )
        blocks = [
            {"skipped_companies": ["B", "A"]},
            {"skipped_companies": ["A", ""]},
        ]

        payload = _latest_tdx_export_payload(row, blocks)

        self.assertEqual(12, payload["export_id"])
        self.assertEqual(exported_at.isoformat(), payload["exported_at"])
        self.assertEqual("2026-05-01", payload["start_date"])
        self.assertEqual("2026-05-07", payload["end_date"])
        self.assertEqual(r"C:\new_tdx", payload["tdx_root"])
        self.assertEqual(20, payload["ranking_top_n"])
        self.assertEqual(8, payload["total_written"])
        self.assertEqual(3, payload["unresolved_count"])
        self.assertEqual(["A", "B"], payload["unresolved_companies"])
        self.assertEqual("cache", payload["stock_basic_source"])
        self.assertEqual("cache.json", payload["source_detail"])
        self.assertEqual(["backup.blk"], payload["backup_files"])
        self.assertEqual(blocks, payload["blocks"])

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_a_share_table_refs_use_core_schema_except_stock_basic(self):
        from backend.services import a_share_analysis_db_storage as storage

        self.assertEqual('"zsxq_core"."zsxq_a_share_daily_mentions"', storage._core_table_ref(storage.DAILY_MENTIONS_TABLE))
        self.assertEqual(
            '"zsxq_core"."zsxq_a_share_topic_stock_extractions"',
            storage._core_table_ref(storage.TOPIC_STOCK_EXTRACTIONS_TABLE),
        )
        self.assertEqual('"public"."stock_basic"', storage._public_table_ref(storage.STOCK_BASIC_TABLE))

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_parse_json_list_handles_invalid_values(self):
        from backend.services import a_share_analysis_db_storage as storage

        self.assertEqual(["算力"], storage._parse_json_list('["算力"]'))
        self.assertEqual([], storage._parse_json_list("not json"))
        self.assertEqual([], storage._parse_json_list({"bad": "shape"}))

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_backfill_sql_targets_core_from_public_sources(self):
        from scripts.backfill_a_share_analysis_to_core import build_backfill_sql

        sql = "\n".join(build_backfill_sql())

        self.assertIn('"zsxq_core"."zsxq_a_share_daily_mentions"', sql)
        self.assertIn('"public"."zsxq_a_share_daily_mentions"', sql)
        self.assertIn("ON CONFLICT (group_id, mention_date, company)", sql)
        self.assertIn('"zsxq_core"."zsxq_a_share_tdx_exports"', sql)

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_analysis_write_dsn_requires_zsxq_database(self):
        from backend.services import a_share_analysis_db_storage as storage

        with patch.object(storage, "get_zsxq_postgres_dsn", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "ZSXQ_POSTGRES_DSN"):
                storage.get_postgres_dsn()

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_stock_basic_dsn_can_use_knowaction_read_source(self):
        from backend.services import a_share_analysis_db_storage as storage

        env_values = {
            "DB_HOST": "localhost",
            "DB_PORT": "5433",
            "DB_NAME": "market",
            "DB_USER": "reader",
            "DB_PASSWORD": "pw",
        }
        with patch.object(storage, "get_zsxq_postgres_dsn", return_value=None), patch.object(
            storage, "_load_env_file", return_value=env_values
        ):
            self.assertEqual(
                "dbname=market user=reader password=pw host=localhost port=5433",
                storage.get_stock_basic_postgres_dsn(),
            )

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_ensure_analysis_tables_is_runtime_noop(self):
        from backend.services import a_share_analysis_db_storage as storage

        with patch.object(storage, "get_connection") as get_connection:
            self.assertIsNone(storage.ensure_analysis_tables())

        get_connection.assert_not_called()

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_get_connection_wraps_missing_schema_errors(self):
        from psycopg2 import errors

        from backend.services import a_share_analysis_db_storage as storage

        class FakeConnection:
            def __init__(self):
                self.rolled_back = False
                self.closed = False

            def rollback(self):
                self.rolled_back = True

            def close(self):
                self.closed = True

        conn = FakeConnection()

        with patch.object(storage.psycopg2, "connect", return_value=conn):
            with self.assertRaisesRegex(RuntimeError, "manage-postgres-core-schema --apply"):
                with storage.get_connection():
                    raise errors.UndefinedTable("missing")

        self.assertTrue(conn.rolled_back)
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
