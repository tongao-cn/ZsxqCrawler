import unittest
from unittest.mock import patch

from backend.storage.zsxq_columns_database import (
    _column_row_to_dict,
    _column_topic_row_to_dict,
    _comment_image_row_to_dict,
    _crawl_log_update_parts,
    _empty_clear_data_stats,
    _empty_stats,
    _group_clear_delete_statements,
    _nest_topic_comments,
    _pending_file_row_to_dict,
    _pending_files_query,
    _pending_video_row_to_dict,
    _pending_videos_query,
    _stats_count_queries,
    _topic_comment_row_to_dict,
    _topic_detail_row_to_dict,
    _topic_file_row_to_dict,
    _topic_image_row_to_dict,
    _topic_video_row_to_dict,
    _topic_child_delete_statements,
    _uncached_image_row_to_dict,
    _uncached_images_query,
)


class ZSXQColumnsDatabaseHelperTests(unittest.TestCase):
    def _sql(self, sql):
        return " ".join(sql.split())

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
