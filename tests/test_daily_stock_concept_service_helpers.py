import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_STOCK_CONCEPT_DEPS = find_spec("openai") is not None


class DailyStockConceptServiceHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_parse_stock_concept_output_matches_stock_basic(self):
        from backend.services.daily_stock_concept_payload import build_stock_lookup, parse_stock_concept_output

        lookup = build_stock_lookup(
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

        stocks = parse_stock_concept_output(message, stock_lookup=lookup)

        self.assertEqual(1, len(stocks))
        self.assertEqual("宁德时代", stocks[0]["stock_name"])
        self.assertEqual("300750", stocks[0]["stock_code"])
        self.assertEqual("SZ", stocks[0]["market"])
        self.assertEqual(["固态电池", "储能"], stocks[0]["concepts"])
        self.assertGreaterEqual(stocks[0]["confidence"], 0.7)

    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_parse_stock_concept_output_keeps_unmatched_with_lower_confidence(self):
        from backend.services.daily_stock_concept_payload import parse_stock_concept_output

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

        stocks = parse_stock_concept_output(str(message).replace("'", '"'), stock_lookup={})

        self.assertEqual(1, len(stocks))
        self.assertEqual("未知公司", stocks[0]["stock_name"])
        self.assertEqual("", stocks[0]["stock_code"])
        self.assertLessEqual(stocks[0]["confidence"], 0.5)

    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_parse_stock_concept_output_handles_invalid_json(self):
        from backend.services.daily_stock_concept_payload import parse_stock_concept_output

        self.assertEqual([], parse_stock_concept_output("not json", stock_lookup={}))

    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_generate_stock_concepts_with_ai_rejects_invalid_json(self):
        from backend.services import daily_stock_concept_service as service
        from backend.services.ai_runtime_request import AIRuntimeTextResult

        with (
            patch.object(
                service,
                "get_openai_compatible_config",
                return_value={
                    "api_key": "test-key",
                    "model": "test-model",
                    "base_url": "http://test",
                    "wire_api": "responses",
                },
            ),
            patch.object(service, "call_runtime_ai_text", return_value=AIRuntimeTextResult("not json", "test-model")),
        ):
            with self.assertRaisesRegex(RuntimeError, "AI 股票概念抽取结果不是合法 JSON"):
                service._generate_stock_concepts_with_ai("topic payload", "2026-05-20")

    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_aggregate_topic_stock_extractions_merges_concepts_topics_and_confidence(self):
        from backend.services.daily_stock_concept_payload import aggregate_topic_stock_extractions, build_stock_lookup

        lookup = build_stock_lookup(
            [
                {"ts_code": "300750.SZ", "symbol": "300750", "name": "宁德时代"},
            ]
        )
        rows = [
            {
                "topic_id": "101",
                "stock_name": "宁德时代",
                "concepts": ["固态电池"],
                "reason": "提到固态电池。",
                "confidence": 0.6,
            },
            {
                "topic_id": "102",
                "stock_name": "宁德时代",
                "concepts": ["储能", "固态电池"],
                "reason": "提到储能。",
                "confidence": 0.8,
            },
        ]

        stocks = aggregate_topic_stock_extractions(rows, stock_lookup=lookup)

        self.assertEqual(1, len(stocks))
        self.assertEqual("宁德时代", stocks[0]["stock_name"])
        self.assertEqual("300750", stocks[0]["stock_code"])
        self.assertEqual("SZ", stocks[0]["market"])
        self.assertEqual(["锂电/电池", "储能"], stocks[0]["concepts"])
        self.assertEqual(["101", "102"], stocks[0]["topic_ids"])
        self.assertEqual(0.8, stocks[0]["confidence"])
        self.assertIn("提到固态电池", stocks[0]["reason"])
        self.assertIn("提到储能", stocks[0]["reason"])

    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_aggregate_topic_stock_extractions_normalizes_aliases_and_keeps_signals(self):
        from backend.services.daily_stock_concept_payload import aggregate_topic_stock_extractions

        rows = [
            {
                "topic_id": "201",
                "stock_name": "沪电股份",
                "concepts": ["PCB钻针", "PCB", "涨价", "未知细分"],
                "reason": "提到PCB钻针涨价。",
                "confidence": 0.7,
            },
        ]

        stocks = aggregate_topic_stock_extractions(rows, stock_lookup={})

        self.assertEqual(1, len(stocks))
        self.assertEqual(["PCB", "涨价/供需", "未知细分"], stocks[0]["concepts"])
        self.assertEqual(["201"], stocks[0]["topic_ids"])

    @unittest.skipUnless(HAS_STOCK_CONCEPT_DEPS, "daily stock concept service dependencies are not installed")
    def test_extract_daily_stock_concepts_uses_material_snapshot_payload_for_ai_fallback(self):
        from datetime import date
        from types import SimpleNamespace
        from unittest.mock import Mock

        from backend.services import daily_stock_concept_service as service

        conn = Mock()
        material = SimpleNamespace(
            topics=[{"topic_id": "101", "talk_text": "body"}],
            topic_count=1,
            prompt_payload="snapshot payload",
        )
        stocks = [
            {
                "stock_name": "宁德时代",
                "stock_code": "300750",
                "market": "SZ",
                "concepts": ["储能"],
                "reason": "topic 101",
                "topic_ids": ["101"],
                "confidence": 0.8,
            }
        ]

        with (
            patch.object(service, "connect_topic_material_db", return_value=conn),
            patch.object(service, "load_daily_topic_material", return_value=material) as load_material,
            patch.object(service, "load_topic_stock_extractions", return_value=[]),
            patch.object(service, "_generate_stock_concepts_with_ai", return_value=(stocks, "model-a")) as generate,
            patch.object(service, "_save_stock_concepts") as save_stock_concepts,
        ):
            result = service.extract_daily_stock_concepts("303", "2026-05-07", comments_per_topic=5)

        load_material.assert_called_once_with(
            "303",
            report_date=date(2026, 5, 7),
            comments_per_topic=5,
        )
        generate.assert_called_once_with("snapshot payload", "2026-05-07")
        save_stock_concepts.assert_called_once_with(
            conn,
            group_id="303",
            report_date="2026-05-07",
            stocks=stocks,
            model="model-a",
            status="completed",
        )
        conn.close.assert_called_once_with()
        self.assertEqual(stocks, result["stocks"])


if __name__ == "__main__":
    unittest.main()
