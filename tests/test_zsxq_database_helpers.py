import unittest
from unittest.mock import patch

from backend.storage.zsxq_database import (
    _answer_insert_statement,
    _article_insert_statement,
    _beijing_now_timestamp,
    _build_pagination,
    _comment_image_batch_from_comment,
    _comment_insert_statement,
    _database_stats_count_query,
    _delete_latest_likes_statement,
    _file_exists_query,
    _format_tag_row,
    _format_tag_topic_row,
    _group_id_param,
    _group_insert_statement,
    _image_insert_statement,
    _insert_tag_statement,
    _insert_topic_tag_statement,
    _iter_additional_comment_user_payloads,
    _iter_topic_user_payloads_from_data,
    _iter_valid_comment_image_payloads,
    _iter_valid_latest_like_payloads,
    _iter_valid_like_emoji_payloads,
    _iter_valid_user_liked_emoji_keys,
    _like_emoji_insert_statement,
    _latest_like_insert_statement,
    _like_insert_statement,
    _newest_topic_create_time_query,
    _nullable_group_id_param,
    _oldest_topic_create_time_query,
    _question_insert_statement,
    _refresh_tag_topic_count_statement,
    _replace_file_topic_relation,
    _talk_insert_statement,
    _tag_id_by_name_query,
    _tags_by_group_query,
    _topic_create_time_by_id_query,
    _topic_count_by_tag_query,
    _topic_detail_scope,
    _topic_count_query,
    _topic_exists_query,
    _topic_files_backfill_query,
    _topic_file_payload_from_row,
    _topic_file_insert_statement,
    _topic_group_id_query,
    _topic_image_payloads_from_data,
    _topic_insert_statement,
    _topic_stats_update_statement,
    _topic_tags_from_data,
    _topics_by_tag_query,
    _update_tag_hid_statement,
    _upsert_core_file,
    _user_liked_emoji_insert_statement,
    _user_insert_statement,
)


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 0
        self.row = None

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        if "INSERT INTO file_topic_relations" in query:
            self.rowcount = 1
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []


class FakeTimestampCursor(FakeCursor):
    def __init__(self, rows):
        super().__init__()
        self.rows = list(rows)

    def fetchone(self):
        if self.rows:
            return self.rows.pop(0)
        return None


class FakeSequenceCursor(FakeTimestampCursor):
    pass


class FakeFailingExecuteCursor(FakeCursor):
    def execute(self, query, params=()):
        super().execute(query, params)
        raise RuntimeError("temporary tag-link failure")


class FakeTagReadCursor(FakeCursor):
    def __init__(self, tag_rows=None, topic_rows=None, total=0, raises=False):
        super().__init__()
        self.tag_rows = list(tag_rows or [])
        self.topic_rows = list(topic_rows or [])
        self.total = total
        self.raises = raises
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        super().execute(query, params)
        if self.raises:
            raise RuntimeError("temporary tag read failure")
        return self

    def fetchall(self):
        if "FROM tags" in self.last_query:
            return self.tag_rows
        if "FROM topics t" in self.last_query:
            return self.topic_rows
        return []

    def fetchone(self):
        return (self.total,)


class FakeFileDatabase:
    def __init__(self):
        self.cursor = FakeCursor()


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


class FakeBackfillCursor(FakeCursor):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchall(self):
        if "FROM topic_files" in self.last_query:
            return self.rows
        return []

    def fetchone(self):
        if "SELECT 1 FROM files" in self.last_query:
            return None
        return self.row


class FakeDatabaseStatsCursor(FakeCursor):
    def __init__(self, fail_on_query_part=None):
        super().__init__()
        self.fail_on_query_part = fail_on_query_part

    def execute(self, query, params=()):
        super().execute(query, params)
        normalized = self.calls[-1][0]
        if self.fail_on_query_part and self.fail_on_query_part in normalized:
            raise RuntimeError("temporary stats failure")
        return self

    def fetchone(self):
        return (len(self.calls),)


class FakeTopicDetailCursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchone(self):
        if "FROM topics t LEFT JOIN groups" in self.last_query:
            return (
                202,
                "talk",
                "title",
                "2026-05-07T10:00:00.000+0800",
                0,
                1,
                3,
                0,
                0,
                2,
                5,
                6,
                0,
                0,
                "note",
                0,
                1,
                303,
                "group",
                "paid",
                "bg",
            )
        if "FROM talks" in self.last_query:
            return None
        return None

    def fetchall(self):
        if "FROM comments c" in self.last_query:
            return [
                (
                    10,
                    "parent",
                    "2026-05-07T11:00:00.000+0800",
                    1,
                    0,
                    0,
                    None,
                    1,
                    901,
                    "Alice",
                    "A",
                    "a.png",
                    "SH",
                    "parent owner",
                    None,
                    None,
                    None,
                ),
                (
                    11,
                    "child",
                    "2026-05-07T11:01:00.000+0800",
                    2,
                    0,
                    1,
                    10,
                    0,
                    902,
                    "Bob",
                    "B",
                    "b.png",
                    "BJ",
                    "child owner",
                    901,
                    "Alice",
                    "a.png",
                ),
            ]
        if "FROM images WHERE comment_id IN" in self.last_query:
            return [
                (
                    11,
                    701,
                    "image",
                    "thumb.jpg",
                    100,
                    80,
                    "large.jpg",
                    1000,
                    800,
                    "origin.jpg",
                    2000,
                    1600,
                    12345,
                )
            ]
        if "FROM likes" in self.last_query or "FROM like_emojis" in self.last_query:
            return []
        return []


class FakeTopicDetailTalkCursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchone(self):
        if "FROM topics t LEFT JOIN groups" in self.last_query:
            return (
                202,
                "talk",
                "title",
                "2026-05-07T10:00:00.000+0800",
                0,
                0,
                1,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
                0,
                0,
                303,
                "group",
                "paid",
                "bg",
            )
        if "FROM talks" in self.last_query:
            return ("body", 901, "Alice", "A", "a.png", "SH", "owner description")
        if "FROM articles" in self.last_query:
            return ("article title", 401, "article-url", "inline-url")
        return None

    def fetchall(self):
        if "FROM images WHERE topic_id = ?" in self.last_query and "comment_id IS NULL" in self.last_query:
            return [
                (
                    701,
                    "image",
                    "thumb.jpg",
                    100,
                    80,
                    "large.jpg",
                    1000,
                    800,
                    "origin.jpg",
                    2000,
                    1600,
                    12345,
                )
            ]
        if "FROM topic_files tf" in self.last_query:
            return [
                (
                    501,
                    "memo.pdf",
                    "hash-1",
                    123,
                    0,
                    7,
                    "2026-05-07T09:00:00.000+0800",
                )
            ]
        if "FROM likes" in self.last_query or "FROM comments c" in self.last_query or "FROM like_emojis" in self.last_query:
            return []
        return []


class FakeTopicDetailEngagementCursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchone(self):
        if "FROM topics t LEFT JOIN groups" in self.last_query:
            return (
                202,
                "talk",
                "title",
                "2026-05-07T10:00:00.000+0800",
                0,
                0,
                2,
                1,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
                0,
                0,
                303,
                "group",
                "paid",
                "bg",
            )
        if "FROM talks" in self.last_query:
            return None
        return None

    def fetchall(self):
        if "FROM likes l" in self.last_query:
            return [
                ("2026-05-07T12:00:00.000+0800", 901, "Alice", "a.png"),
                ("2026-05-07T11:00:00.000+0800", 902, "Bob", "b.png"),
            ]
        if "FROM like_emojis" in self.last_query:
            return [("[like]", 3), ("[ok]", 2)]
        if "FROM comments c" in self.last_query:
            return []
        return []


class FakeTopicDetailQACursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split())
        return super().execute(query, params)

    def fetchone(self):
        if "FROM topics t LEFT JOIN groups" in self.last_query:
            return (
                202,
                "q&a",
                "title",
                "2026-05-07T10:00:00.000+0800",
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
                "",
                0,
                0,
                303,
                "group",
                "paid",
                "bg",
            )
        if "FROM talks" in self.last_query:
            return None
        if "FROM questions q" in self.last_query:
            return (
                "question text",
                0,
                0,
                7,
                "2026-01-01T00:00:00.000+0800",
                "active",
                "question owner location",
                901,
                "Question Owner",
                "QO",
                "owner.png",
                "SH",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        if "FROM answers a" in self.last_query:
            return ("answer text", 902, "Answer Owner", "AO", "answer.png", "BJ", "answer owner")
        return None

    def fetchall(self):
        if "FROM likes l" in self.last_query or "FROM comments c" in self.last_query or "FROM like_emojis" in self.last_query:
            return []
        return []


class ZSXQDatabaseHelperTests(unittest.TestCase):
    def test_beijing_now_timestamp_preserves_existing_format(self):
        self.assertRegex(
            _beijing_now_timestamp(),
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$",
        )

    def test_build_pagination_calculates_pages(self):
        self.assertEqual(
            {'page': 2, 'per_page': 20, 'total': 41, 'pages': 3},
            _build_pagination(2, 20, 41),
        )

    def test_iter_topic_user_payloads_from_data_preserves_source_order(self):
        talk_owner = {"user_id": 1}
        question_owner = {"user_id": 2}
        questionee = {"user_id": 3}
        answer_owner = {"user_id": 4}
        like_owner = {"user_id": 5}
        empty_like_owner = {}
        comment_owner = {"user_id": 6}
        repliee = {"user_id": 7}

        self.assertEqual(
            [
                talk_owner,
                question_owner,
                questionee,
                answer_owner,
                like_owner,
                empty_like_owner,
                comment_owner,
                repliee,
            ],
            list(
                _iter_topic_user_payloads_from_data(
                    {
                        "talk": {"owner": talk_owner},
                        "question": {
                            "owner": question_owner,
                            "questionee": questionee,
                            "anonymous": False,
                        },
                        "answer": {"owner": answer_owner},
                        "latest_likes": [
                            {"owner": like_owner},
                            {"owner": empty_like_owner},
                            {},
                        ],
                        "show_comments": [
                            {"owner": comment_owner, "repliee": repliee},
                            {},
                        ],
                    }
                )
            ),
        )

    def test_topic_image_payloads_from_data_preserves_collection_order(self):
        talk_image = {"image_id": 1}
        comment_image = {"image_id": 2}
        missing_comment_id_image = {"image_id": 3}

        self.assertEqual(
            [
                (talk_image, None),
                (comment_image, 301),
                (missing_comment_id_image, None),
            ],
            _topic_image_payloads_from_data(
                {
                    "talk": {"images": [talk_image]},
                    "show_comments": [
                        {"comment_id": 301, "images": [comment_image]},
                        {"images": [missing_comment_id_image]},
                        {},
                    ],
                }
            ),
        )

    def test_iter_valid_like_emoji_payloads_filters_missing_keys(self):
        valid_first = {"emoji_key": "[ok]", "likes_count": 3}
        valid_second = {"emoji_key": "[fire]", "likes_count": 5}

        self.assertEqual(
            [valid_first, valid_second],
            list(
                _iter_valid_like_emoji_payloads(
                    [
                        {"likes_count": 9},
                        {"emoji_key": ""},
                        valid_first,
                        valid_second,
                    ]
                )
            ),
        )

    def test_iter_valid_user_liked_emoji_keys_filters_falsey_keys(self):
        self.assertEqual(
            ["[ok]", "[fire]"],
            list(_iter_valid_user_liked_emoji_keys(["", "[ok]", None, False, "[fire]"])),
        )

    def test_iter_valid_latest_like_payloads_filters_missing_user_ids(self):
        valid_first = {"owner": {"user_id": 901}, "create_time": "time-1"}
        valid_second = {"owner": {"user_id": 902}, "create_time": "time-2"}

        self.assertEqual(
            [(valid_first, 901), (valid_second, 902)],
            list(
                _iter_valid_latest_like_payloads(
                    [
                        {},
                        {"owner": {}},
                        {"owner": {"user_id": 0}},
                        valid_first,
                        valid_second,
                    ]
                )
            ),
        )

    def test_iter_valid_comment_image_payloads_filters_missing_image_ids(self):
        valid_first = {"image_id": 701, "type": "image"}
        valid_second = {"image_id": 702, "type": "image"}

        self.assertEqual(
            [valid_first, valid_second],
            list(_iter_valid_comment_image_payloads([{}, {"image_id": 0}, valid_first, valid_second])),
        )

    def test_comment_image_batch_from_comment_preserves_existing_access_semantics(self):
        self.assertIsNone(_comment_image_batch_from_comment({}))
        self.assertIsNone(_comment_image_batch_from_comment({"comment_id": 301, "images": []}))
        self.assertEqual(
            (301, [{"image_id": 701}]),
            _comment_image_batch_from_comment({"comment_id": 301, "images": [{"image_id": 701}]}),
        )

        with self.assertRaises(KeyError):
            _comment_image_batch_from_comment({"images": [{"image_id": 702}]})

    def test_iter_additional_comment_user_payloads_preserves_truthy_owner_repliee_order(self):
        owner = {"user_id": 901}
        repliee = {"user_id": 902}

        self.assertEqual([], list(_iter_additional_comment_user_payloads({})))
        self.assertEqual(
            [owner, repliee],
            list(
                _iter_additional_comment_user_payloads(
                    {"owner": owner, "repliee": repliee, "ignored": {"user_id": 903}}
                )
            ),
        )
        self.assertEqual([], list(_iter_additional_comment_user_payloads({"owner": {}, "repliee": None})))

    def test_format_tag_row_keeps_existing_fields(self):
        row = (1, "tag", "hid-1", 7, "2026-01-01")

        self.assertEqual(
            {
                'tag_id': 1,
                'tag_name': "tag",
                'hid': "hid-1",
                'topic_count': 7,
                'created_at': "2026-01-01",
            },
            _format_tag_row(row),
        )

    def test_format_tag_topic_row_maps_talk_author(self):
        row = (
            10,
            "title",
            "2026-01-01",
            1,
            2,
            3,
            "talk",
            0,
            1,
            None,
            None,
            "body",
            99,
            "author",
            "avatar.png",
        )

        topic = _format_tag_topic_row(row)

        self.assertEqual(10, topic["topic_id"])
        self.assertEqual("body", topic["talk_text"])
        self.assertFalse(topic["digested"])
        self.assertTrue(topic["sticky"])
        self.assertEqual({"user_id": 99, "name": "author", "avatar_url": "avatar.png"}, topic["author"])

    def test_format_tag_topic_row_maps_qa_texts(self):
        row = (
            11,
            "title",
            "2026-01-01",
            1,
            2,
            3,
            "q&a",
            None,
            None,
            "question",
            "",
            None,
            None,
            None,
            None,
        )

        topic = _format_tag_topic_row(row)

        self.assertEqual("question", topic["question_text"])
        self.assertEqual("", topic["answer_text"])
        self.assertNotIn("talk_text", topic)
        self.assertFalse(topic["digested"])
        self.assertFalse(topic["sticky"])

    def test_topic_tags_from_data_preserves_sources_decode_dedupe_and_empty_title_skip(self):
        tags = _topic_tags_from_data(
            {
                "talk": {"text": '<e type="hashtag" hid="h1" title="%23AI" />'},
                "question": {"text": '<e type="hashtag" hid="h2" title="Question" />'},
                "answer": {"text": '<e type="hashtag" hid="h3" title="%E7%AD%94%E6%A1%88" />'},
                "show_comments": [
                    {"text": '<e type="hashtag" hid="h1" title="%23AI" />'},
                    {"text": '<e type="hashtag" hid="h4" title="%23" />'},
                    {"text": ""},
                    {},
                ],
            }
        )

        self.assertEqual({("AI", "h1"), ("Question", "h2"), ("答案", "h3")}, tags)

    def test_tag_statement_helpers_preserve_sql_shape_and_params(self):
        lookup_sql, lookup_params = _tag_id_by_name_query(303, "AI")
        self.assertEqual("SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?", lookup_sql)
        self.assertEqual((303, "AI"), lookup_params)

        update_sql, update_params = _update_tag_hid_statement(7, "hid-1")
        self.assertEqual("UPDATE tags SET hid = ? WHERE tag_id = ?", update_sql)
        self.assertEqual(("hid-1", 7), update_params)

        insert_sql, insert_params = _insert_tag_statement(
            303,
            "AI",
            "hid-1",
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO tags (group_id, tag_name, hid, created_at) VALUES (?, ?, ?, ?) RETURNING tag_id",
            " ".join(insert_sql.split()),
        )
        self.assertEqual((303, "AI", "hid-1", "2026-06-12T10:00:00.000+0800"), insert_params)

        topic_tag_sql, topic_tag_params = _insert_topic_tag_statement(
            202,
            7,
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO topic_tags (topic_id, tag_id, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(topic_id, tag_id) DO NOTHING",
            " ".join(topic_tag_sql.split()),
        )
        self.assertEqual((202, 7, "2026-06-12T10:00:00.000+0800"), topic_tag_params)

        count_sql, count_params = _refresh_tag_topic_count_statement(7)
        self.assertEqual(
            "UPDATE tags SET topic_count = ( SELECT COUNT(*) FROM topic_tags WHERE tag_id = ? ) "
            "WHERE tag_id = ?",
            " ".join(count_sql.split()),
        )
        self.assertEqual((7, 7), count_params)

    def test_tag_read_query_helpers_preserve_sql_shape_and_params(self):
        tags_sql, tags_params = _tags_by_group_query(303)
        self.assertEqual(
            "SELECT tag_id, tag_name, hid, topic_count, created_at FROM tags "
            "WHERE group_id = ? ORDER BY topic_count DESC, tag_name ASC",
            " ".join(tags_sql.split()),
        )
        self.assertEqual((303,), tags_params)

        topics_sql, topics_params = _topics_by_tag_query(7, 5, 10)
        self.assertEqual(
            "SELECT t.topic_id, t.title, t.create_time, t.likes_count, t.comments_count, "
            "t.reading_count, t.type, t.digested, t.sticky, q.text as question_text, "
            "a.text as answer_text, tk.text as talk_text, u.user_id, u.name, u.avatar_url "
            "FROM topics t INNER JOIN topic_tags tt ON t.topic_id = tt.topic_id "
            "LEFT JOIN questions q ON t.topic_id = q.topic_id "
            "LEFT JOIN answers a ON t.topic_id = a.topic_id "
            "LEFT JOIN talks tk ON t.topic_id = tk.topic_id "
            "LEFT JOIN users u ON tk.owner_user_id = u.user_id "
            "WHERE tt.tag_id = ? ORDER BY t.create_time DESC LIMIT ? OFFSET ?",
            " ".join(topics_sql.split()),
        )
        self.assertEqual((7, 5, 10), topics_params)

        count_sql, count_params = _topic_count_by_tag_query(7)
        self.assertEqual(
            "SELECT COUNT(*) FROM topic_tags WHERE tag_id = ?",
            " ".join(count_sql.split()),
        )
        self.assertEqual((7,), count_params)

    def test_group_and_user_insert_statement_helpers_preserve_sql_shape_and_params(self):
        group_sql, group_params = _group_insert_statement(
            {
                "group_id": 303,
                "name": "group",
                "type": "paid",
                "background_url": "bg.png",
            },
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO groups (group_id, name, type, background_url, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(group_id) DO UPDATE SET "
            "name = excluded.name, type = excluded.type, background_url = excluded.background_url, "
            "created_at = excluded.created_at",
            " ".join(group_sql.split()),
        )
        self.assertEqual((303, "group", "paid", "bg.png", "2026-06-12T10:00:00.000+0800"), group_params)

        user_sql, user_params = _user_insert_statement(
            {
                "user_id": 901,
                "name": "Alice",
                "alias": "A",
                "avatar_url": "a.png",
                "location": "SH",
                "description": "owner",
                "ai_comment_url": "ai-url",
            },
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO users (user_id, name, alias, avatar_url, location, description, ai_comment_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "name = excluded.name, alias = excluded.alias, avatar_url = excluded.avatar_url, "
            "location = excluded.location, description = excluded.description, "
            "ai_comment_url = excluded.ai_comment_url, created_at = excluded.created_at",
            " ".join(user_sql.split()),
        )
        self.assertEqual(
            (901, "Alice", "A", "a.png", "SH", "owner", "ai-url", "2026-06-12T10:00:00.000+0800"),
            user_params,
        )

    def test_topic_insert_statement_helper_preserves_sql_shape_and_params(self):
        topic_sql, topic_params = _topic_insert_statement(
            {
                "topic_id": 202,
                "group": {"group_id": 303},
                "type": "talk",
                "title": "title",
                "create_time": "2026-05-07T10:00:00.000+0800",
                "digested": True,
                "sticky": True,
                "likes_count": 1,
                "tourist_likes_count": 2,
                "rewards_count": 3,
                "comments_count": 4,
                "reading_count": 5,
                "readers_count": 6,
                "answered": True,
                "silenced": True,
                "annotation": "note",
                "user_liked": True,
                "user_subscribed": True,
            },
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO topics (topic_id, group_id, type, title, create_time, digested, sticky, "
            "likes_count, tourist_likes_count, rewards_count, comments_count, reading_count, "
            "readers_count, answered, silenced, annotation, user_liked, user_subscribed, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(topic_id) DO UPDATE SET group_id = excluded.group_id, type = excluded.type, "
            "title = excluded.title, create_time = excluded.create_time, digested = excluded.digested, "
            "sticky = excluded.sticky, likes_count = excluded.likes_count, "
            "tourist_likes_count = excluded.tourist_likes_count, rewards_count = excluded.rewards_count, "
            "comments_count = excluded.comments_count, reading_count = excluded.reading_count, "
            "readers_count = excluded.readers_count, answered = excluded.answered, "
            "silenced = excluded.silenced, annotation = excluded.annotation, "
            "user_liked = excluded.user_liked, user_subscribed = excluded.user_subscribed, "
            "imported_at = excluded.imported_at",
            " ".join(topic_sql.split()),
        )
        self.assertEqual(
            (
                202,
                303,
                "talk",
                "title",
                "2026-05-07T10:00:00.000+0800",
                True,
                True,
                1,
                2,
                3,
                4,
                5,
                6,
                True,
                True,
                "note",
                True,
                True,
                "2026-06-12T10:00:00.000+0800",
            ),
            topic_params,
        )

    def test_topic_stats_update_statement_helper_preserves_sql_shape_and_params(self):
        sql, params = _topic_stats_update_statement(
            {
                "likes_count": 1,
                "tourist_likes_count": 2,
                "rewards_count": 3,
                "comments_count": 4,
                "reading_count": 5,
                "readers_count": 6,
                "digested": True,
                "sticky": True,
                "user_specific": {"liked": True, "subscribed": True},
            },
            202,
            303,
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "UPDATE topics SET likes_count = ?, tourist_likes_count = ?, rewards_count = ?, "
            "comments_count = ?, reading_count = ?, readers_count = ?, digested = ?, sticky = ?, "
            "user_liked = ?, user_subscribed = ?, imported_at = ? WHERE topic_id = ? "
            "AND (? IS NULL OR group_id = ?)",
            " ".join(sql.split()),
        )
        self.assertEqual(
            (
                1,
                2,
                3,
                4,
                5,
                6,
                True,
                True,
                True,
                True,
                "2026-06-12T10:00:00.000+0800",
                202,
                303,
                303,
            ),
            params,
        )

    def test_talk_insert_statement_helper_preserves_sql_shape_and_params(self):
        sql, params = _talk_insert_statement(
            202,
            {"owner": {"user_id": 901}, "text": "body"},
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO talks (topic_id, owner_user_id, text, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id) DO UPDATE SET "
            "owner_user_id = excluded.owner_user_id, text = excluded.text, "
            "created_at = excluded.created_at",
            " ".join(sql.split()),
        )
        self.assertEqual((202, 901, "body", "2026-06-12T10:00:00.000+0800"), params)

    def test_image_insert_statement_helper_preserves_sql_shape_and_default_params(self):
        sql, params = _image_insert_statement(
            202,
            {
                "image_id": 701,
                "type": "image",
                "thumbnail": {"url": "thumb.jpg"},
                "large": {"url": "large.jpg"},
                "original": {"url": "origin.jpg"},
            },
            None,
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO images (image_id, topic_id, comment_id, type, thumbnail_url, "
            "thumbnail_width, thumbnail_height, large_url, large_width, large_height, "
            "original_url, original_width, original_height, original_size, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(image_id) DO UPDATE SET topic_id = excluded.topic_id, "
            "comment_id = excluded.comment_id, type = excluded.type, "
            "thumbnail_url = excluded.thumbnail_url, thumbnail_width = excluded.thumbnail_width, "
            "thumbnail_height = excluded.thumbnail_height, large_url = excluded.large_url, "
            "large_width = excluded.large_width, large_height = excluded.large_height, "
            "original_url = excluded.original_url, original_width = excluded.original_width, "
            "original_height = excluded.original_height, original_size = excluded.original_size, "
            "created_at = excluded.created_at",
            " ".join(sql.split()),
        )
        self.assertEqual(
            (
                701,
                202,
                None,
                "image",
                "thumb.jpg",
                None,
                None,
                "large.jpg",
                None,
                None,
                "origin.jpg",
                None,
                None,
                None,
                "2026-06-12T10:00:00.000+0800",
            ),
            params,
        )

        _comment_sql, comment_params = _image_insert_statement(
            202,
            {"image_id": 702},
            11,
            "2026-06-12T10:00:00.000+0800",
            missing_numeric_default=0,
        )
        self.assertEqual(
            (
                702,
                202,
                11,
                "",
                "",
                0,
                0,
                "",
                0,
                0,
                "",
                0,
                0,
                0,
                "2026-06-12T10:00:00.000+0800",
            ),
            comment_params,
        )

    def test_like_statement_helpers_preserve_sql_shape_and_params(self):
        self.assertEqual(
            ("DELETE FROM latest_likes WHERE topic_id = ?", (202,)),
            (
                " ".join(_delete_latest_likes_statement(202)[0].split()),
                _delete_latest_likes_statement(202)[1],
            ),
        )

        like_sql, like_params = _like_insert_statement(
            202,
            901,
            {"create_time": "2026-01-01T10:00:00.000+0800"},
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO likes (topic_id, user_id, create_time, imported_at) VALUES (?, ?, ?, ?)",
            " ".join(like_sql.split()),
        )
        self.assertEqual(
            (202, 901, "2026-01-01T10:00:00.000+0800", "2026-06-12T10:00:00.000+0800"),
            like_params,
        )

        latest_sql, latest_params = _latest_like_insert_statement(
            202,
            901,
            {},
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO latest_likes (topic_id, owner_user_id, create_time, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id, owner_user_id, create_time) "
            "DO UPDATE SET created_at = excluded.created_at",
            " ".join(latest_sql.split()),
        )
        self.assertEqual((202, 901, "", "2026-06-12T10:00:00.000+0800"), latest_params)

    def test_like_emoji_insert_statement_helper_preserves_sql_shape_and_defaults(self):
        sql, params = _like_emoji_insert_statement(
            202,
            {"emoji_key": "[ok]"},
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO like_emojis (topic_id, emoji_key, likes_count, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id, emoji_key) DO UPDATE SET "
            "likes_count = excluded.likes_count, created_at = excluded.created_at",
            " ".join(sql.split()),
        )
        self.assertEqual((202, "[ok]", 0, "2026-06-12T10:00:00.000+0800"), params)

    def test_user_liked_emoji_insert_statement_helper_preserves_sql_shape_and_params(self):
        sql, params = _user_liked_emoji_insert_statement(202, "[ok]")

        self.assertEqual(
            "INSERT INTO user_liked_emojis (topic_id, emoji_key) VALUES (?, ?) "
            "ON CONFLICT(topic_id, emoji_key) DO NOTHING",
            " ".join(sql.split()),
        )
        self.assertEqual((202, "[ok]"), params)

    def test_comment_insert_statement_helper_preserves_sql_shape_and_params(self):
        sql, params = _comment_insert_statement(
            202,
            101,
            303,
            901,
            902,
            {
                "parent_comment_id": 100,
                "text": "ok",
                "create_time": "2026-01-01T10:00:00.000+0800",
                "likes_count": 1,
                "rewards_count": 2,
                "replies_count": 3,
                "sticky": True,
            },
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO comments (comment_id, group_id, topic_id, owner_user_id, "
            "parent_comment_id, repliee_user_id, text, create_time, likes_count, "
            "rewards_count, replies_count, sticky, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(comment_id) DO UPDATE SET group_id = excluded.group_id, "
            "topic_id = excluded.topic_id, owner_user_id = excluded.owner_user_id, "
            "parent_comment_id = excluded.parent_comment_id, "
            "repliee_user_id = excluded.repliee_user_id, text = excluded.text, "
            "create_time = excluded.create_time, likes_count = excluded.likes_count, "
            "rewards_count = excluded.rewards_count, replies_count = excluded.replies_count, "
            "sticky = excluded.sticky, imported_at = excluded.imported_at",
            " ".join(sql.split()),
        )
        self.assertEqual(
            (
                101,
                303,
                202,
                901,
                100,
                902,
                "ok",
                "2026-01-01T10:00:00.000+0800",
                1,
                2,
                3,
                True,
                "2026-06-12T10:00:00.000+0800",
            ),
            params,
        )

        _default_sql, default_params = _comment_insert_statement(202, 102, None, None, None, {}, "now")
        self.assertEqual((102, None, 202, None, None, None, "", "", 0, 0, 0, False, "now"), default_params)

    def test_question_and_answer_insert_statement_helpers_preserve_sql_shape_and_params(self):
        question_sql, question_params = _question_insert_statement(
            202,
            None,
            902,
            True,
            {
                "text": "anonymous question",
                "expired": True,
                "owner_detail": {
                    "questions_count": 7,
                    "estimated_join_time": "2024-01-01T00:00:00.000+0800",
                    "status": "active",
                },
                "owner_location": "Shanghai",
            },
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO questions (topic_id, owner_user_id, questionee_user_id, text, "
            "expired, anonymous, owner_questions_count, owner_join_time, owner_status, "
            "owner_location, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(topic_id) DO UPDATE SET owner_user_id = excluded.owner_user_id, "
            "questionee_user_id = excluded.questionee_user_id, text = excluded.text, "
            "expired = excluded.expired, anonymous = excluded.anonymous, "
            "owner_questions_count = excluded.owner_questions_count, "
            "owner_join_time = excluded.owner_join_time, owner_status = excluded.owner_status, "
            "owner_location = excluded.owner_location, created_at = excluded.created_at",
            " ".join(question_sql.split()),
        )
        self.assertEqual(
            (
                202,
                None,
                902,
                "anonymous question",
                True,
                True,
                7,
                "2024-01-01T00:00:00.000+0800",
                "active",
                "Shanghai",
                "2026-06-12T10:00:00.000+0800",
            ),
            question_params,
        )

        _default_question_sql, default_question_params = _question_insert_statement(
            202,
            901,
            None,
            False,
            {},
            "now",
        )
        self.assertEqual((202, 901, None, "", False, False, None, "", "", "", "now"), default_question_params)

        answer_sql, answer_params = _answer_insert_statement(
            202,
            901,
            {"text": "answer text"},
            "2026-06-12T10:00:00.000+0800",
        )
        self.assertEqual(
            "INSERT INTO answers (topic_id, owner_user_id, text, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(topic_id) DO UPDATE SET owner_user_id = excluded.owner_user_id, "
            "text = excluded.text, created_at = excluded.created_at",
            " ".join(answer_sql.split()),
        )
        self.assertEqual((202, 901, "answer text", "2026-06-12T10:00:00.000+0800"), answer_params)

    def test_article_insert_statement_helper_preserves_sql_shape_and_params(self):
        sql, params = _article_insert_statement(
            202,
            "article title",
            "401",
            {
                "article_url": "article-url",
                "inline_article_url": "inline-url",
            },
            "2026-05-07T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO articles (topic_id, title, article_id, article_url, inline_article_url, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(topic_id) DO UPDATE SET "
            "title = excluded.title, article_id = excluded.article_id, "
            "article_url = excluded.article_url, inline_article_url = excluded.inline_article_url, "
            "created_at = excluded.created_at",
            " ".join(sql.split()),
        )
        self.assertEqual(
            (
                202,
                "article title",
                "401",
                "article-url",
                "inline-url",
                "2026-05-07T10:00:00.000+0800",
            ),
            params,
        )

        _default_sql, default_params = _article_insert_statement(203, "", "402", {}, "")
        self.assertEqual((203, "", "402", "", "", ""), default_params)

    def test_topic_file_insert_statement_helper_preserves_sql_shape_and_params(self):
        sql, params = _topic_file_insert_statement(
            202,
            {
                "file_id": 501,
                "name": "memo.pdf",
                "hash": "abc",
                "size": 12,
                "duration": 3,
                "download_count": 4,
                "create_time": "2026-05-07T10:00:00.000+0800",
            },
            "2026-06-12T10:00:00.000+0800",
        )

        self.assertEqual(
            "INSERT INTO topic_files (topic_id, file_id, name, hash, size, duration, "
            "download_count, create_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(topic_id, file_id) DO UPDATE SET name = excluded.name, "
            "hash = excluded.hash, size = excluded.size, duration = excluded.duration, "
            "download_count = excluded.download_count, create_time = excluded.create_time, "
            "created_at = excluded.created_at",
            " ".join(sql.split()),
        )
        self.assertEqual(
            (
                202,
                501,
                "memo.pdf",
                "abc",
                12,
                3,
                4,
                "2026-05-07T10:00:00.000+0800",
                "2026-06-12T10:00:00.000+0800",
            ),
            params,
        )

        _default_sql, default_params = _topic_file_insert_statement(202, {"file_id": 502}, "now")
        self.assertEqual((202, 502, "", "", 0, 0, 0, "", "now"), default_params)

    def test_replace_file_topic_relation_deletes_then_inserts(self):
        file_db = FakeFileDatabase()

        rowcount = _replace_file_topic_relation(file_db, 101, 202)

        self.assertEqual(1, rowcount)
        self.assertEqual(
            [
                (
                    "DELETE FROM file_topic_relations WHERE file_id = ? AND topic_id = ?",
                    (101, 202),
                ),
                (
                    "INSERT INTO file_topic_relations (file_id, topic_id) VALUES (?, ?) ON CONFLICT(file_id, topic_id) DO NOTHING",
                    (101, 202),
                ),
            ],
            file_db.cursor.calls,
        )

    def test_upsert_core_file_uses_current_cursor(self):
        cursor = FakeCursor()

        file_id = _upsert_core_file(
            cursor,
            155,
            202,
            {
                "file_id": 101,
                "name": "memo.pdf",
                "hash": "abc",
                "size": 12,
                "duration": 0,
                "download_count": 3,
                "create_time": "2026-05-07T12:00:00.000+0800",
            },
        )

        self.assertEqual(101, file_id)
        self.assertEqual(1, len(cursor.calls))
        query, params = cursor.calls[0]
        self.assertIn("INSERT INTO files", query)
        self.assertIn("ON CONFLICT(file_id) DO UPDATE SET", query)
        self.assertEqual((101, 155, 202, "memo.pdf", "abc", 12, 0, 3, "2026-05-07T12:00:00.000+0800"), params)

    def test_topic_file_payload_from_row_maps_backfill_columns(self):
        row = (202, 101, "memo.pdf", "abc", 12, 0, 3, "2026-05-07T12:00:00.000+0800")

        self.assertEqual(
            {
                "file_id": 101,
                "name": "memo.pdf",
                "hash": "abc",
                "size": 12,
                "duration": 0,
                "download_count": 3,
                "create_time": "2026-05-07T12:00:00.000+0800",
            },
            _topic_file_payload_from_row(row),
        )

    def test_topic_files_backfill_query_preserves_scope_params_and_order(self):
        sql, params = _topic_files_backfill_query("303")

        self.assertEqual(
            "SELECT tf.topic_id, tf.file_id, tf.name, tf.hash, tf.size, tf.duration, "
            "tf.download_count, tf.create_time, t.group_id, t.type, t.title, t.annotation, "
            "t.create_time, t.likes_count, t.tourist_likes_count, t.rewards_count, "
            "t.comments_count, t.reading_count, t.readers_count, t.digested, t.sticky, "
            "t.user_liked, t.user_subscribed, g.name, g.type, g.background_url "
            "FROM topic_files tf LEFT JOIN topics t ON t.topic_id = tf.topic_id "
            "LEFT JOIN groups g ON g.group_id = t.group_id WHERE tf.file_id IS NOT NULL "
            "AND (? IS NULL OR t.group_id = ?) ORDER BY tf.topic_id ASC, tf.file_id ASC",
            " ".join(sql.split()),
        )
        self.assertEqual((303, 303), params)

        _unscoped_sql, unscoped_params = _topic_files_backfill_query(None)
        self.assertEqual(("", ""), unscoped_params)

    def test_backfill_topic_files_to_core_tables_uses_current_database_cursor(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        row = (
            202,
            101,
            "memo.pdf",
            "abc",
            12,
            0,
            3,
            "2026-05-07T12:00:00.000+0800",
            303,
            "talk",
            "title",
            "",
            "2026-05-07T10:00:00.000+0800",
            1,
            0,
            0,
            2,
            3,
            4,
            False,
            False,
            False,
            False,
            "group",
            "paid",
            "bg",
        )
        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeBackfillCursor([row])
        db.conn = FakeConnection()
        db.group_id = "303"

        stats = ZSXQDatabase.backfill_topic_files_to_core_tables(db, batch_size=1)

        self.assertEqual({"scanned": 1, "new_files": 1, "relations": 1, "topic_files": 1}, stats)
        self.assertGreaterEqual(db.conn.commits, 1)
        self.assertEqual(
            "SELECT tf.topic_id, tf.file_id, tf.name, tf.hash, tf.size, tf.duration, "
            "tf.download_count, tf.create_time, t.group_id, t.type, t.title, t.annotation, "
            "t.create_time, t.likes_count, t.tourist_likes_count, t.rewards_count, "
            "t.comments_count, t.reading_count, t.readers_count, t.digested, t.sticky, "
            "t.user_liked, t.user_subscribed, g.name, g.type, g.background_url "
            "FROM topic_files tf LEFT JOIN topics t ON t.topic_id = tf.topic_id "
            "LEFT JOIN groups g ON g.group_id = t.group_id WHERE tf.file_id IS NOT NULL "
            "AND (? IS NULL OR t.group_id = ?) ORDER BY tf.topic_id ASC, tf.file_id ASC",
            db.cursor.calls[0][0],
        )
        self.assertEqual((303, 303), db.cursor.calls[0][1])
        calls = "\n".join(sql for sql, _params in db.cursor.calls)
        self.assertIn("INSERT INTO groups", calls)
        self.assertIn("INSERT INTO files", calls)
        self.assertIn("INSERT INTO file_topic_relations", calls)

    def test_group_id_param_casts_numeric_ids_for_scoped_queries(self):
        self.assertEqual(155, _group_id_param("155"))
        self.assertEqual("group-x", _group_id_param("group-x"))
        self.assertEqual("", _group_id_param(None))

    def test_nullable_group_id_param_uses_none_for_unscoped_queries(self):
        self.assertIsNone(_nullable_group_id_param(None))
        self.assertIsNone(_nullable_group_id_param(""))
        self.assertEqual(155, _nullable_group_id_param("155"))
        self.assertEqual("group-x", _nullable_group_id_param("group-x"))

    def test_topic_detail_scope_preserves_existing_group_id_semantics(self):
        self.assertEqual(
            (None, "t.topic_id = ?", [202]),
            _topic_detail_scope(202, None),
        )
        self.assertEqual(
            (303, "t.topic_id = ? AND t.group_id = ?", [202, 303]),
            _topic_detail_scope(202, "303"),
        )
        self.assertEqual(
            ("", "t.topic_id = ? AND t.group_id = ?", [202, ""]),
            _topic_detail_scope(202, ""),
        )

    def test_existence_query_helpers_preserve_group_id_param_semantics(self):
        topic_sql, topic_params = _topic_exists_query(202, "303")
        self.assertEqual(
            "SELECT 1 FROM topics WHERE topic_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1",
            topic_sql,
        )
        self.assertEqual((202, 303, 303), topic_params)
        self.assertEqual((202, "", ""), _topic_exists_query(202, None)[1])

        file_sql, file_params = _file_exists_query(101, "303")
        self.assertEqual(
            "SELECT 1 FROM files WHERE file_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1",
            file_sql,
        )
        self.assertEqual((101, 303, 303), file_params)
        self.assertEqual((101, "", ""), _file_exists_query(101, None)[1])

        group_sql, group_params = _topic_group_id_query(202)
        self.assertEqual("SELECT group_id FROM topics WHERE topic_id = ? LIMIT 1", group_sql)
        self.assertEqual((202,), group_params)

        create_time_sql, create_time_params = _topic_create_time_by_id_query(202)
        self.assertEqual("SELECT create_time FROM topics WHERE topic_id = ?", create_time_sql)
        self.assertEqual((202,), create_time_params)

    def test_topic_timestamp_query_helpers_preserve_existing_scope_semantics(self):
        newest_sql, newest_params = _newest_topic_create_time_query(None, nullable_scope=True)
        self.assertIn("ORDER BY create_time DESC LIMIT 1", " ".join(newest_sql.split()))
        self.assertEqual((None, None), newest_params)

        oldest_sql, oldest_params = _oldest_topic_create_time_query(None)
        self.assertIn("ORDER BY create_time ASC LIMIT 1", " ".join(oldest_sql.split()))
        self.assertEqual(("", ""), oldest_params)

        count_sql, count_params = _topic_count_query("303")
        self.assertEqual("SELECT COUNT(*) FROM topics WHERE (? IS NULL OR group_id = ?)", count_sql)
        self.assertEqual((303, 303), count_params)
        self.assertEqual((None, None), _topic_count_query(None)[1])

    def test_database_stats_count_query_preserves_branch_shapes(self):
        self.assertEqual(("SELECT COUNT(*) FROM groups", ()), _database_stats_count_query("groups", None))
        self.assertEqual(
            ("SELECT COUNT(*) FROM groups WHERE group_id = ?", (303,)),
            _database_stats_count_query("groups", "303"),
        )
        self.assertEqual(
            (
                "SELECT COUNT(*) FROM talks WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)",
                (303,),
            ),
            _database_stats_count_query("talks", "303"),
        )

        users_sql, users_params = _database_stats_count_query("users", "303")
        self.assertEqual(
            "SELECT COUNT(DISTINCT user_id) FROM ( "
            "SELECT owner_user_id AS user_id FROM talks WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            "UNION SELECT owner_user_id AS user_id FROM comments WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            "UNION SELECT owner_user_id AS user_id FROM questions WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            "UNION SELECT questionee_user_id AS user_id FROM questions WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            "UNION SELECT owner_user_id AS user_id FROM answers WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            ") scoped_users WHERE user_id IS NOT NULL",
            " ".join(users_sql.split()),
        )
        self.assertEqual((303, 303, 303, 303, 303), users_params)

    def test_get_database_stats_preserves_unscoped_and_scoped_queries(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        unscoped_db = object.__new__(ZSXQDatabase)
        unscoped_db.cursor = FakeDatabaseStatsCursor()
        unscoped_db.group_id = None

        unscoped_stats = ZSXQDatabase.get_database_stats(unscoped_db)

        self.assertEqual(12, len(unscoped_stats))
        self.assertEqual(("SELECT COUNT(*) FROM groups", ()), unscoped_db.cursor.calls[0])
        self.assertEqual(("SELECT COUNT(*) FROM users", ()), unscoped_db.cursor.calls[1])
        self.assertEqual(("SELECT COUNT(*) FROM answers", ()), unscoped_db.cursor.calls[-1])

        scoped_db = object.__new__(ZSXQDatabase)
        scoped_db.cursor = FakeDatabaseStatsCursor()
        scoped_db.group_id = "303"

        scoped_stats = ZSXQDatabase.get_database_stats(scoped_db)

        self.assertEqual(12, len(scoped_stats))
        self.assertEqual(("SELECT COUNT(*) FROM groups WHERE group_id = ?", (303,)), scoped_db.cursor.calls[0])
        users_sql, users_params = scoped_db.cursor.calls[1]
        self.assertEqual(
            "SELECT COUNT(DISTINCT user_id) FROM ( "
            "SELECT owner_user_id AS user_id FROM talks WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            "UNION SELECT owner_user_id AS user_id FROM comments WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            "UNION SELECT owner_user_id AS user_id FROM questions WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            "UNION SELECT questionee_user_id AS user_id FROM questions WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            "UNION SELECT owner_user_id AS user_id FROM answers WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?) "
            ") scoped_users WHERE user_id IS NOT NULL",
            users_sql,
        )
        self.assertEqual((303, 303, 303, 303, 303), users_params)
        self.assertEqual(("SELECT COUNT(*) FROM topics WHERE group_id = ?", (303,)), scoped_db.cursor.calls[2])
        self.assertEqual(
            ("SELECT COUNT(*) FROM talks WHERE topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", (303,)),
            scoped_db.cursor.calls[3],
        )
        self.assertEqual(("SELECT COUNT(*) FROM comments WHERE group_id = ?", (303,)), scoped_db.cursor.calls[9])

    def test_get_database_stats_preserves_per_table_exception_fallback(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeDatabaseStatsCursor(fail_on_query_part="FROM users")
        db.group_id = None

        stats = ZSXQDatabase.get_database_stats(db)

        self.assertEqual(1, stats["groups"])
        self.assertEqual(0, stats["users"])
        self.assertEqual(3, stats["topics"])
        self.assertEqual(12, len(stats))

    def test_timestamp_range_info_uses_nullable_scope_and_preserves_response_shape(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTimestampCursor([("new-time",), ("old-time",), (2,)])
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = None

        self.assertEqual(
            {
                "newest_time": "new-time",
                "oldest_time": "old-time",
                "newest_timestamp": "new-time",
                "oldest_timestamp": "old-time",
                "total_topics": 2,
                "has_data": True,
            },
            ZSXQDatabase.get_timestamp_range_info(db),
        )
        self.assertEqual(
            [
                (
                    "SELECT create_time FROM topics WHERE (? IS NULL OR group_id = ?) "
                    "AND create_time IS NOT NULL AND create_time != '' ORDER BY create_time DESC LIMIT 1",
                    (None, None),
                ),
                (
                    "SELECT create_time FROM topics WHERE (? IS NULL OR group_id = ?) "
                    "AND create_time IS NOT NULL AND create_time != '' ORDER BY create_time ASC LIMIT 1",
                    (None, None),
                ),
                ("SELECT COUNT(*) FROM topics WHERE (? IS NULL OR group_id = ?)", (None, None)),
            ],
            cursor.calls,
        )

    def test_topic_timestamp_methods_keep_legacy_group_scope_for_empty_group(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        newest_db = object.__new__(ZSXQDatabase)
        newest_db.cursor = FakeTimestampCursor([("new-time",)])
        newest_db.group_id = None
        self.assertEqual("new-time", ZSXQDatabase.get_newest_topic_timestamp(newest_db))
        self.assertEqual(("", ""), newest_db.cursor.calls[0][1])

        oldest_db = object.__new__(ZSXQDatabase)
        oldest_db.cursor = FakeTimestampCursor([("old-time",)])
        oldest_db.group_id = None
        self.assertEqual("old-time", ZSXQDatabase.get_oldest_topic_timestamp(oldest_db))
        self.assertEqual(("", ""), oldest_db.cursor.calls[0][1])

    def test_import_topic_data_existing_topic_preserves_skip_and_file_sync(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeCursor()
        cursor.row = (1,)
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.conn = FakeConnection()
        db.group_id = "303"
        synced = []
        db._sync_topic_files_to_core_tables = lambda topic, files: synced.append((topic, files))

        topic_data = {"topic_id": 202, "talk": {"files": [{"file_id": 101}]}}
        with patch("builtins.print"):
            self.assertTrue(ZSXQDatabase.import_topic_data(db, topic_data))

        self.assertEqual(
            [
                (
                    "SELECT 1 FROM topics WHERE topic_id = ? AND (? IS NULL OR group_id = ?) LIMIT 1",
                    (202, 303, 303),
                )
            ],
            cursor.calls,
        )
        self.assertEqual([(topic_data, [{"file_id": 101}])], synced)
        self.assertEqual(0, db.conn.commits)
        self.assertEqual(0, db.conn.rollbacks)

    def test_upsert_group_and_user_preserve_skip_and_insert_params(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        group_db = object.__new__(ZSXQDatabase)
        group_db.cursor = FakeCursor()
        ZSXQDatabase._upsert_group(group_db, {})
        self.assertEqual([], group_db.cursor.calls)

        ZSXQDatabase._upsert_group(
            group_db,
            {
                "group_id": 303,
                "name": "group",
                "type": "paid",
                "background_url": "bg.png",
            },
        )
        group_sql, group_params = group_db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO groups (group_id, name, type, background_url, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(group_id) DO UPDATE SET "
            "name = excluded.name, type = excluded.type, background_url = excluded.background_url, "
            "created_at = excluded.created_at",
            group_sql,
        )
        self.assertEqual((303, "group", "paid", "bg.png"), group_params[:4])
        self.assertRegex(group_params[4], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        user_db = object.__new__(ZSXQDatabase)
        user_db.cursor = FakeCursor()
        ZSXQDatabase._upsert_user(user_db, {})
        self.assertEqual([], user_db.cursor.calls)

        ZSXQDatabase._upsert_user(user_db, {"user_id": 901, "name": "Alice"})
        user_sql, user_params = user_db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO users (user_id, name, alias, avatar_url, location, description, ai_comment_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "name = excluded.name, alias = excluded.alias, avatar_url = excluded.avatar_url, "
            "location = excluded.location, description = excluded.description, "
            "ai_comment_url = excluded.ai_comment_url, created_at = excluded.created_at",
            user_sql,
        )
        self.assertEqual((901, "Alice", "", "", "", "", ""), user_params[:7])
        self.assertRegex(user_params[7], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_import_all_users_preserves_existing_source_order(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        calls = []
        db._upsert_user = lambda user_data: calls.append(user_data)

        talk_owner = {"user_id": 1}
        question_owner = {"user_id": 2}
        questionee = {"user_id": 3}
        answer_owner = {"user_id": 4}
        like_owner = {"user_id": 5}
        empty_like_owner = {}
        comment_owner = {"user_id": 6}
        repliee = {"user_id": 7}

        ZSXQDatabase._import_all_users(
            db,
            {
                "talk": {"owner": talk_owner},
                "question": {
                    "owner": question_owner,
                    "questionee": questionee,
                    "anonymous": True,
                },
                "answer": {"owner": answer_owner},
                "latest_likes": [
                    {"owner": like_owner},
                    {"owner": empty_like_owner},
                    {},
                ],
                "show_comments": [
                    {"owner": comment_owner, "repliee": repliee},
                    {},
                ],
            },
        )

        self.assertEqual(
            [
                talk_owner,
                questionee,
                answer_owner,
                like_owner,
                empty_like_owner,
                comment_owner,
                repliee,
            ],
            calls,
        )

    def test_import_images_preserves_existing_collection_order(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        calls = []
        db._upsert_image = lambda topic_id, image_data, comment_id=None: calls.append(
            (topic_id, image_data, comment_id)
        )

        talk_image_1 = {"image_id": 1}
        talk_image_2 = {"image_id": 2}
        comment_image = {"image_id": 3}
        comment_image_without_id = {"image_id": 4}

        ZSXQDatabase._import_images(
            db,
            202,
            {
                "talk": {"images": [talk_image_1, talk_image_2]},
                "show_comments": [
                    {"comment_id": 301, "images": [comment_image]},
                    {"images": [comment_image_without_id]},
                    {},
                ],
            },
        )

        self.assertEqual(
            [
                (202, talk_image_1, None),
                (202, talk_image_2, None),
                (202, comment_image, 301),
                (202, comment_image_without_id, None),
            ],
            calls,
        )

    def test_upsert_topic_preserves_skip_defaults_and_insert_params(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_topic(db, {})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._upsert_topic(db, {"topic_id": 202, "title": "title"})

        topic_sql, topic_params = db.cursor.calls[0]
        self.assertIn("INSERT INTO topics", topic_sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", topic_sql)
        self.assertEqual(
            (
                202,
                "",
                "",
                "title",
                "",
                False,
                False,
                0,
                0,
                0,
                0,
                0,
                0,
                False,
                False,
                "",
                False,
                False,
            ),
            topic_params[:18],
        )
        self.assertRegex(topic_params[18], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_upsert_talk_preserves_skip_and_insert_params(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_talk(db, 202, {})
        ZSXQDatabase._upsert_talk(db, 202, {"owner": {}})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._upsert_talk(db, 202, {"owner": {"user_id": 901}, "text": "body"})

        talk_sql, talk_params = db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO talks (topic_id, owner_user_id, text, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id) DO UPDATE SET "
            "owner_user_id = excluded.owner_user_id, text = excluded.text, "
            "created_at = excluded.created_at",
            talk_sql,
        )
        self.assertEqual((202, 901, "body"), talk_params[:3])
        self.assertRegex(talk_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_image_writes_preserve_skip_paths_and_distinct_numeric_defaults(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_image(db, 202, {})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._upsert_image(
            db,
            202,
            {
                "image_id": 701,
                "type": "image",
                "thumbnail": {"url": "thumb.jpg"},
                "large": {"url": "large.jpg"},
                "original": {"url": "origin.jpg"},
            },
        )
        image_sql, image_params = db.cursor.calls[0]
        self.assertIn("INSERT INTO images", image_sql)
        self.assertIn("ON CONFLICT(image_id) DO UPDATE SET", image_sql)
        self.assertEqual(
            (
                701,
                202,
                None,
                "image",
                "thumb.jpg",
                None,
                None,
                "large.jpg",
                None,
                None,
                "origin.jpg",
                None,
                None,
                None,
            ),
            image_params[:14],
        )
        self.assertRegex(image_params[14], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        comment_db = object.__new__(ZSXQDatabase)
        comment_db.cursor = FakeCursor()

        ZSXQDatabase._import_comment_images(comment_db, 202, 11, [{}, {"image_id": 702}])

        comment_sql, comment_params = comment_db.cursor.calls[0]
        self.assertIn("INSERT INTO images", comment_sql)
        self.assertEqual(
            (
                702,
                202,
                11,
                "",
                "",
                0,
                0,
                "",
                0,
                0,
                "",
                0,
                0,
                0,
            ),
            comment_params[:14],
        )
        self.assertRegex(comment_params[14], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_import_comments_preserves_upsert_and_image_import_order(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        events = []

        def upsert_comment(topic_id, comment):
            events.append(("upsert", topic_id, comment.get("comment_id")))

        def import_comment_images(topic_id, comment_id, images):
            events.append(("images", topic_id, comment_id, images))

        db._upsert_comment = upsert_comment
        db._import_comment_images = import_comment_images

        images = [{"image_id": 701}]
        ZSXQDatabase._import_comments(
            db,
            202,
            [
                {"comment_id": 301},
                {"comment_id": 302, "images": []},
                {"comment_id": 303, "images": images},
            ],
        )

        self.assertEqual(
            [
                ("upsert", 202, 301),
                ("upsert", 202, 302),
                ("upsert", 202, 303),
                ("images", 202, 303, images),
            ],
            events,
        )

        failing_db = object.__new__(ZSXQDatabase)
        failing_events = []

        def failing_upsert_comment(topic_id, comment):
            failing_events.append(("upsert", topic_id, comment.get("comment_id")))

        def failing_import_comment_images(topic_id, comment_id, images):
            failing_events.append(("images", topic_id, comment_id, images))

        failing_db._upsert_comment = failing_upsert_comment
        failing_db._import_comment_images = failing_import_comment_images

        with self.assertRaises(KeyError):
            ZSXQDatabase._import_comments(failing_db, 202, [{"images": images}])

        self.assertEqual([("upsert", 202, None)], failing_events)

    def test_import_additional_comments_preserves_user_comment_image_order(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        empty_db = object.__new__(ZSXQDatabase)
        empty_db._upsert_user = lambda user: self.fail("unexpected user upsert")
        empty_db._upsert_comment = lambda topic_id, comment: self.fail("unexpected comment upsert")
        empty_db._import_comment_images = lambda topic_id, comment_id, images: self.fail(
            "unexpected comment image import"
        )

        with patch("builtins.print") as mocked_print:
            ZSXQDatabase.import_additional_comments(empty_db, 202, [])

        mocked_print.assert_not_called()

        db = object.__new__(ZSXQDatabase)
        events = []

        def upsert_user(user):
            events.append(("user", user.get("user_id")))

        def upsert_comment(topic_id, comment):
            events.append(("comment", topic_id, comment.get("comment_id")))

        def import_comment_images(topic_id, comment_id, images):
            events.append(("images", topic_id, comment_id, images))

        db._upsert_user = upsert_user
        db._upsert_comment = upsert_comment
        db._import_comment_images = import_comment_images

        owner = {"user_id": 901}
        repliee = {"user_id": 902}
        images = [{"image_id": 701}]

        with patch("builtins.print") as mocked_print:
            ZSXQDatabase.import_additional_comments(
                db,
                202,
                [
                    {"comment_id": 301, "owner": {}, "repliee": None},
                    {"comment_id": 302, "owner": owner, "repliee": repliee, "images": images},
                ],
            )

        self.assertEqual(
            [
                ("comment", 202, 301),
                ("user", 901),
                ("user", 902),
                ("comment", 202, 302),
                ("images", 202, 302, images),
            ],
            events,
        )
        self.assertEqual(2, mocked_print.call_count)

    def test_import_likes_preserves_delete_skip_and_insert_order(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._import_likes(db, 202, {})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._import_likes(db, 202, {"latest_likes": []})
        self.assertEqual([("DELETE FROM latest_likes WHERE topic_id = ?", (202,))], db.cursor.calls)

        active_db = object.__new__(ZSXQDatabase)
        active_db.cursor = FakeCursor()

        ZSXQDatabase._import_likes(
            active_db,
            202,
            {
                "latest_likes": [
                    {"owner": {}, "create_time": "skipped"},
                    {"owner": {"user_id": 901}, "create_time": "2026-01-01T10:00:00.000+0800"},
                ]
            },
        )

        self.assertEqual("DELETE FROM latest_likes WHERE topic_id = ?", active_db.cursor.calls[0][0])
        self.assertEqual((202,), active_db.cursor.calls[0][1])

        likes_sql, likes_params = active_db.cursor.calls[1]
        self.assertEqual(
            "INSERT INTO likes (topic_id, user_id, create_time, imported_at) VALUES (?, ?, ?, ?)",
            likes_sql,
        )
        self.assertEqual((202, 901, "2026-01-01T10:00:00.000+0800"), likes_params[:3])
        self.assertRegex(likes_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        latest_sql, latest_params = active_db.cursor.calls[2]
        self.assertEqual(
            "INSERT INTO latest_likes (topic_id, owner_user_id, create_time, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id, owner_user_id, create_time) "
            "DO UPDATE SET created_at = excluded.created_at",
            latest_sql,
        )
        self.assertEqual((202, 901, "2026-01-01T10:00:00.000+0800"), latest_params[:3])
        self.assertRegex(latest_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_import_like_emojis_preserves_skip_defaults_and_upsert_params(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._import_like_emojis(db, 202, {})
        ZSXQDatabase._import_like_emojis(db, 202, {"likes_detail": {}})
        ZSXQDatabase._import_like_emojis(db, 202, {"likes_detail": {"emojis": []}})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._import_like_emojis(
            db,
            202,
            {"likes_detail": {"emojis": [{"likes_count": 9}, {"emoji_key": "[ok]"}]}},
        )

        emoji_sql, emoji_params = db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO like_emojis (topic_id, emoji_key, likes_count, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id, emoji_key) DO UPDATE SET "
            "likes_count = excluded.likes_count, created_at = excluded.created_at",
            emoji_sql,
        )
        self.assertEqual((202, "[ok]", 0), emoji_params[:3])
        self.assertRegex(emoji_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_import_user_liked_emojis_preserves_skip_and_insert_params(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._import_user_liked_emojis(db, 202, {})
        ZSXQDatabase._import_user_liked_emojis(db, 202, {"user_specific": {}})
        ZSXQDatabase._import_user_liked_emojis(db, 202, {"user_specific": {"liked_emojis": []}})
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._import_user_liked_emojis(
            db,
            202,
            {"user_specific": {"liked_emojis": ["", "[ok]"]}},
        )

        sql, params = db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO user_liked_emojis (topic_id, emoji_key) VALUES (?, ?) "
            "ON CONFLICT(topic_id, emoji_key) DO NOTHING",
            sql,
        )
        self.assertEqual((202, "[ok]"), params)

    def test_update_topic_stats_preserves_skip_rowcount_and_exception_branches(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        empty_db = object.__new__(ZSXQDatabase)
        empty_db.cursor = FakeCursor()
        empty_db.group_id = "303"
        self.assertFalse(ZSXQDatabase.update_topic_stats(empty_db, {}))
        self.assertEqual([], empty_db.cursor.calls)

        success_db = object.__new__(ZSXQDatabase)
        success_db.cursor = FakeCursor()
        success_db.cursor.rowcount = 1
        success_db.group_id = "303"
        self.assertTrue(
            ZSXQDatabase.update_topic_stats(
                success_db,
                {
                    "topic_id": 202,
                    "likes_count": 1,
                    "tourist_likes_count": 2,
                    "rewards_count": 3,
                    "comments_count": 4,
                    "reading_count": 5,
                    "readers_count": 6,
                    "digested": True,
                    "sticky": True,
                    "user_specific": {"liked": True, "subscribed": True},
                },
            )
        )
        stats_sql, stats_params = success_db.cursor.calls[0]
        self.assertEqual(
            "UPDATE topics SET likes_count = ?, tourist_likes_count = ?, rewards_count = ?, "
            "comments_count = ?, reading_count = ?, readers_count = ?, digested = ?, sticky = ?, "
            "user_liked = ?, user_subscribed = ?, imported_at = ? WHERE topic_id = ? "
            "AND (? IS NULL OR group_id = ?)",
            stats_sql,
        )
        self.assertEqual((1, 2, 3, 4, 5, 6, True, True, True, True), stats_params[:10])
        self.assertRegex(stats_params[10], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")
        self.assertEqual((202, 303, 303), stats_params[11:])

        missing_db = object.__new__(ZSXQDatabase)
        missing_db.cursor = FakeCursor()
        missing_db.group_id = None
        with patch("builtins.print") as mocked_print:
            self.assertFalse(ZSXQDatabase.update_topic_stats(missing_db, {"topic_id": 202}))
        mocked_print.assert_called_once_with("警告：话题 202 不存在，无法更新")
        self.assertEqual((202, "", ""), missing_db.cursor.calls[0][1][11:])

        failing_db = object.__new__(ZSXQDatabase)
        failing_db.cursor = FakeFailingExecuteCursor()
        failing_db.group_id = "303"
        with patch("builtins.print") as mocked_print, patch("traceback.print_exc") as mocked_traceback:
            self.assertFalse(ZSXQDatabase.update_topic_stats(failing_db, {"topic_id": 202}))
        mocked_print.assert_called_once()
        mocked_traceback.assert_called_once()

    def test_resolve_topic_group_id_preserves_explicit_scope_lookup_and_exception_fallback(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        class GroupLookupCursor:
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

        explicit_db = object.__new__(ZSXQDatabase)
        explicit_db.cursor = GroupLookupCursor((999,))
        explicit_db.group_id = "303"
        self.assertEqual(404, ZSXQDatabase._resolve_topic_group_id(explicit_db, 202, explicit_group_id="404"))
        self.assertEqual([], explicit_db.cursor.calls)

        scoped_db = object.__new__(ZSXQDatabase)
        scoped_db.cursor = GroupLookupCursor((999,))
        scoped_db.group_id = "303"
        self.assertEqual(303, ZSXQDatabase._resolve_topic_group_id(scoped_db, 202))
        self.assertEqual([], scoped_db.cursor.calls)

        lookup_db = object.__new__(ZSXQDatabase)
        lookup_db.cursor = GroupLookupCursor((303,))
        lookup_db.group_id = None
        self.assertEqual(303, ZSXQDatabase._resolve_topic_group_id(lookup_db, 202))
        self.assertEqual(
            [("SELECT group_id FROM topics WHERE topic_id = ? LIMIT 1", (202,))],
            lookup_db.cursor.calls,
        )

        missing_db = object.__new__(ZSXQDatabase)
        missing_db.cursor = GroupLookupCursor(None)
        missing_db.group_id = None
        self.assertIsNone(ZSXQDatabase._resolve_topic_group_id(missing_db, 202))

        failing_db = object.__new__(ZSXQDatabase)
        failing_db.cursor = GroupLookupCursor(raises=True)
        failing_db.group_id = None
        self.assertIsNone(ZSXQDatabase._resolve_topic_group_id(failing_db, 202))

    def test_upsert_comment_writes_group_id_from_runtime_scope(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        empty_db = object.__new__(ZSXQDatabase)
        empty_db.cursor = FakeCursor()
        empty_db.group_id = "303"
        ZSXQDatabase._upsert_comment(empty_db, 202, {})
        self.assertEqual([], empty_db.cursor.calls)

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()
        db.group_id = "303"

        ZSXQDatabase._upsert_comment(
            db,
            202,
            {
                "comment_id": 101,
                "owner": {"user_id": 901},
                "repliee": {"user_id": 902},
                "parent_comment_id": 100,
                "text": "ok",
                "create_time": "2026-01-01T10:00:00.000+0800",
                "likes_count": 1,
                "rewards_count": 2,
                "replies_count": 3,
                "sticky": True,
            },
        )

        sql, params = db.cursor.calls[-1]
        self.assertIn("INSERT INTO comments", sql)
        self.assertIn("ON CONFLICT(comment_id) DO UPDATE SET", sql)
        self.assertIn("comment_id, group_id, topic_id", sql)
        self.assertEqual(
            (
                101,
                303,
                202,
                901,
                100,
                902,
                "ok",
                "2026-01-01T10:00:00.000+0800",
                1,
                2,
                3,
                True,
            ),
            params[:12],
        )
        self.assertRegex(params[12], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        default_db = object.__new__(ZSXQDatabase)
        default_db.cursor = FakeCursor()
        default_db.group_id = None
        default_db._resolve_topic_group_id = lambda _topic_id, _explicit_group_id=None: None

        ZSXQDatabase._upsert_comment(default_db, 202, {"comment_id": 102})

        _default_sql, default_params = default_db.cursor.calls[0]
        self.assertEqual((102, None, 202, None, None, None, "", "", 0, 0, 0, False), default_params[:12])

    def test_upsert_question_preserves_anonymous_skip_defaults_and_owner_detail_fallback(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        empty_db = object.__new__(ZSXQDatabase)
        empty_db.cursor = FakeCursor()
        ZSXQDatabase._upsert_question(empty_db, 202, {})
        self.assertEqual([], empty_db.cursor.calls)

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_question(
            db,
            202,
            {
                "text": "anonymous question",
                "questionee": {"user_id": 902},
                "anonymous": True,
                "expired": True,
                "owner_detail": {
                    "questions_count": 7,
                    "estimated_join_time": "2024-01-01T00:00:00.000+0800",
                    "status": "active",
                },
                "owner_location": "Shanghai",
            },
        )

        question_sql, question_params = db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO questions (topic_id, owner_user_id, questionee_user_id, text, "
            "expired, anonymous, owner_questions_count, owner_join_time, owner_status, "
            "owner_location, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(topic_id) DO UPDATE SET owner_user_id = excluded.owner_user_id, "
            "questionee_user_id = excluded.questionee_user_id, text = excluded.text, "
            "expired = excluded.expired, anonymous = excluded.anonymous, "
            "owner_questions_count = excluded.owner_questions_count, "
            "owner_join_time = excluded.owner_join_time, owner_status = excluded.owner_status, "
            "owner_location = excluded.owner_location, created_at = excluded.created_at",
            question_sql,
        )
        self.assertEqual(
            (
                202,
                None,
                902,
                "anonymous question",
                True,
                True,
                7,
                "2024-01-01T00:00:00.000+0800",
                "active",
                "Shanghai",
            ),
            question_params[:10],
        )
        self.assertRegex(question_params[10], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        default_db = object.__new__(ZSXQDatabase)
        default_db.cursor = FakeCursor()
        ZSXQDatabase._upsert_question(default_db, 202, {"owner": {"user_id": 901}})
        _default_sql, default_params = default_db.cursor.calls[0]
        self.assertEqual((202, 901, None, "", False, False, None, "", "", ""), default_params[:10])

    def test_upsert_answer_preserves_skip_defaults_and_insert_params(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        empty_db = object.__new__(ZSXQDatabase)
        empty_db.cursor = FakeCursor()
        ZSXQDatabase._upsert_answer(empty_db, 202, {})
        self.assertEqual([], empty_db.cursor.calls)

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_answer(db, 202, {"owner": {"user_id": 901}, "text": "answer text"})

        answer_sql, answer_params = db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO answers (topic_id, owner_user_id, text, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(topic_id) DO UPDATE SET owner_user_id = excluded.owner_user_id, "
            "text = excluded.text, created_at = excluded.created_at",
            answer_sql,
        )
        self.assertEqual((202, 901, "answer text"), answer_params[:3])
        self.assertRegex(answer_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_upsert_article_uses_topic_create_time_and_preserves_empty_payload_skip(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        empty_db = object.__new__(ZSXQDatabase)
        empty_db.cursor = FakeCursor()
        ZSXQDatabase._upsert_article(empty_db, 202, {})
        self.assertEqual([], empty_db.cursor.calls)

        article_db = object.__new__(ZSXQDatabase)
        article_db.cursor = FakeCursor()
        article_db.cursor.row = ("2026-05-07T10:00:00.000+0800",)

        ZSXQDatabase._upsert_article(
            article_db,
            202,
            {
                "title": "article title",
                "article_id": "401",
                "article_url": "article-url",
                "inline_article_url": "inline-url",
            },
        )

        self.assertEqual(
            ("SELECT create_time FROM topics WHERE topic_id = ?", (202,)),
            article_db.cursor.calls[0],
        )
        article_sql, article_params = article_db.cursor.calls[1]
        self.assertIn("INSERT INTO articles", article_sql)
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", article_sql)
        self.assertEqual(
            (
                202,
                "article title",
                "401",
                "article-url",
                "inline-url",
                "2026-05-07T10:00:00.000+0800",
            ),
            article_params,
        )

        fallback_db = object.__new__(ZSXQDatabase)
        fallback_db.cursor = FakeCursor()
        fallback_db.cursor.row = None

        ZSXQDatabase._upsert_article(fallback_db, 203, {"article_id": "402"})

        self.assertEqual(
            ("SELECT create_time FROM topics WHERE topic_id = ?", (203,)),
            fallback_db.cursor.calls[0],
        )
        fallback_sql, fallback_params = fallback_db.cursor.calls[1]
        self.assertIn("INSERT INTO articles", fallback_sql)
        self.assertEqual((203, "", "402", "", "", ""), fallback_params)

    def test_import_files_preserves_skip_defaults_and_timestamp(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._import_files(db, 202, [])
        ZSXQDatabase._import_files(db, 202, [{}])
        self.assertEqual([], db.cursor.calls)

        ZSXQDatabase._import_files(db, 202, [{"file_id": 501}])

        topic_file_sql, topic_file_params = db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO topic_files (topic_id, file_id, name, hash, size, duration, "
            "download_count, create_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(topic_id, file_id) DO UPDATE SET name = excluded.name, "
            "hash = excluded.hash, size = excluded.size, duration = excluded.duration, "
            "download_count = excluded.download_count, create_time = excluded.create_time, "
            "created_at = excluded.created_at",
            topic_file_sql,
        )
        self.assertEqual((202, 501, "", "", 0, 0, 0, ""), topic_file_params[:8])
        self.assertRegex(topic_file_params[8], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

    def test_import_tags_preserves_text_sources_decode_dedupe_and_link_behavior(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        missing_group_db = object.__new__(ZSXQDatabase)
        missing_calls = []
        missing_group_db._upsert_tag = lambda group_id, tag_name, hid: missing_calls.append((group_id, tag_name, hid))
        missing_group_db._link_topic_tag = lambda topic_id, tag_id: missing_calls.append((topic_id, tag_id))

        ZSXQDatabase._import_tags(
            missing_group_db,
            202,
            {"talk": {"text": '<e type="hashtag" hid="h1" title="%23AI" />'}},
        )

        self.assertEqual([], missing_calls)

        db = object.__new__(ZSXQDatabase)
        upsert_calls = []
        link_calls = []

        def fake_upsert_tag(group_id, tag_name, hid):
            upsert_calls.append((group_id, tag_name, hid))
            return {"h1": 7, "h2": None, "h3": 9}[hid]

        db._upsert_tag = fake_upsert_tag
        db._link_topic_tag = lambda topic_id, tag_id: link_calls.append((topic_id, tag_id))

        ZSXQDatabase._import_tags(
            db,
            202,
            {
                "group": {"group_id": 303},
                "talk": {"text": '<e type="hashtag" hid="h1" title="%23AI" />'},
                "question": {"text": '<e type="hashtag" hid="h2" title="Question" />'},
                "answer": {"text": '<e type="hashtag" hid="h3" title="%E7%AD%94%E6%A1%88" />'},
                "show_comments": [
                    {"text": '<e type="hashtag" hid="h1" title="%23AI" />'},
                    {"text": ""},
                    {},
                ],
            },
        )

        self.assertEqual(
            {
                (303, "AI", "h1"),
                (303, "Question", "h2"),
                (303, "答案", "h3"),
            },
            set(upsert_calls),
        )
        self.assertEqual({(202, 7), (202, 9)}, set(link_calls))

    def test_upsert_tag_preserves_existing_update_insert_and_missing_return_branches(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        existing_db = object.__new__(ZSXQDatabase)
        existing_db.cursor = FakeSequenceCursor([(7,)])
        self.assertEqual(7, ZSXQDatabase._upsert_tag(existing_db, 303, "AI", "hid-1"))
        self.assertEqual(
            [
                ("SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?", (303, "AI")),
                ("UPDATE tags SET hid = ? WHERE tag_id = ?", ("hid-1", 7)),
            ],
            existing_db.cursor.calls,
        )

        no_hid_db = object.__new__(ZSXQDatabase)
        no_hid_db.cursor = FakeSequenceCursor([(8,)])
        self.assertEqual(8, ZSXQDatabase._upsert_tag(no_hid_db, 303, "AI", None))
        self.assertEqual(
            [("SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?", (303, "AI"))],
            no_hid_db.cursor.calls,
        )

        new_db = object.__new__(ZSXQDatabase)
        new_db.cursor = FakeSequenceCursor([None, (9,)])
        self.assertEqual(9, ZSXQDatabase._upsert_tag(new_db, 303, "AI", "hid-2"))
        self.assertEqual("SELECT tag_id FROM tags WHERE group_id = ? AND tag_name = ?", new_db.cursor.calls[0][0])
        insert_sql, insert_params = new_db.cursor.calls[1]
        self.assertEqual(
            "INSERT INTO tags (group_id, tag_name, hid, created_at) VALUES (?, ?, ?, ?) RETURNING tag_id",
            insert_sql,
        )
        self.assertEqual((303, "AI", "hid-2"), insert_params[:3])
        self.assertRegex(insert_params[3], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")

        missing_return_db = object.__new__(ZSXQDatabase)
        missing_return_db.cursor = FakeSequenceCursor([None, None])
        self.assertIsNone(ZSXQDatabase._upsert_tag(missing_return_db, 303, "AI", "hid-3"))

    def test_link_topic_tag_inserts_relation_refreshes_count_and_swallows_errors(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._link_topic_tag(db, 202, 7)

        self.assertEqual(2, len(db.cursor.calls))
        insert_sql, insert_params = db.cursor.calls[0]
        self.assertEqual(
            "INSERT INTO topic_tags (topic_id, tag_id, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(topic_id, tag_id) DO NOTHING",
            insert_sql,
        )
        self.assertEqual((202, 7), insert_params[:2])
        self.assertRegex(insert_params[2], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0800$")
        self.assertEqual(
            (
                "UPDATE tags SET topic_count = ( SELECT COUNT(*) FROM topic_tags WHERE tag_id = ? ) "
                "WHERE tag_id = ?",
                (7, 7),
            ),
            db.cursor.calls[1],
        )

        failing_db = object.__new__(ZSXQDatabase)
        failing_db.cursor = FakeFailingExecuteCursor()
        with patch("builtins.print") as mocked_print:
            self.assertIsNone(ZSXQDatabase._link_topic_tag(failing_db, 202, 7))
        mocked_print.assert_called_once()
        self.assertEqual(1, len(failing_db.cursor.calls))

    def test_get_tags_by_group_uses_helper_query_and_preserves_response_shape(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeTagReadCursor(
            tag_rows=[(7, "AI", "hid-1", 12, "2026-06-12T10:00:00.000+0800")]
        )

        self.assertEqual(
            [
                {
                    "tag_id": 7,
                    "tag_name": "AI",
                    "hid": "hid-1",
                    "topic_count": 12,
                    "created_at": "2026-06-12T10:00:00.000+0800",
                }
            ],
            ZSXQDatabase.get_tags_by_group(db, 303),
        )
        self.assertEqual(
            [
                (
                    "SELECT tag_id, tag_name, hid, topic_count, created_at FROM tags "
                    "WHERE group_id = ? ORDER BY topic_count DESC, tag_name ASC",
                    (303,),
                )
            ],
            db.cursor.calls,
        )

    def test_get_topics_by_tag_uses_helper_queries_and_preserves_pagination(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeTagReadCursor(
            topic_rows=[
                (
                    202,
                    "title",
                    "2026-05-07",
                    1,
                    2,
                    3,
                    "talk",
                    0,
                    1,
                    None,
                    None,
                    "body",
                    901,
                    "Alice",
                    "a.png",
                )
            ],
            total=12,
        )

        self.assertEqual(
            {
                "topics": [
                    {
                        "topic_id": 202,
                        "title": "title",
                        "create_time": "2026-05-07",
                        "likes_count": 1,
                        "comments_count": 2,
                        "reading_count": 3,
                        "type": "talk",
                        "digested": False,
                        "sticky": True,
                        "talk_text": "body",
                        "author": {"user_id": 901, "name": "Alice", "avatar_url": "a.png"},
                    }
                ],
                "pagination": {"page": 2, "per_page": 5, "total": 12, "pages": 3},
            },
            ZSXQDatabase.get_topics_by_tag(db, 7, page=2, per_page=5),
        )
        self.assertEqual((7, 5, 5), db.cursor.calls[0][1])
        self.assertIn("FROM topics t INNER JOIN topic_tags tt", db.cursor.calls[0][0])
        self.assertEqual(("SELECT COUNT(*) FROM topic_tags WHERE tag_id = ?", (7,)), db.cursor.calls[1])

    def test_get_topics_by_tag_preserves_exception_fallback_shape(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeTagReadCursor(raises=True)

        with patch("builtins.print") as mocked_print:
            result = ZSXQDatabase.get_topics_by_tag(db, 7, page=2, per_page=5)

        self.assertEqual({"topics": [], "pagination": {"page": 2, "per_page": 5, "total": 0, "pages": 0}}, result)
        mocked_print.assert_called_once()
        self.assertEqual(1, len(db.cursor.calls))

    def test_content_child_writes_use_explicit_unique_semantics(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        ZSXQDatabase._upsert_talk(db, 202, {"owner": {"user_id": 9}, "text": "body"})
        talk_sql, _talk_params = db.cursor.calls[-1]
        self.assertIn("ON CONFLICT(topic_id) DO UPDATE SET", talk_sql)

        ZSXQDatabase._import_likes(
            db,
            202,
            {"latest_likes": [{"owner": {"user_id": 9}, "create_time": "2026-01-01"}]},
        )
        calls = "\n".join(sql for sql, _params in db.cursor.calls)
        self.assertIn("DELETE FROM latest_likes WHERE topic_id = ?", calls)
        self.assertIn("ON CONFLICT(topic_id, owner_user_id, create_time) DO UPDATE SET", calls)

        ZSXQDatabase._import_like_emojis(
            db,
            202,
            {"likes_detail": {"emojis": [{"emoji_key": "[ok]", "likes_count": 2}]}},
        )
        emoji_sql, _emoji_params = db.cursor.calls[-1]
        self.assertIn("ON CONFLICT(topic_id, emoji_key) DO UPDATE SET", emoji_sql)

    def test_get_topic_detail_scopes_child_queries_when_group_is_set(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeCursor()
        cursor.row = (
            202,
            "talk",
            "title",
            "2026-05-07T10:00:00.000+0800",
            0,
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            "",
            0,
            0,
            303,
            "group",
            "paid",
            "bg",
        )
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        self.assertEqual(202, detail["topic_id"])
        calls = "\n".join(sql for sql, _params in cursor.calls)
        self.assertIn("WHERE t.topic_id = ? AND t.group_id = ?", calls)
        self.assertIn("AND (? IS NULL OR c.group_id = ?)", calls)
        self.assertIn("topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)", calls)

    def test_get_topic_detail_builds_nested_comments_with_images_and_repliee(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTopicDetailCursor()
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        comments = detail["show_comments"]
        self.assertEqual(1, len(comments))
        parent = comments[0]
        self.assertEqual(10, parent["comment_id"])
        self.assertEqual("parent", parent["text"])
        self.assertEqual(1, len(parent["replied_comments"]))
        child = parent["replied_comments"][0]
        self.assertEqual(11, child["comment_id"])
        self.assertEqual(10, child["parent_comment_id"])
        self.assertEqual({"user_id": 901, "name": "Alice", "avatar_url": "a.png"}, child["repliee"])
        self.assertEqual(
            [
                {
                    "image_id": 701,
                    "type": "image",
                    "thumbnail": {"url": "thumb.jpg", "width": 100, "height": 80},
                    "large": {"url": "large.jpg", "width": 1000, "height": 800},
                    "original": {
                        "url": "origin.jpg",
                        "width": 2000,
                        "height": 1600,
                        "size": 12345,
                    },
                }
            ],
            child["images"],
        )
        image_calls = [params for sql, params in cursor.calls if "FROM images WHERE comment_id IN" in sql]
        self.assertEqual([[10, 11, 303, 303]], image_calls)

    def test_get_topic_detail_builds_talk_with_images_files_and_article(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTopicDetailTalkCursor()
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        self.assertEqual(
            {
                "text": "body",
                "owner": {
                    "user_id": 901,
                    "name": "Alice",
                    "alias": "A",
                    "avatar_url": "a.png",
                    "location": "SH",
                    "description": "owner description",
                },
                "images": [
                    {
                        "image_id": 701,
                        "type": "image",
                        "thumbnail": {"url": "thumb.jpg", "width": 100, "height": 80},
                        "large": {"url": "large.jpg", "width": 1000, "height": 800},
                        "original": {
                            "url": "origin.jpg",
                            "width": 2000,
                            "height": 1600,
                            "size": 12345,
                        },
                    }
                ],
                "files": [
                    {
                        "file_id": 501,
                        "name": "memo.pdf",
                        "hash": "hash-1",
                        "size": 123,
                        "duration": 0,
                        "download_count": 7,
                        "create_time": "2026-05-07T09:00:00.000+0800",
                    }
                ],
                "article": {
                    "title": "article title",
                    "article_id": 401,
                    "article_url": "article-url",
                    "inline_article_url": "inline-url",
                },
            },
            detail["talk"],
        )
        scoped_attachment_calls = [
            params
            for sql, params in cursor.calls
            if (
                "FROM images WHERE topic_id = ?" in sql
                or "FROM topic_files tf" in sql
                or "FROM articles" in sql
            )
        ]
        self.assertEqual([(202, 303, 303), (202, 303, 303), (202, 303, 303)], scoped_attachment_calls)

    def test_get_topic_detail_builds_latest_likes_and_like_emojis(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTopicDetailEngagementCursor()
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        self.assertEqual(
            [
                {
                    "create_time": "2026-05-07T12:00:00.000+0800",
                    "owner": {"user_id": 901, "name": "Alice", "avatar_url": "a.png"},
                },
                {
                    "create_time": "2026-05-07T11:00:00.000+0800",
                    "owner": {"user_id": 902, "name": "Bob", "avatar_url": "b.png"},
                },
            ],
            detail["latest_likes"],
        )
        self.assertEqual(
            {"emojis": [{"emoji_key": "[like]", "likes_count": 3}, {"emoji_key": "[ok]", "likes_count": 2}]},
            detail["likes_detail"],
        )
        engagement_calls = [
            params
            for sql, params in cursor.calls
            if "FROM likes l" in sql or "FROM like_emojis" in sql
        ]
        self.assertEqual([(202, 303, 303), (202, 303, 303)], engagement_calls)

    def test_get_topic_detail_builds_question_and_answer_payloads(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        cursor = FakeTopicDetailQACursor()
        db = object.__new__(ZSXQDatabase)
        db.cursor = cursor
        db.group_id = "303"

        detail = ZSXQDatabase.get_topic_detail(db, 202)

        self.assertEqual(
            {
                "text": "question text",
                "expired": False,
                "anonymous": False,
                "owner_detail": {
                    "questions_count": 7,
                    "estimated_join_time": "2026-01-01T00:00:00.000+0800",
                    "status": "active",
                },
                "owner_location": "question owner location",
                "owner": {
                    "user_id": 901,
                    "name": "Question Owner",
                    "alias": "QO",
                    "avatar_url": "owner.png",
                    "location": "SH",
                    "description": "SH",
                },
            },
            detail["question"],
        )
        self.assertEqual(
            {
                "text": "answer text",
                "owner": {
                    "user_id": 902,
                    "name": "Answer Owner",
                    "alias": "AO",
                    "avatar_url": "answer.png",
                    "location": "BJ",
                    "description": "answer owner",
                },
            },
            detail["answer"],
        )
        qa_calls = [
            params
            for sql, params in cursor.calls
            if "FROM questions q" in sql or "FROM answers a" in sql
        ]
        self.assertEqual([(202, 303, 303), (202, 303, 303)], qa_calls)

    def test_runtime_init_database_does_not_execute_ddl(self):
        from backend.storage.zsxq_database import ZSXQDatabase

        db = object.__new__(ZSXQDatabase)
        db.cursor = FakeCursor()

        self.assertIsNone(ZSXQDatabase._init_database(db))
        self.assertEqual([], db.cursor.calls)


if __name__ == "__main__":
    unittest.main()
