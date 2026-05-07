import unittest

from backend.storage.zsxq_database import (
    _build_pagination,
    _format_tag_row,
    _format_tag_topic_row,
    _replace_file_topic_relation,
    _upsert_synced_file,
)


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 0

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        if "INSERT OR IGNORE INTO file_topic_relations" in query:
            self.rowcount = 1
        return self


class FakeFileDatabase:
    def __init__(self):
        self.cursor = FakeCursor()


class ZSXQDatabaseHelperTests(unittest.TestCase):
    def test_build_pagination_calculates_pages(self):
        self.assertEqual(
            {'page': 2, 'per_page': 20, 'total': 41, 'pages': 3},
            _build_pagination(2, 20, 41),
        )

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
                    "INSERT OR IGNORE INTO file_topic_relations (file_id, topic_id) VALUES (?, ?)",
                    (101, 202),
                ),
            ],
            file_db.cursor.calls,
        )

    def test_upsert_synced_file_uses_current_cursor(self):
        cursor = FakeCursor()

        file_id = _upsert_synced_file(
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


if __name__ == "__main__":
    unittest.main()
