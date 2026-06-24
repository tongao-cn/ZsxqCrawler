import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_stock_topic_incremental_backlog as script


class StockTopicIncrementalBacklogScriptTests(unittest.TestCase):
    def test_main_sanitizes_unicode_log_messages_for_gbk_console(self):
        printed = []

        def fake_print(*values, **kwargs):
            text = " ".join(str(value) for value in values)
            if "📚" in text:
                raise UnicodeEncodeError("gbk", text, 0, 1, "illegal multibyte sequence")
            printed.append(text)

        def fake_batch(_group_id, _names, *, log_callback):
            log_callback("📚 搜索股票相关话题...")
            return {"summary": {"success": 1, "failed": 0, "no_topics": 0, "aborted": False}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            pending = [{"stock": "示例股份", "pending_topic_count": 11}]
            with (
                patch("builtins.print", side_effect=fake_print),
                patch.object(script, "load_pending_stocks", side_effect=[pending, []]),
                patch.object(script.stock_topic_service, "analyze_stock_topics_batch", side_effect=fake_batch),
            ):
                exit_code = script.main(
                    [
                        "--group-id",
                        "51111112855254",
                        "--pending-threshold",
                        "10",
                        "--chunk-size",
                        "5",
                        "--output-root",
                        str(Path(tmp_dir)),
                    ]
                )

        self.assertEqual(0, exit_code)
        self.assertTrue(any("? 搜索股票相关话题" in line for line in printed))


if __name__ == "__main__":
    unittest.main()
