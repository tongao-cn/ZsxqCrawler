import unittest

from backend.services.columns_media_cache_service import cache_topic_images, cache_video_cover


class FakeCacheManager:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.urls = []

    def download_and_cache(self, url):
        self.urls.append(url)
        if self.error:
            raise self.error
        return self.result


class FakeColumnsDb:
    def __init__(self):
        self.updated_images = []
        self.updated_video_covers = []

    def update_image_local_path(self, image_id, local_path):
        self.updated_images.append((image_id, local_path))

    def update_video_cover_path(self, video_id, local_path):
        self.updated_video_covers.append((video_id, local_path))


class ColumnsMediaCacheServiceTests(unittest.TestCase):
    def test_cache_topic_images_updates_local_paths(self):
        cache_manager = FakeCacheManager((True, "local.jpg", None))
        db = FakeColumnsDb()
        topic_detail = {
            "talk": {
                "images": [
                    {"image_id": 1, "original": {"url": "https://example.test/1.jpg"}},
                    {"image_id": 2, "original": {}},
                ]
            }
        }

        cached = cache_topic_images(
            cache_manager_factory=lambda _group_id: cache_manager,
            db=db,
            group_id="123",
            task_id="task-1",
            topic_detail=topic_detail,
        )

        self.assertEqual(1, cached)
        self.assertEqual(["https://example.test/1.jpg"], cache_manager.urls)
        self.assertEqual([(1, "local.jpg")], db.updated_images)

    def test_cache_topic_images_stops_when_task_is_stopped(self):
        cache_manager = FakeCacheManager((True, "local.jpg", None))
        db = FakeColumnsDb()
        topic_detail = {"talk": {"images": [{"image_id": 1, "original": {"url": "https://example.test/1.jpg"}}]}}

        cached = cache_topic_images(
            cache_manager_factory=lambda _group_id: cache_manager,
            db=db,
            group_id="123",
            is_task_stopped=lambda _task_id: True,
            task_id="task-1",
            topic_detail=topic_detail,
        )

        self.assertEqual(0, cached)
        self.assertEqual([], cache_manager.urls)
        self.assertEqual([], db.updated_images)

    def test_cache_video_cover_updates_local_path(self):
        cache_manager = FakeCacheManager((True, "cover.jpg", None))
        db = FakeColumnsDb()
        logs = []

        cached = cache_video_cover(
            add_task_log=lambda task_id, message: logs.append((task_id, message)),
            cache_manager_factory=lambda _group_id: cache_manager,
            cover_url="https://example.test/cover.jpg",
            db=db,
            group_id="123",
            task_id="task-1",
            video_id=7,
        )

        self.assertTrue(cached)
        self.assertEqual(["https://example.test/cover.jpg"], cache_manager.urls)
        self.assertEqual([(7, "cover.jpg")], db.updated_video_covers)
        self.assertEqual([("task-1", "      ✅ 视频封面缓存成功")], logs)

    def test_cache_video_cover_logs_cache_error(self):
        cache_manager = FakeCacheManager((False, None, "bad image"))
        db = FakeColumnsDb()
        logs = []
        warnings = []

        cached = cache_video_cover(
            add_task_log=lambda task_id, message: logs.append((task_id, message)),
            cache_manager_factory=lambda _group_id: cache_manager,
            cover_url="https://example.test/cover.jpg",
            db=db,
            group_id="123",
            log_warning=warnings.append,
            task_id="task-1",
            video_id=7,
        )

        self.assertFalse(cached)
        self.assertEqual([], db.updated_video_covers)
        self.assertEqual([("task-1", "      ⚠️ 视频封面缓存失败: bad image")], logs)
        self.assertEqual(
            ["视频封面缓存失败: video_id=7, url=https://example.test/cover.jpg, error=bad image"],
            warnings,
        )


if __name__ == "__main__":
    unittest.main()
