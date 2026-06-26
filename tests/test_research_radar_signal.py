import unittest


class ResearchRadarSignalTests(unittest.TestCase):
    def test_build_candidates_groups_by_concept_and_binds_topic_evidence(self):
        from backend.services.research_radar_signal import build_research_radar_candidates

        topics = [
            {
                "topic_id": "101",
                "title": "PCB涨价继续发酵",
                "create_time": "2026-06-26T08:30:00.000+0800",
                "talk_text": "AI服务器需求拉动PCB和铜箔涨价，沪电股份被多次提到。",
                "comments": [{"text": "胜宏科技也受益于高端PCB订单。"}],
            },
            {
                "topic_id": "102",
                "title": "机器人订单",
                "create_time": "2026-06-26T09:10:00.000+0800",
                "talk_text": "机器人方向有新订单催化。",
                "comments": [],
            },
        ]
        current_rows = [
            {
                "topic_id": "101",
                "stock_name": "沪电股份",
                "stock_code": "002463",
                "market": "SZ",
                "concepts": ["PCB", "涨价/供需"],
                "reason": "PCB涨价和AI服务器需求。",
                "confidence": 0.8,
            },
            {
                "topic_id": "101",
                "stock_name": "胜宏科技",
                "stock_code": "300476",
                "market": "SZ",
                "concepts": ["PCB"],
                "reason": "高端PCB订单。",
                "confidence": 0.75,
            },
        ]
        baseline_rows = [
            {
                "topic_id": "90",
                "stock_name": "旧股票",
                "concepts": ["机器人"],
                "reason": "历史机器人讨论。",
                "confidence": 0.6,
            }
        ]

        candidates = build_research_radar_candidates(
            topics=topics,
            current_stock_rows=current_rows,
            baseline_stock_rows=baseline_rows,
            max_candidates=5,
        )

        self.assertEqual(1, len(candidates))
        candidate = candidates[0]
        self.assertEqual("PCB", candidate["direction"])
        self.assertEqual("strong", candidate["tier"])
        self.assertGreaterEqual(candidate["confidence"], 0.75)
        self.assertEqual(["涨价/供需"], candidate["catalysts"])
        self.assertEqual(["PCB"], candidate["concepts"])
        self.assertEqual(["沪电股份", "胜宏科技"], [stock["name"] for stock in candidate["stocks"]])
        self.assertEqual(1, len(candidate["evidence"]))
        self.assertEqual("topic", candidate["evidence"][0]["source_type"])
        self.assertEqual("101", candidate["evidence"][0]["topic_id"])
        self.assertIn("AI服务器需求", candidate["evidence"][0]["excerpt"])

    def test_build_candidates_marks_single_evidence_as_weak_signal(self):
        from backend.services.research_radar_signal import build_research_radar_candidates

        candidates = build_research_radar_candidates(
            topics=[
                {
                    "topic_id": "201",
                    "title": "新材料线索",
                    "create_time": "2026-06-26T10:00:00.000+0800",
                    "talk_text": "新材料方向出现国产替代讨论。",
                    "comments": [],
                }
            ],
            current_stock_rows=[
                {
                    "topic_id": "201",
                    "stock_name": "材料公司",
                    "concepts": ["新材料", "国产替代/自主可控"],
                    "reason": "国产替代讨论刚出现。",
                    "confidence": 0.45,
                }
            ],
            baseline_stock_rows=[],
            max_candidates=5,
        )

        self.assertEqual(1, len(candidates))
        self.assertEqual("weak", candidates[0]["tier"])
        self.assertEqual(["国产替代/自主可控"], candidates[0]["catalysts"])

    def test_build_candidates_returns_empty_without_stock_rows(self):
        from backend.services.research_radar_signal import build_research_radar_candidates

        self.assertEqual(
            [],
            build_research_radar_candidates(
                topics=[{"topic_id": "1", "title": "只有话题", "talk_text": "没有股票抽取"}],
                current_stock_rows=[],
                baseline_stock_rows=[],
            ),
        )


if __name__ == "__main__":
    unittest.main()
