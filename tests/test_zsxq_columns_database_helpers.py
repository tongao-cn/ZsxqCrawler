import unittest

from backend.storage.zsxq_columns_database import (
    _column_row_to_dict,
    _column_topic_row_to_dict,
    _empty_stats,
    _topic_detail_row_to_dict,
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

    def test_topic_detail_row_to_dict_preserves_base_shape(self):
        row = (
            202,
            303,
            "talk",
            "topic title",
            "full topic text",
            11,
            22,
            33,
            0,
            1,
            "2026-05-01T08:00:00+0800",
            "2026-05-02T08:00:00+0800",
            '{"topic_id":202}',
            "2026-05-03 12:00:00",
            "2026-05-04 12:00:00",
            404,
            "owner name",
            "owner alias",
            "avatar-url",
            "owner description",
            "owner location",
        )

        result = _topic_detail_row_to_dict(row)

        self.assertEqual(
            result,
            {
                "topic_id": 202,
                "group_id": 303,
                "type": "talk",
                "title": "topic title",
                "full_text": "full topic text",
                "likes_count": 11,
                "comments_count": 22,
                "readers_count": 33,
                "digested": False,
                "sticky": True,
                "create_time": "2026-05-01T08:00:00+0800",
                "modify_time": "2026-05-02T08:00:00+0800",
                "raw_json": '{"topic_id":202}',
                "imported_at": "2026-05-03 12:00:00",
                "updated_at": "2026-05-04 12:00:00",
                "owner": {
                    "user_id": 404,
                    "name": "owner name",
                    "alias": "owner alias",
                    "avatar_url": "avatar-url",
                    "description": "owner description",
                    "location": "owner location",
                },
                "images": [],
                "files": [],
                "comments": [],
            },
        )
        self.assertEqual(
            list(result),
            [
                "topic_id",
                "group_id",
                "type",
                "title",
                "full_text",
                "likes_count",
                "comments_count",
                "readers_count",
                "digested",
                "sticky",
                "create_time",
                "modify_time",
                "raw_json",
                "imported_at",
                "updated_at",
                "owner",
                "images",
                "files",
                "comments",
            ],
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

    def test_insert_comment_writes_group_id_from_runtime_scope(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

            def fetchone(self):
                return None

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.group_id = "303"
        db.insert_user = lambda user: user.get("user_id") if user else None

        db._insert_comment(202, {"comment_id": 101, "owner": {"user_id": 9}, "text": "ok"})

        sql, params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO comments", sql)
        self.assertIn("ON CONFLICT(comment_id) DO UPDATE SET", sql)
        self.assertIn("comment_id, group_id, topic_id", sql)
        self.assertEqual((101, 303, 202), params[:3])

    def test_column_queries_are_scoped_by_group(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

            def fetchone(self):
                return None

            def fetchall(self):
                return []

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.group_id = "303"

        self.assertIsNone(ZSXQColumnsDatabase.get_column(db, 101))
        column_sql, column_params = db.cursor.calls[-1]
        self.assertIn("WHERE column_id = ? AND (? IS NULL OR group_id = ?)", column_sql)
        self.assertEqual((101, 303, 303), column_params)

        self.assertEqual([], ZSXQColumnsDatabase.get_column_topics(db, 101))
        topics_sql, topics_params = db.cursor.calls[-1]
        self.assertIn("ct.group_id = td.group_id", topics_sql)
        self.assertIn("WHERE ct.column_id = ? AND (? IS NULL OR ct.group_id = ?)", topics_sql)
        self.assertEqual((101, 303, 303), topics_params)

    def test_topic_detail_queries_are_scoped_by_group(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.fetchone_results = [None]

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

            def fetchone(self):
                return self.fetchone_results.pop(0) if self.fetchone_results else None

            def fetchall(self):
                return []

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.group_id = "303"

        self.assertIsNone(ZSXQColumnsDatabase.get_topic_detail(db, 202))
        detail_sql, detail_params = db.cursor.calls[-1]
        self.assertIn("WHERE td.topic_id = ? AND (? IS NULL OR td.group_id = ?)", detail_sql)
        self.assertEqual((202, 303, 303), detail_params)

        self.assertEqual([], ZSXQColumnsDatabase.get_topic_comments(db, 202))
        comments_sql, comments_params = db.cursor.calls[-1]
        self.assertIn("WHERE c.topic_id = ? AND (? IS NULL OR c.group_id = ?)", comments_sql)
        self.assertEqual((202, 303, 303), comments_params)

    def test_runtime_init_database_is_noop(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((sql, params))

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()

        self.assertIsNone(ZSXQColumnsDatabase._init_database(db))
        self.assertEqual([], db.cursor.calls)


if __name__ == "__main__":
    unittest.main()
