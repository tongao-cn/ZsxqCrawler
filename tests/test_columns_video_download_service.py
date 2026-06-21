import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from backend.services.columns_video_download_service import download_column_video


class FakeColumnsDb:
    def __init__(self):
        self.status_updates = []

    def update_video_download_status(self, video_id, status, m3u8_url="", local_path=None):
        self.status_updates.append((video_id, status, m3u8_url, local_path))


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self.payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.payload


async def no_sleep(_seconds):
    return None


class ColumnsVideoDownloadServiceTests(unittest.TestCase):
    def test_download_column_video_skips_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            videos_dir = os.path.join(tmp_dir, "column_videos")
            os.makedirs(videos_dir, exist_ok=True)
            local_path = os.path.join(videos_dir, "video_123.mp4")
            with open(local_path, "wb") as file_obj:
                file_obj.write(b"video")

            db = FakeColumnsDb()
            result = asyncio.run(
                download_column_video(
                    db=db,
                    group_dir=tmp_dir,
                    headers={},
                    request_get=lambda *args, **kwargs: self.fail("request_get should not be called"),
                    topic_id=456,
                    video_duration=10,
                    video_id=123,
                    video_size=5,
                )
            )

        self.assertEqual("skipped", result)
        self.assertEqual([(123, "completed", "", local_path)], db.status_updates)

    def test_download_column_video_raises_when_link_is_empty(self):
        db = FakeColumnsDb()
        response = FakeResponse({"succeeded": True, "resp_data": {"url": ""}})

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(Exception, "视频链接为空"):
                asyncio.run(
                    download_column_video(
                        db=db,
                        group_dir=tmp_dir,
                        headers={},
                        request_get=lambda *args, **kwargs: response,
                        sleep=no_sleep,
                        topic_id=456,
                        video_duration=10,
                        video_id=123,
                        video_size=5,
                    )
                )

        self.assertEqual([], db.status_updates)

    def test_download_column_video_writes_m3u8_link_file_when_ffmpeg_missing(self):
        db = FakeColumnsDb()
        m3u8_url = "https://example.test/video.m3u8"
        response = FakeResponse({"succeeded": True, "resp_data": {"url": m3u8_url}})

        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("backend.services.columns_video_download_service.subprocess.run", side_effect=FileNotFoundError),
                self.assertRaisesRegex(Exception, "ffmpeg未安装"),
            ):
                asyncio.run(
                    download_column_video(
                        db=db,
                        group_dir=tmp_dir,
                        headers={},
                        request_get=lambda *args, **kwargs: response,
                        sleep=no_sleep,
                        topic_id=456,
                        video_duration=10,
                        video_id=123,
                        video_size=5,
                    )
                )

            m3u8_link_file = os.path.join(tmp_dir, "column_videos", "video_123.m3u8.txt")
            with open(m3u8_link_file, encoding="utf-8") as file_obj:
                link_text = file_obj.read()

        self.assertIn(f"M3U8 URL: {m3u8_url}", link_text)
        self.assertEqual(
            [
                (123, "downloading", m3u8_url, None),
                (123, "pending_manual", m3u8_url, None),
            ],
            db.status_updates,
        )


if __name__ == "__main__":
    unittest.main()
