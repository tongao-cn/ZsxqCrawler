import unittest
from unittest.mock import Mock


class RowDouble:
    def __init__(self, **values):
        self.values = values

    def __getitem__(self, key):
        return self.values[key]


class ResearchRadarStoreTests(unittest.TestCase):
    def test_save_research_radar_run_replaces_existing_date_and_serializes_children(self):
        from backend.services.research_radar_store import save_research_radar_run

        conn = Mock()
        existing_cursor = Mock()
        existing_cursor.fetchall.return_value = [{"id": 7}]
        insert_cursor = Mock()
        insert_cursor.fetchone.return_value = RowDouble(id=8)
        logic_insert_cursor = Mock()
        logic_insert_cursor.fetchone.return_value = RowDouble(id=9)
        conn.execute.side_effect = [
            existing_cursor,
            Mock(),
            Mock(),
            Mock(),
            Mock(),
            insert_cursor,
            logic_insert_cursor,
            Mock(),
            Mock(),
            Mock(),
        ]

        run_id = save_research_radar_run(
            conn,
            group_id="303",
            report_date="2026-06-26",
            task_id="task-1",
            status="completed",
            model="model-a",
            logic_items=[
                {
                    "title": "PCB研究信号升温",
                    "summary": "PCB方向由涨价和AI服务器需求驱动。",
                    "tier": "strong",
                    "direction": "PCB",
                    "concepts": ["PCB"],
                    "stocks": [{"name": "沪电股份", "code": "002463", "market": "SZ"}],
                    "catalysts": ["涨价/供需"],
                    "risks": [],
                    "confidence": 0.82,
                    "evidence": [
                        {
                            "source_type": "topic",
                            "source_id": "101",
                            "topic_id": "101",
                            "source_time": "2026-06-26T08:30:00.000+0800",
                            "excerpt": "AI服务器需求拉动PCB。",
                            "matched_entities": {"direction": "PCB"},
                            "support_reason": "话题讨论PCB涨价。",
                            "navigation": {"type": "topic", "topic_id": "101"},
                        }
                    ],
                }
            ],
            summary={"direction_count": 1},
        )

        self.assertEqual(8, run_id)
        self.assertIn("SELECT id FROM research_radar_runs", conn.execute.call_args_list[0].args[0])
        self.assertIn("DELETE FROM research_radar_evidence", conn.execute.call_args_list[1].args[0])
        self.assertIn("INSERT INTO research_radar_runs", conn.execute.call_args_list[5].args[0])
        self.assertIn("INSERT INTO research_radar_logic_items", conn.execute.call_args_list[6].args[0])
        self.assertIn("INSERT INTO research_radar_evidence", conn.execute.call_args_list[7].args[0])
        self.assertIn("INSERT INTO research_radar_entities", conn.execute.call_args_list[8].args[0])
        self.assertEqual(9, conn.execute.call_args_list[7].args[1][0])
        self.assertEqual(9, conn.execute.call_args_list[8].args[1][1])
        self.assertEqual(9, conn.execute.call_args_list[9].args[1][1])
        self.assertEqual(1, conn.execute.call_args_list[8].args[1][7])
        self.assertEqual(1, conn.execute.call_args_list[9].args[1][7])
        conn.commit.assert_called_once_with()

    def test_load_research_radar_run_maps_logic_evidence_and_entities(self):
        from backend.services.research_radar_store import load_research_radar_run_by_date

        conn = Mock()
        run_cursor = Mock()
        run_cursor.fetchone.return_value = {
            "id": 8,
            "group_id": "303",
            "report_date": "2026-06-26",
            "window_days": 1,
            "status": "completed",
            "model": "model-a",
            "summary_json": '{"direction_count": 1}',
            "task_id": "task-1",
            "error": "",
            "created_at": "2026-06-26T09:00:00",
            "updated_at": "2026-06-26T09:01:00",
        }
        logic_cursor = Mock()
        logic_cursor.fetchall.return_value = [
            {
                "id": 10,
                "rank": 1,
                "tier": "strong",
                "title": "PCB研究信号升温",
                "summary": "PCB方向由涨价驱动。",
                "direction": "PCB",
                "concepts_json": '["PCB"]',
                "stocks_json": '[{"name": "沪电股份"}]',
                "catalysts_json": '["涨价/供需"]',
                "risks_json": "[]",
                "evidence_count": 1,
                "confidence": 0.82,
            }
        ]
        evidence_cursor = Mock()
        evidence_cursor.fetchall.return_value = [
            {
                "id": 20,
                "logic_id": 10,
                "source_type": "topic",
                "source_id": "101",
                "topic_id": "101",
                "source_time": "2026-06-26T08:30:00.000+0800",
                "excerpt": "AI服务器需求拉动PCB。",
                "matched_entities_json": '{"direction": "PCB"}',
                "support_reason": "话题讨论PCB涨价。",
                "navigation_json": '{"type": "topic", "topic_id": "101"}',
            }
        ]
        entity_cursor = Mock()
        entity_cursor.fetchall.return_value = [
            {
                "logic_id": 10,
                "entity_type": "stock",
                "name": "沪电股份",
                "code": "002463",
                "market": "SZ",
                "weight": 0.82,
                "evidence_count": 1,
            }
        ]
        conn.execute.side_effect = [run_cursor, logic_cursor, evidence_cursor, entity_cursor]

        result = load_research_radar_run_by_date(conn, group_id="303", report_date="2026-06-26")

        self.assertEqual("303", result["group_id"])
        self.assertEqual("PCB研究信号升温", result["logic_items"][0]["title"])
        self.assertEqual("101", result["logic_items"][0]["evidence"][0]["topic_id"])
        self.assertEqual("沪电股份", result["logic_items"][0]["entities"][0]["name"])


if __name__ == "__main__":
    unittest.main()
