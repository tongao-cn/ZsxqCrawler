import unittest
import json


class OfficialTopicClientHelperTests(unittest.TestCase):
    def test_official_payload_topics_accepts_topics_brief(self):
        from backend.crawlers.official_topic_client import official_payload_topics

        self.assertEqual([{"topic_id": "1"}], official_payload_topics({"topics_brief": [{"topic_id": "1"}]}))

    def test_official_payload_topic_accepts_topic_object(self):
        from backend.crawlers.official_topic_client import official_payload_topic

        self.assertEqual({"topic_id": "1"}, official_payload_topic({"topic": {"topic_id": "1"}}))
        self.assertEqual({}, official_payload_topic({"topic": None}))

    def test_official_payload_user_and_groups_accept_expected_objects(self):
        from backend.crawlers.official_topic_client import official_payload_groups, official_payload_user

        self.assertEqual({"user_id": "u1"}, official_payload_user({"user": {"user_id": "u1"}}))
        self.assertEqual({}, official_payload_user({"user": None}))
        self.assertEqual([{"group_id": "g1"}], official_payload_groups({"groups": [{"group_id": "g1"}]}))
        self.assertEqual([], official_payload_groups({"groups": None}))

    def test_normalize_official_topic_maps_talk_payload(self):
        from backend.crawlers.official_topic_client import normalize_official_topic

        topic = {
            "topic_id": "14422581515515282",
            "type": "talk",
            "title": "sample",
            "content": "hello",
            "create_time": "2026-05-21T10:59:02.752+0800",
            "group": {"group_id": "51111112855254", "name": "纪要又要"},
            "owner": {"user_id": "415421882824548", "name": "Bolk"},
            "counts": {"comments": 2, "likes": 3, "readers": 4, "reading": 5, "rewards": 6},
            "images": [{"image_id": "img-1"}],
            "files": [{"file_id": "file-1", "name": "report.pdf"}],
        }

        normalized = normalize_official_topic(topic, "51111112855254", comments=[{"comment_id": "10"}])

        self.assertEqual(14422581515515282, normalized["topic_id"])
        self.assertEqual(51111112855254, normalized["group"]["group_id"])
        self.assertEqual(2, normalized["comments_count"])
        self.assertEqual(3, normalized["likes_count"])
        self.assertEqual("hello", normalized["talk"]["text"])
        self.assertEqual([{"comment_id": "10"}], normalized["show_comments"])
        self.assertEqual([{"file_id": "file-1", "name": "report.pdf"}], normalized["talk"]["files"])

    def test_normalize_official_topic_maps_question_payload(self):
        from backend.crawlers.official_topic_client import normalize_official_topic

        normalized = normalize_official_topic(
            {
                "topic_id": "1",
                "type": "q&a",
                "content": "question text",
                "owner": {"user_id": "2", "name": "user"},
                "group": {"group_id": "3"},
                "counts": {},
            },
            "3",
        )

        self.assertEqual("question text", normalized["question"]["text"])
        self.assertNotIn("talk", normalized)

    def test_official_page_cursor_stops_when_cursor_does_not_move(self):
        from backend.services.crawl_service import _official_page_cursor

        self.assertIsNone(_official_page_cursor({"next_end_time": "same"}, "same"))
        self.assertEqual("next", _official_page_cursor({"next_end_time": "next"}, "same"))

    def test_official_client_requires_mcp_url(self):
        from unittest.mock import patch

        from backend.crawlers.official_topic_client import OfficialTopicClient

        with patch.dict("os.environ", {}, clear=True), patch("backend.crawlers.official_topic_client._load_project_env_file"):
            client = OfficialTopicClient(mcp_url="")

        with self.assertRaisesRegex(RuntimeError, "ZSXQ_TOPIC_MCP_URL"):
            client._ensure_url()

    def test_project_env_loader_loads_mcp_url_without_overriding_existing_env(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from backend.crawlers.official_topic_client import _load_project_env_file

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                'ZSXQ_TOPIC_MCP_URL="https://mcp.example/topic?api_key=from-file"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                _load_project_env_file(env_path)
                self.assertEqual("https://mcp.example/topic?api_key=from-file", os.environ["ZSXQ_TOPIC_MCP_URL"])
            with patch.dict(os.environ, {"ZSXQ_TOPIC_MCP_URL": "already-set"}, clear=True):
                _load_project_env_file(env_path)
                self.assertEqual("already-set", os.environ["ZSXQ_TOPIC_MCP_URL"])

    def test_official_client_parses_sse_tool_response(self):
        from unittest.mock import Mock, patch

        from backend.crawlers.official_topic_client import OfficialTopicClient

        tool_result = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"success": True, "topics_brief": [{"topic_id": "1"}]}),
                    }
                ]
            },
        }
        responses = [
            Mock(
                headers={"mcp-session-id": "session-1"},
                content=b'data: {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"TopicServer"}}}\n\n',
                raise_for_status=lambda: None,
            ),
            Mock(headers={}, content=b"", raise_for_status=lambda: None),
            Mock(
                headers={},
                content=f"data: {json.dumps(tool_result)}\n\n".encode("utf-8"),
                raise_for_status=lambda: None,
            ),
        ]

        with patch("backend.crawlers.official_topic_client.requests.post", side_effect=responses) as post:
            client = OfficialTopicClient(mcp_url="https://mcp.example/topic")
            payload = client.get_group_topics("group-1", 30)

        self.assertEqual([{"topic_id": "1"}], payload["topics_brief"])
        self.assertEqual("session-1", client.headers["Mcp-Session-Id"])
        self.assertEqual(3, post.call_count)
        self.assertEqual("tools/call", post.call_args_list[-1].kwargs["json"]["method"])

    def test_official_client_retries_retryable_request_errors(self):
        from unittest.mock import Mock, patch

        import requests

        from backend.crawlers.official_topic_client import OfficialTopicClient

        response = Mock(
            headers={},
            content=b'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n',
            raise_for_status=lambda: None,
        )

        with (
            patch(
                "backend.crawlers.official_topic_client.requests.post",
                side_effect=[requests.exceptions.SSLError("EOF"), response],
            ) as post,
            patch("backend.crawlers.official_topic_client.time.sleep") as sleep,
        ):
            client = OfficialTopicClient(mcp_url="https://mcp.example/topic?api_key=secret")
            payload = client._rpc("tools/list")

        self.assertEqual({"ok": True}, payload["result"])
        self.assertEqual(2, post.call_count)
        sleep.assert_called_once()

    def test_official_client_uses_retry_after_for_rate_limit(self):
        from unittest.mock import Mock

        import requests

        from backend.crawlers.official_topic_client import OfficialTopicClient

        response = Mock(status_code=429, headers={"Retry-After": "7"})
        error = requests.exceptions.HTTPError("429 Too Many Requests", response=response)
        client = OfficialTopicClient(mcp_url="https://mcp.example/topic")

        self.assertEqual(7.0, client._retry_delay_seconds(error, 1))

    def test_official_client_uses_long_default_delay_for_rate_limit(self):
        from unittest.mock import Mock

        import requests

        from backend.crawlers.official_topic_client import OfficialTopicClient

        response = Mock(status_code=429, headers={})
        error = requests.exceptions.HTTPError("429 Too Many Requests", response=response)
        client = OfficialTopicClient(mcp_url="https://mcp.example/topic")

        self.assertEqual(20.0, client._retry_delay_seconds(error, 1))
        self.assertEqual(40.0, client._retry_delay_seconds(error, 2))

    def test_official_client_throttles_tool_calls(self):
        from unittest.mock import patch

        from backend.crawlers.official_topic_client import OfficialTopicClient

        client = OfficialTopicClient(mcp_url="https://mcp.example/topic")
        client._last_tool_call_at = 10.0
        with (
            patch("backend.crawlers.official_topic_client.time.monotonic", side_effect=[10.2, 10.5]),
            patch("backend.crawlers.official_topic_client.time.sleep") as sleep,
        ):
            client._throttle_tool_call()

        sleep.assert_called_once_with(0.3000000000000007)
        self.assertEqual(10.5, client._last_tool_call_at)

    def test_official_client_sanitizes_mcp_url_after_retry_failure(self):
        from unittest.mock import patch

        import requests

        from backend.crawlers.official_topic_client import OfficialTopicClient

        error = requests.exceptions.SSLError(
            "HTTPSConnectionPool(host='mcp.example', url='/topic/mcp?api_key=secret-token')"
        )
        with (
            patch("backend.crawlers.official_topic_client.requests.post", side_effect=error),
            patch("backend.crawlers.official_topic_client.time.sleep"),
        ):
            client = OfficialTopicClient(mcp_url="https://mcp.example/topic?api_key=secret-token")
            with self.assertRaisesRegex(RuntimeError, r"api_key=\\*\\*\\*") as raised:
                client._rpc("tools/list")

        self.assertNotIn("secret-token", str(raised.exception))

    def test_official_client_calls_topic_info_tool(self):
        from unittest.mock import patch

        from backend.crawlers.official_topic_client import OfficialTopicClient

        client = OfficialTopicClient(mcp_url="https://mcp.example/topic")
        with patch.object(client, "_call_tool", return_value={"success": True, "topic": {"topic_id": "1"}}) as call_tool:
            payload = client.get_topic_info(1)

        self.assertEqual({"topic_id": "1"}, payload["topic"])
        call_tool.assert_called_once_with("get_topic_info", {"topic_id": "1"})

    def test_official_client_calls_user_groups_tool(self):
        from unittest.mock import patch

        from backend.crawlers.official_topic_client import OfficialTopicClient

        client = OfficialTopicClient(mcp_url="https://mcp.example/topic")
        with patch.object(client, "_call_tool", return_value={"success": True, "groups": []}) as call_tool:
            payload = client.get_user_groups("u1")

        self.assertEqual([], payload["groups"])
        call_tool.assert_called_once_with("get_user_groups", {"user_id": "u1", "limit": 200, "scope": "all"})


if __name__ == "__main__":
    unittest.main()
