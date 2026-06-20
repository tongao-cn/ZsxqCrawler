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


class FakeSingleTopicImportDb(FakeDb):
    def __init__(self, import_result, existing=False):
        super().__init__()
        self.import_result = import_result
        self.imported_topics = []
        self.existing = existing
        self.topic_exists_calls = []

    def topic_exists(self, topic_id):
        self.topic_exists_calls.append(topic_id)
        return self.existing

    def import_topic_data_with_result(self, topic_data):
        self.imported_topics.append(topic_data)
        return self.import_result


class FakeSingleTopicClient:
    def __init__(self, comments=None):
        self.comments = comments or []
        self.info_calls = []
        self.comment_calls = []

    def get_topic_info(self, topic_id):
        self.info_calls.append(topic_id)
        return {"topic": {"topic_id": topic_id}}

    def get_topic_comments(self, topic_id):
        self.comment_calls.append(topic_id)
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
    def test_delete_single_topic_records_deletes_detail_tables_and_topic(self):
        from backend.storage.zsxq_database import TOPIC_DETAIL_TABLES, ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        deleted = ZSXQDatabase.delete_single_topic_records(db, 10, 123)

        self.assertTrue(deleted)
        self.assertEqual(len(TOPIC_DETAIL_TABLES) + 1, len(db.cursor.calls))
        self.assertEqual(("DELETE FROM user_liked_emojis WHERE topic_id = ?", (10,)), db.cursor.calls[0])
        self.assertEqual(("DELETE FROM topics WHERE topic_id = ? AND group_id = ?", (10, 123)), db.cursor.calls[-1])

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_delete_group_topic_records_returns_deleted_counts(self):
        from backend.storage.zsxq_database import GROUP_TOPIC_TABLES, ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        deleted_counts = ZSXQDatabase.delete_group_topic_records(db, 123)

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
    def test_fetch_single_topic_response_commits_created_import_result(self):
        from backend.routes.topic_routes import _fetch_single_topic_response
        from backend.storage.zsxq_database import TopicImportResult

        db = FakeSingleTopicImportDb(TopicImportResult("created", topic_id=14))
        client = FakeSingleTopicClient(comments=[{"comment_id": 1}])
        topic_data = {"topic_id": 14, "group": {"group_id": 123}, "comments_count": 1}

        with (
            patch("backend.routes.topic_routes.ZSXQDatabase", return_value=db),
            patch("backend.routes.topic_routes.OfficialTopicClient", return_value=client),
            patch("backend.routes.topic_routes.official_payload_topic", return_value={"topic_id": 14, "group": {"group_id": 123}}),
            patch("backend.routes.topic_routes.normalize_official_topic", return_value=topic_data),
        ):
            response = _fetch_single_topic_response("123", 14, fetch_comments=True)

        self.assertEqual(
            {
                "success": True,
                "topic_id": 14,
                "group_id": 123,
                "imported": "created",
                "comments_fetched": 1,
            },
            response,
        )
        self.assertTrue(db.committed)
        self.assertTrue(db.closed)
        self.assertEqual([14], client.info_calls)
        self.assertEqual([14], client.comment_calls)
        self.assertEqual([14], db.topic_exists_calls)
        self.assertEqual([{**topic_data, "show_comments": [{"comment_id": 1}]}], db.imported_topics)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_fetch_single_topic_response_skips_existing_topic_via_storage(self):
        from backend.routes.topic_routes import _fetch_single_topic_response
        from backend.storage.zsxq_database import TopicImportResult

        db = FakeSingleTopicImportDb(TopicImportResult("created", topic_id=14), existing=True)
        client = FakeSingleTopicClient()

        with (
            patch("backend.routes.topic_routes.ZSXQDatabase", return_value=db),
            patch("backend.routes.topic_routes.OfficialTopicClient", return_value=client),
        ):
            response = _fetch_single_topic_response("123", 14, fetch_comments=True)

        self.assertEqual(
            {
                "success": True,
                "topic_id": 14,
                "group_id": 123,
                "imported": "skipped",
                "comments_fetched": 0,
                "message": "话题已存在，跳过采集",
            },
            response,
        )
        self.assertEqual([14], db.topic_exists_calls)
        self.assertEqual([], client.info_calls)
        self.assertEqual([], client.comment_calls)
        self.assertEqual([], db.imported_topics)
        self.assertFalse(db.committed)
        self.assertTrue(db.closed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_fetch_single_topic_response_rejects_failed_import_result(self):
        from fastapi import HTTPException

        from backend.routes.topic_routes import _fetch_single_topic_response
        from backend.storage.zsxq_database import TopicImportResult

        db = FakeSingleTopicImportDb(TopicImportResult("error", topic_id=14, error_message="boom"))
        client = FakeSingleTopicClient()

        with (
            patch("backend.routes.topic_routes.ZSXQDatabase", return_value=db),
            patch("backend.routes.topic_routes.OfficialTopicClient", return_value=client),
            patch("backend.routes.topic_routes.official_payload_topic", return_value={"topic_id": 14, "group": {"group_id": 123}}),
            patch(
                "backend.routes.topic_routes.normalize_official_topic",
                return_value={"topic_id": 14, "group": {"group_id": 123}, "comments_count": 0},
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _fetch_single_topic_response("123", 14, fetch_comments=False)

        self.assertEqual(500, ctx.exception.status_code)
        self.assertEqual("话题导入失败: boom", ctx.exception.detail)
        self.assertFalse(db.committed)
        self.assertTrue(db.closed)
        self.assertEqual([14], db.topic_exists_calls)
        self.assertEqual(1, len(db.imported_topics))

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_delete_single_topic_response_uses_storage_topic_exists(self):
        from backend.routes.topic_routes import _delete_single_topic_response

        class FakeDeleteTopicDb(FakeDb):
            def __init__(self, existing):
                super().__init__()
                self.existing = existing
                self.topic_exists_calls = []
                self.deleted_topic_calls = []

            def topic_exists(self, topic_id):
                self.topic_exists_calls.append(topic_id)
                return self.existing

            def delete_single_topic_records(self, topic_id, group_id):
                self.deleted_topic_calls.append((topic_id, group_id))
                return True

        existing_db = FakeDeleteTopicDb(existing=True)
        missing_db = FakeDeleteTopicDb(existing=False)

        with patch("backend.routes.topic_routes.ZSXQDatabase", return_value=existing_db):
            response = _delete_single_topic_response(14, 123)

        self.assertEqual({"success": True, "deleted_topic_id": 14, "deleted": True}, response)
        self.assertEqual([14], existing_db.topic_exists_calls)
        self.assertEqual([(14, 123)], existing_db.deleted_topic_calls)
        self.assertTrue(existing_db.committed)
        self.assertTrue(existing_db.closed)

        with patch("backend.routes.topic_routes.ZSXQDatabase", return_value=missing_db):
            response = _delete_single_topic_response(15, 123)

        self.assertEqual({"success": False, "message": "话题不存在"}, response)
        self.assertEqual([15], missing_db.topic_exists_calls)
        self.assertEqual([], missing_db.deleted_topic_calls)
        self.assertFalse(missing_db.committed)
        self.assertTrue(missing_db.closed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_delete_group_topics_response_uses_storage_count_and_delete(self):
        from backend.routes.topic_routes import _delete_group_topics_response

        class FakeDeleteGroupDb(FakeDb):
            def __init__(self, topics_count):
                super().__init__()
                self.topics_count = topics_count
                self.count_topic_calls = []
                self.deleted_group_calls = []

            def count_topics(self, group_id):
                self.count_topic_calls.append(group_id)
                return self.topics_count

            def delete_group_topic_records(self, group_id):
                self.deleted_group_calls.append(group_id)
                return {"topics": 2}

        existing_db = FakeDeleteGroupDb(topics_count=2)
        missing_db = FakeDeleteGroupDb(topics_count=0)

        with patch("backend.routes.topic_routes.ZSXQDatabase", return_value=existing_db):
            response = _delete_group_topics_response(123)

        self.assertEqual(
            {
                "message": "成功删除群组 123 的所有话题数据",
                "deleted_topics_count": 2,
                "deleted_details": {"topics": 2},
            },
            response,
        )
        self.assertEqual([123], existing_db.count_topic_calls)
        self.assertEqual([123], existing_db.deleted_group_calls)
        self.assertTrue(existing_db.committed)
        self.assertTrue(existing_db.closed)

        with patch("backend.routes.topic_routes.ZSXQDatabase", return_value=missing_db):
            response = _delete_group_topics_response(123)

        self.assertEqual({"message": "该群组没有话题数据", "deleted_count": 0}, response)
        self.assertEqual([123], missing_db.count_topic_calls)
        self.assertEqual([], missing_db.deleted_group_calls)
        self.assertFalse(missing_db.committed)
        self.assertTrue(missing_db.closed)

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
    def test_format_group_topic_row_maps_author_for_talk(self):
        from backend.storage.zsxq_database import _format_group_topic_row

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
    def test_group_topics_query_with_search_uses_matching_text_filters(self):
        from backend.storage.zsxq_database import _group_topics_count_query, _group_topics_query

        query, params = _group_topics_query(123, 10, 10, "offer")
        count_query, count_params = _group_topics_count_query(123, "offer")

        self.assertIn("t.title LIKE ? OR q.text LIKE ? OR tk.text LIKE ?", query)
        self.assertEqual((123, "%offer%", "%offer%", "%offer%", 10, 10), params)
        self.assertIn("COUNT(DISTINCT t.topic_id)", count_query)
        self.assertIn("t.title LIKE ? OR q.text LIKE ? OR tk.text LIKE ?", count_query)
        self.assertEqual((123, "%offer%", "%offer%", "%offer%"), count_params)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_get_topics_response_delegates_to_storage(self):
        from backend.routes.topic_routes import _get_topics_response

        class FakeTopicsDb(FakeDb):
            def __init__(self):
                super().__init__()
                self.topic_calls = []

            def get_topics(self, page, per_page, search):
                self.topic_calls.append((page, per_page, search))
                return {"topics": [{"topic_id": 202}], "pagination": {"page": page}}

        db = FakeTopicsDb()

        with patch("backend.routes.topic_routes.ZSXQDatabase", return_value=db) as database:
            response = _get_topics_response(page=2, per_page=5, search="offer")

        database.assert_called_once_with()
        self.assertEqual({"topics": [{"topic_id": 202}], "pagination": {"page": 2}}, response)
        self.assertEqual([(2, 5, "offer")], db.topic_calls)
        self.assertTrue(db.closed)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_get_group_topics_response_delegates_to_storage(self):
        from backend.routes.topic_routes import _get_group_topics_response

        class FakeGroupTopicsDb(FakeDb):
            def __init__(self):
                super().__init__()
                self.group_topic_calls = []

            def get_group_topics(self, group_id, page, per_page, search):
                self.group_topic_calls.append((group_id, page, per_page, search))
                return {"topics": [{"topic_id": "202"}], "pagination": {"page": page}}

        db = FakeGroupTopicsDb()

        with patch("backend.routes.topic_routes.ZSXQDatabase", return_value=db) as database:
            response = _get_group_topics_response(123, page=2, per_page=5, search="offer")

        database.assert_called_once_with("123")
        self.assertEqual({"topics": [{"topic_id": "202"}], "pagination": {"page": 2}}, response)
        self.assertEqual([(123, 2, 5, "offer")], db.group_topic_calls)
        self.assertTrue(db.closed)

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

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_topic_route_error_preserves_status_and_detail_format(self):
        from backend.routes import topic_routes

        error = topic_routes._topic_route_error("获取话题列表失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("获取话题列表失败: boom", error.detail)

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_topic_routes_preserve_wrapped_unexpected_errors(self):
        from backend.routes import topic_routes

        cases = [
            (
                topic_routes.get_topics,
                (),
                {"page": 2, "per_page": 5, "search": "offer"},
                "_topics_page",
                "获取话题列表失败: boom",
                None,
            ),
            (
                topic_routes.get_group_topics,
                (123,),
                {"page": 3, "per_page": 10, "search": "alpha"},
                "_group_topics_page",
                "获取群组话题失败: boom",
                None,
            ),
            (
                topic_routes.clear_topic_database,
                ("group-1",),
                {},
                "_cleared_topic_database",
                "删除话题数据库失败: boom",
                ("ERROR", "删除话题数据库失败: boom"),
            ),
            (topic_routes.get_topic_detail, (99, "123"), {}, "_topic_detail", "获取话题详情失败: boom", None),
            (topic_routes.refresh_topic, (11, "group-1"), {}, "_refreshed_topic", "更新话题失败: boom", None),
            (topic_routes.fetch_more_comments, (12, "group-1"), {}, "_more_comments", "获取更多评论失败: boom", None),
            (topic_routes.delete_single_topic, (13, 123), {}, "_deleted_single_topic", "删除话题失败: boom", None),
            (
                topic_routes.fetch_single_topic,
                ("123", 14),
                {"fetch_comments": False},
                "_fetched_single_topic",
                "单个话题采集失败: boom",
                None,
            ),
            (topic_routes.get_group_tags, ("123",), {}, "_group_tags", "获取标签列表失败: boom", None),
            (
                topic_routes.get_topics_by_tag,
                (123, 9),
                {"page": 2, "per_page": 5},
                "_tagged_topics",
                "根据标签获取话题失败: boom",
                None,
            ),
            (topic_routes.delete_group_topics, (123,), {}, "_deleted_group_topics", "删除话题数据失败: boom", None),
        ]

        for route, route_args, route_kwargs, helper_name, expected_detail, expected_log in cases:
            with (
                self.subTest(helper=helper_name),
                patch.object(topic_routes, helper_name, side_effect=RuntimeError("boom")),
                patch.object(topic_routes, "_log_topic_event") as log_topic_event,
            ):
                with self.assertRaises(topic_routes.HTTPException) as ctx:
                    self._run_async(route(*route_args, **route_kwargs))

                self.assertEqual(500, ctx.exception.status_code)
                self.assertEqual(expected_detail, ctx.exception.detail)
                if expected_log:
                    log_topic_event.assert_called_once_with(*expected_log)
                else:
                    log_topic_event.assert_not_called()

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_topic_routes_preserve_http_exception_passthrough(self):
        from backend.routes import topic_routes

        cases = [
            (topic_routes.get_topics, (), {"page": 2, "per_page": 5, "search": "offer"}, "_topics_page"),
            (
                topic_routes.get_group_topics,
                (123,),
                {"page": 3, "per_page": 10, "search": "alpha"},
                "_group_topics_page",
            ),
            (topic_routes.clear_topic_database, ("group-1",), {}, "_cleared_topic_database"),
            (topic_routes.get_topic_detail, (99, "123"), {}, "_topic_detail"),
            (topic_routes.refresh_topic, (11, "group-1"), {}, "_refreshed_topic"),
            (topic_routes.fetch_more_comments, (12, "group-1"), {}, "_more_comments"),
            (topic_routes.delete_single_topic, (13, 123), {}, "_deleted_single_topic"),
            (topic_routes.fetch_single_topic, ("123", 14), {"fetch_comments": False}, "_fetched_single_topic"),
            (topic_routes.get_group_tags, ("123",), {}, "_group_tags"),
            (topic_routes.get_topics_by_tag, (123, 9), {"page": 2, "per_page": 5}, "_tagged_topics"),
            (topic_routes.delete_group_topics, (123,), {}, "_deleted_group_topics"),
        ]

        for route, route_args, route_kwargs, helper_name in cases:
            original_error = topic_routes.HTTPException(status_code=409, detail="conflict")
            with (
                self.subTest(helper=helper_name),
                patch.object(topic_routes, helper_name, side_effect=original_error),
                patch.object(topic_routes, "_log_topic_event") as log_topic_event,
            ):
                with self.assertRaises(topic_routes.HTTPException) as ctx:
                    self._run_async(route(*route_args, **route_kwargs))

                self.assertIs(original_error, ctx.exception)
                self.assertEqual(409, ctx.exception.status_code)
                self.assertEqual("conflict", ctx.exception.detail)
                log_topic_event.assert_not_called()

    @unittest.skipUnless(HAS_TOPIC_ROUTE_DEPS, "topic route dependencies are not installed")
    def test_operation_helpers_preserve_service_call_shapes(self):
        from backend.routes import topic_routes

        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"called": func.__name__, "args": args}

        with patch("backend.routes.topic_routes.asyncio.to_thread", side_effect=fake_to_thread):
            clear_result = self._run_async(topic_routes._cleared_topic_database("group-1"))
            refresh_result = self._run_async(topic_routes._refreshed_topic(11, "group-1"))
            comments_result = self._run_async(topic_routes._more_comments(12, "group-1"))
            delete_result = self._run_async(topic_routes._deleted_single_topic(13, 123))
            fetch_single_result = self._run_async(topic_routes._fetched_single_topic("123", 14, False))
            tags_result = self._run_async(topic_routes._group_tags("123"))
            tag_topics_result = self._run_async(topic_routes._tagged_topics(123, 9, 2, 5))
            delete_group_result = self._run_async(topic_routes._deleted_group_topics(123))

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
