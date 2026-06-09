import unittest
from unittest.mock import patch

from backend.core.console_output import safe_console_print


class ConsoleOutputTests(unittest.TestCase):
    def test_safe_console_print_replaces_unencodable_characters(self):
        calls = []

        def fake_print(*values, **kwargs):
            text = " ".join(str(value) for value in values)
            if "📁" in text:
                raise UnicodeEncodeError("gbk", text, 0, 1, "illegal multibyte sequence")
            calls.append(text)

        fake_stdout = type("FakeStdout", (), {"encoding": "gbk"})()

        with patch("backend.core.console_output.builtins.print", side_effect=fake_print):
            with patch("backend.core.console_output.sys.stdout", fake_stdout):
                safe_console_print("📁 下载目录")

        self.assertEqual(["? 下载目录"], calls)


if __name__ == "__main__":
    unittest.main()
