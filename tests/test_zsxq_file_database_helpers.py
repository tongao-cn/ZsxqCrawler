import unittest

from backend.storage.zsxq_file_database_helpers import _FILE_AI_ANALYSIS_FIELDS
from backend.storage.zsxq_file_database import (
    _api_response_record_params,
    _close_connection,
    _column_record_params,
    _comment_record_params,
    _count_tables,
    _file_ai_analysis_params,
    _file_attachment_params,
    _file_download_status_params,
    _file_record_params,
    _file_topic_relation_params,
    _group_record_params,
    _image_record_params,
    _latest_like_record_params,
    _like_emoji_record_params,
    _new_import_stats,
    _record_imported_items,
    _record_imported_value,
    _row_to_file_ai_analysis,
    _solution_record_params,
    _talk_record_params,
    _topic_column_record_params,
    _topic_record_params,
    _user_liked_emoji_record_params,
    _user_record_params,
)


class FakeCursor:
    def __init__(self, counts):
        self.counts = counts
        self.executed = []
        self.current_table = None

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT COUNT(*) FROM files"):
            self.current_table = "files"
        elif normalized.startswith("SELECT COUNT(*) FROM topics"):
            self.current_table = "topics"
        elif normalized.startswith("SELECT COUNT(*) FROM talks"):
            self.current_table = "talks"
        else:
            self.current_table = normalized.rsplit(" ", 1)[-1]

    def fetchone(self):
        return (self.counts[self.current_table],)


class FakeRowCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        if self.rows:
            return self.rows.pop(0)
        return None


class FakeListPageCursor:
    def __init__(self, rows=None, total=0):
        self.rows = list(rows or [])
        self.total = total
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return (self.total,)


class FakeClearFileRecordsCursor:
    def __init__(self, rowcounts):
        self.rowcounts = list(rowcounts)
        self.executed = []
        self.rowcount = 0

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))
        self.rowcount = self.rowcounts.pop(0)


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeImportDatabase:
    def __init__(self):
        self.calls = []
        self.cursor = self
        self.conn = self
        self.lastrowid = 1

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        if normalized.startswith("INSERT INTO api_responses"):
            self.calls.append(("api_response", params))
        elif normalized.startswith("DELETE FROM file_topic_relations"):
            self.calls.append(("delete_relation", params))
        elif normalized.startswith("INSERT INTO file_topic_relations"):
            self.calls.append(("insert_relation", params))
        return self

    def insert_group(self, group_data):
        self.calls.append(("group", group_data.get("group_id")))
        return group_data.get("group_id")

    def insert_topic(self, topic_data):
        self.calls.append(("topic", topic_data.get("topic_id")))
        return topic_data.get("topic_id")

    def insert_file(self, file_data, group_id=None, topic_id=None):
        self.calls.append(("file", file_data.get("file_id"), group_id, topic_id))
        return file_data.get("file_id")

    def insert_talk(self, topic_id, talk_data):
        self.calls.append(("talk", topic_id))

    def insert_topic_files(self, topic_id, files_data):
        self.calls.append(("topic_files", topic_id, [item.get("file_id") for item in files_data]))

    def commit(self):
        self.calls.append(("commit",))

    def rollback(self):
        self.calls.append(("rollback",))


class FakeAnalysisCursor:
    def __init__(self):
        self.calls = []
        self.row = None

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        return self

    def fetchone(self):
        return self.row


class FakeAnalysisConnection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakeCommentCursor:
    def __init__(self):
        self.calls = []
        self.row = None

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        return self

    def fetchone(self):
        return self.row


