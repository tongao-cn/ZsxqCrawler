import unittest
from pathlib import Path

from backend.services.tdx_a_share_export_service import (
    DEFAULT_TDX_EXPORT_SPECS,
    DEFAULT_TDX_EXPORT_WINDOWS,
    _build_block_export_result,
    _build_export_block_name,
    _build_export_result,
    _build_pending_block_write,
    _build_ranking_block_name,
    _collect_ranking_companies,
    _ensure_tdx_cfg_records,
    _next_tdx_block_code,
    _normalize_tdx_code,
    resolve_company_codes,
)


class TdxAShareExportServiceHelperTests(unittest.TestCase):
    def test_build_ranking_block_name_uses_group_prefix_without_recommendation_pool_suffix(self):
        self.assertEqual(_build_ranking_block_name(3, "纪要又要"), "纪要又要-3日")

    def test_build_ranking_block_name_keeps_legacy_name_without_group_name(self):
        self.assertEqual(_build_ranking_block_name(3), "3日推荐池")
        self.assertEqual(_build_ranking_block_name(30), "30日推荐池")

    def test_default_tdx_export_uses_coverage_pool_specs(self):
        self.assertEqual(((30, 300), (14, 150), (7, 100)), DEFAULT_TDX_EXPORT_SPECS)
        self.assertEqual((30, 14, 7), DEFAULT_TDX_EXPORT_WINDOWS)

    def test_build_export_block_name_includes_top_n(self):
        self.assertEqual(_build_export_block_name(30, 300, "纪要又要"), "纪要又要-30日Top300")
        self.assertEqual(_build_export_block_name(14, 150), "14日Top150")

    def test_next_tdx_block_code_uses_next_available_zx_number(self):
        records = [
            {"name": "已有1", "code": "ZX001"},
            {"name": "已有2", "code": "ZX009"},
            {"name": "其他", "code": "OTHER"},
        ]

        self.assertEqual("ZX010", _next_tdx_block_code(records))

    def test_ensure_tdx_cfg_records_creates_missing_blocks(self):
        records = [
            {"name": "纪要又要-30日", "code": "ZX001"},
        ]

        cfg_by_name, created_records = _ensure_tdx_cfg_records(
            records,
            ["纪要又要-30日", "纪要又要-7日", "纪要又要-14日"],
        )

        self.assertEqual(
            created_records,
            [
                {"name": "纪要又要-7日", "code": "ZX002"},
                {"name": "纪要又要-14日", "code": "ZX003"},
            ],
        )
        self.assertEqual(cfg_by_name["纪要又要-30日"]["code"], "ZX001")
        self.assertEqual(cfg_by_name["纪要又要-7日"]["code"], "ZX002")
        self.assertEqual(cfg_by_name["纪要又要-14日"]["code"], "ZX003")
        self.assertEqual(records, [
            {"name": "纪要又要-30日", "code": "ZX001"},
            {"name": "纪要又要-7日", "code": "ZX002"},
            {"name": "纪要又要-14日", "code": "ZX003"},
        ])

    def test_collect_ranking_companies_preserves_existing_filtering(self):
        rankings = {
            "3": [
                {"company": " 平安银行 "},
                {"company": ""},
                {"company": None},
                {},
            ],
            "7": [
                {"company": "万科A"},
            ],
        }

        self.assertEqual(_collect_ranking_companies(rankings, [3, 7]), ["平安银行", "万科A"])

    def test_resolve_company_codes_handles_a_share_name_markers_and_short_names(self):
        records = [
            {"ts_code": "688702.SH", "name": "盛科通信-U"},
            {"ts_code": "688387.SH", "name": "信科移动-U"},
            {"ts_code": "688498.SH", "name": "DR源杰科"},
            {"ts_code": "603083.SH", "name": "XD剑桥科"},
            {"ts_code": "603228.SH", "name": "XD景旺电"},
        ]

        resolved, unresolved, ambiguous = resolve_company_codes(
            ["盛科通信", "信科移动", "源杰科技", "剑桥科技", "景旺电子"],
            records,
        )

        self.assertEqual(
            resolved,
            {
                "盛科通信": "688702.SH",
                "信科移动": "688387.SH",
                "源杰科技": "688498.SH",
                "剑桥科技": "603083.SH",
                "景旺电子": "603228.SH",
            },
        )
        self.assertEqual([], unresolved)
        self.assertEqual({}, ambiguous)

    def test_normalize_tdx_code_supports_beijing_market(self):
        self.assertEqual("2920522", _normalize_tdx_code("920522.BJ"))

    def test_build_pending_block_write_converts_and_dedupes_codes_and_skips(self):
        rankings = {
            "3": [
                {"company": "平安银行"},
                {"company": "招商银行"},
                {"company": "平安银行"},
                {"company": "未知公司"},
                {"company": "坏代码"},
                {"company": " "},
            ]
        }
        resolved_codes = {
            "平安银行": "000001.SZ",
            "招商银行": "600036.SH",
            "坏代码": "123456.HK",
        }
        cfg_by_name = {
            "纪要又要-3日Top100": {
                "name": "纪要又要-3日Top100",
                "code": "ZX001",
            }
        }

        pending = _build_pending_block_write(
            3,
            100,
            rankings,
            resolved_codes,
            cfg_by_name,
            Path("blocknew"),
            "纪要又要",
        )

        self.assertEqual(
            pending,
            (
                3,
                "纪要又要-3日Top100",
                "ZX001",
                Path("blocknew") / "ZX001.blk",
                ["0000001", "1600036"],
                ["未知公司", "坏代码"],
            ),
        )

    def test_build_block_export_result_keeps_response_shape(self):
        result = _build_block_export_result(
            7,
            "7日推荐池",
            "ZX007",
            Path("blocknew") / "ZX007.blk",
            ["0000001"],
            ["未知公司"],
        )

        self.assertEqual(
            result,
            {
                "window_days": 7,
                "block_name": "7日推荐池",
                "block_code": "ZX007",
                "block_path": str(Path("blocknew") / "ZX007.blk"),
                "written_count": 1,
                "skipped_count": 1,
                "skipped_companies": ["未知公司"],
            },
        )

    def test_build_export_result_keeps_response_shape_and_dedupes_unresolved(self):
        block_results = [
            {
                "window_days": 3,
                "block_name": "3日推荐池",
                "block_code": "ZX001",
                "block_path": "blocknew/ZX001.blk",
                "written_count": 1,
                "skipped_count": 0,
                "skipped_companies": [],
            }
        ]

        result = _build_export_result(
            normalized_group_id="group-1",
            resolved_root=Path("tdx-root"),
            chart_payload={
                "selected_start_date": "2026-01-01",
                "selected_end_date": "2026-01-31",
            },
            ranking_top_n=20,
            stock_basic_source="cache",
            source_detail="cache.json",
            backup_files=["backup/ZX001.blk"],
            block_results=block_results,
            total_written=1,
            aggregate_skipped=["未知公司", "未知公司", "另一个未知"],
            ambiguous_companies={"重名": ["000001.SZ", "000002.SZ"]},
            effective_export_id=123,
        )

        self.assertEqual(result["group_id"], "group-1")
        self.assertEqual(result["tdx_root"], str(Path("tdx-root")))
        self.assertEqual(result["selected_start_date"], "2026-01-01")
        self.assertEqual(result["selected_end_date"], "2026-01-31")
        self.assertEqual(result["ranking_top_n"], 20)
        self.assertTrue(result["used_stock_cache"])
        self.assertEqual(result["stock_basic_source"], "cache")
        self.assertEqual(result["stock_cache_path"], "cache.json")
        self.assertEqual(result["backup_files"], ["backup/ZX001.blk"])
        self.assertEqual(result["blocks"], block_results)
        self.assertEqual(result["total_written"], 1)
        self.assertEqual(result["unresolved_companies"], ["未知公司", "另一个未知"])
        self.assertEqual(result["ambiguous_companies"], {"重名": ["000001.SZ", "000002.SZ"]})
        self.assertEqual(result["export_id"], 123)
        self.assertIsInstance(result["exported_at"], str)


if __name__ == "__main__":
    unittest.main()
