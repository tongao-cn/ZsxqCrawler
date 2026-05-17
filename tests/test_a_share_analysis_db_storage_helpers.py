import unittest
from datetime import datetime
from importlib.util import find_spec
from unittest.mock import patch
from contextlib import contextmanager


HAS_STORAGE_DEPS = find_spec("psycopg2") is not None


class _FakeStorageCursor:
    def __init__(self, fail_on_execute_values_call=None):
        self.executed = []
        self.execute_values_calls = []
        self.fail_on_execute_values_call = fail_on_execute_values_call
        self.fetchall_rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.fetchall_rows


class _FakeStorageConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _fake_execute_values(cursor, sql, rows, template=None):
    cursor.execute_values_calls.append((sql, list(rows), template))
    if cursor.fail_on_execute_values_call == len(cursor.execute_values_calls):
        raise RuntimeError("boom")


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

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_checkpoint_upserts_mentions_and_state_without_delete(self):
        from backend.services import a_share_analysis_db_storage as storage

        cursor = _FakeStorageCursor()
        conn = _FakeStorageConnection(cursor)

        @contextmanager
        def fake_connection(env_path=storage.DEFAULT_KNOW_ACTION_ENV_PATH):
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        with patch.object(storage, "get_connection", fake_connection), patch.object(
            storage, "execute_values", side_effect=_fake_execute_values
        ):
            result = storage.save_recommendation_pool_checkpoint(
                daily_delta={"2026-05-10": {"宁德时代": 2}},
                processed_keys=["topics:1001:2026-05-10"],
                topic_stock_extractions=[
                    {
                        "group_id": "511",
                        "topic_id": "1001",
                        "topic_date": "2026-05-10",
                        "stock_name": "宁德时代",
                        "concepts": ["电池"],
                        "excerpt": "原文关键证据",
                        "reason": "提到电池。",
                    }
                ],
                group_id="511",
            )

        self.assertEqual({"daily_mentions": 1, "topic_stock_extractions": 1, "processed_state": 1}, result)
        joined_sql = "\n".join(call[0] for call in cursor.execute_values_calls)
        self.assertIn("ON CONFLICT (group_id, mention_date, company)", joined_sql)
        self.assertIn("mentions_count = \"zsxq_core\".\"zsxq_a_share_daily_mentions\".mentions_count + excluded.mentions_count", joined_sql)
        self.assertIn("ON CONFLICT (group_id, source, topic_id, day) DO UPDATE SET", joined_sql)
        self.assertIn("excerpt", joined_sql)
        self.assertNotIn("DELETE FROM", joined_sql)
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_save_topic_stock_extractions_uses_excerpt_column(self):
        from backend.services import a_share_analysis_db_storage as storage

        cursor = _FakeStorageCursor()
        conn = _FakeStorageConnection(cursor)

        @contextmanager
        def fake_connection(env_path=storage.DEFAULT_KNOW_ACTION_ENV_PATH):
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        with patch.object(storage, "get_connection", fake_connection), patch.object(
            storage, "execute_values", side_effect=_fake_execute_values
        ):
            result = storage.save_topic_stock_extractions(
                [
                    {
                        "group_id": "511",
                        "topic_id": "1001",
                        "topic_date": "2026-05-10",
                        "stock_name": "钧达股份",
                        "stock_code": "",
                        "market": "",
                        "concepts": ["商业航天"],
                        "excerpt": "原文证据",
                        "reason": "推荐逻辑。",
                        "confidence": 0.98,
                        "model": "test-model",
                        "prompt_version": "v1",
                    }
                ],
                group_id="511",
            )

        self.assertEqual(1, result)
        sql, rows, template = cursor.execute_values_calls[0]
        self.assertIn("excerpt", sql)
        self.assertEqual(13, len(rows[0]))
        self.assertEqual("(%s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", template)
        self.assertTrue(conn.committed)

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_checkpoint_rolls_back_when_any_write_fails(self):
        from backend.services import a_share_analysis_db_storage as storage

        cursor = _FakeStorageCursor(fail_on_execute_values_call=2)
        conn = _FakeStorageConnection(cursor)

        @contextmanager
        def fake_connection(env_path=storage.DEFAULT_KNOW_ACTION_ENV_PATH):
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        with patch.object(storage, "get_connection", fake_connection), patch.object(
            storage, "execute_values", side_effect=_fake_execute_values
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                storage.save_recommendation_pool_checkpoint(
                    daily_delta={"2026-05-10": {"宁德时代": 2}},
                    processed_keys=["topics:1001:2026-05-10"],
                    topic_stock_extractions=[
                        {
                            "group_id": "511",
                            "topic_id": "1001",
                            "topic_date": "2026-05-10",
                            "stock_name": "宁德时代",
                            "excerpt": "原文关键证据",
                            "reason": "提到电池。",
                        }
                    ],
                    group_id="511",
                )

        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_load_topic_stock_extractions_includes_excerpt(self):
        from backend.services import a_share_analysis_db_storage as storage

        conn = _FakeStorageConnection(_FakeStorageCursor())
        conn.cursor_obj.fetchall = lambda: [
            (
                "511",
                "1001",
                datetime(2026, 5, 10),
                "宁德时代",
                "",
                "",
                '["电池"]',
                "原文关键证据",
                "提到电池。",
                0.8,
                "test-model",
                "v1",
                datetime(2026, 5, 10, 10, 0, 0),
            )
        ]

        @contextmanager
        def fake_connection(env_path=storage.DEFAULT_KNOW_ACTION_ENV_PATH):
            yield conn

        with patch.object(storage, "get_connection", fake_connection):
            rows = storage.load_topic_stock_extractions(group_id="511")

        self.assertEqual("原文关键证据", rows[0]["excerpt"])
        self.assertEqual("提到电池。", rows[0]["reason"])

    @unittest.skipUnless(HAS_STORAGE_DEPS, "PostgreSQL storage dependencies are not installed")
    def test_reset_a_share_analysis_range_deletes_recommendation_and_analysis_rows(self):
        from backend.services import a_share_analysis_db_storage as storage

        cursor = _FakeStorageCursor()
        cursor.fetchall_rows = [("1001",), ("1002",)]
        conn = _FakeStorageConnection(cursor)

        @contextmanager
        def fake_connection(env_path=storage.DEFAULT_KNOW_ACTION_ENV_PATH):
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        with patch.object(storage, "get_connection", fake_connection):
            result = storage.reset_a_share_analysis_range("2026-05-01", "2026-05-07", group_id="511")

        self.assertEqual(
            {"daily_mentions": 0, "processed_state": 0, "topic_stock_extractions": 0, "stock_topic_processed_states": 0, "stock_topic_analyses": 0},
            result,
        )
        joined_sql = "\n".join(sql for sql, _params in cursor.executed)
        self.assertIn("DELETE FROM", joined_sql)
        self.assertIn("zsxq_a_share_topic_stock_extractions", joined_sql)
        self.assertIn("stock_topic_processed_states", joined_sql)
        self.assertIn("stock_topic_analyses", joined_sql)
        self.assertIn("SELECT DISTINCT topic_id", joined_sql)
        self.assertIn("topic_id = ANY", joined_sql)
        self.assertIn("?|", joined_sql)
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)


if __name__ == "__main__":
    unittest.main()
