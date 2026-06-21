import asyncio
import unittest

from backend.services.columns_resource_service import (
    collect_topic_files,
    download_topic_files,
    download_topic_video,
    get_topic_video,
    process_topic_resources,
)


async def no_sleep(_seconds):
    return None


class ColumnsResourceServiceTests(unittest.TestCase):
    def test_collect_topic_files_includes_content_voice(self):
        file_info = {"file_id": 1, "name": "file.pdf"}
        voice_info = {"file_id": 2, "name": "voice.m4a"}

        self.assertEqual(
            [file_info, voice_info],
            collect_topic_files({"talk": {"files": [file_info]}, "content_voice": voice_info}),
        )

    def test_get_topic_video_returns_video_with_id(self):
        video = {"video_id": 7, "size": 1024}

        self.assertEqual(video, get_topic_video({"talk": {"video": video}}))
        self.assertIsNone(get_topic_video({"talk": {"video": {"size": 1024}}}))
        self.assertIsNone(get_topic_video({}))

    def test_download_topic_files_counts_downloaded_and_skipped_files(self):
        calls = []

        async def fake_download_column_file(**kwargs):
            calls.append(kwargs)
            return "downloaded" if len(calls) == 1 else "skipped"

        topic_detail = {
            "talk": {
                "files": [
                    {"file_id": 1, "name": "downloaded.pdf", "size": 10},
                    {"file_id": 2, "name": "skipped.pdf", "size": 20},
                ]
            }
        }

        downloaded, skipped, request_count = asyncio.run(
            download_topic_files(
                add_task_log=lambda _task_id, _message: None,
                crawl_interval_max=0,
                crawl_interval_min=0,
                current_request_count=0,
                db=object(),
                download_column_file=fake_download_column_file,
                group_id="123",
                headers={},
                is_task_stopped=lambda _task_id: False,
                items_per_batch=10,
                log_exception=lambda _message: None,
                long_sleep_max=0,
                long_sleep_min=0,
                random_uniform=lambda _min, _max: 0,
                sleep=no_sleep,
                task_id="task-1",
                topic_detail=topic_detail,
                topic_id=10,
            )
        )

        self.assertEqual(1, downloaded)
        self.assertEqual(1, skipped)
        self.assertEqual(1, request_count)
        self.assertEqual(2, len(calls))
        self.assertEqual(
            {
                "group_id": "123",
                "file_id": 1,
                "file_name": "downloaded.pdf",
                "file_size": 10,
                "topic_id": 10,
                "headers": {},
                "task_id": "task-1",
            },
            {
                key: calls[0][key]
                for key in ("group_id", "file_id", "file_name", "file_size", "topic_id", "headers", "task_id")
            },
        )

    def test_download_topic_video_counts_skipped_result(self):
        calls = []

        async def fake_download_column_video(**kwargs):
            calls.append(kwargs)
            return "skipped"

        downloaded, skipped, request_count = asyncio.run(
            download_topic_video(
                add_task_log=lambda _task_id, _message: None,
                crawl_interval_max=0,
                crawl_interval_min=0,
                current_request_count=0,
                db=object(),
                download_column_video=fake_download_column_video,
                group_id="123",
                headers={},
                items_per_batch=10,
                log_exception=lambda _message: None,
                long_sleep_max=0,
                long_sleep_min=0,
                random_uniform=lambda _min, _max: 0,
                sleep=no_sleep,
                task_id="task-1",
                topic_id=10,
                video={"video_id": 7, "size": 1024, "duration": 30},
            )
        )

        self.assertEqual(0, downloaded)
        self.assertEqual(1, skipped)
        self.assertEqual(0, request_count)
        self.assertEqual(
            {
                "group_id": "123",
                "video_id": 7,
                "video_size": 1024,
                "video_duration": 30,
                "topic_id": 10,
                "headers": {},
                "task_id": "task-1",
            },
            {
                key: calls[0][key]
                for key in ("group_id", "video_id", "video_size", "video_duration", "topic_id", "headers", "task_id")
            },
        )

    def test_process_topic_resources_aggregates_resource_counts(self):
        file_calls = []
        video_calls = []
        image_calls = []
        cover_calls = []

        async def fake_download_topic_files(**kwargs):
            file_calls.append(kwargs)
            return 1, 2, 3

        async def fake_download_topic_video(**kwargs):
            video_calls.append(kwargs)
            return 4, 5, 6

        config = {
            "download_files": True,
            "download_videos": True,
            "cache_images": True,
            "items_per_batch": 10,
            "long_sleep_min": 0,
            "long_sleep_max": 0,
            "crawl_interval_min": 0,
            "crawl_interval_max": 0,
        }
        topic_detail = {
            "talk": {
                "video": {
                    "video_id": 7,
                    "size": 1024,
                    "duration": 30,
                    "cover": {"url": "https://example.test/cover.jpg"},
                }
            }
        }

        stats = asyncio.run(
            process_topic_resources(
                add_task_log=lambda _task_id, _message: None,
                cache_topic_images=lambda **kwargs: image_calls.append(kwargs) or 8,
                cache_video_cover=lambda **kwargs: cover_calls.append(kwargs) or True,
                config=config,
                current_request_count=0,
                db=object(),
                download_topic_files=fake_download_topic_files,
                download_topic_video=fake_download_topic_video,
                get_topic_video_fn=get_topic_video,
                group_id="123",
                headers={},
                task_id="task-1",
                topic_detail=topic_detail,
                topic_id=10,
            )
        )

        self.assertEqual(1, stats.files_count)
        self.assertEqual(2, stats.files_skipped)
        self.assertEqual(8, stats.images_count)
        self.assertEqual(4, stats.videos_count)
        self.assertEqual(5, stats.videos_skipped)
        self.assertEqual(9, stats.request_count)
        self.assertEqual(1, len(cover_calls))
        self.assertEqual(0, file_calls[0]["current_request_count"])
        self.assertEqual(3, video_calls[0]["current_request_count"])
        self.assertEqual("123", image_calls[0]["group_id"])
        self.assertEqual(7, cover_calls[0]["video_id"])


if __name__ == "__main__":
    unittest.main()
