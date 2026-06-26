import unittest
from pathlib import Path


class RetentionTaskRegistrationScriptTests(unittest.TestCase):
    def test_registration_script_defaults_to_idle_weekly_and_requires_apply_for_deletes(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "register_retention_cleanup_task.ps1"
        text = script_path.read_text(encoding="utf-8")

        self.assertIn("RunOnlyIfIdle", text)
        self.assertIn('Default: "Sunday"', text)
        self.assertIn('Default: "03:30"', text)
        self.assertIn("if ($Apply)", text)
        self.assertIn('"--apply"', text)


if __name__ == "__main__":
    unittest.main()
