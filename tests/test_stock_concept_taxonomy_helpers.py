import unittest


class StockConceptTaxonomyHelperTests(unittest.TestCase):
    def test_normalize_stock_concept_term_maps_industry_concept(self):
        from backend.services.stock_concept_taxonomy import normalize_stock_concept_term

        self.assertEqual(("concept", "PCB"), normalize_stock_concept_term("PCB钻针"))

    def test_normalize_stock_concept_term_maps_signal_tag(self):
        from backend.services.stock_concept_taxonomy import normalize_stock_concept_term

        self.assertEqual(("signal", "涨价/供需"), normalize_stock_concept_term("供需紧张"))

    def test_normalize_stock_concept_terms_preserves_raw_and_unmapped(self):
        from backend.services.stock_concept_taxonomy import normalize_stock_concept_terms

        result = normalize_stock_concept_terms(["PCB钻针", "供需紧张", "未知细分"])

        self.assertEqual(["PCB"], result["industry_concepts"][:1])
        self.assertIn("未知细分", result["industry_concepts"])
        self.assertEqual(["涨价/供需"], result["signal_tags"])
        self.assertEqual(["PCB钻针", "供需紧张", "未知细分"], result["raw_terms"])
        self.assertEqual(["未知细分"], result["unmapped_terms"])


if __name__ == "__main__":
    unittest.main()
