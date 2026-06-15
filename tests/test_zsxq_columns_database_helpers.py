import unittest
from unittest.mock import patch

from backend.storage.zsxq_columns_database import (
    _column_insert_params,
    _column_insert_statement,
    _column_query,
    _column_row_to_dict,
    _column_topic_insert_params,
    _column_topic_insert_statement,
    _column_topic_row_to_dict,
    _column_topics_query,
    _columns_query,
    _comment_image_row_to_dict,
    _comment_images_query,
    _crawl_log_insert_statement,
    _crawl_log_update_parts,
    _crawl_log_update_statement,
    _empty_clear_data_stats,
    _empty_stats,
    _file_download_status_update,
    _group_clear_delete_statements,
    _image_local_path_update,
    _iter_topic_related_payloads,
    _iter_topic_comment_import_payloads,
    _iter_topic_comment_user_payloads,
    _group_topic_ids_query,
    _nest_topic_comments,
    _pending_file_row_to_dict,
    _pending_files_query,
    _pending_video_row_to_dict,
    _pending_videos_query,
    _stats_count_queries,
    _topic_comment_insert_params,
    _topic_comment_insert_statement,
    _topic_comments_query,
    _topic_comment_row_to_dict,
    _topic_comment_row_with_images,
    _topic_detail_insert_params,
    _topic_detail_insert_statement,
    _topic_detail_exists_query,
    _topic_detail_query,
    _topic_detail_row_to_dict,
    _topic_file_insert_params,
    _topic_file_insert_statement,
    _topic_files_query,
    _topic_file_row_to_dict,
    _topic_image_insert_params,
    _topic_image_insert_statement,
    _topic_images_query,
    _topic_image_row_to_dict,
    _topic_owner_insert_params,
    _topic_owner_insert_statement,
    _topic_video_insert_params,
    _topic_video_insert_statement,
    _topic_videos_query,
    _topic_video_row_to_dict,
    _topic_group_id_query,
    _topic_child_delete_statements,
    _uncached_image_row_to_dict,
    _uncached_images_query,
    _user_insert_params,
    _user_insert_statement,
    _video_cover_path_update,
    _video_download_status_update,
)


