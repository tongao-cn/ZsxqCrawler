import json
import unittest
from unittest.mock import patch


class ResearchRadarAITests(unittest.TestCase):
    def test_text_stringifies_falsy_values_except_none(self):
        from backend.services.research_radar_ai import _text

        self.assertEqual("0", _text(0))
        self.assertEqual("False", _text(False))
        self.assertEqual("", _text(None))

    def test_candidate_prompt_payload_includes_only_safe_fields_and_dict_evidence_snippets(self):
        from backend.services.research_radar_ai import _candidate_prompt_payload

        payload = _candidate_prompt_payload(
            [
                {
                    "candidate_id": "direction:PCB",
                    "direction": "PCB",
                    "title": "must not leak",
                    "summary": "must not leak",
                    "tier": "strong",
                    "confidence": 0.82,
                    "concepts": ["PCB"],
                    "stocks": [{"name": "沪电股份", "code": "002463", "market": "SZ"}],
                    "catalysts": ["涨价/供需"],
                    "risks": ["must not leak"],
                    "evidence_count": 2,
                    "evidence": [
                        {
                            "topic_id": "101",
                            "source_id": "fallback-must-not-leak",
                            "source_time": "must not leak",
                            "excerpt": "PCB涨价",
                            "support_reason": "讨论提到涨价",
                        },
                        "non-dict must be ignored",
                    ],
                }
            ]
        )

        item = json.loads(payload)[0]
        self.assertEqual(
            {"candidate_id", "direction", "tier", "confidence", "concepts", "stocks", "catalysts", "evidence"},
            set(item.keys()),
        )
        self.assertEqual(
            [{"topic_id": "101", "excerpt": "PCB涨价", "support_reason": "讨论提到涨价"}],
            item["evidence"],
        )

    def test_apply_ai_logic_summaries_keeps_candidate_evidence_and_updates_wording(self):
        from backend.services.research_radar_ai import apply_ai_logic_summaries

        candidates = [
            {
                "candidate_id": "direction:PCB",
                "direction": "PCB",
                "title": "PCB研究信号升温",
                "summary": "old",
                "tier": "strong",
                "confidence": 0.82,
                "concepts": ["PCB"],
                "stocks": [{"name": "沪电股份"}],
                "catalysts": ["涨价/供需"],
                "risks": [],
                "evidence": [{"topic_id": "101", "excerpt": "PCB涨价"}],
                "evidence_count": 1,
            }
        ]
        payload = {
            "logic_items": [
                {
                    "candidate_id": "direction:PCB",
                    "title": "PCB涨价逻辑升温",
                    "summary": "多条讨论把PCB关注度归因于涨价和AI服务器需求。",
                }
            ]
        }
        result = apply_ai_logic_summaries(candidates, payload)
        self.assertEqual("PCB涨价逻辑升温", result[0]["title"])
        self.assertEqual("多条讨论把PCB关注度归因于涨价和AI服务器需求。", result[0]["summary"])
        self.assertEqual("PCB", result[0]["direction"])
        self.assertEqual("strong", result[0]["tier"])
        self.assertEqual(0.82, result[0]["confidence"])
        self.assertEqual(["PCB"], result[0]["concepts"])
        self.assertEqual([{"name": "沪电股份"}], result[0]["stocks"])
        self.assertEqual(["涨价/供需"], result[0]["catalysts"])
        self.assertEqual([], result[0]["risks"])
        self.assertEqual([{"topic_id": "101", "excerpt": "PCB涨价"}], result[0]["evidence"])
        self.assertEqual(1, result[0]["evidence_count"])

    def test_apply_ai_logic_summaries_truncates_wording_updates(self):
        from backend.services.research_radar_ai import apply_ai_logic_summaries

        candidates = [{"candidate_id": "direction:PCB", "title": "old", "summary": "old"}]
        payload = {
            "logic_items": [
                {
                    "candidate_id": "direction:PCB",
                    "title": "题" * 130,
                    "summary": "摘" * 820,
                }
            ]
        }
        result = apply_ai_logic_summaries(candidates, payload)
        self.assertEqual("题" * 120, result[0]["title"])
        self.assertEqual("摘" * 800, result[0]["summary"])

    def test_apply_ai_logic_summaries_ignores_unknown_candidate_ids(self):
        from backend.services.research_radar_ai import apply_ai_logic_summaries

        candidates = [{"candidate_id": "direction:PCB", "title": "old", "summary": "old"}]
        payload = {"logic_items": [{"candidate_id": "direction:机器人", "title": "bad", "summary": "bad"}]}
        result = apply_ai_logic_summaries(candidates, payload)
        self.assertEqual("old", result[0]["title"])
        self.assertEqual("old", result[0]["summary"])

    def test_apply_ai_logic_summaries_ignores_empty_wording_updates(self):
        from backend.services.research_radar_ai import apply_ai_logic_summaries

        candidates = [{"candidate_id": "direction:PCB", "title": "old title", "summary": "old summary"}]
        payload = {"logic_items": [{"candidate_id": "direction:PCB", "title": "  ", "summary": ""}]}
        result = apply_ai_logic_summaries(candidates, payload)
        self.assertEqual("old title", result[0]["title"])
        self.assertEqual("old summary", result[0]["summary"])

    def test_summarize_radar_candidates_calls_structured_ai_object(self):
        from backend.services import research_radar_ai as ai

        candidates = [
            {
                "candidate_id": "direction:PCB",
                "direction": "PCB",
                "title": "PCB研究信号升温",
                "summary": "old",
                "evidence": [{"topic_id": "101", "excerpt": "PCB涨价"}],
            }
        ]
        with patch.object(
            ai,
            "call_structured_ai_object",
            return_value=type(
                "Result",
                (),
                {
                    "payload": {
                        "logic_items": [
                            {
                                "candidate_id": "direction:PCB",
                                "title": "PCB涨价逻辑升温",
                                "summary": "证据显示PCB涨价逻辑被集中讨论。",
                            }
                        ]
                    },
                    "model": "model-a",
                },
            )(),
        ) as call_ai, patch.object(ai, "get_summary_reasoning_effort", return_value="medium"):
            items, model = ai.summarize_radar_candidates(candidates, report_date="2026-06-26")
        self.assertEqual("model-a", model)
        self.assertEqual("PCB涨价逻辑升温", items[0]["title"])
        self.assertEqual("证据显示PCB涨价逻辑被集中讨论。", items[0]["summary"])
        call_ai.assert_called_once()
        args, kwargs = call_ai.call_args
        self.assertEqual(1, len(args))
        self.assertEqual("research_radar_logic_summaries", kwargs["schema_name"])
        self.assertIs(ai.RESEARCH_RADAR_AI_SCHEMA, kwargs["schema"])
        self.assertEqual("研究雷达 AI 摘要结果", kwargs["label"])
        self.assertIs(ai.get_openai_compatible_config, kwargs["get_ai_config"])
        self.assertEqual("medium", kwargs["reasoning_effort"])
        self.assertEqual(180, kwargs["timeout"])
        self.assertIn("direction:PCB", args[0][1]["content"])


if __name__ == "__main__":
    unittest.main()
