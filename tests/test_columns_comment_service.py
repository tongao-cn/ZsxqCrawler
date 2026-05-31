import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from backend.services.columns_comment_service import fetch_column_topic_full_comments


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


class FakeColumnsDb:
    def __init__(self):
        self.closed = False
        self.imported = []

    def close(self):
        self.closed = True

    def import_comments(self, topic_id, comments):
        self.imported.append((topic_id, comments))
        return len(comments)


class ColumnsCommentServiceTests(unittest.TestCase):
    def test_fetch_column_topic_full_comments_processes_and_persists_replies(self):
        db = FakeColumnsDb()
        manager = Mock()
        manager.get_account_for_group.return_value = {"cookie": "cookie-value"}
        response = FakeResponse({
            "succeeded": True,
            "resp_data": {
                "comments": [
                    {
                        "comment_id": 1,
                        "text": "parent",
                        "replied_comments": [
                            {"comment_id": 2, "text": "reply", "likes_count": 3},
                        ],
                    },
                ],
            },
        })
        request_get = Mock(return_value=response)

        with (
            patch("backend.services.columns_comment_service.get_accounts_sql_manager", return_value=manager),
            patch("backend.services.columns_comment_service.build_stealth_headers", return_value={"Cookie": "cookie-value"}),
        ):
            result = fetch_column_topic_full_comments(
                "123",
                456,
                columns_db_factory=lambda _group_id: db,
                request_get=request_get,
            )

        self.assertTrue(result["success"])
        self.assertEqual(2, result["total"])
        self.assertEqual("parent", result["comments"][0]["text"])
        self.assertEqual("reply", result["comments"][0]["replied_comments"][0]["text"])
        self.assertEqual([(456, result["comments"])], db.imported)
        self.assertTrue(db.closed)
        request_get.assert_called_once()
        self.assertIn("/topics/456/comments", request_get.call_args.args[0])

    def test_fetch_column_topic_full_comments_raises_http_status(self):
        manager = Mock()
        manager.get_account_for_group.return_value = {"cookie": "cookie-value"}
        request_get = Mock(return_value=FakeResponse({}, status_code=429, text="rate limited"))

        with (
            patch("backend.services.columns_comment_service.get_accounts_sql_manager", return_value=manager),
            patch("backend.services.columns_comment_service.build_stealth_headers", return_value={"Cookie": "cookie-value"}),
        ):
            with self.assertRaises(HTTPException) as raised:
                fetch_column_topic_full_comments("123", 456, request_get=request_get)

        self.assertEqual(429, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
