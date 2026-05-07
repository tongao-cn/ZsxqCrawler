import unittest

from backend.storage.zsxq_columns_database import (
    _column_row_to_dict,
    _column_topic_row_to_dict,
    _empty_stats,
    _topic_image_row_to_dict,
)


class ZSXQColumnsDatabaseHelperTests(unittest.TestCase):
    def test_column_row_to_dict_preserves_shape(self):
        row = (
            101,
            202,
            "column name",
            "https://example.test/cover.png",
            33,
            "2026-05-01T08:00:00+0800",
            "2026-05-02T08:00:00+0800",
            "2026-05-03 12:00:00",
        )

        self.assertEqual(
            _column_row_to_dict(row),
            {
                "column_id": 101,
                "group_id": 202,
                "name": "column name",
                "cover_url": "https://example.test/cover.png",
                "topics_count": 33,
                "create_time": "2026-05-01T08:00:00+0800",
                "last_topic_attach_time": "2026-05-02T08:00:00+0800",
                "imported_at": "2026-05-03 12:00:00",
            },
        )

    def test_column_topic_row_to_dict_normalizes_has_detail(self):
        row = (
            301,
            101,
            202,
            "topic title",
            "topic text",
            "2026-05-01T08:00:00+0800",
            "2026-05-02T08:00:00+0800",
            "2026-05-03 12:00:00",
            1,
        )

        result = _column_topic_row_to_dict(row)

        self.assertEqual(result["topic_id"], 301)
        self.assertIs(result["has_detail"], True)

    def test_topic_image_row_to_dict_preserves_nested_image_shape(self):
        row = (
            401,
            "image",
            "thumb-url",
            120,
            80,
            "large-url",
            960,
            640,
            "original-url",
            1920,
            1280,
            2048,
            "cache/image.png",
        )

        self.assertEqual(
            _topic_image_row_to_dict(row),
            {
                "image_id": 401,
                "type": "image",
                "thumbnail": {
                    "url": "thumb-url",
                    "width": 120,
                    "height": 80,
                },
                "large": {
                    "url": "large-url",
                    "width": 960,
                    "height": 640,
                },
                "original": {
                    "url": "original-url",
                    "width": 1920,
                    "height": 1280,
                    "size": 2048,
                },
                "local_path": "cache/image.png",
            },
        )

    def test_empty_stats_returns_independent_default_dicts(self):
        first = _empty_stats()
        second = _empty_stats()

        first["columns_count"] = 9

        self.assertEqual(second["columns_count"], 0)
        self.assertEqual(
            set(second),
            {
                "columns_count",
                "topics_count",
                "details_count",
                "images_count",
                "files_count",
                "files_downloaded",
                "videos_count",
                "videos_downloaded",
                "comments_count",
            },
        )


if __name__ == "__main__":
    unittest.main()
