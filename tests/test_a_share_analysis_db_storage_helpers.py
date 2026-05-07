import unittest
from datetime import datetime
from importlib.util import find_spec


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


if __name__ == "__main__":
    unittest.main()
