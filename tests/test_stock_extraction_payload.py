import unittest

from backend.services.stock_extraction_payload import (
    build_stock_lookup,
    match_stock,
    normalize_stock_name,
    safe_confidence,
    safe_text_list,
)


class StockExtractionPayloadTests(unittest.TestCase):
    def test_build_stock_lookup_matches_full_and_normalized_names(self):
        lookup = build_stock_lookup(
            [
                {"ts_code": "300750.SZ", "symbol": "300750", "name": "宁德时代股份有限公司"},
            ]
        )

        self.assertEqual("宁德时代股份有限公司", match_stock("宁德时代", lookup)["stock_name"])
        self.assertEqual("300750", match_stock("宁德时代股份有限公司", lookup)["stock_code"])
        self.assertEqual("SZ", match_stock("宁德时代", lookup)["market"])

    def test_safe_confidence_clamps_invalid_and_out_of_range_values(self):
        self.assertEqual(0.0, safe_confidence("bad"))
        self.assertEqual(0.0, safe_confidence(-1))
        self.assertEqual(1.0, safe_confidence(2))
        self.assertEqual(0.42, safe_confidence("0.42"))

    def test_safe_text_list_preserves_daily_and_a_share_dedupe_policies(self):
        long_a = "A" * 81
        long_b = "A" * 80 + "B"

        self.assertEqual([long_a[:80], long_b[:80]], safe_text_list([long_a, long_b]))
        self.assertEqual(
            [long_a[:80]],
            safe_text_list([long_a, long_b], dedupe_after_truncate=True),
        )
        self.assertEqual(["机器人"], safe_text_list([" 机器人 ", "", "机器人"]))

    def test_normalize_stock_name_removes_company_suffixes(self):
        self.assertEqual("宁德时代", normalize_stock_name("宁德时代股份有限公司"))


if __name__ == "__main__":
    unittest.main()
