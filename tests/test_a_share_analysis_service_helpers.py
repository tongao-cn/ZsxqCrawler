from datetime import datetime
from unittest.mock import Mock, patch
import os
import tempfile
import unittest


class _FakeAShareCursor:
    def __init__(self):
        self.calls = []
        self._rows = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "FROM topics" in sql:
            self._rows = [
                (1001, "topic title", "2026-05-07T10:00:00+0800"),
                (1002, "fallback title", "2026-05-07T11:00:00+0800"),
            ]
        elif "FROM talks" in sql:
            self._rows = [(1001, "talk body")]
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeAShareConnection:
    def __init__(self):
        self.cursor_obj = _FakeAShareCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


class _FakeOpenAIResponseMessage:
    content = '{"stocks":[]}'


class _FakeOpenAIChoice:
    message = _FakeOpenAIResponseMessage()


class _FakeOpenAIResponse:
    choices = [_FakeOpenAIChoice()]


class _FakeChatCompletions:
    def __init__(self, recorder):
        self.recorder = recorder

    def create(self, **kwargs):
        self.recorder.update(kwargs)
        return _FakeOpenAIResponse()


class _FakeOpenAIClient:
    recorder = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = Mock()
        self.chat.completions = _FakeChatCompletions(self.recorder)


class AShareAnalysisServiceHelperTests(unittest.TestCase):
    def test_db_storage_reads_empty_db_without_local_file_fallback(self):
        from backend.services import a_share_analysis_service as service

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "company_mentions.csv")
            state_path = os.path.join(temp_dir, "company_mentions_state.json")
            with open(output_path, "w", encoding="utf-8") as file_obj:
                file_obj.write("date,company,articles_count\n2026-05-01,旧数据,3\n")
            with open(state_path, "w", encoding="utf-8") as file_obj:
                file_obj.write('{"processed": ["old-topic"]}')

            with patch.object(service, "should_use_db_storage", return_value=True), patch.object(
                service, "load_daily_mentions_from_db", return_value={}
            ), patch.object(service, "load_processed_state_from_db", return_value=set()), patch.object(
                service, "_read_existing_csv_file"
            ) as read_file, patch.object(
                service, "_load_state_file"
            ) as load_file:
                self.assertEqual({}, service.read_existing_csv(output_path, group_id="511"))
                self.assertEqual(set(), service.load_state(state_path, group_id="511"))

        read_file.assert_not_called()
        load_file.assert_not_called()

    def test_db_storage_writes_do_not_write_local_files(self):
        from backend.services import a_share_analysis_service as service

        daily = {"2026-05-01": {"宁德时代": 2}}
        processed = {"topic-1"}

        with patch.object(service, "should_use_db_storage", return_value=True), patch.object(
            service, "save_daily_mentions_to_db"
        ) as save_daily, patch.object(service, "save_processed_state_to_db") as save_processed, patch.object(
            service, "_write_csv_file"
        ) as write_file, patch.object(
            service, "_save_state_file"
        ) as save_file:
            service.write_csv(daily, group_id="511")
            service.save_state(processed_keys=processed, group_id="511")

        save_daily.assert_called_once_with(daily, group_id="511")
        save_processed.assert_called_once_with(processed, group_id="511")
        write_file.assert_not_called()
        save_file.assert_not_called()

    def test_file_fallback_still_reads_and_writes_local_files(self):
        from backend.services import a_share_analysis_service as service

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "company_mentions.csv")
            state_path = os.path.join(temp_dir, "company_mentions_state.json")

            with patch.object(service, "should_use_db_storage", return_value=False):
                service.write_csv({"2026-05-01": {"宁德时代": 2}}, output_path, group_id="511")
                service.save_state(state_path, {"topic-1"}, group_id="511")
                daily = service.read_existing_csv(output_path, group_id="511")
                processed = service.load_state(state_path, group_id="511")

        self.assertEqual({"2026-05-01": {"宁德时代": 2}}, daily)
        self.assertEqual({"topic-1"}, processed)

    def test_normalize_date_range_validates_and_rejects_reversed_range(self):
        from backend.services.a_share_analysis_service import _normalize_date_range

        self.assertEqual(("2026-05-01", "2026-05-07"), _normalize_date_range(" 2026-05-01 ", "2026-05-07"))

        with self.assertRaisesRegex(ValueError, "start_date 不能晚于 end_date"):
            _normalize_date_range("2026-05-08", "2026-05-07")

        with self.assertRaisesRegex(ValueError, "reset_start_date 必须是 YYYY-MM-DD 格式"):
            _normalize_date_range(
                "20260501",
                "2026-05-07",
                "reset_start_date",
                "reset_end_date",
                "reset_start_date 不能晚于 reset_end_date",
            )

    def test_select_available_date_range_defaults_swaps_and_filters(self):
        from backend.services.a_share_analysis_service import _select_available_date_range

        available_dates = ["2026-05-01", "2026-05-02", "2026-05-03"]

        self.assertEqual(
            ("2026-05-01", "2026-05-03", available_dates),
            _select_available_date_range(available_dates),
        )
        self.assertEqual(
            ("2026-05-02", "2026-05-03", ["2026-05-02", "2026-05-03"]),
            _select_available_date_range(available_dates, "2026-05-03", "2026-05-02"),
        )
        self.assertEqual(
            ("2026-04-01", "2026-04-02", []),
            _select_available_date_range(available_dates, "2026-04-01", "2026-04-02"),
        )

    def test_empty_chart_payload_preserves_existing_shape(self):
        from backend.services.a_share_analysis_service import _empty_chart_payload

        self.assertEqual(
            {
                "group_id": "12345",
                "available_dates": ["2026-05-01"],
                "selected_start_date": "2026-05-02",
                "selected_end_date": "2026-05-03",
                "chart_data": [],
                "series": [],
                "rankings": {},
                "date_count": 0,
                "company_count": 0,
                "total_companies_in_range": 0,
                "top_n": 20,
                "ranking_top_n": 35,
            },
            _empty_chart_payload(" 12345 ", ["2026-05-01"], "2026-05-02", "2026-05-03", 20, 35),
        )

    def test_parse_topic_stock_extraction_output_supports_new_schema(self):
        from backend.services.a_share_analysis_service import _parse_company_extraction_output, _parse_topic_stock_extraction_output

        message = """
        {
          "stocks": [
            {
              "stock_name": "宁德时代",
              "concepts": ["固态电池", "储能"],
              "reason": "话题明确讨论宁德时代电池链。",
              "confidence": 0.86
            },
            {
              "stock_name": "沪深300ETF",
              "concepts": ["指数"],
              "reason": "不是股票",
              "confidence": 0.9
            }
          ]
        }
        """

        stocks = _parse_topic_stock_extraction_output(message)

        self.assertEqual(
            [
                {
                    "stock_name": "宁德时代",
                    "concepts": ["固态电池", "储能"],
                    "excerpt": "",
                    "reason": "话题明确讨论宁德时代电池链。",
                    "confidence": 0.86,
                }
            ],
            stocks,
        )
        self.assertEqual(["宁德时代"], _parse_company_extraction_output(message))

    def test_parse_topic_stock_extraction_output_keeps_legacy_company_schema(self):
        from backend.services.a_share_analysis_service import _parse_topic_stock_extraction_output

        stocks = _parse_topic_stock_extraction_output('{"companies": ["宁德时代", "中信证券"]}')

        self.assertEqual(
            [{"stock_name": "宁德时代", "concepts": [], "excerpt": "", "reason": "", "confidence": 0.7}],
            stocks,
        )

    def test_topic_stock_extraction_prompt_requires_positive_recommendation_context(self):
        from backend.services.a_share_analysis_service import (
            TOPIC_STOCK_EXTRACTION_PROMPT_VERSION,
            _build_topic_stock_extraction_prompt,
        )

        prompt = _build_topic_stock_extraction_prompt()

        self.assertEqual("a-share-topic-stock-extraction-v2", TOPIC_STOCK_EXTRACTION_PROMPT_VERSION)
        self.assertIn("正向推荐或受益语义", prompt)
        self.assertIn("不要仅因为公司名称出现就输出", prompt)
        self.assertIn("excerpt 是从原文中直接摘出的证据片段", prompt)
        self.assertIn("如果全文都在讲一个股票，返回全文", prompt)
        self.assertIn("风险、暴雷、利空、业绩下修", prompt)
        self.assertIn("如果只有负面或风险语义，应直接不输出", prompt)
        self.assertIn("重点关注、买入/增持、受益", prompt)

    def test_call_openai_extract_topic_stocks_sends_recommendation_pool_prompt(self):
        from backend.services import a_share_analysis_service as service

        _FakeOpenAIClient.recorder = {}

        with patch("openai.OpenAI", _FakeOpenAIClient):
            self.assertEqual(
                [],
                service.call_openai_extract_topic_stocks(
                    "五粮液年报出现重大调整，营收利润重算后大幅下滑。",
                    api_key="test-key",
                    model="test-model",
                    wire_api="chat",
                ),
            )

        messages = _FakeOpenAIClient.recorder["messages"]
        self.assertIn("正向推荐或明确受益", messages[0]["content"])
        self.assertIn("负面风险、暴雷、利空、避雷、跌幅归因", messages[0]["content"])
        self.assertIn("不要仅因为公司名称出现就输出", messages[1]["content"])
        self.assertIn("excerpt 规则", messages[1]["content"])
        self.assertIn("业绩下修", messages[1]["content"])
        self.assertIn("营收利润重算后大幅下滑", messages[1]["content"])

    def test_call_openai_extract_topic_stocks_skips_empty_or_too_short_content(self):
        from backend.services import a_share_analysis_service as service

        with patch.object(service, "log_debug") as log_debug, patch("openai.OpenAI") as openai_client:
            self.assertEqual(
                [],
                service.call_openai_extract_topic_stocks(
                    "短内容不够长",
                    api_key="test-key",
                    model="test-model",
                    wire_api="responses",
                ),
            )

        openai_client.assert_not_called()
        log_debug.assert_called_once()

    def test_backfill_topic_stock_extractions_uses_recent_seven_day_reset_range(self):
        from backend.services import a_share_analysis_service as service

        with patch.object(service, "datetime") as mock_datetime, patch.object(service, "run_analysis") as run_analysis:
            mock_datetime.now.return_value = datetime(2026, 5, 10, 12, 0, 0)
            mock_datetime.strptime.side_effect = datetime.strptime
            run_analysis.return_value = {"ok": True}

            result = service.backfill_topic_stock_extractions(group_id="123", days=7, concurrency=2)

        self.assertEqual({"ok": True}, result)
        run_analysis.assert_called_once()
        kwargs = run_analysis.call_args.kwargs
        self.assertEqual("123", kwargs["group_id"])
        self.assertEqual(7, kwargs["days"])
        self.assertEqual("2026-05-04", kwargs["reset_start_date"])
        self.assertEqual("2026-05-10", kwargs["reset_end_date"])
        self.assertEqual(2, kwargs["concurrency"])

    def test_run_analysis_checkpoints_every_twenty_successful_topics(self):
        from backend.services import a_share_analysis_service as service

        items = [
            {
                "topic_id": index,
                "title": f"title {index}",
                "text": f"这是一个长度超过二十个字的推荐池测试话题内容 {index}",
                "create_time": "2026-05-10T10:00:00+0800",
                "day": "2026-05-10",
                "source": "topics",
                "group_id": "511",
            }
            for index in range(1, 46)
        ]
        checkpoint_calls = []

        def fake_extract(text, api_key, model, api_base, **kwargs):
            topic_id = kwargs["item_context"].split("topic_id=", 1)[1].split(" ", 1)[0]
            return [
                {
                    "stock_name": f"公司{topic_id}",
                    "concepts": [],
                    "reason": "",
                    "confidence": 0.8,
                }
            ]

        def fake_checkpoint(**kwargs):
            checkpoint_calls.append(kwargs)
            return {
                "daily_mentions": sum(len(values) for values in kwargs["daily_delta"].values()),
                "topic_stock_extractions": len(kwargs["topic_stock_extractions"]),
                "processed_state": len(set(kwargs["processed_keys"])),
            }

        with patch.object(service, "get_openai_compatible_config", return_value={"api_key": "key"}), patch.object(
            service, "read_existing_csv", return_value={}
        ), patch.object(service, "load_state", return_value=set()), patch.object(
            service, "read_topics_last_days", return_value=items
        ), patch.object(service, "should_use_db_storage", return_value=True), patch.object(
            service, "call_openai_extract_topic_stocks", side_effect=fake_extract
        ), patch.object(service, "save_recommendation_pool_checkpoint", side_effect=fake_checkpoint), patch.object(
            service, "write_csv"
        ), patch.object(
            service, "save_state"
        ), patch.object(
            service,
            "get_analysis_summary",
            return_value={"date_count": 1, "output_path": "db.daily", "state_path": "db.state"},
        ):
            result = service.run_analysis(group_id="511", days=1, concurrency=1)

        self.assertEqual([20, 20, 5], [len(call["processed_keys"]) for call in checkpoint_calls])
        self.assertEqual(45, result["items_succeeded"])
        self.assertEqual(45, result["topic_stock_extractions"])

    def test_run_analysis_marks_short_items_processed_without_extractions(self):
        from backend.services import a_share_analysis_service as service

        items = [
            {
                "topic_id": 1,
                "title": "title 1",
                "text": "too short",
                "create_time": "2026-05-10T10:00:00+0800",
                "day": "2026-05-10",
                "source": "topics",
                "group_id": "511",
            }
        ]
        saved_state = []
        checkpoint_calls = []

        def fake_checkpoint(**kwargs):
            checkpoint_calls.append(kwargs)
            return {"daily_mentions": 0, "topic_stock_extractions": 0, "processed_state": len(set(kwargs["processed_keys"]))}

        with patch.object(service, "get_openai_compatible_config", return_value={"api_key": "key"}), patch.object(
            service, "read_existing_csv", return_value={}
        ), patch.object(service, "load_state", return_value=set()), patch.object(
            service, "read_topics_last_days", return_value=items
        ), patch.object(service, "should_use_db_storage", return_value=True), patch.object(
            service, "call_openai_extract_topic_stocks", return_value=[]
        ) as extract, patch.object(service, "save_recommendation_pool_checkpoint", side_effect=fake_checkpoint), patch.object(
            service, "write_csv"
        ), patch.object(
            service, "save_state", side_effect=lambda _path, keys=None, **_kwargs: saved_state.append(set(keys or set()))
        ), patch.object(
            service,
            "get_analysis_summary",
            return_value={"date_count": 1, "output_path": "db.daily", "state_path": "db.state"},
        ):
            result = service.run_analysis(group_id="511", days=1, concurrency=1)

        extract.assert_not_called()
        self.assertEqual(1, result["items_succeeded"])
        self.assertEqual(0, result["topic_stock_extractions"])
        self.assertEqual(1, len(saved_state[0]))
        self.assertEqual(1, len(checkpoint_calls[0]["processed_keys"]))

    def test_run_analysis_checkpoint_failure_stops_final_writes(self):
        from backend.services import a_share_analysis_service as service

        items = [
            {
                "topic_id": index,
                "title": f"title {index}",
                "text": f"这是一个长度超过二十个字的推荐池测试话题内容 {index}",
                "create_time": "2026-05-10T10:00:00+0800",
                "day": "2026-05-10",
                "source": "topics",
                "group_id": "511",
            }
            for index in range(1, 21)
        ]

        with patch.object(service, "get_openai_compatible_config", return_value={"api_key": "key"}), patch.object(
            service, "read_existing_csv", return_value={}
        ), patch.object(service, "load_state", return_value=set()), patch.object(
            service, "read_topics_last_days", return_value=items
        ), patch.object(service, "should_use_db_storage", return_value=True), patch.object(
            service,
            "call_openai_extract_topic_stocks",
            return_value=[{"stock_name": "宁德时代", "concepts": [], "reason": "", "confidence": 0.8}],
        ), patch.object(
            service, "save_recommendation_pool_checkpoint", side_effect=RuntimeError("checkpoint failed")
        ), patch.object(
            service, "write_csv"
        ) as write_csv, patch.object(
            service, "save_state"
        ) as save_state:
            with self.assertRaisesRegex(RuntimeError, "checkpoint failed"):
                service.run_analysis(group_id="511", days=1, concurrency=1)

        write_csv.assert_not_called()
        save_state.assert_not_called()

    def test_run_analysis_file_only_mode_skips_checkpoint(self):
        from backend.services import a_share_analysis_service as service

        item = {
            "topic_id": 1001,
            "title": "title",
            "text": "text",
            "create_time": "2026-05-10T10:00:00+0800",
            "day": "2026-05-10",
            "source": "topics",
            "group_id": "511",
        }

        with patch.object(service, "get_openai_compatible_config", return_value={"api_key": "key"}), patch.object(
            service, "read_existing_csv", return_value={}
        ), patch.object(service, "load_state", return_value=set()), patch.object(
            service, "read_topics_last_days", return_value=[item]
        ), patch.object(service, "should_use_db_storage", return_value=False), patch.object(
            service,
            "call_openai_extract_topic_stocks",
            return_value=[{"stock_name": "宁德时代", "concepts": [], "reason": "", "confidence": 0.8}],
        ), patch.object(
            service, "save_recommendation_pool_checkpoint"
        ) as checkpoint, patch.object(
            service, "write_csv"
        ) as write_csv, patch.object(
            service, "save_state"
        ) as save_state, patch.object(
            service,
            "get_analysis_summary",
            return_value={"date_count": 1, "output_path": "file.csv", "state_path": "state.json"},
        ):
            result = service.run_analysis(group_id="511", days=1, concurrency=1)

        checkpoint.assert_not_called()
        write_csv.assert_called()
        save_state.assert_called()
        self.assertEqual(1, result["items_succeeded"])

    def test_read_topics_last_days_filters_topics_and_talks_by_group_scope(self):
        from backend.services import a_share_analysis_service as service

        fake_conn = _FakeAShareConnection()

        with patch.object(service, "connect", return_value=fake_conn), patch.object(
            service,
            "get_last_days_range",
            return_value=(datetime(2026, 5, 1), datetime(2026, 5, 8, 23, 59, 59)),
        ):
            items = service.read_topics_last_days("51111112855254", 21)

        topic_sql, topic_params = fake_conn.cursor_obj.calls[0]
        talk_sql, talk_params = fake_conn.cursor_obj.calls[1]

        self.assertIn("WHERE t.group_id = ?", topic_sql)
        self.assertEqual((51111112855254,), topic_params)
        self.assertIn("WHERE topic_id IN (?, ?)", talk_sql)
        self.assertEqual((1001, 1002), talk_params)
        self.assertTrue(fake_conn.closed)
        self.assertEqual(
            [
                {
                    "topic_id": 1001,
                    "title": "topic title",
                    "text": "talk body",
                    "create_time": "2026-05-07T10:00:00+0800",
                    "day": "2026-05-07",
                    "source": "topics",
                    "group_id": "51111112855254",
                },
                {
                    "topic_id": 1002,
                    "title": "fallback title",
                    "text": "fallback title",
                    "create_time": "2026-05-07T11:00:00+0800",
                    "day": "2026-05-07",
                    "source": "topics",
                    "group_id": "51111112855254",
                },
            ],
            items,
        )

    def test_read_topics_in_date_range_filters_topics_and_talks_by_group_scope(self):
        from backend.services import a_share_analysis_service as service

        fake_conn = _FakeAShareConnection()

        with patch.object(service, "connect", return_value=fake_conn):
            items = service.read_topics_in_date_range("51111112855254", "2026-05-07", "2026-05-07")

        topic_sql, topic_params = fake_conn.cursor_obj.calls[0]
        talk_sql, talk_params = fake_conn.cursor_obj.calls[1]

        self.assertIn("WHERE t.group_id = ?", topic_sql)
        self.assertEqual((51111112855254,), topic_params)
        self.assertIn("WHERE topic_id IN (?, ?)", talk_sql)
        self.assertEqual((1001, 1002), talk_params)
        self.assertTrue(fake_conn.closed)
        self.assertEqual(["2026-05-07", "2026-05-07"], [item["day"] for item in items])

    def test_run_analysis_uses_explicit_date_range_when_provided(self):
        from backend.services import a_share_analysis_service as service

        item = {
            "topic_id": 1001,
            "title": "title",
            "text": "text",
            "create_time": "2026-05-07T10:00:00+0800",
            "day": "2026-05-07",
            "source": "topics",
            "group_id": "511",
        }

        with patch.object(service, "get_openai_compatible_config", return_value={"api_key": "key"}), patch.object(
            service, "read_existing_csv", return_value={}
        ), patch.object(service, "load_state", return_value=set()), patch.object(
            service, "read_topics_last_days"
        ) as read_last_days, patch.object(
            service, "read_topics_in_date_range", return_value=[item]
        ) as read_date_range, patch.object(
            service, "should_use_db_storage", return_value=False
        ), patch.object(
            service,
            "call_openai_extract_topic_stocks",
            return_value=[{"stock_name": "宁德时代", "concepts": [], "reason": "", "confidence": 0.8}],
        ), patch.object(
            service, "write_csv"
        ), patch.object(
            service, "save_state"
        ), patch.object(
            service,
            "get_analysis_summary",
            return_value={"date_count": 1, "output_path": "file.csv", "state_path": "state.json"},
        ):
            result = service.run_analysis(
                group_id="511",
                days=21,
                start_date="2026-05-07",
                end_date="2026-05-07",
                concurrency=1,
            )

        read_last_days.assert_not_called()
        read_date_range.assert_called_once_with("511", "2026-05-07", "2026-05-07", None)
        self.assertEqual(1, result["items_succeeded"])

    def test_run_analysis_rejects_partial_or_reversed_date_range(self):
        from backend.services import a_share_analysis_service as service

        with patch.object(service, "read_existing_csv", return_value={}), patch.object(
            service, "load_state", return_value=set()
        ):
            with self.assertRaisesRegex(ValueError, "start_date 和 end_date 需要同时提供"):
                service.run_analysis(group_id="511", start_date="2026-05-07")

            with self.assertRaisesRegex(ValueError, "start_date 不能晚于 end_date"):
                service.run_analysis(group_id="511", start_date="2026-05-08", end_date="2026-05-07")

    def test_get_source_topics_summary_filters_by_group_scope(self):
        from backend.services import a_share_analysis_service as service

        fake_conn = _FakeAShareConnection()
        fake_conn.cursor_obj._rows = [(2, "2026-05-01T10:00:00+0800", "2026-05-07T10:00:00+0800")]

        def execute(sql, params=None):
            fake_conn.cursor_obj.calls.append((sql, params))
            fake_conn.cursor_obj._rows = [(2, "2026-05-01T10:00:00+0800", "2026-05-07T10:00:00+0800")]

        fake_conn.cursor_obj.execute = execute

        with patch.object(service, "connect", return_value=fake_conn):
            summary = service.get_source_topics_summary("51111112855254")

        sql, params = fake_conn.cursor_obj.calls[0]
        self.assertIn("WHERE group_id = ?", sql)
        self.assertEqual((51111112855254,), params)
        self.assertTrue(fake_conn.closed)
        self.assertEqual(2, summary["topics_count"])


if __name__ == "__main__":
    unittest.main()
