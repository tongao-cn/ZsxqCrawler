import unittest
from unittest.mock import patch


class ResearchRadarAITests(unittest.TestCase):
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
        self.assertEqual([{"topic_id": "101", "excerpt": "PCB涨价"}], result[0]["evidence"])

    def test_apply_ai_logic_summaries_ignores_unknown_candidate_ids(self):
        from backend.services.research_radar_ai import apply_ai_logic_summaries

        candidates = [{"candidate_id": "direction:PCB", "title": "old", "summary": "old"}]
        payload = {"logic_items": [{"candidate_id": "direction:机器人", "title": "bad", "summary": "bad"}]}
        result = apply_ai_logic_summaries(candidates, payload)
        self.assertEqual("old", result[0]["title"])
        self.assertEqual("old", result[0]["summary"])

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
        ) as call_ai:
            items, model = ai.summarize_radar_candidates(candidates, report_date="2026-06-26")
        self.assertEqual("model-a", model)
        self.assertEqual("PCB涨价逻辑升温", items[0]["title"])
        call_ai.assert_called_once()


if __name__ == "__main__":
    unittest.main()
