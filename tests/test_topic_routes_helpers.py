import unittest
from importlib.util import find_spec


HAS_TOPIC_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("requests") is not None


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


class FakeCommentCrawler:
    def __init__(self, comments):
        self.db = FakeTopicDb()
        self.comments = comments

    def fetch_all_comments(self, topic_id, comments_count):
        return self.comments


class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self.data = data or {}

    def json(self):
        return self.data


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


class FakeDownloader:
    def __init__(self):
        self.file_db = FakeDb()


class FakeCrawler:
    def __init__(self, with_downloader=True):
        self.db = FakeDb()
        if with_downloader:
            self.file_downloader = FakeDownloader()


class TopicRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_close_crawler_databases_closes_topic_and_file_databases(self):
        from backend.routes.topic_routes import _close_crawler_databases

        crawler = FakeCrawler()

        _close_crawler_databases(crawler)

        self.assertTrue(crawler.db.closed)
        self.assertTrue(crawler.file_downloader.file_db.closed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_close_crawler_databases_allows_missing_downloader(self):
        from backend.routes.topic_routes import _close_crawler_databases

        crawler = FakeCrawler(with_downloader=False)

        _close_crawler_databases(crawler)

        self.assertTrue(crawler.db.closed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_rollback_crawler_db_rolls_back_when_available(self):
        from backend.routes.topic_routes import _rollback_crawler_db

        crawler = FakeCrawler()

        _rollback_crawler_db(crawler)

        self.assertTrue(crawler.db.rolled_back)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_rollback_crawler_db_allows_missing_crawler(self):
        from backend.routes.topic_routes import _rollback_crawler_db

        _rollback_crawler_db(None)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_delete_single_topic_rows_deletes_detail_tables_and_topic(self):
        from backend.routes.topic_routes import TOPIC_DETAIL_TABLES, _delete_single_topic_rows

        db = FakeSqlDb()

        deleted = _delete_single_topic_rows(db, 10, 123)

        self.assertTrue(deleted)
        self.assertEqual(len(TOPIC_DETAIL_TABLES) + 1, len(db.cursor.calls))
        self.assertEqual(("DELETE FROM user_liked_emojis WHERE topic_id = ?", (10,)), db.cursor.calls[0])
        self.assertEqual(("DELETE FROM topics WHERE topic_id = ? AND group_id = ?", (10, 123)), db.cursor.calls[-1])

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_delete_group_topic_rows_returns_deleted_counts(self):
        from backend.routes.topic_routes import GROUP_TOPIC_TABLES, _delete_group_topic_rows

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
        crawler = FakeCommentCrawler(comments)

        fetched = _fetch_and_import_topic_comments(crawler, 10, 1)

        self.assertEqual(1, fetched)
        self.assertEqual([(10, comments)], crawler.db.imported_comments)
        self.assertTrue(crawler.db.committed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_parse_refresh_topic_response_returns_topic_data(self):
        from backend.routes.topic_routes import _parse_refresh_topic_response

        topic = {"topic_id": 10, "likes_count": 3}
        response = FakeResponse(200, {"succeeded": True, "resp_data": {"topic": topic}})

        topic_data, error_response = _parse_refresh_topic_response(response)

        self.assertEqual(topic, topic_data)
        self.assertIsNone(error_response)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_parse_refresh_topic_response_returns_status_failure(self):
        from backend.routes.topic_routes import _parse_refresh_topic_response

        topic_data, error_response = _parse_refresh_topic_response(FakeResponse(403))

        self.assertIsNone(topic_data)
        self.assertEqual({"success": False, "message": "API请求失败: 403"}, error_response)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_parse_refresh_topic_response_returns_format_failure(self):
        from backend.routes.topic_routes import _parse_refresh_topic_response

        topic_data, error_response = _parse_refresh_topic_response(FakeResponse(200, {"succeeded": False}))

        self.assertIsNone(topic_data)
        self.assertEqual({"success": False, "message": "API返回数据格式错误"}, error_response)

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

        crawler = FakeCommentCrawler([])

        fetched = _import_more_comments(crawler, 10, 9)

        self.assertEqual(0, fetched)
        self.assertEqual([], crawler.db.imported_comments)
        self.assertFalse(crawler.db.committed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_import_more_comments_imports_and_commits(self):
        from backend.routes.topic_routes import _import_more_comments

        comments = [{"comment_id": 1}, {"comment_id": 2}]
        crawler = FakeCommentCrawler(comments)

        fetched = _import_more_comments(crawler, 10, 9)

        self.assertEqual(2, fetched)
        self.assertEqual([(10, comments)], crawler.db.imported_comments)
        self.assertTrue(crawler.db.committed)

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


if __name__ == "__main__":
    unittest.main()
