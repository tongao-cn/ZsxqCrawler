import unittest

from backend.storage.topic_file_attachment_writer import sync_topic_file_attachment


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 1

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        return self


class FakeFileDatabase:
    def __init__(self):
        self.cursor = FakeCursor()


class TopicFileAttachmentWriterTests(unittest.TestCase):
    def test_sync_topic_file_attachment_upserts_file_and_replaces_relation(self):
        file_db = FakeFileDatabase()

        file_id = sync_topic_file_attachment(
            file_db,
            group_id=303,
            topic_id=202,
            file_data={"file_id": 101, "name": "memo.pdf"},
        )

        self.assertEqual(101, file_id)
        self.assertIn("INSERT INTO files", file_db.cursor.calls[0][0])
        self.assertEqual((101, 303, 202, "memo.pdf", None, None, None, None, None), file_db.cursor.calls[0][1])
        self.assertEqual(
            ("DELETE FROM file_topic_relations WHERE file_id = ? AND topic_id = ?", (101, 202)),
            file_db.cursor.calls[1],
        )
        self.assertEqual(
            (
                "INSERT INTO file_topic_relations (file_id, topic_id) VALUES (?, ?) "
                "ON CONFLICT(file_id, topic_id) DO NOTHING",
                (101, 202),
            ),
            file_db.cursor.calls[2],
        )

    def test_sync_topic_file_attachment_skips_relation_without_file_id(self):
        file_db = FakeFileDatabase()

        file_id = sync_topic_file_attachment(
            file_db,
            group_id=303,
            topic_id=202,
            file_data={"name": "memo.pdf"},
        )

        self.assertIsNone(file_id)
        self.assertEqual([], file_db.cursor.calls)


if __name__ == "__main__":
    unittest.main()