class ZSXQColumnsDatabaseHelperTests(unittest.TestCase):
    def _sql(self, sql):
        return " ".join(sql.split())

    def test_columns_database_scope_group_id_param_prefers_explicit_then_instance_group(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        db = object.__new__(ZSXQColumnsDatabase)
        db.group_id = "303"

        self.assertEqual(404, ZSXQColumnsDatabase._scope_group_id_param(db, "404"))
        self.assertEqual(303, ZSXQColumnsDatabase._scope_group_id_param(db, None))
        db.group_id = ""
        self.assertIsNone(ZSXQColumnsDatabase._scope_group_id_param(db, None))

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

    def test_comment_image_row_to_dict_preserves_nested_image_shape_without_local_path(self):
        row = (
            402,
            "image",
            "comment-thumb-url",
            100,
            66,
            "comment-large-url",
            900,
            600,
            "comment-original-url",
            1800,
            1200,
            1024,
        )

        self.assertEqual(
            _comment_image_row_to_dict(row),
            {
                "image_id": 402,
                "type": "image",
                "thumbnail": {
                    "url": "comment-thumb-url",
                    "width": 100,
                    "height": 66,
                },
                "large": {
                    "url": "comment-large-url",
                    "width": 900,
                    "height": 600,
                },
                "original": {
                    "url": "comment-original-url",
                    "width": 1800,
                    "height": 1200,
                    "size": 1024,
                },
            },
        )

    def test_topic_file_row_to_dict_preserves_file_shape(self):
        row = (
            501,
            "report.pdf",
            "file-hash",
            4096,
            120,
            7,
            "2026-05-01T08:00:00+0800",
            "downloaded",
            "downloads/report.pdf",
            "2026-05-02 12:00:00",
        )

        self.assertEqual(
            _topic_file_row_to_dict(row),
            {
                "file_id": 501,
                "name": "report.pdf",
                "hash": "file-hash",
                "size": 4096,
                "duration": 120,
                "download_count": 7,
                "create_time": "2026-05-01T08:00:00+0800",
                "download_status": "downloaded",
                "local_path": "downloads/report.pdf",
                "download_time": "2026-05-02 12:00:00",
            },
        )

    def test_topic_video_row_to_dict_preserves_cover_shape(self):
        row = (
            601,
            8192,
            300,
            "cover-url",
            320,
            180,
            "cache/cover.jpg",
            "video-url",
            "pending",
            "downloads/video.mp4",
            "2026-05-03 12:00:00",
        )

        self.assertEqual(
            _topic_video_row_to_dict(row),
            {
                "video_id": 601,
                "size": 8192,
                "duration": 300,
                "cover": {
                    "url": "cover-url",
                    "width": 320,
                    "height": 180,
                    "local_path": "cache/cover.jpg",
                },
                "video_url": "video-url",
                "download_status": "pending",
                "local_path": "downloads/video.mp4",
                "download_time": "2026-05-03 12:00:00",
            },
        )

    def test_pending_video_row_to_dict_preserves_download_queue_shape(self):
        row = (
            602,
            202,
            8192,
            300,
            "cover-url",
            303,
        )

        self.assertEqual(
            _pending_video_row_to_dict(row),
            {
                "video_id": 602,
                "topic_id": 202,
                "size": 8192,
                "duration": 300,
                "cover_url": "cover-url",
                "group_id": 303,
            },
        )

    def test_pending_file_row_to_dict_preserves_download_queue_shape(self):
        row = (
            502,
            202,
            "report.pdf",
            4096,
            "file-hash",
            303,
        )

        self.assertEqual(
            _pending_file_row_to_dict(row),
            {
                "file_id": 502,
                "topic_id": 202,
                "name": "report.pdf",
                "size": 4096,
                "hash": "file-hash",
                "group_id": 303,
            },
        )

    def test_uncached_image_row_to_dict_preserves_cache_queue_shape(self):
        row = (
            403,
            202,
            "original-url",
            303,
        )

        self.assertEqual(
            _uncached_image_row_to_dict(row),
            {
                "image_id": 403,
                "topic_id": 202,
                "original_url": "original-url",
                "group_id": 303,
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

    def test_topic_comment_row_to_dict_preserves_owner_and_repliee_shape(self):
        row = (
            701,
            700,
            "comment text",
            "2026-05-01T08:00:00+0800",
            5,
            6,
            7,
            1,
            801,
            "owner name",
            "owner alias",
            "owner-avatar",
            "owner location",
            901,
            "repliee name",
            "repliee alias",
            "repliee-avatar",
        )

        self.assertEqual(
            _topic_comment_row_to_dict(row),
            {
                "comment_id": 701,
                "parent_comment_id": 700,
                "text": "comment text",
                "create_time": "2026-05-01T08:00:00+0800",
                "likes_count": 5,
                "rewards_count": 6,
                "replies_count": 7,
                "sticky": True,
                "owner": {
                    "user_id": 801,
                    "name": "owner name",
                    "alias": "owner alias",
                    "avatar_url": "owner-avatar",
                    "location": "owner location",
                },
                "repliee": {
                    "user_id": 901,
                    "name": "repliee name",
                    "alias": "repliee alias",
                    "avatar_url": "repliee-avatar",
                },
            },
        )

    def test_topic_comment_row_with_images_preserves_truthy_image_field_semantics(self):
        row = (
            701,
            None,
            "comment text",
            "2026-05-01T08:00:00+0800",
            5,
            6,
            7,
            False,
            801,
            "owner name",
            "owner alias",
            "owner-avatar",
            "owner location",
            None,
            None,
            None,
            None,
        )
        image = {"image_id": 301}

        without_images = _topic_comment_row_with_images(row, [])
        with_images = _topic_comment_row_with_images(row, [image])

        self.assertNotIn("images", without_images)
        self.assertEqual([image], with_images["images"])

    def test_column_insert_params_preserve_column_order_and_defaults(self):
        self.assertEqual(
            (
                101,
                303,
                "column name",
                "cover-url",
                9,
                "2026-06-10T10:00:00",
                "2026-06-10T11:00:00",
            ),
            _column_insert_params(
                303,
                {
                    "column_id": 101,
                    "name": "column name",
                    "cover_url": "cover-url",
                    "statistics": {"topics_count": 9},
                    "create_time": "2026-06-10T10:00:00",
                    "last_topic_attach_time": "2026-06-10T11:00:00",
                },
            ),
        )
        self.assertEqual(
            (101, 303, "", None, 0, None, None),
            _column_insert_params(303, {"column_id": 101}),
        )

    def test_column_insert_statement_preserves_upsert_shape(self):
        sql = self._sql(_column_insert_statement())

        self.assertIn("INSERT INTO columns", sql)
        self.assertIn(
            "(column_id, group_id, name, cover_url, topics_count, create_time, last_topic_attach_time)",
            sql,
        )
        self.assertIn("VALUES (?, ?, ?, ?, ?, ?, ?)", sql)
        self.assertIn("ON CONFLICT(column_id) DO UPDATE SET", sql)
        self.assertIn("last_topic_attach_time = excluded.last_topic_attach_time", sql)

    def test_column_topic_and_user_insert_params_preserve_column_order_and_defaults(self):
        self.assertEqual(
            (
                202,
                101,
                303,
                "topic title",
                "topic text",
                "2026-06-10T12:00:00",
                "2026-06-10T13:00:00",
            ),
            _column_topic_insert_params(
                101,
                303,
                {
                    "topic_id": 202,
                    "title": "topic title",
                    "text": "topic text",
                    "create_time": "2026-06-10T12:00:00",
                    "attached_to_column_time": "2026-06-10T13:00:00",
                },
            ),
        )
        self.assertEqual(
            (202, 101, 303, None, None, None, None),
            _column_topic_insert_params(101, 303, {"topic_id": 202}),
        )
        self.assertEqual(
            (801, "user name", "alias", "avatar-url", "description", "location"),
            _user_insert_params(
                {
                    "user_id": 801,
                    "name": "user name",
                    "alias": "alias",
                    "avatar_url": "avatar-url",
                    "description": "description",
                    "location": "location",
                },
            ),
        )
        self.assertEqual(
            (801, "", None, None, None, None),
            _user_insert_params({"user_id": 801}),
        )

    def test_column_topic_and_user_insert_statements_preserve_upsert_shape(self):
        topic_sql = self._sql(_column_topic_insert_statement())
        user_sql = self._sql(_user_insert_statement())

        self.assertIn("INSERT INTO column_topics", topic_sql)
        self.assertIn(
            "(topic_id, column_id, group_id, title, text, create_time, attached_to_column_time)",
            topic_sql,
        )
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", topic_sql)
        self.assertIn("attached_to_column_time = excluded.attached_to_column_time", topic_sql)

        self.assertIn("INSERT INTO users", user_sql)
        self.assertIn("(user_id, name, alias, avatar_url, description, location)", user_sql)
        self.assertIn("VALUES (?, ?, ?, ?, ?, ?)", user_sql)
        self.assertIn("ON CONFLICT(user_id) DO UPDATE SET", user_sql)
        self.assertIn("location = excluded.location", user_sql)

    def test_topic_detail_insert_params_preserve_column_order_and_defaults(self):
        self.assertEqual(
            (
                202,
                303,
                "talk",
                "topic title",
                "full text",
                5,
                6,
                7,
                True,
                True,
                "2026-06-10T14:00:00",
                "2026-06-10T15:00:00",
                '{"raw": true}',
            ),
            _topic_detail_insert_params(
                303,
                {
                    "topic_id": 202,
                    "type": "talk",
                    "title": "topic title",
                    "talk": {"text": "full text"},
                    "likes_count": 5,
                    "comments_count": 6,
                    "readers_count": 7,
                    "digested": True,
                    "sticky": True,
                    "create_time": "2026-06-10T14:00:00",
                    "modify_time": "2026-06-10T15:00:00",
                },
                '{"raw": true}',
            ),
        )
        self.assertEqual(
            (202, 303, None, None, "", 0, 0, 0, False, False, None, None, None),
            _topic_detail_insert_params(303, {"topic_id": 202}, None),
        )

    def test_topic_detail_insert_statement_preserves_upsert_shape(self):
        sql = self._sql(_topic_detail_insert_statement())

        self.assertIn("INSERT INTO topic_details", sql)
        self.assertIn(
            "(topic_id, group_id, type, title, full_text, likes_count, comments_count, readers_count, digested, sticky, create_time, modify_time, raw_json, updated_at)",
            sql,
        )
        self.assertIn("VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", sql)
        self.assertIn("raw_json = excluded.raw_json", sql)
        self.assertIn("updated_at = excluded.updated_at", sql)

    def test_topic_owner_insert_params_preserve_column_order(self):
        self.assertEqual((202, 801), _topic_owner_insert_params(202, 801))

    def test_topic_owner_insert_statement_preserves_owner_type_and_upsert_shape(self):
        sql = self._sql(_topic_owner_insert_statement())

        self.assertIn("INSERT INTO topic_owners (topic_id, user_id, owner_type)", sql)
        self.assertIn("VALUES (?, ?, 'talk')", sql)
        self.assertIn("ON CONFLICT(topic_id, owner_type) DO UPDATE SET", sql)
        self.assertIn("user_id = excluded.user_id", sql)

    def test_topic_media_insert_params_preserve_column_order_and_defaults(self):
        self.assertEqual(
            (
                301,
                202,
                "png",
                "thumb-url",
                100,
                80,
                "large-url",
                1000,
                800,
                "original-url",
                1200,
                900,
                4567,
            ),
            _topic_image_insert_params(
                202,
                {
                    "image_id": 301,
                    "type": "png",
                    "thumbnail": {"url": "thumb-url", "width": 100, "height": 80},
                    "large": {"url": "large-url", "width": 1000, "height": 800},
                    "original": {"url": "original-url", "width": 1200, "height": 900, "size": 4567},
                },
            ),
        )
        self.assertEqual(
            (301, 202, None, None, None, None, None, None, None, None, None, None, None),
            _topic_image_insert_params(202, {"image_id": 301}),
        )
        self.assertEqual(
            (401, 202, "memo.pdf", "abc", 2048, 3, 4, "2026-06-10T12:00:00"),
            _topic_file_insert_params(
                202,
                {
                    "file_id": 401,
                    "name": "memo.pdf",
                    "hash": "abc",
                    "size": 2048,
                    "duration": 3,
                    "download_count": 4,
                    "create_time": "2026-06-10T12:00:00",
                },
            ),
        )
        self.assertEqual(
            (401, 202, "", None, None, None, 0, None),
            _topic_file_insert_params(202, {"file_id": 401}),
        )
        self.assertEqual(
            (501, 202, 4096, 60, "cover-url", 640, 360),
            _topic_video_insert_params(
                202,
                {
                    "video_id": 501,
                    "size": 4096,
                    "duration": 60,
                    "cover": {"url": "cover-url", "width": 640, "height": 360},
                },
            ),
        )
        self.assertEqual(
            (501, 202, None, None, None, None, None),
            _topic_video_insert_params(202, {"video_id": 501}),
        )

    def test_topic_media_insert_statements_preserve_upsert_shape(self):
        image_sql = self._sql(_topic_image_insert_statement())
        file_sql = self._sql(_topic_file_insert_statement())
        video_sql = self._sql(_topic_video_insert_statement())

        self.assertIn("INSERT INTO images", image_sql)
        self.assertIn(
            "(image_id, topic_id, type, thumbnail_url, thumbnail_width, thumbnail_height, large_url, large_width, large_height, original_url, original_width, original_height, original_size)",
            image_sql,
        )
        self.assertIn("ON CONFLICT(image_id) DO UPDATE SET", image_sql)
        self.assertIn("original_size = excluded.original_size", image_sql)

        self.assertIn("INSERT INTO files", file_sql)
        self.assertIn("(file_id, topic_id, name, hash, size, duration, download_count, create_time)", file_sql)
        self.assertIn("ON CONFLICT(file_id) DO UPDATE SET", file_sql)
        self.assertIn("create_time = excluded.create_time", file_sql)

        self.assertIn("INSERT INTO videos", video_sql)
        self.assertIn("(video_id, topic_id, size, duration, cover_url, cover_width, cover_height)", video_sql)
        self.assertIn("ON CONFLICT(video_id) DO UPDATE SET", video_sql)
        self.assertIn("cover_height = excluded.cover_height", video_sql)

    def test_topic_comment_insert_params_preserve_column_order_and_defaults(self):
        self.assertEqual(
            (
                701,
                303,
                202,
                801,
                700,
                901,
                "comment text",
                "2026-06-10T12:00:00",
                5,
                6,
                7,
                True,
            ),
            _topic_comment_insert_params(
                202,
                303,
                801,
                901,
                {
                    "comment_id": 701,
                    "parent_comment_id": 700,
                    "text": "comment text",
                    "create_time": "2026-06-10T12:00:00",
                    "likes_count": 5,
                    "rewards_count": 6,
                    "replies_count": 7,
                    "sticky": True,
                },
            ),
        )
        self.assertEqual(
            (701, None, 202, None, None, None, "", None, 0, 0, 0, False),
            _topic_comment_insert_params(202, None, None, None, {"comment_id": 701}),
        )

    def test_topic_comment_insert_statement_preserves_upsert_shape(self):
        sql = self._sql(_topic_comment_insert_statement())

        self.assertIn("INSERT INTO comments", sql)
        self.assertIn(
            "(comment_id, group_id, topic_id, owner_user_id, parent_comment_id, repliee_user_id, text, create_time, likes_count, rewards_count, replies_count, sticky)",
            sql,
        )
        self.assertIn("VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", sql)
        self.assertIn("ON CONFLICT(comment_id) DO UPDATE SET", sql)
        self.assertIn("repliee_user_id = excluded.repliee_user_id", sql)
        self.assertIn("sticky = excluded.sticky", sql)

    def test_nest_topic_comments_preserves_existing_nested_shape(self):
        parent = {"comment_id": 1, "parent_comment_id": None, "text": "parent"}
        child_before_parent = {"comment_id": 2, "parent_comment_id": 1, "text": "reply-a"}
        parent_later = {"comment_id": 3, "parent_comment_id": None, "text": "parent-later"}
        child_after_parent = {"comment_id": 4, "parent_comment_id": 3, "text": "reply-b"}
        orphan_child = {"comment_id": 5, "parent_comment_id": 999, "text": "orphan"}

        nested = _nest_topic_comments(
            [
                child_before_parent,
                parent,
                orphan_child,
                parent_later,
                child_after_parent,
            ]
        )

        self.assertEqual([parent, parent_later], nested)
        self.assertEqual([child_before_parent], parent["replied_comments"])
        self.assertEqual([child_after_parent], parent_later["replied_comments"])
        self.assertNotIn(orphan_child, nested)

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

    def test_stats_count_queries_preserve_order_and_group_filter(self):
        queries = _stats_count_queries(303)

        self.assertEqual(
            [key for key, _, _ in queries],
            [
                "columns_count",
                "topics_count",
                "details_count",
                "images_count",
                "files_count",
                "files_downloaded",
                "videos_count",
                "videos_downloaded",
                "comments_count",
            ],
        )
        self.assertTrue(all(params == (303,) for _, _, params in queries))
        self.assertIn("FROM columns WHERE group_id = ?", self._sql(queries[0][1]))
        self.assertIn("FROM column_topics WHERE group_id = ?", self._sql(queries[1][1]))
        self.assertIn("FROM topic_details WHERE group_id = ?", self._sql(queries[2][1]))
        self.assertIn("FROM images i JOIN topic_details td ON i.topic_id = td.topic_id", self._sql(queries[3][1]))
        self.assertIn("FROM files f JOIN topic_details td ON f.topic_id = td.topic_id", self._sql(queries[4][1]))
        self.assertIn("f.download_status = 'completed'", self._sql(queries[5][1]))
        self.assertIn("FROM videos v JOIN topic_details td ON v.topic_id = td.topic_id", self._sql(queries[6][1]))
        self.assertIn("v.download_status = 'completed'", self._sql(queries[7][1]))
        self.assertIn("FROM comments c JOIN topic_details td ON c.topic_id = td.topic_id", self._sql(queries[8][1]))

    def test_get_stats_preserves_count_result_shape(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.next_count = 1

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

            def fetchone(self):
                count = self.next_count
                self.next_count += 1
                return (count,)

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()

        self.assertEqual(
            ZSXQColumnsDatabase.get_stats(db, 303),
            {
                "columns_count": 1,
                "topics_count": 2,
                "details_count": 3,
                "images_count": 4,
                "files_count": 5,
                "files_downloaded": 6,
                "videos_count": 7,
                "videos_downloaded": 8,
                "comments_count": 9,
            },
        )
        self.assertEqual(len(db.cursor.calls), 9)
        self.assertTrue(all(params == (303,) for _, params in db.cursor.calls))

    def test_crawl_log_update_parts_preserve_field_and_value_order(self):
        updates, values = _crawl_log_update_parts(
            columns_count=1,
            topics_count=2,
            details_count=3,
            files_count=4,
            status="completed",
            error_message="done",
        )

        self.assertEqual(
            [
                "columns_count = ?",
                "topics_count = ?",
                "details_count = ?",
                "files_count = ?",
                "status = ?",
                "end_time = CURRENT_TIMESTAMP",
                "error_message = ?",
            ],
            updates,
        )
        self.assertEqual([1, 2, 3, 4, "completed", "done"], values)

    def test_crawl_log_update_parts_preserve_falsy_update_semantics(self):
        updates, values = _crawl_log_update_parts(
            columns_count=0,
            topics_count=0,
            details_count=0,
            files_count=0,
            status="",
            error_message="",
        )

        self.assertEqual([], updates)
        self.assertEqual([], values)

        running_updates, running_values = _crawl_log_update_parts(status="running")
        self.assertEqual(["status = ?"], running_updates)
        self.assertEqual(["running"], running_values)

    def test_crawl_log_insert_statement_preserves_returning_id_shape(self):
        sql = self._sql(_crawl_log_insert_statement())

        self.assertIn("INSERT INTO crawl_log (group_id, crawl_type)", sql)
        self.assertIn("VALUES (?, ?)", sql)
        self.assertIn("RETURNING id", sql)

    def test_crawl_log_update_statement_preserves_dynamic_set_shape(self):
        updates = [
            "columns_count = ?",
            "topics_count = ?",
            "status = ?",
            "end_time = CURRENT_TIMESTAMP",
        ]
        sql = self._sql(_crawl_log_update_statement(updates))

        self.assertEqual(
            "UPDATE crawl_log SET columns_count = ?, topics_count = ?, status = ?, "
            "end_time = CURRENT_TIMESTAMP WHERE id = ?",
            sql,
        )

    def test_clear_data_helpers_preserve_stats_and_topic_delete_order(self):
        first = _empty_clear_data_stats()
        second = _empty_clear_data_stats()
        first["comments_deleted"] = 9

        self.assertEqual(second["comments_deleted"], 0)
        self.assertEqual(
            [
                "columns_deleted",
                "topics_deleted",
                "details_deleted",
                "images_deleted",
                "files_deleted",
                "videos_deleted",
                "comments_deleted",
                "users_deleted",
            ],
            list(second),
        )

        statements = _topic_child_delete_statements("?,?")
        self.assertEqual(
            ["comments_deleted", "videos_deleted", "files_deleted", "images_deleted", None],
            [stat_key for stat_key, _ in statements],
        )
        self.assertIn("DELETE FROM comments WHERE topic_id IN (?,?)", statements[0][1])
        self.assertIn("DELETE FROM videos WHERE topic_id IN (?,?)", statements[1][1])
        self.assertIn("DELETE FROM files WHERE topic_id IN (?,?)", statements[2][1])
        self.assertIn("DELETE FROM images WHERE topic_id IN (?,?)", statements[3][1])
        self.assertIn("DELETE FROM topic_owners WHERE topic_id IN (?,?)", statements[4][1])

        group_statements = _group_clear_delete_statements()
        self.assertEqual(
            ["details_deleted", "topics_deleted", "columns_deleted", None],
            [stat_key for stat_key, _ in group_statements],
        )
        self.assertEqual("DELETE FROM topic_details WHERE group_id = ?", group_statements[0][1])
        self.assertEqual("DELETE FROM column_topics WHERE group_id = ?", group_statements[1][1])
        self.assertEqual("DELETE FROM columns WHERE group_id = ?", group_statements[2][1])
        self.assertEqual("DELETE FROM crawl_log WHERE group_id = ?", group_statements[3][1])

    def test_incremental_select_query_helpers_preserve_sql_and_params(self):
        group_sql, group_params = _topic_group_id_query(202)
        self.assertEqual("SELECT group_id FROM topic_details WHERE topic_id = ? LIMIT 1", group_sql)
        self.assertEqual((202,), group_params)

        exists_sql, exists_params = _topic_detail_exists_query(202)
        self.assertEqual("SELECT 1 FROM topic_details WHERE topic_id = ?", exists_sql)
        self.assertEqual((202,), exists_params)

        topic_ids_sql, topic_ids_params = _group_topic_ids_query(303)
        self.assertEqual("SELECT topic_id FROM topic_details WHERE group_id = ?", topic_ids_sql)
        self.assertEqual((303,), topic_ids_params)

    def test_pending_queue_queries_preserve_group_filter_branches(self):
        video_sql, video_params = _pending_videos_query(303)
        file_sql, file_params = _pending_files_query(303)
        image_sql, image_params = _uncached_images_query(303)

        self.assertIn("WHERE v.download_status = 'pending' AND td.group_id = ?", self._sql(video_sql))
        self.assertEqual((303,), video_params)
        self.assertIn("WHERE f.download_status = 'pending' AND td.group_id = ?", self._sql(file_sql))
        self.assertEqual((303,), file_params)
        self.assertIn(
            "WHERE i.local_path IS NULL AND i.original_url IS NOT NULL AND td.group_id = ?",
            self._sql(image_sql),
        )
        self.assertEqual((303,), image_params)

    def test_pending_queue_queries_preserve_unscoped_branches(self):
        video_sql, video_params = _pending_videos_query(None)
        file_sql, file_params = _pending_files_query(None)
        image_sql, image_params = _uncached_images_query(None)

        self.assertIn("WHERE v.download_status = 'pending'", self._sql(video_sql))
        self.assertNotIn("AND td.group_id = ?", self._sql(video_sql))
        self.assertIsNone(video_params)
        self.assertIn("WHERE f.download_status = 'pending'", self._sql(file_sql))
        self.assertNotIn("AND td.group_id = ?", self._sql(file_sql))
        self.assertIsNone(file_params)
        self.assertIn("WHERE i.local_path IS NULL AND i.original_url IS NOT NULL", self._sql(image_sql))
        self.assertNotIn("AND td.group_id = ?", self._sql(image_sql))
        self.assertIsNone(image_params)

    def test_pending_queue_methods_preserve_execute_arity_and_row_shapes(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.fetchall_results = [
                    [(501, 202, 4096, 30, "cover-url", 303)],
                    [(401, 202, "file.pdf", 8192, "hash", 304)],
                    [(301, 202, "original-url", 305)],
                ]

            def execute(self, *args):
                self.calls.append(args)

            def fetchall(self):
                return self.fetchall_results.pop(0)

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()

        self.assertEqual(
            [
                {
                    "video_id": 501,
                    "topic_id": 202,
                    "size": 4096,
                    "duration": 30,
                    "cover_url": "cover-url",
                    "group_id": 303,
                }
            ],
            ZSXQColumnsDatabase.get_pending_videos(db, 303),
        )
        self.assertEqual(
            [
                {
                    "file_id": 401,
                    "topic_id": 202,
                    "name": "file.pdf",
                    "size": 8192,
                    "hash": "hash",
                    "group_id": 304,
                }
            ],
            ZSXQColumnsDatabase.get_pending_files(db),
        )
        self.assertEqual(
            [
                {
                    "image_id": 301,
                    "topic_id": 202,
                    "original_url": "original-url",
                    "group_id": 305,
                }
            ],
            ZSXQColumnsDatabase.get_uncached_images(db),
        )

        self.assertEqual(2, len(db.cursor.calls[0]))
        self.assertIn("WHERE v.download_status = 'pending' AND td.group_id = ?", self._sql(db.cursor.calls[0][0]))
        self.assertEqual((303,), db.cursor.calls[0][1])
        self.assertEqual(1, len(db.cursor.calls[1]))
        self.assertIn("WHERE f.download_status = 'pending'", self._sql(db.cursor.calls[1][0]))
        self.assertNotIn("AND td.group_id = ?", self._sql(db.cursor.calls[1][0]))
        self.assertEqual(1, len(db.cursor.calls[2]))
        self.assertIn("WHERE i.local_path IS NULL AND i.original_url IS NOT NULL", self._sql(db.cursor.calls[2][0]))
        self.assertNotIn("AND td.group_id = ?", self._sql(db.cursor.calls[2][0]))

    def test_fetch_mapped_rows_preserves_optional_params_execute_arity(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.fetchall_results = [[("first",)], [("second",)]]

            def execute(self, *args):
                self.calls.append(args)

            def fetchall(self):
                return self.fetchall_results.pop(0)

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()

        mapper = lambda row: {"value": row[0]}

        self.assertEqual(
            [{"value": "first"}],
            ZSXQColumnsDatabase._fetch_mapped_rows(db, "SELECT first", None, mapper),
        )
        self.assertEqual(
            [{"value": "second"}],
            ZSXQColumnsDatabase._fetch_mapped_rows(db, "SELECT second WHERE id = ?", (202,), mapper),
        )

        self.assertEqual(("SELECT first",), db.cursor.calls[0])
        self.assertEqual(("SELECT second WHERE id = ?", (202,)), db.cursor.calls[1])

    def test_column_queries_preserve_scope_params_and_order(self):
        columns_sql, columns_params = _columns_query(303)
        self.assertIn("SELECT column_id, group_id, name, cover_url, topics_count", self._sql(columns_sql))
        self.assertIn("FROM columns WHERE group_id = ?", self._sql(columns_sql))
        self.assertIn("ORDER BY create_time DESC", self._sql(columns_sql))
        self.assertEqual((303,), columns_params)

        column_sql, column_params = _column_query(101, 303)
        self.assertIn("FROM columns WHERE column_id = ? AND (? IS NULL OR group_id = ?)", self._sql(column_sql))
        self.assertEqual((101, 303, 303), column_params)
        self.assertEqual((101, None, None), _column_query(101, None)[1])

    def test_column_topics_query_preserves_detail_join_scope_params_and_order(self):
        sql, params = _column_topics_query(101, 303)

        self.assertIn("SELECT ct.topic_id, ct.column_id, ct.group_id", self._sql(sql))
        self.assertIn("CASE WHEN td.topic_id IS NOT NULL THEN 1 ELSE 0 END as has_detail", self._sql(sql))
        self.assertIn(
            "LEFT JOIN topic_details td ON ct.topic_id = td.topic_id AND ct.group_id = td.group_id",
            self._sql(sql),
        )
        self.assertIn("WHERE ct.column_id = ? AND (? IS NULL OR ct.group_id = ?)", self._sql(sql))
        self.assertIn("ORDER BY ct.attached_to_column_time DESC", self._sql(sql))
        self.assertEqual((101, 303, 303), params)
        self.assertEqual((101, None, None), _column_topics_query(101, None)[1])

    def test_topic_attachment_queries_preserve_scope_params_and_selects(self):
        image_sql, image_params = _topic_images_query(202, 303)
        self.assertIn("SELECT image_id, type, thumbnail_url", self._sql(image_sql))
        self.assertIn("FROM images WHERE topic_id = ?", self._sql(image_sql))
        self.assertIn("topic_details WHERE group_id = ?", self._sql(image_sql))
        self.assertEqual((202, 303, 303), image_params)

        file_sql, file_params = _topic_files_query(202, 303)
        self.assertIn("SELECT file_id, name, hash, size, duration, download_count", self._sql(file_sql))
        self.assertIn("FROM files WHERE topic_id = ?", self._sql(file_sql))
        self.assertIn("topic_details WHERE group_id = ?", self._sql(file_sql))
        self.assertEqual((202, 303, 303), file_params)

        video_sql, video_params = _topic_videos_query(202, 303)
        self.assertIn("SELECT video_id, size, duration, cover_url", self._sql(video_sql))
        self.assertIn("FROM videos WHERE topic_id = ?", self._sql(video_sql))
        self.assertIn("topic_details WHERE group_id = ?", self._sql(video_sql))
        self.assertEqual((202, 303, 303), video_params)

        self.assertEqual((202, None, None), _topic_images_query(202, None)[1])
        self.assertEqual((202, None, None), _topic_files_query(202, None)[1])
        self.assertEqual((202, None, None), _topic_videos_query(202, None)[1])

    def test_topic_detail_query_preserves_owner_join_and_scope_params(self):
        sql, params = _topic_detail_query(202, 303)

        self.assertIn("SELECT td.topic_id, td.group_id, td.type", self._sql(sql))
        self.assertIn("FROM topic_details td", self._sql(sql))
        self.assertIn("LEFT JOIN topic_owners tow ON td.topic_id = tow.topic_id", self._sql(sql))
        self.assertIn("tow.owner_type = 'talk'", self._sql(sql))
        self.assertIn("LEFT JOIN users u ON tow.user_id = u.user_id", self._sql(sql))
        self.assertIn("WHERE td.topic_id = ? AND (? IS NULL OR td.group_id = ?)", self._sql(sql))
        self.assertEqual((202, 303, 303), params)
        self.assertEqual((202, None, None), _topic_detail_query(202, None)[1])

    def test_comment_images_query_preserves_topic_filter_params_and_selects(self):
        sql, params = _comment_images_query(701, 303, 202)

        self.assertIn("SELECT image_id, type, thumbnail_url", self._sql(sql))
        self.assertIn("FROM images WHERE comment_id = ?", self._sql(sql))
        self.assertIn("AND (? IS NULL OR topic_id = ?)", self._sql(sql))
        self.assertEqual((701, 303, 202), params)
        self.assertEqual((701, None, 202), _comment_images_query(701, None, 202)[1])

    def test_topic_comments_query_preserves_scope_params_joins_and_order(self):
        sql, params = _topic_comments_query(202, 303)

        self.assertIn("SELECT c.comment_id, c.parent_comment_id, c.text", self._sql(sql))
        self.assertIn("FROM comments c", self._sql(sql))
        self.assertIn("LEFT JOIN users u ON c.owner_user_id = u.user_id", self._sql(sql))
        self.assertIn("LEFT JOIN users r ON c.repliee_user_id = r.user_id", self._sql(sql))
        self.assertIn("WHERE c.topic_id = ? AND (? IS NULL OR c.group_id = ?)", self._sql(sql))
        self.assertIn("ORDER BY c.create_time ASC", self._sql(sql))
        self.assertEqual((202, 303, 303), params)
        self.assertEqual((202, None, None), _topic_comments_query(202, None)[1])

    def test_download_status_update_helpers_preserve_truthy_branches(self):
        video_sql, video_params = _video_download_status_update(501, "completed", "https://v", "local.mp4")
        self.assertIn(
            "UPDATE videos SET download_status = ?, video_url = ?, local_path = ?, download_time = CURRENT_TIMESTAMP",
            self._sql(video_sql),
        )
        self.assertEqual(("completed", "https://v", "local.mp4", 501), video_params)

        video_url_sql, video_url_params = _video_download_status_update(501, "pending", "https://v", "")
        self.assertIn("UPDATE videos SET download_status = ?, video_url = ?", self._sql(video_url_sql))
        self.assertNotIn("local_path", self._sql(video_url_sql))
        self.assertEqual(("pending", "https://v", 501), video_url_params)

        video_min_sql, video_min_params = _video_download_status_update(501, "failed", "", "")
        self.assertIn("UPDATE videos SET download_status = ?", self._sql(video_min_sql))
        self.assertNotIn("video_url", self._sql(video_min_sql))
        self.assertEqual(("failed", 501), video_min_params)

        file_path_sql, file_path_params = _file_download_status_update(401, "completed", 303, "local.pdf")
        self.assertIn(
            "UPDATE files SET download_status = ?, local_path = ?, download_time = CURRENT_TIMESTAMP",
            self._sql(file_path_sql),
        )
        self.assertEqual(("completed", "local.pdf", 401, 303, 303), file_path_params)

        file_min_sql, file_min_params = _file_download_status_update(401, "pending", None, "")
        self.assertIn("UPDATE files SET download_status = ?", self._sql(file_min_sql))
        self.assertNotIn("local_path", self._sql(file_min_sql))
        self.assertEqual(("pending", 401, None, None), file_min_params)

    def test_local_path_update_helpers_preserve_sql_and_params(self):
        video_sql, video_params = _video_cover_path_update(501, "cover.jpg")
        self.assertIn("UPDATE videos SET cover_local_path = ?", self._sql(video_sql))
        self.assertIn("WHERE video_id = ?", self._sql(video_sql))
        self.assertEqual(("cover.jpg", 501), video_params)

        image_sql, image_params = _image_local_path_update(301, "image.jpg")
        self.assertIn("UPDATE images SET local_path = ?", self._sql(image_sql))
        self.assertIn("WHERE image_id = ?", self._sql(image_sql))
        self.assertEqual(("image.jpg", 301), image_params)

    def test_download_status_methods_preserve_execute_params_and_commit(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.conn = FakeConnection()
        db.group_id = "303"

        ZSXQColumnsDatabase.update_video_download_status(db, 501, "completed", "https://v", "local.mp4")
        self.assertIn("UPDATE videos SET download_status = ?, video_url = ?, local_path = ?", db.cursor.calls[-1][0])
        self.assertEqual(("completed", "https://v", "local.mp4", 501), db.cursor.calls[-1][1])
        self.assertEqual(1, db.conn.commits)

        ZSXQColumnsDatabase.update_video_download_status(db, 502, "failed", "", "")
        self.assertIn("UPDATE videos SET download_status = ? WHERE video_id = ?", db.cursor.calls[-1][0])
        self.assertEqual(("failed", 502), db.cursor.calls[-1][1])
        self.assertEqual(2, db.conn.commits)

        ZSXQColumnsDatabase.update_file_download_status(db, 401, "completed", "local.pdf")
        self.assertIn("UPDATE files SET download_status = ?, local_path = ?", db.cursor.calls[-1][0])
        self.assertEqual(("completed", "local.pdf", 401, 303, 303), db.cursor.calls[-1][1])
        self.assertEqual(3, db.conn.commits)

        ZSXQColumnsDatabase.update_file_download_status(db, 402, "pending", "")
        self.assertIn("UPDATE files SET download_status = ? WHERE file_id = ?", db.cursor.calls[-1][0])
        self.assertEqual(("pending", 402, 303, 303), db.cursor.calls[-1][1])
        self.assertEqual(4, db.conn.commits)

    def test_local_path_update_methods_preserve_execute_params_and_commit(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.conn = FakeConnection()

        ZSXQColumnsDatabase.update_video_cover_path(db, 501, "cover.jpg")
        self.assertIn("UPDATE videos SET cover_local_path = ? WHERE video_id = ?", db.cursor.calls[-1][0])
        self.assertEqual(("cover.jpg", 501), db.cursor.calls[-1][1])
        self.assertEqual(1, db.conn.commits)

        ZSXQColumnsDatabase.update_image_local_path(db, 301, "image.jpg")
        self.assertIn("UPDATE images SET local_path = ? WHERE image_id = ?", db.cursor.calls[-1][0])
        self.assertEqual(("image.jpg", 301), db.cursor.calls[-1][1])
        self.assertEqual(2, db.conn.commits)

    def test_incremental_select_methods_preserve_execute_params_and_fetch_shape(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.fetchone_results = [(1,), None]
                self.fetchall_result = [(10,), (11,)]

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

            def fetchone(self):
                return self.fetchone_results.pop(0)

            def fetchall(self):
                return self.fetchall_result

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()

        self.assertTrue(ZSXQColumnsDatabase.topic_detail_exists(db, 202))
        self.assertEqual(("SELECT 1 FROM topic_details WHERE topic_id = ?", (202,)), db.cursor.calls[-1])

        self.assertFalse(ZSXQColumnsDatabase.topic_detail_exists(db, 203))
        self.assertEqual(("SELECT 1 FROM topic_details WHERE topic_id = ?", (203,)), db.cursor.calls[-1])

        self.assertEqual({10, 11}, ZSXQColumnsDatabase.get_existing_topic_ids(db, 303))
        self.assertEqual(("SELECT topic_id FROM topic_details WHERE group_id = ?", (303,)), db.cursor.calls[-1])

    def test_fetch_group_topic_ids_preserves_query_params_order_and_empty_shape(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.fetchall_results = [
                    [(10,), (11,)],
                    [],
                ]

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))

            def fetchall(self):
                return self.fetchall_results.pop(0)

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()

        self.assertEqual([10, 11], ZSXQColumnsDatabase._fetch_group_topic_ids(db, 303))
        self.assertEqual(("SELECT topic_id FROM topic_details WHERE group_id = ?", (303,)), db.cursor.calls[-1])

        self.assertEqual([], ZSXQColumnsDatabase._fetch_group_topic_ids(db, 304))
        self.assertEqual(("SELECT topic_id FROM topic_details WHERE group_id = ?", (304,)), db.cursor.calls[-1])

    def test_resolve_topic_group_id_preserves_scope_lookup_and_exception_fallback(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self, row=None, raises=False):
                self.calls = []
                self.row = row
                self.raises = raises

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                if self.raises:
                    raise RuntimeError("temporary storage failure")
                return self

            def fetchone(self):
                return self.row

        scoped_db = object.__new__(ZSXQColumnsDatabase)
        scoped_db.cursor = FakeCursor((999,))
        scoped_db.group_id = "303"
        self.assertEqual(303, ZSXQColumnsDatabase._resolve_topic_group_id(scoped_db, 202))
        self.assertEqual([], scoped_db.cursor.calls)

        lookup_db = object.__new__(ZSXQColumnsDatabase)
        lookup_db.cursor = FakeCursor((303,))
        lookup_db.group_id = None
        self.assertEqual(303, ZSXQColumnsDatabase._resolve_topic_group_id(lookup_db, 202))
        self.assertEqual(
            [("SELECT group_id FROM topic_details WHERE topic_id = ? LIMIT 1", (202,))],
            lookup_db.cursor.calls,
        )

        missing_db = object.__new__(ZSXQColumnsDatabase)
        missing_db.cursor = FakeCursor(None)
        missing_db.group_id = None
        self.assertIsNone(ZSXQColumnsDatabase._resolve_topic_group_id(missing_db, 202))

        failing_db = object.__new__(ZSXQColumnsDatabase)
        failing_db.cursor = FakeCursor(raises=True)
        failing_db.group_id = None
        self.assertIsNone(ZSXQColumnsDatabase._resolve_topic_group_id(failing_db, 202))

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
        self.assertEqual((101, 303, 202, 9, None, None, "ok", None, 0, 0, 0, False), params)

    def test_insert_comment_preserves_user_upsert_order_and_falsey_skip(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append(("execute", " ".join(sql.split()), params))
                return self

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        calls = []

        def insert_user(user):
            calls.append(("insert_user", user))
            return user.get("user_id")

        def resolve_topic_group_id(topic_id):
            calls.append(("resolve_group", topic_id))
            return 303

        db.insert_user = insert_user
        db._resolve_topic_group_id = resolve_topic_group_id

        self.assertIsNone(
            ZSXQColumnsDatabase._insert_comment(
                db,
                202,
                {
                    "comment_id": 701,
                    "owner": {"user_id": 801, "name": "owner"},
                    "repliee": {"user_id": 901, "name": "repliee"},
                    "text": "comment text",
                },
            )
        )

        self.assertEqual(
            [
                ("insert_user", {"user_id": 801, "name": "owner"}),
                ("insert_user", {"user_id": 901, "name": "repliee"}),
                ("resolve_group", 202),
            ],
            calls,
        )
        sql_call = db.cursor.calls[-1]
        self.assertEqual("execute", sql_call[0])
        self.assertIn("INSERT INTO comments", sql_call[1])
        self.assertEqual(
            (701, 303, 202, 801, None, 901, "comment text", None, 0, 0, 0, False),
            sql_call[2],
        )

        db.cursor = FakeCursor()
        calls = []
        self.assertIsNone(
            ZSXQColumnsDatabase._insert_comment(
                db,
                202,
                {"comment_id": 702, "owner": {}, "repliee": None},
            )
        )
        self.assertEqual([("resolve_group", 202)], calls)
        self.assertEqual(
            (702, 303, 202, None, None, None, "", None, 0, 0, 0, False),
            db.cursor.calls[-1][2],
        )

    def test_iter_topic_comment_user_payloads_preserves_owner_repliee_order(self):
        self.assertEqual([], list(_iter_topic_comment_user_payloads({})))
        self.assertEqual(
            [],
            list(_iter_topic_comment_user_payloads({"owner": {}, "repliee": None})),
        )

        comment = {
            "owner": {"user_id": 801, "name": "owner"},
            "repliee": {"user_id": 901, "name": "repliee"},
        }

        self.assertEqual(
            [
                ("owner", comment["owner"]),
                ("repliee", comment["repliee"]),
            ],
            list(_iter_topic_comment_user_payloads(comment)),
        )

    def test_import_comments_preserves_order_parent_mutation_and_commit(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        empty_db = object.__new__(ZSXQColumnsDatabase)
        empty_db.conn = FakeConnection()
        empty_calls = []
        empty_db._insert_comment = lambda topic_id, comment: empty_calls.append((topic_id, comment))

        self.assertEqual(0, ZSXQColumnsDatabase.import_comments(empty_db, 202, []))
        self.assertEqual([], empty_calls)
        self.assertEqual(0, empty_db.conn.commits)

        db = object.__new__(ZSXQColumnsDatabase)
        db.conn = FakeConnection()
        inserted = []
        db._insert_comment = lambda topic_id, comment: inserted.append((topic_id, comment))

        comments = [
            {
                "comment_id": 701,
                "text": "parent",
                "replied_comments": [
                    {"comment_id": 702, "text": "reply without parent"},
                    {"comment_id": 703, "parent_comment_id": 999, "text": "reply with parent"},
                ],
            },
            {
                "comment_id": 704,
                "text": "second parent",
                "replied_comments": [],
            },
        ]

        self.assertEqual(4, ZSXQColumnsDatabase.import_comments(db, 202, comments))

        self.assertEqual(
            [
                (202, comments[0]),
                (202, comments[0]["replied_comments"][0]),
                (202, comments[0]["replied_comments"][1]),
                (202, comments[1]),
            ],
            inserted,
        )
        self.assertEqual(701, comments[0]["replied_comments"][0]["parent_comment_id"])
        self.assertEqual(999, comments[0]["replied_comments"][1]["parent_comment_id"])
        self.assertEqual(1, db.conn.commits)

    def test_iter_topic_comment_import_payloads_preserves_order_and_parent_mutation(self):
        comments = [
            {
                "comment_id": 701,
                "replied_comments": [
                    {"comment_id": 702},
                    {"comment_id": 703, "parent_comment_id": 999},
                ],
            },
            {"comment_id": 704},
        ]

        self.assertEqual(
            [
                comments[0],
                comments[0]["replied_comments"][0],
                comments[0]["replied_comments"][1],
                comments[1],
            ],
            list(_iter_topic_comment_import_payloads(comments)),
        )
        self.assertEqual(701, comments[0]["replied_comments"][0]["parent_comment_id"])
        self.assertEqual(999, comments[0]["replied_comments"][1]["parent_comment_id"])
        self.assertEqual([], list(_iter_topic_comment_import_payloads([])))

    def test_insert_media_and_comment_helpers_preserve_missing_id_skip_behavior(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()

        self.assertIsNone(ZSXQColumnsDatabase._insert_image(db, 202, {}))
        self.assertIsNone(ZSXQColumnsDatabase._insert_file(db, 202, {}))
        self.assertIsNone(ZSXQColumnsDatabase._insert_video(db, 202, {}))
        self.assertIsNone(ZSXQColumnsDatabase._insert_comment(db, 202, {}))
        self.assertEqual([], db.cursor.calls)

    def test_column_topic_and_user_insert_methods_preserve_skip_params_and_commit(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.conn = FakeConnection()

        self.assertIsNone(ZSXQColumnsDatabase.insert_column(db, 303, {}))
        self.assertEqual([], db.cursor.calls)
        self.assertEqual(0, db.conn.commits)

        self.assertEqual(
            101,
            ZSXQColumnsDatabase.insert_column(
                db,
                303,
                {
                    "column_id": 101,
                    "name": "column name",
                    "statistics": {"topics_count": 9},
                },
            ),
        )
        column_sql, column_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO columns", column_sql)
        self.assertIn("ON CONFLICT(column_id) DO UPDATE SET", column_sql)
        self.assertEqual((101, 303, "column name", None, 9, None, None), column_params)
        self.assertEqual(1, db.conn.commits)

        calls_after_column = list(db.cursor.calls)
        self.assertIsNone(ZSXQColumnsDatabase.insert_column_topic(db, 101, 303, {}))
        self.assertEqual(calls_after_column, db.cursor.calls)
        self.assertEqual(1, db.conn.commits)

        self.assertEqual(
            202,
            ZSXQColumnsDatabase.insert_column_topic(
                db,
                101,
                303,
                {"topic_id": 202, "title": "topic title", "text": "topic text"},
            ),
        )
        topic_sql, topic_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO column_topics", topic_sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", topic_sql)
        self.assertEqual((202, 101, 303, "topic title", "topic text", None, None), topic_params)
        self.assertEqual(2, db.conn.commits)

        calls_after_topic = list(db.cursor.calls)
        self.assertIsNone(ZSXQColumnsDatabase.insert_user(db, {}))
        self.assertEqual(calls_after_topic, db.cursor.calls)
        self.assertEqual(2, db.conn.commits)

        self.assertEqual(
            801,
            ZSXQColumnsDatabase.insert_user(db, {"user_id": 801, "name": "user name"}),
        )
        user_sql, user_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO users", user_sql)
        self.assertIn("ON CONFLICT(user_id) DO UPDATE SET", user_sql)
        self.assertEqual((801, "user name", None, None, None, None), user_params)
        self.assertEqual(2, db.conn.commits)

    def test_topic_detail_insert_method_preserves_skip_params_and_commit(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.conn = FakeConnection()

        self.assertIsNone(ZSXQColumnsDatabase.insert_topic_detail(db, 303, {}))
        self.assertEqual([], db.cursor.calls)
        self.assertEqual(0, db.conn.commits)

        self.assertEqual(
            202,
            ZSXQColumnsDatabase.insert_topic_detail(
                db,
                303,
                {
                    "topic_id": 202,
                    "type": "talk",
                    "title": "topic title",
                    "talk": {"text": "full text"},
                    "likes_count": 5,
                    "comments_count": 6,
                    "readers_count": 7,
                    "digested": True,
                    "sticky": True,
                    "create_time": "2026-06-10T14:00:00",
                    "modify_time": "2026-06-10T15:00:00",
                },
                '{"raw": true}',
            ),
        )

        detail_sql, detail_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO topic_details", detail_sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", detail_sql)
        self.assertEqual(
            (
                202,
                303,
                "talk",
                "topic title",
                "full text",
                5,
                6,
                7,
                True,
                True,
                "2026-06-10T14:00:00",
                "2026-06-10T15:00:00",
                '{"raw": true}',
            ),
            detail_params,
        )
        self.assertEqual(1, db.conn.commits)

    def test_insert_topic_owner_preserves_skip_and_insert_user_behavior(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        inserted_users = []
        db.insert_user = lambda user: inserted_users.append(user) or user.get("user_id")

        self.assertIsNone(ZSXQColumnsDatabase._insert_topic_owner(db, 202, {}))
        self.assertEqual([], db.cursor.calls)
        self.assertEqual([], inserted_users)

        self.assertIsNone(ZSXQColumnsDatabase._insert_topic_owner(db, 202, {"owner": {}}))
        self.assertEqual([], db.cursor.calls)
        self.assertEqual([], inserted_users)

        self.assertIsNone(
            ZSXQColumnsDatabase._insert_topic_owner(
                db,
                202,
                {"owner": {"user_id": 801, "name": "owner"}},
            )
        )
        owner_sql, owner_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO topic_owners", owner_sql)
        self.assertIn("ON CONFLICT(topic_id, owner_type) DO UPDATE SET", owner_sql)
        self.assertEqual((202, 801), owner_params)
        self.assertEqual([{"user_id": 801, "name": "owner"}], inserted_users)

        db.cursor = FakeCursor()
        inserted_users = []
        db.insert_user = lambda user: inserted_users.append(user) and None
        self.assertIsNone(
            ZSXQColumnsDatabase._insert_topic_owner(
                db,
                202,
                {"owner": {"user_id": 0, "name": "missing"}},
            )
        )
        self.assertEqual([], db.cursor.calls)
        self.assertEqual([{"user_id": 0, "name": "missing"}], inserted_users)

    def test_insert_topic_related_payloads_preserves_order_and_empty_skip_behavior(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        db = object.__new__(ZSXQColumnsDatabase)
        calls = []
        db._insert_image = lambda topic_id, image: calls.append(("image", topic_id, image))
        db._insert_file = lambda topic_id, file: calls.append(("file", topic_id, file))
        db._insert_video = lambda topic_id, video: calls.append(("video", topic_id, video))
        db._insert_comment = lambda topic_id, comment: calls.append(("comment", topic_id, comment))

        self.assertIsNone(
            ZSXQColumnsDatabase._insert_topic_related_payloads(db, 202, {}, {})
        )
        self.assertEqual([], calls)

        self.assertIsNone(
            ZSXQColumnsDatabase._insert_topic_related_payloads(
                db,
                202,
                {
                    "content_voice": {"file_id": 402},
                    "show_comments": [{"comment_id": 701}],
                },
                {
                    "images": [{"image_id": 301}],
                    "files": [{"file_id": 401}],
                    "video": {"video_id": 501},
                },
            )
        )
        self.assertEqual(
            [
                ("image", 202, {"image_id": 301}),
                ("file", 202, {"file_id": 401}),
                ("file", 202, {"file_id": 402}),
                ("video", 202, {"video_id": 501}),
                ("comment", 202, {"comment_id": 701}),
            ],
            calls,
        )

    def test_iter_topic_related_payloads_preserves_existing_order(self):
        self.assertEqual([], list(_iter_topic_related_payloads({}, {})))

        topic_data = {
            "content_voice": {"file_id": 402},
            "show_comments": [{"comment_id": 701}, {"comment_id": 702}],
        }
        talk = {
            "images": [{"image_id": 301}, {"image_id": 302}],
            "files": [{"file_id": 401}],
            "video": {"video_id": 501},
        }

        self.assertEqual(
            [
                ("image", {"image_id": 301}),
                ("image", {"image_id": 302}),
                ("file", {"file_id": 401}),
                ("file", {"file_id": 402}),
                ("video", {"video_id": 501}),
                ("comment", {"comment_id": 701}),
                ("comment", {"comment_id": 702}),
            ],
            list(_iter_topic_related_payloads(topic_data, talk)),
        )

        self.assertEqual(
            [],
            list(
                _iter_topic_related_payloads(
                    {"content_voice": {}, "show_comments": []},
                    {"images": [], "files": [], "video": {}},
                )
            ),
        )

    def test_insert_topic_detail_preserves_related_insert_order(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                normalized_sql = " ".join(sql.split())
                if normalized_sql.startswith("INSERT INTO topic_details"):
                    self.calls.append(("detail", params))
                elif normalized_sql.startswith("INSERT INTO topic_owners"):
                    self.calls.append(("owner", params))
                else:
                    self.calls.append(("sql", params))
                return self

        class FakeConnection:
            def __init__(self, calls):
                self.calls = calls

            def commit(self):
                self.calls.append(("commit", None))

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.conn = FakeConnection(db.cursor.calls)

        def insert_user(user):
            db.cursor.calls.append(("insert_user", user))
            return user.get("user_id")

        def insert_image(topic_id, image):
            db.cursor.calls.append(("image", topic_id, image))

        def insert_file(topic_id, file):
            db.cursor.calls.append(("file", topic_id, file))

        def insert_video(topic_id, video):
            db.cursor.calls.append(("video", topic_id, video))

        def insert_comment(topic_id, comment):
            db.cursor.calls.append(("comment", topic_id, comment))

        db.insert_user = insert_user
        db._insert_image = insert_image
        db._insert_file = insert_file
        db._insert_video = insert_video
        db._insert_comment = insert_comment

        self.assertEqual(
            202,
            ZSXQColumnsDatabase.insert_topic_detail(
                db,
                303,
                {
                    "topic_id": 202,
                    "talk": {
                        "text": "full text",
                        "owner": {"user_id": 801, "name": "owner"},
                        "images": [{"image_id": 301}],
                        "files": [{"file_id": 401}],
                        "video": {"video_id": 501},
                    },
                    "content_voice": {"file_id": 402},
                    "show_comments": [{"comment_id": 701}],
                },
            ),
        )

        self.assertEqual(
            [
                "detail",
                "insert_user",
                "owner",
                "image",
                "file",
                "file",
                "video",
                "comment",
                "commit",
            ],
            [call[0] for call in db.cursor.calls],
        )
        self.assertEqual((202, 801), db.cursor.calls[2][1])
        self.assertEqual(("image", 202, {"image_id": 301}), db.cursor.calls[3])
        self.assertEqual(("file", 202, {"file_id": 401}), db.cursor.calls[4])
        self.assertEqual(("file", 202, {"file_id": 402}), db.cursor.calls[5])
        self.assertEqual(("video", 202, {"video_id": 501}), db.cursor.calls[6])
        self.assertEqual(("comment", 202, {"comment_id": 701}), db.cursor.calls[7])

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

        self.assertEqual([], ZSXQColumnsDatabase.get_topic_images(db, 202))
        images_sql, images_params = db.cursor.calls[-1]
        self.assertIn("FROM images WHERE topic_id = ?", images_sql)
        self.assertIn("topic_details WHERE group_id = ?", images_sql)
        self.assertEqual((202, 303, 303), images_params)

        self.assertEqual([], ZSXQColumnsDatabase.get_topic_files(db, 202))
        files_sql, files_params = db.cursor.calls[-1]
        self.assertIn("FROM files WHERE topic_id = ?", files_sql)
        self.assertIn("topic_details WHERE group_id = ?", files_sql)
        self.assertEqual((202, 303, 303), files_params)

        self.assertEqual([], ZSXQColumnsDatabase.get_topic_videos(db, 202))
        videos_sql, videos_params = db.cursor.calls[-1]
        self.assertIn("FROM videos WHERE topic_id = ?", videos_sql)
        self.assertIn("topic_details WHERE group_id = ?", videos_sql)
        self.assertEqual((202, 303, 303), videos_params)

        self.assertEqual([], ZSXQColumnsDatabase.get_topic_comments(db, 202))
        comments_sql, comments_params = db.cursor.calls[-1]
        self.assertIn("WHERE c.topic_id = ? AND (? IS NULL OR c.group_id = ?)", comments_sql)
        self.assertEqual((202, 303, 303), comments_params)

    def test_column_and_attachment_read_methods_preserve_row_shapes(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.fetchall_results = [
                    [
                        (
                            101,
                            303,
                            "column name",
                            "cover-url",
                            7,
                            "2026-06-10T10:00:00",
                            "2026-06-10T11:00:00",
                            "2026-06-10 12:00:00",
                        )
                    ],
                    [
                        (
                            202,
                            101,
                            303,
                            "topic title",
                            "topic text",
                            "2026-06-10T12:00:00",
                            "2026-06-10T13:00:00",
                            "2026-06-10 14:00:00",
                            1,
                        )
                    ],
                    [
                        (
                            301,
                            "image",
                            "thumb-url",
                            10,
                            20,
                            "large-url",
                            30,
                            40,
                            "original-url",
                            50,
                            60,
                            70,
                            "cache/image.jpg",
                        )
                    ],
                    [
                        (
                            401,
                            "file.pdf",
                            "hash",
                            8192,
                            30,
                            5,
                            "2026-06-10T15:00:00",
                            "pending",
                            "downloads/file.pdf",
                            "2026-06-10 16:00:00",
                        )
                    ],
                    [
                        (
                            501,
                            4096,
                            60,
                            "cover-url",
                            320,
                            180,
                            "cache/cover.jpg",
                            "video-url",
                            "completed",
                            "downloads/video.mp4",
                            "2026-06-10 17:00:00",
                        )
                    ],
                ]

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

            def fetchall(self):
                return self.fetchall_results.pop(0)

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.group_id = "303"

        self.assertEqual(
            [
                {
                    "column_id": 101,
                    "group_id": 303,
                    "name": "column name",
                    "cover_url": "cover-url",
                    "topics_count": 7,
                    "create_time": "2026-06-10T10:00:00",
                    "last_topic_attach_time": "2026-06-10T11:00:00",
                    "imported_at": "2026-06-10 12:00:00",
                }
            ],
            ZSXQColumnsDatabase.get_columns(db, 303),
        )
        self.assertEqual(
            [
                {
                    "topic_id": 202,
                    "column_id": 101,
                    "group_id": 303,
                    "title": "topic title",
                    "text": "topic text",
                    "create_time": "2026-06-10T12:00:00",
                    "attached_to_column_time": "2026-06-10T13:00:00",
                    "imported_at": "2026-06-10 14:00:00",
                    "has_detail": True,
                }
            ],
            ZSXQColumnsDatabase.get_column_topics(db, 101),
        )
        self.assertEqual(301, ZSXQColumnsDatabase.get_topic_images(db, 202)[0]["image_id"])
        self.assertEqual("file.pdf", ZSXQColumnsDatabase.get_topic_files(db, 202)[0]["name"])
        self.assertEqual(501, ZSXQColumnsDatabase.get_topic_videos(db, 202)[0]["video_id"])

        self.assertIn("FROM columns WHERE group_id = ?", db.cursor.calls[0][0])
        self.assertEqual((303,), db.cursor.calls[0][1])
        self.assertIn("WHERE ct.column_id = ? AND (? IS NULL OR ct.group_id = ?)", db.cursor.calls[1][0])
        self.assertEqual((101, 303, 303), db.cursor.calls[1][1])
        self.assertIn("FROM images WHERE topic_id = ?", db.cursor.calls[2][0])
        self.assertEqual((202, 303, 303), db.cursor.calls[2][1])
        self.assertIn("FROM files WHERE topic_id = ?", db.cursor.calls[3][0])
        self.assertEqual((202, 303, 303), db.cursor.calls[3][1])
        self.assertIn("FROM videos WHERE topic_id = ?", db.cursor.calls[4][0])
        self.assertEqual((202, 303, 303), db.cursor.calls[4][1])

    def test_topic_comments_preserve_comment_image_queries_and_nested_shape(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.fetchall_results = [
                    [
                        (
                            701,
                            None,
                            "parent",
                            "2026-06-10T10:00:00",
                            1,
                            2,
                            3,
                            False,
                            801,
                            "owner",
                            "alias",
                            "avatar",
                            "location",
                            None,
                            None,
                            None,
                            None,
                        ),
                        (
                            702,
                            701,
                            "child",
                            "2026-06-10T10:01:00",
                            0,
                            0,
                            0,
                            False,
                            802,
                            "reply-owner",
                            None,
                            None,
                            None,
                            801,
                            "owner",
                            "alias",
                            "avatar",
                        ),
                    ],
                    [
                        (
                            301,
                            "image",
                            "thumb-url",
                            10,
                            20,
                            "large-url",
                            30,
                            40,
                            "original-url",
                            50,
                            60,
                            70,
                        )
                    ],
                    [],
                ]

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

            def fetchall(self):
                return self.fetchall_results.pop(0)

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.group_id = "303"

        comments = ZSXQColumnsDatabase.get_topic_comments(db, 202)

        self.assertEqual(1, len(comments))
        self.assertEqual(701, comments[0]["comment_id"])
        self.assertEqual(301, comments[0]["images"][0]["image_id"])
        self.assertEqual(1, len(comments[0]["replied_comments"]))
        self.assertEqual(702, comments[0]["replied_comments"][0]["comment_id"])
        self.assertNotIn("images", comments[0]["replied_comments"][0])

        self.assertIn("FROM comments c", db.cursor.calls[0][0])
        self.assertEqual((202, 303, 303), db.cursor.calls[0][1])
        self.assertIn("FROM images WHERE comment_id = ?", db.cursor.calls[1][0])
        self.assertEqual((701, 303, 202), db.cursor.calls[1][1])
        self.assertIn("FROM images WHERE comment_id = ?", db.cursor.calls[2][0])
        self.assertEqual((702, 303, 202), db.cursor.calls[2][1])

    def test_load_topic_comment_images_preserves_query_params_and_shape(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.fetchall_results = [
                    [
                        (
                            301,
                            "image",
                            "thumb-url",
                            10,
                            20,
                            "large-url",
                            30,
                            40,
                            "original-url",
                            50,
                            60,
                            70,
                        )
                    ],
                    [],
                ]

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

            def fetchall(self):
                return self.fetchall_results.pop(0)

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()

        self.assertEqual(
            [
                {
                    "image_id": 301,
                    "type": "image",
                    "thumbnail": {"url": "thumb-url", "width": 10, "height": 20},
                    "large": {"url": "large-url", "width": 30, "height": 40},
                    "original": {
                        "url": "original-url",
                        "width": 50,
                        "height": 60,
                        "size": 70,
                    },
                }
            ],
            ZSXQColumnsDatabase._load_topic_comment_images(db, 701, 303, 202),
        )
        self.assertIn("FROM images WHERE comment_id = ?", db.cursor.calls[0][0])
        self.assertEqual((701, 303, 202), db.cursor.calls[0][1])

        self.assertEqual(
            [],
            ZSXQColumnsDatabase._load_topic_comment_images(db, 702, None, 202),
        )
        self.assertEqual((702, None, 202), db.cursor.calls[1][1])

    def test_start_crawl_log_preserves_insert_params_commit_and_none_row(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.fetchone_results = [(77,), None]

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))
                return self

            def fetchone(self):
                return self.fetchone_results.pop(0)

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.conn = FakeConnection()

        self.assertEqual(77, ZSXQColumnsDatabase.start_crawl_log(db, 303, "columns"))
        self.assertIn("INSERT INTO crawl_log (group_id, crawl_type) VALUES (?, ?) RETURNING id", db.cursor.calls[-1][0])
        self.assertEqual((303, "columns"), db.cursor.calls[-1][1])
        self.assertEqual(1, db.conn.commits)

        self.assertIsNone(ZSXQColumnsDatabase.start_crawl_log(db, 304, "details"))
        self.assertEqual((304, "details"), db.cursor.calls[-1][1])
        self.assertEqual(2, db.conn.commits)

    def test_update_crawl_log_preserves_noop_when_no_update_parts(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.conn = FakeConnection()

        self.assertIsNone(ZSXQColumnsDatabase.update_crawl_log(db, 7))
        self.assertEqual([], db.cursor.calls)
        self.assertEqual(0, db.conn.commits)

    def test_update_crawl_log_preserves_dynamic_sql_values_and_commit(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((" ".join(sql.split()), params))

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.conn = FakeConnection()

        ZSXQColumnsDatabase.update_crawl_log(
            db,
            7,
            columns_count=1,
            topics_count=2,
            details_count=3,
            files_count=4,
            status="failed",
            error_message="boom",
        )

        sql, params = db.cursor.calls[-1]
        self.assertEqual(
            "UPDATE crawl_log SET columns_count = ?, topics_count = ?, details_count = ?, "
            "files_count = ?, status = ?, end_time = CURRENT_TIMESTAMP, error_message = ? WHERE id = ?",
            sql,
        )
        self.assertEqual([1, 2, 3, 4, "failed", "boom", 7], params)
        self.assertEqual(1, db.conn.commits)

    def test_clear_all_data_preserves_delete_order_stats_and_commit(self):
        from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self.rowcount = 0

            def execute(self, sql, params=()):
                normalized_sql = " ".join(sql.split())
                self.calls.append((normalized_sql, params))
                rowcounts = {
                    "DELETE FROM comments": 2,
                    "DELETE FROM videos": 3,
                    "DELETE FROM files": 4,
                    "DELETE FROM images": 5,
                    "DELETE FROM topic_owners": 6,
                    "DELETE FROM topic_details": 7,
                    "DELETE FROM column_topics": 8,
                    "DELETE FROM columns": 9,
                    "DELETE FROM crawl_log": 10,
                }
                for prefix, rowcount in rowcounts.items():
                    if normalized_sql.startswith(prefix):
                        self.rowcount = rowcount
                        break
                return self

            def fetchall(self):
                return [(10,), (11,)]

        class FakeConnection:
            def __init__(self):
                self.commits = 0
                self.rollbacks = 0

            def commit(self):
                self.commits += 1

            def rollback(self):
                self.rollbacks += 1

        db = object.__new__(ZSXQColumnsDatabase)
        db.cursor = FakeCursor()
        db.conn = FakeConnection()

        with patch("builtins.print"):
            self.assertEqual(
                {
                    "columns_deleted": 9,
                    "topics_deleted": 8,
                    "details_deleted": 7,
                    "images_deleted": 5,
                    "files_deleted": 4,
                    "videos_deleted": 3,
                    "comments_deleted": 2,
                    "users_deleted": 0,
                },
                ZSXQColumnsDatabase.clear_all_data(db, 303),
            )
        self.assertEqual(1, db.conn.commits)
        self.assertEqual(0, db.conn.rollbacks)
        self.assertEqual(
            [
                "SELECT topic_id FROM topic_details WHERE group_id = ?",
                "DELETE FROM comments WHERE topic_id IN (?,?)",
                "DELETE FROM videos WHERE topic_id IN (?,?)",
                "DELETE FROM files WHERE topic_id IN (?,?)",
                "DELETE FROM images WHERE topic_id IN (?,?)",
                "DELETE FROM topic_owners WHERE topic_id IN (?,?)",
                "DELETE FROM topic_details WHERE group_id = ?",
                "DELETE FROM column_topics WHERE group_id = ?",
                "DELETE FROM columns WHERE group_id = ?",
                "DELETE FROM crawl_log WHERE group_id = ?",
            ],
            [sql for sql, _ in db.cursor.calls],
        )
        self.assertEqual((303,), db.cursor.calls[0][1])
        self.assertTrue(all(params == [10, 11] for _, params in db.cursor.calls[1:6]))
        self.assertTrue(all(params == (303,) for _, params in db.cursor.calls[6:]))

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