class ZSXQFileDatabaseHelperTests(unittest.TestCase):
    def test_new_import_stats_returns_expected_zero_counts(self):
        stats = _new_import_stats()

        self.assertEqual(
            {
                "files": 0,
                "topics": 0,
                "users": 0,
                "groups": 0,
                "images": 0,
                "comments": 0,
                "likes": 0,
                "columns": 0,
                "solutions": 0,
            },
            stats,
        )

    def test_record_imported_value_increments_only_for_truthy_values(self):
        stats = _new_import_stats()

        self.assertEqual(101, _record_imported_value(stats, "files", 101))
        self.assertEqual(0, _record_imported_value(stats, "topics", 0))
        self.assertIsNone(_record_imported_value(stats, "groups", None))

        self.assertEqual(1, stats["files"])
        self.assertEqual(0, stats["topics"])
        self.assertEqual(0, stats["groups"])

    def test_record_imported_items_increments_by_current_payload_length(self):
        stats = _new_import_stats()
        items = [{"id": 1}, {"id": None}]

        self.assertIs(items, _record_imported_items(stats, "comments", items))
        self.assertEqual([], _record_imported_items(stats, "likes", []))
        self.assertIsNone(_record_imported_items(stats, "images", None))

        self.assertEqual(2, stats["comments"])
        self.assertEqual(0, stats["likes"])
        self.assertEqual(0, stats["images"])

    def test_row_to_file_ai_analysis_maps_columns_and_handles_missing_row(self):
        row = tuple(f"value-{index}" for index, _field in enumerate(_FILE_AI_ANALYSIS_FIELDS))

        self.assertIsNone(_row_to_file_ai_analysis(None))
        self.assertEqual(
            dict(zip(_FILE_AI_ANALYSIS_FIELDS, row)),
            _row_to_file_ai_analysis(row),
        )

    def test_file_attachment_params_keep_sql_column_order(self):
        params = _file_attachment_params(
            202,
            {
                "file_id": 101,
                "name": "memo.pdf",
                "hash": "abc",
                "size": 20,
                "duration": 3,
                "download_count": 4,
                "create_time": "2026-06-10T12:00:00",
            },
        )

        self.assertEqual(
            (202, 101, "memo.pdf", "abc", 20, 3, 4, "2026-06-10T12:00:00"),
            params,
        )

    def test_file_record_params_keep_insert_file_column_order(self):
        params = _file_record_params(
            {
                "file_id": 101,
                "hash": "abc",
                "size": 20,
                "duration": 3,
                "download_count": 4,
                "create_time": "2026-06-10T12:00:00",
            },
            group_id="303",
            topic_id=202,
        )

        self.assertEqual(
            (101, 303, 202, "", "abc", 20, 3, 4, "2026-06-10T12:00:00"),
            params,
        )
        self.assertEqual(None, _file_record_params({"file_id": 101}, group_id=None)[1])

    def test_file_download_status_params_keep_update_column_order(self):
        self.assertEqual(
            ("completed", r"C:\tmp\file.pdf", "completed", "completed", None, "completed", None, 101, 303, 303),
            _file_download_status_params("303", 101, "completed", r"C:\tmp\file.pdf"),
        )
        self.assertEqual(
            ("failed", None, "failed", "failed", "size_mismatch", "failed", "bad size", 101, 303, 303),
            _file_download_status_params("303", 101, "failed", error_code="size_mismatch", error_message="bad size"),
        )

    def test_file_ai_analysis_params_keep_upsert_column_order(self):
        self.assertEqual(
            (101, 303, "completed", None, None, None, None, None, None, None, None, None, None, None),
            _file_ai_analysis_params("303", 101),
        )
        self.assertEqual(
            (
                101,
                303,
                "failed",
                "summary",
                "full text",
                "preview",
                "application/pdf",
                r"C:\tmp\file.pdf",
                456,
                "model-a",
                "https://api.example.test",
                "responses",
                "low",
                "boom",
            ),
            _file_ai_analysis_params(
                "303",
                101,
                status="failed",
                summary="summary",
                extracted_text="full text",
                extracted_text_preview="preview",
                content_type="application/pdf",
                source_path=r"C:\tmp\file.pdf",
                source_size=456,
                model="model-a",
                api_base="https://api.example.test",
                wire_api="responses",
                reasoning_effort="low",
                error_message="boom",
            ),
        )

    def test_user_and_group_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (9, "Alice", "A", "avatar", "desc", "Shanghai", "ai-url"),
            _user_record_params(
                {
                    "user_id": 9,
                    "name": "Alice",
                    "alias": "A",
                    "avatar_url": "avatar",
                    "description": "desc",
                    "location": "Shanghai",
                    "ai_comment_url": "ai-url",
                }
            ),
        )
        self.assertEqual((9, "", None, None, None, None, None), _user_record_params({"user_id": 9}))
        self.assertEqual(
            (303, "group", "paid", "bg"),
            _group_record_params({"group_id": 303, "name": "group", "type": "paid", "background_url": "bg"}),
        )
        self.assertEqual((303, "", None, None), _group_record_params({"group_id": 303}))

    def test_topic_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (
                202,
                303,
                "talk",
                "title",
                "note",
                4,
                5,
                6,
                7,
                8,
                9,
                True,
                True,
                "2026-06-10T12:00:00",
                "2026-06-10T12:30:00",
                True,
                True,
            ),
            _topic_record_params(
                {
                    "topic_id": 202,
                    "group": {"group_id": 303},
                    "type": "talk",
                    "title": "title",
                    "annotation": "note",
                    "likes_count": 4,
                    "tourist_likes_count": 5,
                    "rewards_count": 6,
                    "comments_count": 7,
                    "reading_count": 8,
                    "readers_count": 9,
                    "digested": True,
                    "sticky": True,
                    "create_time": "2026-06-10T12:00:00",
                    "modify_time": "2026-06-10T12:30:00",
                    "user_specific": {"liked": True, "subscribed": True},
                }
            ),
        )
        self.assertEqual(
            (202, None, None, None, None, 0, 0, 0, 0, 0, 0, False, False, None, None, False, False),
            _topic_record_params({"topic_id": 202}),
        )

    def test_talk_record_params_keep_insert_column_order(self):
        self.assertEqual((202, 9, "body"), _talk_record_params(202, 9, {"text": "body"}))
        self.assertEqual((202, None, ""), _talk_record_params(202, None, {}))

    def test_image_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (
                301,
                202,
                "image",
                "thumb-url",
                100,
                80,
                "large-url",
                1000,
                800,
                "origin-url",
                1200,
                900,
                12345,
            ),
            _image_record_params(
                202,
                {
                    "image_id": 301,
                    "type": "image",
                    "thumbnail": {"url": "thumb-url", "width": 100, "height": 80},
                    "large": {"url": "large-url", "width": 1000, "height": 800},
                    "original": {"url": "origin-url", "width": 1200, "height": 900, "size": 12345},
                },
            ),
        )
        self.assertEqual((301, 202, None, None, None, None, None, None, None, None, None, None, None), _image_record_params(202, {"image_id": 301}))

    def test_comment_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (101, 303, 202, 9, 88, 10, "ok", "2026-06-10T12:00:00", 1, 2, 3, True),
            _comment_record_params(
                303,
                202,
                9,
                10,
                {
                    "comment_id": 101,
                    "parent_comment_id": 88,
                    "text": "ok",
                    "create_time": "2026-06-10T12:00:00",
                    "likes_count": 1,
                    "rewards_count": 2,
                    "replies_count": 3,
                    "sticky": True,
                },
            ),
        )
        self.assertEqual(
            (101, None, 202, None, None, None, "", None, 0, 0, 0, False),
            _comment_record_params(None, 202, None, None, {"comment_id": 101}),
        )

    def test_latest_like_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (202, 9, "2026-06-10T12:00:00"),
            _latest_like_record_params(202, 9, {"create_time": "2026-06-10T12:00:00"}),
        )

    def test_like_emoji_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (202, "[ok]", 2),
            _like_emoji_record_params(202, {"emoji_key": "[ok]", "likes_count": 2}),
        )
        self.assertEqual(
            (202, "[default]", 0),
            _like_emoji_record_params(202, {"emoji_key": "[default]"}),
        )

    def test_user_liked_emoji_record_params_keep_insert_column_order(self):
        self.assertEqual((202, "[ok]"), _user_liked_emoji_record_params(202, "[ok]"))

    def test_column_record_params_keep_insert_column_order(self):
        self.assertEqual((301, "weekly"), _column_record_params({"column_id": 301, "name": "weekly"}))
        self.assertEqual((301, ""), _column_record_params({"column_id": 301}))

    def test_topic_column_record_params_keep_insert_column_order(self):
        self.assertEqual((202, 301), _topic_column_record_params(202, 301))

    def test_solution_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (202, 401, 9, "answer"),
            _solution_record_params(202, 9, {"task_id": 401, "text": "answer"}),
        )
        self.assertEqual((202, None, None, ""), _solution_record_params(202, None, {}))

    def test_api_response_record_params_keep_insert_column_order(self):
        self.assertEqual(
            (True, "next", 2),
            _api_response_record_params({"succeeded": True, "resp_data": {"index": "next"}}, 2),
        )
        self.assertEqual((False, None, 0), _api_response_record_params({}, 0))

    def test_file_topic_relation_params_keep_sql_column_order(self):
        self.assertEqual((101, 202), _file_topic_relation_params(101, 202))

    def test_count_tables_builds_stats_from_cursor_counts(self):
        cursor = FakeCursor({"files": 3, "topics": 2})

        self.assertEqual({"files": 3, "topics": 2}, _count_tables(cursor, ("files", "topics")))
        self.assertEqual([("SELECT COUNT(*) FROM files", ()), ("SELECT COUNT(*) FROM topics", ())], cursor.executed)

    def test_count_tables_filters_direct_tables_by_group_scope(self):
        cursor = FakeCursor({"files": 3, "topics": 2})

        self.assertEqual({"files": 3, "topics": 2}, _count_tables(cursor, ("files", "topics"), group_id="303"))
        self.assertEqual(
            [
                ("SELECT COUNT(*) FROM files WHERE group_id = ?", (303,)),
                ("SELECT COUNT(*) FROM topics WHERE group_id = ?", (303,)),
            ],
            cursor.executed,
        )

    def test_count_tables_filters_child_tables_through_group_topics(self):
        cursor = FakeCursor({"talks": 4})

        self.assertEqual({"talks": 4}, _count_tables(cursor, ("talks",), group_id="303"))
        sql, params = cursor.executed[0]
        self.assertIn("WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", sql)
        self.assertEqual((303,), params)

    def test_count_files_scopes_by_group_and_defaults_missing_row_to_zero(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeRowCursor([(5,)])
        db.group_id = "303"

        self.assertEqual(5, ZSXQFileDatabase.count_files(db))
        self.assertEqual([("SELECT COUNT(*) FROM files WHERE group_id = ?", (303,))], db.cursor.executed)

        missing_db = object.__new__(ZSXQFileDatabase)
        missing_db.cursor = FakeRowCursor([])
        missing_db.group_id = "303"

        self.assertEqual(0, ZSXQFileDatabase.count_files(missing_db, group_id="404"))
        self.assertEqual([("SELECT COUNT(*) FROM files WHERE group_id = ?", (404,))], missing_db.cursor.executed)

    def test_get_download_file_record_scopes_and_normalizes_row(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeRowCursor([(101, None, None, None), None])
        db.group_id = "303"

        record = ZSXQFileDatabase.get_download_file_record(db, 101)
        missing = ZSXQFileDatabase.get_download_file_record(db, 102, group_id="404")

        self.assertEqual((101, "file_101", 0, 0), record)
        self.assertIsNone(missing)
        self.assertEqual(
            [
                (
                    "SELECT file_id, name, size, download_count FROM files WHERE file_id = ? AND group_id = ?",
                    (101, 303),
                ),
                (
                    "SELECT file_id, name, size, download_count FROM files WHERE file_id = ? AND group_id = ?",
                    (102, 404),
                ),
            ],
            db.cursor.executed,
        )

    def test_get_file_status_record_scopes_and_preserves_status_row(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeRowCursor([("file.pdf", 456, None), None])
        db.group_id = "303"

        record = ZSXQFileDatabase.get_file_status_record(db, 101)
        missing = ZSXQFileDatabase.get_file_status_record(db, 102, group_id="404")

        self.assertEqual(("file.pdf", 456, None), record)
        self.assertIsNone(missing)
        self.assertEqual(
            [
                (
                    "SELECT name, size, download_status FROM files WHERE file_id = ? AND group_id = ?",
                    (101, 303),
                ),
                (
                    "SELECT name, size, download_status FROM files WHERE file_id = ? AND group_id = ?",
                    (102, 404),
                ),
            ],
            db.cursor.executed,
        )

    def test_get_file_download_stats_scopes_and_defaults_missing_row_to_zeroes(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeRowCursor([(9, 4, 3, None), None])
        db.group_id = "303"

        stats = ZSXQFileDatabase.get_file_download_stats(db)
        missing_stats = ZSXQFileDatabase.get_file_download_stats(db, group_id="404")

        self.assertEqual((9, 4, 3, 0), stats)
        self.assertEqual((0, 0, 0, 0), missing_stats)
        first_sql, first_params = db.cursor.executed[0]
        second_sql, second_params = db.cursor.executed[1]
        self.assertIn(
            "COUNT(CASE WHEN download_status IN ('completed', 'downloaded', 'skipped') THEN 1 END)",
            first_sql,
        )
        self.assertEqual((303,), first_params)
        self.assertEqual((404,), second_params)
        self.assertEqual(first_sql, second_sql)

    def test_load_file_list_page_keeps_empty_status_unfiltered(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeListPageCursor(total=0)
        db.group_id = "123"

        page = ZSXQFileDatabase.load_file_list_page(db)

        query, params = db.cursor.executed[0]
        count_query, count_params = db.cursor.executed[1]
        self.assertIn("LEFT JOIN file_ai_analyses faa ON faa.file_id = f.file_id", query)
        self.assertNotIn("f.download_status IN", query)
        self.assertNotIn("f.download_status =", query)
        self.assertNotIn("f.download_status IN", count_query)
        self.assertNotIn("f.download_status =", count_query)
        self.assertEqual((123, 20, 0), params)
        self.assertEqual((123,), count_params)
        self.assertEqual([], page.records)
        self.assertEqual(0, page.total)

    def test_load_file_list_page_applies_completed_search_analysis_and_pagination(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeListPageCursor(
            rows=[
                (
                    101,
                    "Report.PDF",
                    123,
                    7,
                    "2026-06-10T10:00:00+08:00",
                    "downloaded",
                    r"C:\old\Report.PDF",
                    "E1",
                    "boom",
                    "2026-06-11T09:00:00+08:00",
                    "2026-06-11T10:00:00+08:00",
                )
            ],
            total=21,
        )
        db.group_id = "123"

        page = ZSXQFileDatabase.load_file_list_page(
            db,
            page=2,
            per_page=5,
            status="completed",
            search=" Foo ",
            analysis_status="analyzed",
        )

        query, params = db.cursor.executed[0]
        count_query, count_params = db.cursor.executed[1]
        self.assertIn("f.download_status IN (?, ?, ?)", query)
        self.assertIn("faa.updated_at IS NOT NULL", query)
        self.assertIn("LOWER(COALESCE(f.name, '')) LIKE ?", query)
        self.assertEqual((123, "completed", "downloaded", "skipped", *["%foo%"] * 8, 5, 5), params)
        self.assertEqual((123, "completed", "downloaded", "skipped", *["%foo%"] * 8), count_params)
        self.assertTrue(count_query.strip().startswith("SELECT COUNT(*)"))
        self.assertEqual(21, page.total)
        self.assertEqual(101, page.records[0].file_id)
        self.assertEqual("2026-06-11T10:00:00+08:00", page.records[0].analysis_updated_at)

    def test_load_file_list_page_applies_pending_analysis_status(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeListPageCursor(total=0)
        db.group_id = "group-1"

        ZSXQFileDatabase.load_file_list_page(db, analysis_status="pending")

        self.assertTrue(any("faa.updated_at IS NULL" in sql for sql, _params in db.cursor.executed))
        self.assertEqual(("group-1", 20, 0), db.cursor.executed[0][1])
        self.assertEqual(("group-1",), db.cursor.executed[1][1])

    def test_clear_group_file_records_deletes_scoped_file_tables_and_commits(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeClearFileRecordsCursor([5, 4, 3, 2])
        db.conn = FakeAnalysisConnection()
        db.group_id = "303"

        deleted = ZSXQFileDatabase.clear_group_file_records(db)

        self.assertEqual(
            {
                "file_ai_analyses": 5,
                "files": 4,
                "file_topic_relations": 3,
                "topic_files": 2,
            },
            deleted,
        )
        self.assertEqual(1, db.conn.commits)
        self.assertEqual(4, len(db.cursor.executed))
        self.assertIn("DELETE FROM file_ai_analyses WHERE file_id IN", db.cursor.executed[0][0])
        self.assertIn("UNION SELECT file_id FROM file_topic_relations", db.cursor.executed[0][0])
        self.assertIn("UNION SELECT file_id FROM topic_files", db.cursor.executed[0][0])
        self.assertIn("DELETE FROM files WHERE file_id IN", db.cursor.executed[1][0])
        self.assertIn("DELETE FROM file_topic_relations WHERE topic_id IN", db.cursor.executed[2][0])
        self.assertIn("DELETE FROM topic_files WHERE topic_id IN", db.cursor.executed[3][0])
        self.assertEqual((303, 303, 303), db.cursor.executed[0][1])
        self.assertEqual((303, 303, 303), db.cursor.executed[1][1])
        self.assertEqual((303,), db.cursor.executed[2][1])
        self.assertEqual((303,), db.cursor.executed[3][1])

    def test_close_connection_ignores_none_and_closes_connection(self):
        _close_connection(None)

        conn = FakeConnection()
        _close_connection(conn)

        self.assertTrue(conn.closed)

    def test_import_file_response_writes_topic_before_file_and_relation(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        fake = FakeImportDatabase()
        db.cursor = fake
        db.conn = fake
        db.insert_group = fake.insert_group
        db.insert_topic = fake.insert_topic
        db.insert_file = fake.insert_file
        db.insert_talk = fake.insert_talk
        db.insert_topic_files = fake.insert_topic_files

        stats = ZSXQFileDatabase.import_file_response(
            db,
            {
                "succeeded": True,
                "resp_data": {
                    "index": "next",
                    "files": [
                        {
                            "file": {"file_id": 101, "name": "memo.pdf"},
                            "topic": {
                                "topic_id": 202,
                                "group": {"group_id": 303, "name": "group"},
                                "talk": {"files": [{"file_id": 101, "name": "memo.pdf"}]},
                            },
                        }
                    ],
                },
            },
        )

        ordered = [call[0] for call in fake.calls]
        self.assertLess(ordered.index("group"), ordered.index("topic"))
        self.assertLess(ordered.index("topic"), ordered.index("file"))
        self.assertLess(ordered.index("file"), ordered.index("insert_relation"))
        self.assertEqual(1, stats["files"])
        self.assertEqual(1, stats["topics"])
        self.assertEqual(1, stats["groups"])
        self.assertIn(("api_response", (True, "next", 1)), fake.calls)
        self.assertIn(("file", 101, 303, 202), fake.calls)
        self.assertIn(("delete_relation", (101, 202)), fake.calls)
        self.assertIn(("insert_relation", (101, 202)), fake.calls)

    def test_import_file_response_counts_current_payload_shapes(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        fake = FakeImportDatabase()
        db.cursor = fake
        db.conn = fake
        db.insert_group = fake.insert_group
        db.insert_topic = fake.insert_topic
        db.insert_file = fake.insert_file
        db.insert_talk = fake.insert_talk
        db.insert_topic_files = fake.insert_topic_files
        db.insert_images = lambda topic_id, images: fake.calls.append(("images", topic_id, len(images)))
        db.insert_latest_likes = lambda topic_id, likes: fake.calls.append(("likes", topic_id, len(likes)))
        db.insert_comments = lambda topic_id, comments: fake.calls.append(("comments", topic_id, len(comments)))
        db.insert_columns = lambda topic_id, columns: fake.calls.append(("columns", topic_id, len(columns)))

        def fake_insert_solution(topic_id, solution):
            fake.calls.append(("solution", topic_id, solution.get("task_id")))
            return 777

        db.insert_solution = fake_insert_solution

        stats = ZSXQFileDatabase.import_file_response(
            db,
            {
                "succeeded": True,
                "resp_data": {
                    "files": [
                        {
                            "file": {"file_id": 101, "name": "memo.pdf"},
                            "topic": {
                                "topic_id": 202,
                                "group": {"group_id": 303, "name": "group"},
                                "talk": {"images": [{"image_id": 1}, {"image_id": 2}]},
                                "latest_likes": [{"owner": {"user_id": 9}}],
                                "show_comments": [{"comment_id": 1}, {"text": "missing id"}],
                                "columns": [{"column_id": 301}, {"name": "missing id"}],
                                "solution": {"task_id": 401},
                            },
                        }
                    ],
                },
            },
        )

        self.assertEqual(
            {
                "files": 1,
                "topics": 1,
                "users": 0,
                "groups": 1,
                "images": 2,
                "comments": 2,
                "likes": 1,
                "columns": 2,
                "solutions": 1,
            },
            stats,
        )

    def test_insert_file_writes_group_and_topic_ids(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        cursor = FakeCommentCursor()
        db.cursor = cursor

        file_id = ZSXQFileDatabase.insert_file(
            db,
            {"file_id": 101, "name": "memo.pdf", "hash": "h", "size": 20},
            group_id="303",
            topic_id=202,
        )

        self.assertEqual(101, file_id)
        sql, params = cursor.calls[-1]
        self.assertIn("INSERT INTO files", sql)
        self.assertIn("file_id, group_id, topic_id", sql)
        self.assertIn("group_id = COALESCE", sql)
        self.assertEqual((101, 303, 202), params[:3])

    def test_insert_user_and_group_use_record_params(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()

        self.assertIsNone(ZSXQFileDatabase.insert_user(db, {}))
        self.assertIsNone(ZSXQFileDatabase.insert_group(db, {}))
        self.assertEqual([], db.cursor.calls)

        self.assertEqual(9, ZSXQFileDatabase.insert_user(db, {"user_id": 9, "name": "Alice"}))
        user_sql, user_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO users", user_sql)
        self.assertEqual((9, "Alice", None, None, None, None, None), user_params)

        self.assertEqual(303, ZSXQFileDatabase.insert_group(db, {"group_id": 303, "name": "group"}))
        group_sql, group_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO groups", group_sql)
        self.assertEqual((303, "group", None, None), group_params)

    def test_insert_topic_uses_record_params(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()

        self.assertIsNone(ZSXQFileDatabase.insert_topic(db, {}))
        self.assertEqual([], db.cursor.calls)

        self.assertEqual(
            202,
            ZSXQFileDatabase.insert_topic(
                db,
                {
                    "topic_id": 202,
                    "group": {"group_id": 303},
                    "type": "talk",
                    "title": "title",
                    "user_specific": {"liked": True},
                },
            ),
        )
        topic_sql, topic_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO topics", topic_sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", topic_sql)
        self.assertEqual((202, 303, "talk", "title", None), topic_params[:5])
        self.assertEqual((False, None, None, True, False), topic_params[12:])

    def test_insert_talk_uses_record_params_after_user_upsert(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()
        users = []

        def fake_insert_user(user):
            users.append(user)
            return user.get("user_id") if user else None

        db.insert_user = fake_insert_user

        self.assertIsNone(ZSXQFileDatabase.insert_talk(db, 202, {}))
        self.assertEqual([], db.cursor.calls)
        self.assertEqual([], users)

        self.assertIsNone(
            ZSXQFileDatabase.insert_talk(db, 202, {"owner": {"user_id": 9}, "text": "body"})
        )
        talk_sql, talk_params = db.cursor.calls[-1]
        self.assertEqual([{"user_id": 9}], users)
        self.assertIn("INSERT INTO talks", talk_sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", talk_sql)
        self.assertEqual((202, 9, "body"), talk_params)

    def test_insert_images_uses_record_params_and_skips_missing_ids(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()

        ZSXQFileDatabase.insert_images(
            db,
            202,
            [
                {"type": "image"},
                {
                    "image_id": 301,
                    "type": "image",
                    "thumbnail": {"url": "thumb-url", "width": 100, "height": 80},
                    "large": {"url": "large-url", "width": 1000, "height": 800},
                    "original": {"url": "origin-url", "width": 1200, "height": 900, "size": 12345},
                },
            ],
        )

        self.assertEqual(1, len(db.cursor.calls))
        image_sql, image_params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO images", image_sql)
        self.assertIn("ON CONFLICT(image_id) DO UPDATE SET", image_sql)
        self.assertEqual(
            (301, 202, "image", "thumb-url", 100, 80, "large-url", 1000, 800, "origin-url", 1200, 900, 12345),
            image_params,
        )

    def test_update_file_download_status_casts_timestamp_to_text(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        cursor = FakeCommentCursor()
        db.cursor = cursor
        db.conn = FakeAnalysisConnection()
        db.group_id = "303"

        db.update_file_download_status(101, "completed", r"C:\tmp\file.pdf")

        sql, params = cursor.calls[-1]
        self.assertIn("CURRENT_TIMESTAMP::text", sql)
        self.assertIn("download_error_code", sql)
        self.assertIn("last_download_attempt_at", sql)
        self.assertEqual(
            ("completed", r"C:\tmp\file.pdf", "completed", "completed", None, "completed", None, 101, 303, 303),
            params,
        )
        self.assertEqual(1, db.conn.commits)

    def test_update_file_download_status_persists_failure_reason(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        cursor = FakeCommentCursor()
        db.cursor = cursor
        db.conn = FakeAnalysisConnection()
        db.group_id = "303"

        db.update_file_download_status(101, "failed", error_code="size_mismatch", error_message="bad size")

        _sql, params = cursor.calls[-1]
        self.assertEqual(
            ("failed", None, "failed", "failed", "size_mismatch", "failed", "bad size", 101, 303, 303),
            params,
        )
        self.assertEqual(1, db.conn.commits)

    def test_file_ai_analysis_queries_are_scoped_by_group(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        cursor = FakeAnalysisCursor()
        db.cursor = cursor
        db.conn = FakeAnalysisConnection()
        db.group_id = "303"

        db.get_file_ai_analysis(101)
        select_sql, select_params = cursor.calls[-1]
        self.assertIn("WHERE file_id = ? AND (? IS NULL OR group_id = ?)", select_sql)
        self.assertEqual((101, 303, 303), select_params)

        db.upsert_file_ai_analysis(101, status="completed", summary="ok")
        insert_sql, insert_params = cursor.calls[-1]
        self.assertIn("file_id, group_id, status", insert_sql)
        self.assertEqual((101, 303, "completed"), insert_params[:3])

    def test_insert_comments_uses_record_params_and_skips_missing_ids(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()
        db.group_id = "303"
        users = []

        def fake_insert_user(user):
            users.append(user)
            return user.get("user_id") if user else None

        db.insert_user = fake_insert_user

        db.insert_comments(
            202,
            [
                {"text": "missing id"},
                {
                    "comment_id": 101,
                    "owner": {"user_id": 9},
                    "repliee": {"user_id": 10},
                    "parent_comment_id": 88,
                    "text": "ok",
                    "create_time": "2026-06-10T12:00:00",
                    "likes_count": 1,
                    "rewards_count": 2,
                    "replies_count": 3,
                    "sticky": True,
                },
            ],
        )

        self.assertEqual([{"user_id": 9}, {"user_id": 10}], users)
        self.assertEqual(1, len(db.cursor.calls))
        sql, params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO comments", sql)
        self.assertIn("ON CONFLICT(comment_id) DO UPDATE SET", sql)
        self.assertIn("comment_id, group_id, topic_id", sql)
        self.assertEqual(
            (101, 303, 202, 9, 88, 10, "ok", "2026-06-10T12:00:00", 1, 2, 3, True),
            params,
        )

    def test_insert_columns_uses_record_params_and_skips_missing_ids(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()

        ZSXQFileDatabase.insert_columns(
            db,
            202,
            [{"name": "missing id"}, {"column_id": 301, "name": "weekly"}, {"column_id": 302}],
        )

        self.assertEqual(4, len(db.cursor.calls))
        first_column_sql, first_column_params = db.cursor.calls[0]
        first_relation_sql, first_relation_params = db.cursor.calls[1]
        second_column_sql, second_column_params = db.cursor.calls[2]
        second_relation_sql, second_relation_params = db.cursor.calls[3]
        self.assertIn("INSERT INTO columns", first_column_sql)
        self.assertIn("ON CONFLICT(column_id) DO UPDATE SET", first_column_sql)
        self.assertEqual((301, "weekly"), first_column_params)
        self.assertIn("INSERT INTO topic_columns", first_relation_sql)
        self.assertIn("ON CONFLICT(topic_id, column_id) DO NOTHING", first_relation_sql)
        self.assertEqual((202, 301), first_relation_params)
        self.assertEqual((302, ""), second_column_params)
        self.assertEqual((202, 302), second_relation_params)

    def test_insert_solution_uses_record_params_and_returns_id(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()
        db.cursor.row = (777,)
        users = []

        def fake_insert_user(user):
            users.append(user)
            return user.get("user_id") if user else None

        db.insert_user = fake_insert_user

        self.assertIsNone(ZSXQFileDatabase.insert_solution(db, 202, {}))
        self.assertEqual([], db.cursor.calls)
        self.assertEqual([], users)

        solution_id = ZSXQFileDatabase.insert_solution(
            db,
            202,
            {
                "task_id": 401,
                "owner": {"user_id": 9},
                "text": "answer",
                "files": [
                    {
                        "file_id": 101,
                        "name": "memo.pdf",
                        "hash": "abc",
                        "size": 20,
                        "duration": 3,
                        "download_count": 4,
                        "create_time": "2026-06-10T12:00:00",
                    }
                ],
            },
        )

        self.assertEqual(777, solution_id)
        self.assertEqual([{"user_id": 9}], users)
        self.assertEqual(2, len(db.cursor.calls))
        solution_sql, solution_params = db.cursor.calls[0]
        solution_file_sql, solution_file_params = db.cursor.calls[1]
        self.assertIn("INSERT INTO solutions", solution_sql)
        self.assertIn("RETURNING id", solution_sql)
        self.assertEqual((202, 401, 9, "answer"), solution_params)
        self.assertIn("INSERT INTO solution_files", solution_file_sql)
        self.assertIn("ON CONFLICT(solution_id, file_id) DO UPDATE SET", solution_file_sql)
        self.assertEqual((777, 101, "memo.pdf", "abc", 20, 3, 4, "2026-06-10T12:00:00"), solution_file_params)

    def test_content_child_writes_use_explicit_unique_semantics(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()
        db.insert_user = lambda user: user.get("user_id") if user else None

        ZSXQFileDatabase.insert_talk(db, 202, {"owner": {"user_id": 9}, "text": "body"})
        talk_sql, _talk_params = db.cursor.calls[-1]
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", talk_sql)

        ZSXQFileDatabase.insert_latest_likes(
            db,
            202,
            [{"owner": {"user_id": 9}, "create_time": "2026-01-01"}],
        )
        _latest_delete_sql, latest_delete_params = db.cursor.calls[-2]
        _latest_sql, latest_params = db.cursor.calls[-1]
        calls = "\n".join(sql for sql, _params in db.cursor.calls)
        self.assertIn("DELETE FROM latest_likes WHERE topic_id = ?", calls)
        self.assertIn("ON CONFLICT(topic_id, owner_user_id, create_time) DO NOTHING", calls)
        self.assertEqual((202,), latest_delete_params)
        self.assertEqual((202, 9, "2026-01-01"), latest_params)

        ZSXQFileDatabase.insert_like_emojis(
            db,
            202,
            {"emojis": [{"emoji_key": "[ok]", "likes_count": 2}, {"emoji_key": "[default]"}]},
        )
        first_emoji_sql, first_emoji_params = db.cursor.calls[-2]
        second_emoji_sql, second_emoji_params = db.cursor.calls[-1]
        self.assertIn("ON CONFLICT(topic_id, emoji_key) DO UPDATE SET", first_emoji_sql)
        self.assertIn("ON CONFLICT(topic_id, emoji_key) DO UPDATE SET", second_emoji_sql)
        self.assertEqual((202, "[ok]", 2), first_emoji_params)
        self.assertEqual((202, "[default]", 0), second_emoji_params)

        ZSXQFileDatabase.insert_user_liked_emojis(db, 202, ["[ok]"])
        user_emoji_sql, user_emoji_params = db.cursor.calls[-1]
        self.assertIn("ON CONFLICT(topic_id, emoji_key) DO NOTHING", user_emoji_sql)
        self.assertEqual((202, "[ok]"), user_emoji_params)

    def test_runtime_create_tables_and_migration_are_noops(self):
        from backend.storage.zsxq_file_database import ZSXQFileDatabase

        db = object.__new__(ZSXQFileDatabase)
        db.cursor = FakeCommentCursor()

        self.assertIsNone(ZSXQFileDatabase.create_tables(db))
        self.assertIsNone(ZSXQFileDatabase._migrate_database(db))
        self.assertEqual([], db.cursor.calls)


if __name__ == "__main__":
    unittest.main()
