import unittest

from backend.services.a_share_recommendation_pool_storage import (
    AShareRecommendationPoolStorage,
    AShareRecommendationPoolStorageAdapters,
)


class RecommendationPoolStorageTestDoubles:
    def __init__(self, *, use_db):
        self.use_db = use_db
        self.calls = []
        self.logs = []
        self.daily_from_db = {}
        self.state_from_db = set()

    def build(self):
        return AShareRecommendationPoolStorage(
            AShareRecommendationPoolStorageAdapters(
                should_use_db_storage=lambda group_id: self.use_db,
                resolve_analysis_paths=self.resolve_paths,
                read_daily_file=self.read_daily_file,
                write_daily_file=self.write_daily_file,
                load_state_file=self.load_state_file,
                save_state_file=self.save_state_file,
                load_daily_mentions_from_db=self.load_daily_mentions_from_db,
                save_daily_mentions_to_db=self.save_daily_mentions_to_db,
                load_processed_state_from_db=self.load_processed_state_from_db,
                save_processed_state_to_db=self.save_processed_state_to_db,
                normalize_group_id=lambda group_id: str(group_id or "").strip(),
                log_info=self.logs.append,
            )
        )

    def resolve_paths(self, output_path, state_path, group_id):
        self.calls.append(("resolve_paths", output_path, state_path, group_id))
        return f"resolved:{output_path}", f"resolved:{state_path}"

    def read_daily_file(self, output_path):
        self.calls.append(("read_daily_file", output_path))
        return {"2026-05-01": {"本地": 1}}

    def write_daily_file(self, daily, output_path):
        self.calls.append(("write_daily_file", daily, output_path))

    def load_state_file(self, state_path):
        self.calls.append(("load_state_file", state_path))
        return {"local:1:2026-05-01"}

    def save_state_file(self, state_path, processed_keys):
        self.calls.append(("save_state_file", state_path, set(processed_keys)))

    def load_daily_mentions_from_db(self, *, group_id):
        self.calls.append(("load_daily_mentions_from_db", group_id))
        return self.daily_from_db

    def save_daily_mentions_to_db(self, daily, *, group_id):
        self.calls.append(("save_daily_mentions_to_db", daily, group_id))

    def load_processed_state_from_db(self, *, group_id):
        self.calls.append(("load_processed_state_from_db", group_id))
        return self.state_from_db

    def save_processed_state_to_db(self, processed_keys, *, group_id):
        self.calls.append(("save_processed_state_to_db", set(processed_keys), group_id))


class AShareRecommendationPoolStorageTests(unittest.TestCase):
    def test_db_storage_reads_without_local_file_fallback(self):
        doubles = RecommendationPoolStorageTestDoubles(use_db=True)
        doubles.daily_from_db = {}
        doubles.state_from_db = set()
        storage = doubles.build()

        self.assertEqual({}, storage.read_daily("out.csv", "state.json", group_id="511"))
        self.assertEqual(set(), storage.load_processed("out.csv", "state.json", group_id="511"))

        self.assertIn(("load_daily_mentions_from_db", "511"), doubles.calls)
        self.assertIn(("load_processed_state_from_db", "511"), doubles.calls)
        self.assertNotIn(("read_daily_file", "resolved:out.csv"), doubles.calls)
        self.assertNotIn(("load_state_file", "resolved:state.json"), doubles.calls)

    def test_db_storage_writes_and_logs_summary(self):
        doubles = RecommendationPoolStorageTestDoubles(use_db=True)
        storage = doubles.build()
        daily = {"2026-05-01": {"宁德时代": 2, "比亚迪": 3}}

        storage.save_daily(daily, "out.csv", "state.json", group_id=" 511 ")
        storage.save_processed("out.csv", "state.json", {"topics:1:2026-05-01"}, group_id=" 511 ")

        self.assertIn(("save_daily_mentions_to_db", daily, " 511 "), doubles.calls)
        self.assertIn(("save_processed_state_to_db", {"topics:1:2026-05-01"}, " 511 "), doubles.calls)
        self.assertEqual(
            ["db daily mentions saved: group_id=511, days=1, rows=2, mentions=5"],
            doubles.logs,
        )

    def test_local_storage_uses_resolved_paths(self):
        doubles = RecommendationPoolStorageTestDoubles(use_db=False)
        storage = doubles.build()

        self.assertEqual({"2026-05-01": {"本地": 1}}, storage.read_daily("out.csv", "state.json", group_id="511"))
        storage.save_daily({"2026-05-02": {"本地": 2}}, "out.csv", "state.json", group_id="511")
        self.assertEqual({"local:1:2026-05-01"}, storage.load_processed("out.csv", "state.json", group_id="511"))
        storage.save_processed("out.csv", "state.json", None, group_id="511")

        self.assertIn(("read_daily_file", "resolved:out.csv"), doubles.calls)
        self.assertIn(("write_daily_file", {"2026-05-02": {"本地": 2}}, "resolved:out.csv"), doubles.calls)
        self.assertIn(("load_state_file", "resolved:state.json"), doubles.calls)
        self.assertIn(("save_state_file", "resolved:state.json", set()), doubles.calls)

    def test_db_errors_are_wrapped_with_operation_context(self):
        doubles = RecommendationPoolStorageTestDoubles(use_db=True)

        def fail_save_daily(_daily, *, group_id):
            raise RuntimeError(f"db down for {group_id}")

        doubles.save_daily_mentions_to_db = fail_save_daily
        storage = doubles.build()

        with self.assertRaisesRegex(RuntimeError, "save daily mentions to PostgreSQL failed: db down for 511"):
            storage.save_daily({"2026-05-01": {"宁德时代": 2}}, "out.csv", "state.json", group_id="511")


if __name__ == "__main__":
    unittest.main()
