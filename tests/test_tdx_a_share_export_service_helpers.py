import unittest
from pathlib import Path

from backend.services.tdx_a_share_export_plan import (
    DEFAULT_TDX_EXPORT_SPECS,
    DEFAULT_TDX_EXPORT_WINDOWS,
    TdxBlock,
    build_block_export_result,
    build_export_block_name,
    build_pending_block_sync,
    build_ranking_block_name,
    build_tdx_export_plan,
    build_tdx_export_ranking_selection,
    collect_ranking_companies,
    ensure_tdx_api_blocks,
    next_tdx_block_code,
    normalize_tdx_api_code,
)
from backend.services.tdx_a_share_export_service import (
    TdxBlockClient,
    _build_export_result,
    resolve_company_codes,
)


class TdxAShareExportServiceHelperTests(unittest.TestCase):
    def test_build_ranking_block_name_uses_group_prefix_without_recommendation_pool_suffix(self):
        self.assertEqual(build_ranking_block_name(3, "纪要又要"), "纪要又要-3日")

    def test_build_ranking_block_name_keeps_legacy_name_without_group_name(self):
        self.assertEqual(build_ranking_block_name(3), "3日推荐池")
        self.assertEqual(build_ranking_block_name(30), "30日推荐池")

    def test_default_tdx_export_uses_coverage_pool_specs(self):
        self.assertEqual(((30, 300), (14, 150), (7, 100)), DEFAULT_TDX_EXPORT_SPECS)
        self.assertEqual((30, 14, 7), DEFAULT_TDX_EXPORT_WINDOWS)

    def test_build_export_block_name_includes_top_n(self):
        self.assertEqual(build_export_block_name(30, 300, "纪要又要"), "纪要又要-30日Top300")
        self.assertEqual(build_export_block_name(14, 150), "14日Top150")

    def test_next_tdx_block_code_uses_next_available_zx_number(self):
        records = [
            {"name": "已有1", "code": "ZX001"},
            {"name": "已有2", "code": "ZX009"},
            {"name": "其他", "code": "OTHER"},
        ]

        self.assertEqual("ZX010", next_tdx_block_code(records))

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

        self.assertEqual(collect_ranking_companies(rankings, [3, 7]), ["平安银行", "万科A"])

    def test_resolve_company_codes_handles_a_share_name_markers_and_short_names(self):
        records = [
            {"ts_code": "688702.SH", "name": "盛科通信-U"},
            {"ts_code": "688387.SH", "name": "信科移动-U"},
            {"ts_code": "688498.SH", "name": "DR源杰科"},
            {"ts_code": "603083.SH", "name": "XD剑桥科"},
            {"ts_code": "603228.SH", "name": "XD景旺电"},
            {"ts_code": "000725.SZ", "name": "京东方Ａ"},
            {"ts_code": "301550.SZ", "name": "斯菱智驱"},
        ]

        resolved, unresolved, ambiguous = resolve_company_codes(
            ["盛科通信", "信科移动", "源杰科技", "剑桥科技", "景旺电子", "京东方A", "斯菱股份"],
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
                "京东方A": "000725.SZ",
                "斯菱股份": "301550.SZ",
            },
        )
        self.assertEqual([], unresolved)
        self.assertEqual({}, ambiguous)

    def test_normalize_tdx_api_code_keeps_official_code_shape(self):
        self.assertEqual("000001.SZ", normalize_tdx_api_code("000001.sz"))
        self.assertEqual("920522.BJ", normalize_tdx_api_code("920522.BJ"))

    def test_ensure_tdx_api_blocks_reuses_names_and_allocates_next_zx(self):
        cfg_by_name, created_records = ensure_tdx_api_blocks(
            [
                TdxBlock(code="ZX001", name="已有"),
                TdxBlock(code="ZX009", name="纪要又要-30日Top300"),
            ],
            ["纪要又要-30日Top300", "纪要又要-7日Top100"],
        )

        self.assertEqual(cfg_by_name["纪要又要-30日Top300"]["code"], "ZX009")
        self.assertEqual(cfg_by_name["纪要又要-7日Top100"]["code"], "ZX010")
        self.assertEqual(created_records, [{"name": "纪要又要-7日Top100", "code": "ZX010"}])

    def test_build_pending_block_sync_uses_official_api_codes(self):
        rankings = {
            "3": [
                {"company": "平安银行"},
                {"company": "招商银行"},
                {"company": "平安银行"},
                {"company": "坏代码"},
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

        pending = build_pending_block_sync(
            3,
            100,
            rankings,
            resolved_codes,
            cfg_by_name,
            "纪要又要",
        )

        self.assertEqual(pending.window, 3)
        self.assertEqual(pending.block_name, "纪要又要-3日Top100")
        self.assertEqual(pending.block_code, "ZX001")
        self.assertEqual(pending.block_path, "tdx-api://ZX001")
        self.assertEqual(pending.converted_codes, ("000001.SZ", "600036.SH"))
        self.assertEqual(pending.skipped_companies, ("坏代码",))

    def test_build_tdx_export_plan_slices_rankings_and_allocates_missing_blocks(self):
        selection = build_tdx_export_ranking_selection(
            {
                "3": [
                    {"company": "平安银行"},
                    {"company": "招商银行"},
                    {"company": "超出TopN"},
                ]
            },
            ((3, 2),),
        )

        plan = build_tdx_export_plan(
            selection=selection,
            export_specs=((3, 2),),
            resolved_codes={
                "平安银行": "000001.SZ",
                "招商银行": "600036.SH",
                "超出TopN": "300000.SZ",
            },
            existing_blocks=[TdxBlock(code="ZX009", name="已有")],
            group_name="纪要又要",
        )

        self.assertEqual(selection.companies, ("平安银行", "招商银行"))
        self.assertEqual(plan.expected_block_names, ("纪要又要-3日Top2",))
        self.assertEqual(plan.created_cfg_records, ({"name": "纪要又要-3日Top2", "code": "ZX010"},))
        self.assertEqual(len(plan.pending_writes), 1)
        self.assertEqual(plan.pending_writes[0].block_code, "ZX010")
        self.assertEqual(plan.pending_writes[0].converted_codes, ("000001.SZ", "600036.SH"))

    def test_build_block_export_result_keeps_response_shape(self):
        result = build_block_export_result(
            7,
            "7日推荐池",
            "ZX007",
            "tdx-api://ZX007",
            ["000001.SZ"],
            ["未知公司"],
        )

        self.assertEqual(
            result,
            {
                "window_days": 7,
                "block_name": "7日推荐池",
                "block_code": "ZX007",
                "block_path": "tdx-api://ZX007",
                "written_count": 1,
                "skipped_count": 1,
                "skipped_companies": ["未知公司"],
            },
        )

    def test_build_block_export_result_can_include_verified_count(self):
        result = build_block_export_result(
            7,
            "7日推荐池",
            "ZX007",
            "tdx-api://ZX007",
            ["000001.SZ"],
            [],
            verified_count=1,
        )

        self.assertEqual(result["block_path"], "tdx-api://ZX007")
        self.assertEqual(result["verified_count"], 1)

    def test_tdx_block_client_replaces_block_stocks_through_official_api(self):
        class FakeTq:
            def __init__(self):
                self.sectors = []
                self.sent = []
                self.cleared = []

            def get_user_sector(self):
                return self.sectors

            def create_sector(self, *, block_code, block_name):
                self.sectors.append({"Code": block_code, "Name": block_name})
                return {"ErrorId": 0}

            def clear_sector(self, *, block_code):
                self.cleared.append(block_code)
                return {"ErrorId": 0}

            def send_user_block(self, *, block_code, stocks, show):
                self.sent.append((block_code, stocks, show))
                return {"ErrorId": 0}

        fake_tq = FakeTq()
        client = TdxBlockClient(tq=fake_tq)

        result = client.replace_block_stocks(
            block_code="ZX010",
            block_name="纪要又要-7日Top100",
            ts_codes=["000001.SZ", "000001.SZ", "600036.SH"],
        )

        self.assertEqual(fake_tq.sectors, [{"Code": "ZX010", "Name": "纪要又要-7日Top100"}])
        self.assertEqual(fake_tq.cleared, ["ZX010"])
        self.assertEqual(fake_tq.sent, [("ZX010", ["000001.SZ", "600036.SH"], False)])
        self.assertEqual(result["clear_result"], {"ErrorId": 0})
        self.assertEqual(result["send_result"], {"ErrorId": 0})

    def test_build_export_result_keeps_response_shape_and_dedupes_unresolved(self):
        block_results = [
            {
                "window_days": 3,
                "block_name": "3日推荐池",
                "block_code": "ZX001",
                "block_path": "tdx-api://ZX001",
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
            backup_files=[],
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
        self.assertEqual(result["backup_files"], [])
        self.assertEqual(result["blocks"], block_results)
        self.assertEqual(result["total_written"], 1)
        self.assertEqual(result["unresolved_companies"], ["未知公司", "另一个未知"])
        self.assertEqual(result["ambiguous_companies"], {"重名": ["000001.SZ", "000002.SZ"]})
        self.assertEqual(result["export_id"], 123)
        self.assertIsInstance(result["exported_at"], str)


if __name__ == "__main__":
    unittest.main()
