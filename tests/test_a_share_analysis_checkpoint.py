import unittest


class AShareAnalysisCheckpointTests(unittest.TestCase):
    def test_checkpoint_manager_flushes_at_batch_size_and_updates_processed_keys(self):
        from backend.services.a_share_analysis_checkpoint import AShareAnalysisCheckpointManager

        processed_keys = {"existing-key"}
        saves = []
        logs = []

        def save_checkpoint(**kwargs):
            saves.append(
                {
                    "daily_delta": kwargs["daily_delta"],
                    "processed_keys": set(kwargs["processed_keys"]),
                    "topic_stock_extractions": list(kwargs["topic_stock_extractions"]),
                    "group_id": kwargs["group_id"],
                }
            )
            return {
                "daily_mentions": sum(sum(values.values()) for values in kwargs["daily_delta"].values()),
                "topic_stock_extractions": len(kwargs["topic_stock_extractions"]),
                "processed_state": len(kwargs["processed_keys"]),
            }

        manager = AShareAnalysisCheckpointManager(
            enabled=True,
            group_id="511",
            processed_keys=processed_keys,
            save_checkpoint=save_checkpoint,
            emit_log=logs.append,
            batch_size=2,
        )

        manager.record_success(
            "topic-1",
            "2026-05-01",
            [{"stock_name": "宁德时代"}],
            ["宁德时代"],
        )
        self.assertEqual([], saves)

        manager.record_success(
            "topic-2",
            "2026-05-01",
            [{"stock_name": "比亚迪"}],
            ["宁德时代", "比亚迪"],
        )

        self.assertEqual(1, len(saves))
        self.assertEqual({"2026-05-01": {"宁德时代": 2, "比亚迪": 1}}, saves[0]["daily_delta"])
        self.assertEqual({"topic-1", "topic-2"}, saves[0]["processed_keys"])
        self.assertEqual("511", saves[0]["group_id"])
        self.assertEqual({"existing-key", "topic-1", "topic-2"}, processed_keys)
        self.assertEqual(2, manager.saved_topic_stock_extractions)
        self.assertEqual({}, manager.pending_daily)
        self.assertEqual(set(), manager.pending_keys)
        self.assertEqual([], manager.pending_extractions)
        self.assertIn("group_id=511", logs[0])

    def test_checkpoint_manager_force_flushes_key_without_companies(self):
        from backend.services.a_share_analysis_checkpoint import AShareAnalysisCheckpointManager

        saves = []
        manager = AShareAnalysisCheckpointManager(
            enabled=True,
            group_id="511",
            processed_keys=set(),
            save_checkpoint=lambda **kwargs: saves.append(kwargs) or {"processed_state": len(kwargs["processed_keys"])},
            emit_log=lambda _message: None,
            batch_size=20,
        )

        manager.record_success("topic-short", "2026-05-01", [], [])
        self.assertEqual([], saves)

        manager.flush(force=True)

        self.assertEqual(set(), saves[0]["daily_delta"].get("2026-05-01", set()))
        self.assertEqual({"topic-short"}, set(saves[0]["processed_keys"]))

    def test_checkpoint_manager_disabled_has_no_success_callback_or_flush(self):
        from backend.services.a_share_analysis_checkpoint import AShareAnalysisCheckpointManager

        saves = []
        manager = AShareAnalysisCheckpointManager(
            enabled=False,
            group_id=None,
            processed_keys=set(),
            save_checkpoint=lambda **kwargs: saves.append(kwargs),
            emit_log=lambda _message: None,
            batch_size=1,
        )

        self.assertIsNone(manager.success_callback())
        manager.record_success("topic-1", "2026-05-01", [{"stock_name": "宁德时代"}], ["宁德时代"])
        manager.flush(force=True)

        self.assertEqual([], saves)
        self.assertEqual(set(), manager.processed_keys)


if __name__ == "__main__":
    unittest.main()
