import unittest
from importlib.util import find_spec


HAS_STOCK_CONCEPT_DEPS = find_spec("openai") is not None


class DailyStockConceptServiceHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_parse_stock_concept_output_matches_stock_basic(self):
        from backend.services.daily_stock_concept_service import _build_stock_lookup, _parse_stock_concept_output

        lookup = _build_stock_lookup(
            [
                {"ts_code": "300750.SZ", "symbol": "300750", "name": "宁德时代"},
            ]
        )
        message = """
        {
          "stocks": [
            {
              "stock_name": "宁德时代",
              "stock_code": "",
              "market": "",
              "concepts": ["固态电池", "储能"],
              "reason": "话题讨论电池产业链。",
              "topic_ids": ["101"],
              "confidence": 0.5
            }
          ]
        }
        """

        stocks = _parse_stock_concept_output(message, stock_lookup=lookup)

        self.assertEqual(1, len(stocks))
        self.assertEqual("宁德时代", stocks[0]["stock_name"])
        self.assertEqual("300750", stocks[0]["stock_code"])
        self.assertEqual("SZ", stocks[0]["market"])
        self.assertEqual(["固态电池", "储能"], stocks[0]["concepts"])
        self.assertGreaterEqual(stocks[0]["confidence"], 0.7)

    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_parse_stock_concept_output_keeps_unmatched_with_lower_confidence(self):
        from backend.services.daily_stock_concept_service import _parse_stock_concept_output

        message = {
            "stocks": [
                {
                    "stock_name": "未知公司",
                    "stock_code": "",
                    "market": "",
                    "concepts": ["机器人"],
                    "reason": "仅上下文提到。",
                    "topic_ids": [202],
                    "confidence": 0.9,
                }
            ]
        }

        stocks = _parse_stock_concept_output(str(message).replace("'", '"'), stock_lookup={})

        self.assertEqual(1, len(stocks))
        self.assertEqual("未知公司", stocks[0]["stock_name"])
        self.assertEqual("", stocks[0]["stock_code"])
        self.assertLessEqual(stocks[0]["confidence"], 0.5)

    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_parse_stock_concept_output_handles_invalid_json(self):
        from backend.services.daily_stock_concept_service import _parse_stock_concept_output

        self.assertEqual([], _parse_stock_concept_output("not json", stock_lookup={}))


if __name__ == "__main__":
    unittest.main()
