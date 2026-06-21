import unittest
from pathlib import Path


class WorkflowTaskLaunchTests(unittest.TestCase):
    def test_script_entrypoints_do_not_import_routes(self):
        root = Path(__file__).resolve().parents[1]
        for relative_path in (
            "scripts/export_daily_review_topics.py",
            "scripts/run_zsxq_topic_recommendation_refresh.py",
        ):
            text = (root / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("backend.routes", text, relative_path)


if __name__ == "__main__":
    unittest.main()
