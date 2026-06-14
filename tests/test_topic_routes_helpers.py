import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_TOPIC_ROUTE_DEPS = find_spec("fastapi") is not None


class FakeDb:
    def __init__(self):
        self.closed = False
        self.rolled_back = False
        self.committed = False
        self.conn = self

    def close(self):
        self.closed = True

    def rollback(self):
        self.rolled_back = True

    def commit(self):
        self.committed = True


class FakeTopicDb(FakeDb):
    def __init__(self):
        super().__init__()
        self.imported_comments = []

    def import_additional_comments(self, topic_id, comments):
        self.imported_comments.append((topic_id, comments))


class FakeCursor:
    def __init__(self, rows=None, total=0):
        self.calls = []
        self.rowcount = 1
        self.rows = rows or []
        self.total = total

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return (self.total,)


class FakeSqlDb:
    def __init__(self, rows=None, total=0):
        self.cursor = FakeCursor(rows=rows, total=total)


class FakeCommentClient:
    def __init__(self, comments):
        self.comments = comments

    def get_topic_comments(self, topic_id):
        return self.comments


class TopicRoutesHelperTests(unittest.TestCase):
    def _run_async(self, coro):
        import asyncio

        return asyncio.run(coro)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_close_topic_db_closes_database(self):
        from backend.routes.topic_routes import _close_topic_db

        db = FakeDb()

        _close_topic_db(db)

        self.assertTrue(db.closed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_rollback_topic_db_rolls_back_when_available(self):
        from backend.routes.topic_routes import _rollback_topic_db

        db = FakeDb()

        _rollback_topic_db(db)

        self.assertTrue(db.rolled_back)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_rollback_topic_db_allows_missing_db(self):
        from backend.routes.topic_routes import _rollback_topic_db

        _rollback_topic_db(None)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_delete_single_topic_rows_deletes_detail_tables_and_topic(self):
        from backend.routes.topic_routes import _delete_single_topic_rows
        from backend.services.topic_workflow_service import TOPIC_DETAIL_TABLES

        db = FakeSqlDb()

        deleted = _delete_single_topic_rows(db, 10, 123)

        self.assertTrue(deleted)
        self.assertEqual(len(TOPIC_DETAIL_TABLES) + 1, len(db.cursor.calls))
        self.assertEqual(("DELETE FROM user_liked_emojis WHERE topic_id = ?", (10,)), db.cursor.calls[0])
        self.assertEqual(("DELETE FROM topics WHERE topic_id = ? AND group_id = ?", (10, 123)), db.cursor.calls[-1])

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_delete_group_topic_rows_returns_deleted_counts(self):
        from backend.routes.topic_routes import _delete_group_topic_rows
        from backend.services.topic_workflow_service import GROUP_TOPIC_TABLES

        db = FakeSqlDb()

        deleted_counts = _delete_group_topic_rows(db, 123)

        self.assertEqual({table: 1 for table, _ in GROUP_TOPIC_TABLES}, deleted_counts)
        self.assertEqual(len(GROUP_TOPIC_TABLES), len(db.cursor.calls))
        self.assertIn("SELECT topic_id FROM topics WHERE group_id = ?", db.cursor.calls[0][0])
        self.assertEqual(("DELETE FROM topics WHERE group_id = ?", (123,)), db.cursor.calls[-1])

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_build_single_topic_response_includes_optional_message(self):
        from backend.routes.topic_routes import _build_single_topic_response

        response = _build_single_topic_response(10, "123", "skipped", 0, "already exists")

        self.assertEqual(
            {
                "success": True,
                "topic_id": 10,
                "group_id": 123,
                "imported": "skipped",
                "comments_fetched": 0,
                "message": "already exists",
            },
            response,
        )

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_validate_topic_group_rejects_mismatched_group(self):
        from fastapi import HTTPException

        from backend.routes.topic_routes import _validate_topic_group

        with self.assertRaises(HTTPException) as ctx:
            _validate_topic_group({"group": {"group_id": 456}}, "123")

        self.assertEqual(400, ctx.exception.status_code)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_fetch_and_import_topic_comments_imports_comments(self):
        from backend.routes.topic_routes import _fetch_and_import_topic_comments

        comments = [{"comment_id": 1}]
        db = FakeTopicDb()

        fetched = _fetch_and_import_topic_comments(db, 10, 1, FakeCommentClient(comments))

        self.assertEqual(1, fetched)
        self.assertEqual([(10, comments)], db.imported_comments)
        self.assertTrue(db.committed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_build_refresh_topic_success_defaults_missing_counts(self):
        from backend.routes.topic_routes import _build_refresh_topic_success

        response = _build_refresh_topic_success({"likes_count": 5, "comments_count": 2})

        self.assertEqual(
            {
                "success": True,
                "message": "话题信息已更新",
                "updated_data": {
                    "likes_count": 5,
                    "comments_count": 2,
                    "reading_count": 0,
                    "readers_count": 0,
                },
            },
            response,
        )

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_should_fetch_more_comments_uses_existing_threshold(self):
        from backend.routes.topic_routes import _should_fetch_more_comments

        self.assertFalse(_should_fetch_more_comments(8))
        self.assertTrue(_should_fetch_more_comments(9))

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_build_fetch_comments_skip_response_matches_endpoint_shape(self):
        from backend.routes.topic_routes import _build_fetch_comments_skip_response

        self.assertEqual(
            {
                "success": True,
                "message": "话题只有 8 条评论，无需获取更多",
                "comments_fetched": 0,
            },
            _build_fetch_comments_skip_response(8),
        )

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_import_more_comments_returns_zero_when_fetch_empty(self):
        from backend.routes.topic_routes import _import_more_comments

        db = FakeTopicDb()

        fetched = _import_more_comments(db, 10, 9, FakeCommentClient([]))

        self.assertEqual(0, fetched)
        self.assertEqual([], db.imported_comments)
        self.assertFalse(db.committed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_import_more_comments_imports_and_commits(self):
        from backend.routes.topic_routes import _import_more_comments

        comments = [{"comment_id": 1}, {"comment_id": 2}]
        db = FakeTopicDb()

        fetched = _import_more_comments(db, 10, 9, FakeCommentClient(comments))

        self.assertEqual(2, fetched)
        self.assertEqual([(10, comments)], db.imported_comments)
        self.assertTrue(db.committed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_build_pagination_calculates_pages(self):
        from backend.routes.topic_routes import _build_pagination

        self.assertEqual({"page": 2, "per_page": 20, "total": 41, "pages": 3}, _build_pagination(2, 20, 41))

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_format_topic_row_maps_basic_topic_fields(self):
        from backend.routes.topic_routes import _format_topic_row

        self.assertEqual(
            {
                "topic_id": 10,
                "title": "标题",
                "create_time": "2026-01-01",
                "likes_count": 1,
                "comments_count": 2,
                "reading_count": 3,
            },
            _format_topic_row((10, "标题", "2026-01-01", 1, 2, 3)),
        )

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_format_group_topic_row_maps_author_for_talk(self):
        from backend.routes.topic_routes import _format_group_topic_row

        row = (
            10,
            "标题",
            "2026-01-01",
            1,
            2,
            3,
            "talk",
            0,
            1,
            None,
            None,
            "正文",
            99,
            "作者",
            "avatar.png",
            "2026-01-02",
        )

        topic = _format_group_topic_row(row)

        self.assertEqual("10", topic["topic_id"])
        self.assertEqual("正文", topic["talk_text"])
        self.assertFalse(topic["digested"])
        self.assertTrue(topic["sticky"])
        self.assertEqual({"user_id": 99, "name": "作者", "avatar_url": "avatar.png"}, topic["author"])

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_build_topics_query_with_search_uses_like_and_offset(self):
        from backend.routes.topic_routes import _build_topics_query

        query, params, count_query, count_params = _build_topics_query(3, 20, "offer")

        self.assertIn("WHERE title LIKE ?", query)
        self.assertEqual(("%offer%", 20, 40), params)
        self.assertEqual("SELECT COUNT(*) FROM topics WHERE title LIKE ?", count_query)
        self.assertEqual(("%offer%",), count_params)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_build_group_topics_query_with_search_uses_all_text_filters(self):
        from backend.routes.topic_routes import _build_group_topics_query

        query, params, count_query, count_params = _build_group_topics_query(123, 2, 10, "offer")

        self.assertIn("t.title LIKE ? OR q.text LIKE ? OR tk.text LIKE ?", query)
        self.assertEqual((123, "%offer%", "%offer%", "%offer%", 10, 10), params)
        self.assertEqual("SELECT COUNT(*) FROM topics WHERE group_id = ? AND title LIKE ?", count_query)
        self.assertEqual((123, "%offer%"), count_params)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_fetch_rows_and_total_executes_data_and_count_queries(self):
        from backend.routes.topic_routes import _fetch_rows_and_total

        cursor = FakeCursor(rows=[("row",)], total=7)

        rows, total = _fetch_rows_and_total(cursor, "SELECT rows", ("p",), "SELECT count", ("c",))

        self.assertEqual([("row",)], rows)
        self.assertEqual(7, total)
        self.assertEqual([("SELECT rows", ("p",)), ("SELECT count", ("c",))], cursor.calls)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_build_topic_page_response_formats_rows_and_pagination(self):
        from backend.routes.topic_routes import _build_topic_page_response

        cursor = FakeCursor(rows=[("row-1",), ("row-2",)], total=7)

        response = _build_topic_page_response(
            cursor,
            "SELECT rows",
            ("p",),
            "SELECT count",
            ("c",),
            lambda row: {"value": row[0]},
            page=2,
            per_page=3,
        )

        self.assertEqual(
            {
                "topics": [{"value": "row-1"}, {"value": "row-2"}],
                "pagination": {"page": 2, "per_page": 3, "total": 7, "pages": 3},
            },
            response,
        )
        self.assertEqual([("SELECT rows", ("p",)), ("SELECT count", ("c",))], cursor.calls)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_read_routes_offload_sync_db_work_to_thread(self):
        from backend.routes import topic_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"called": func.__name__, "args": args}

        with patch("backend.routes.topic_routes.asyncio.to_thread", side_effect=fake_to_thread):
            topics = self._run_async(topic_routes.get_topics(page=2, per_page=5, search="offer"))
            group_topics = self._run_async(topic_routes.get_group_topics(123, page=3, per_page=10, search="alpha"))
            detail = self._run_async(topic_routes.get_topic_detail(99, "123"))

        self.assertEqual(
            [
                (topic_routes._get_topics_response, (2, 5, "offer")),
                (topic_routes._get_group_topics_response, (123, 3, 10, "alpha")),
                (topic_routes._get_topic_detail_response, (99, "123")),
            ],
            calls,
        )
        self.assertEqual({"called": "_get_topics_response", "args": (2, 5, "offer")}, topics)
        self.assertEqual({"called": "_get_group_topics_response", "args": (123, 3, 10, "alpha")}, group_topics)
        self.assertEqual({"called": "_get_topic_detail_response", "args": (99, "123")}, detail)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_read_helpers_preserve_service_call_shapes(self):
        from backend.routes import topic_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"called": func.__name__, "args": args}

        with patch("backend.routes.topic_routes.asyncio.to_thread", side_effect=fake_to_thread):
            topics = self._run_async(topic_routes._topics_page(2, 5, "offer"))
            group_topics = self._run_async(topic_routes._group_topics_page(123, 3, 10, "alpha"))
            detail = self._run_async(topic_routes._topic_detail(99, "123"))

        self.assertEqual(
            [
                (topic_routes._get_topics_response, (2, 5, "offer")),
                (topic_routes._get_group_topics_response, (123, 3, 10, "alpha")),
                (topic_routes._get_topic_detail_response, (99, "123")),
            ],
            calls,
        )
        self.assertEqual({"called": "_get_topics_response", "args": (2, 5, "offer")}, topics)
        self.assertEqual({"called": "_get_group_topics_response", "args": (123, 3, 10, "alpha")}, group_topics)
        self.assertEqual({"called": "_get_topic_detail_response", "args": (99, "123")}, detail)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_operation_routes_offload_sync_work_to_thread(self):
        from backend.routes import topic_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"called": func.__name__, "args": args}

        with patch("backend.routes.topic_routes.asyncio.to_thread", side_effect=fake_to_thread):
            clear_result = self._run_async(topic_routes.clear_topic_database("group-1"))
            refresh_result = self._run_async(topic_routes.refresh_topic(11, "group-1"))
            comments_result = self._run_async(topic_routes.fetch_more_comments(12, "group-1"))
            delete_result = self._run_async(topic_routes.delete_single_topic(13, 123))
            fetch_single_result = self._run_async(topic_routes.fetch_single_topic("123", 14, fetch_comments=False))
            tags_result = self._run_async(topic_routes.get_group_tags("123"))
            tag_topics_result = self._run_async(topic_routes.get_topics_by_tag(123, 9, page=2, per_page=5))
            delete_group_result = self._run_async(topic_routes.delete_group_topics(123))

        self.assertEqual(
            [
                (topic_routes._clear_topic_database_response, ("group-1",)),
                (topic_routes._refresh_topic_response, (11, "group-1")),
                (topic_routes._fetch_more_comments_response, (12, "group-1")),
                (topic_routes._delete_single_topic_response, (13, 123)),
                (topic_routes._fetch_single_topic_response, ("123", 14, False)),
                (topic_routes._get_group_tags_response, ("123",)),
                (topic_routes._get_topics_by_tag_response, (123, 9, 2, 5)),
                (topic_routes._delete_group_topics_response, (123,)),
            ],
            calls,
        )
        self.assertEqual({"called": "_clear_topic_database_response", "args": ("group-1",)}, clear_result)
        self.assertEqual({"called": "_refresh_topic_response", "args": (11, "group-1")}, refresh_result)
        self.assertEqual({"called": "_fetch_more_comments_response", "args": (12, "group-1")}, comments_result)
        self.assertEqual({"called": "_delete_single_topic_response", "args": (13, 123)}, delete_result)
        self.assertEqual({"called": "_fetch_single_topic_response", "args": ("123", 14, False)}, fetch_single_result)
        self.assertEqual({"called": "_get_group_tags_response", "args": ("123",)}, tags_result)
        self.assertEqual({"called": "_get_topics_by_tag_response", "args": (123, 9, 2, 5)}, tag_topics_result)
        self.assertEqual({"called": "_delete_group_topics_response", "args": (123,)}, delete_group_result)


if __name__ == "__main__":
    unittest.main()
