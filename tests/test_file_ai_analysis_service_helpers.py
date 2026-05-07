import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch


HAS_FILE_AI_DEPS = find_spec("openai") is not None and find_spec("pypdf") is not None


class FileAIAnalysisServiceHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_cached_analysis_result_marks_completed_summary_as_cached(self):
        from backend.services.file_ai_analysis_service import _cached_analysis_result

        existing = {"status": "completed", "summary": "ok", "file_id": 123}

        result = _cached_analysis_result(existing, force=False)

        self.assertEqual({"status": "completed", "summary": "ok", "file_id": 123, "cached": True}, result)

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_cached_analysis_result_skips_force_and_incomplete_records(self):
        from backend.services.file_ai_analysis_service import _cached_analysis_result

        self.assertIsNone(_cached_analysis_result({"status": "completed", "summary": "ok"}, force=True))
        self.assertIsNone(_cached_analysis_result({"status": "failed", "summary": "ok"}, force=False))
        self.assertIsNone(_cached_analysis_result({"status": "completed", "summary": ""}, force=False))

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_extract_file_content_for_analysis_uses_audio_transcription(self):
        from backend.services.file_ai_analysis_service import _extract_file_content_for_analysis

        with patch("backend.services.file_ai_analysis_service._transcribe_audio_with_faster_whisper", return_value="text"):
            text, content_type = _extract_file_content_for_analysis(Path("voice.mp3"))

        self.assertEqual("text", text)
        self.assertEqual("audio/mp3", content_type)

    @unittest.skipUnless(HAS_FILE_AI_DEPS, "file AI service dependencies are not installed")
    def test_extract_file_content_for_analysis_delegates_non_audio(self):
        from backend.services.file_ai_analysis_service import _extract_file_content_for_analysis

        with patch("backend.services.file_ai_analysis_service.extract_file_text", return_value=("text", "text/plain")):
            text, content_type = _extract_file_content_for_analysis(Path("note.txt"))

        self.assertEqual("text", text)
        self.assertEqual("text/plain", content_type)


if __name__ == "__main__":
    unittest.main()
