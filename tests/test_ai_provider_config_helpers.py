import unittest
from unittest.mock import patch


class AIProviderConfigHelperTests(unittest.TestCase):
    def test_summary_reasoning_defaults_to_medium_while_extraction_stays_low(self):
        from backend.core import ai_provider_config as config

        with (
            patch.object(config, "_load_project_env_file"),
            patch.object(config, "_load_toml_file", return_value={}),
            patch.dict(
                "os.environ",
                {
                    "OPENAI_SUMMARY_REASONING_EFFORT": "",
                    "AI_SUMMARY_REASONING_EFFORT": "",
                    "OPENAI_EXTRACTION_REASONING_EFFORT": "",
                    "AI_EXTRACTION_REASONING_EFFORT": "",
                },
                clear=False,
            ),
        ):
            self.assertEqual("medium", config.get_summary_reasoning_effort())
            self.assertEqual("low", config.get_extraction_reasoning_effort())


if __name__ == "__main__":
    unittest.main()
