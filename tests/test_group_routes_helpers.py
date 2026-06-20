import json
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch


HAS_GROUP_ROUTE_DEPS = find_spec("fastapi") is not None

if HAS_GROUP_ROUTE_DEPS:
    from backend.routes import group_routes
    from backend.services import group_workflow_service


class FakePathManager:
    def __init__(self, group_dir=None):
        self.group_dir = group_dir

    def get_group_data_dir(self, group_id):
        return self.group_dir


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rows = [
            ("数据库群", "paid", "https://example.com/bg.png"),
            ("2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z"),
            (12,),
        ]

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))

    def fetchone(self):
        return self.rows.pop(0)


class FakeDb:
    last_instance = None

    def __init__(self, group_id=None):
        self.group_id = group_id
        self.cursor = FakeCursor()
        self.calls = []
        self.closed = False
        FakeDb.last_instance = self

    def load_local_group_db_fields(self, fields):
        self.calls.append(dict(fields))
        result = dict(fields)
        result["local_name"] = "数据库群"
        result["local_type"] = "paid"
        result["local_bg"] = "https://example.com/bg.png"
        result["join_time"] = "2024-01-01T00:00:00Z"
        result["expiry_time"] = "2024-02-01T00:00:00Z"
        result["last_active_time"] = "2024-02-01T00:00:00Z"
        result["statistics"] = {
            "topics": {
                "topics_count": 12,
                "answers_count": 0,
                "digests_count": 0,
            }
        }
        return result

    def close(self):
        self.closed = True


class FakeFileCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))

    def fetchone(self):
        return (7,)


class FakeFileDb:
    last_instance = None

    def __init__(self):
        self.group_id = None
        self.cursor = FakeFileCursor()
        self.count_calls = 0
        self.closed = False
        FakeFileDb.last_instance = self

    def count_files(self):
        self.count_calls += 1
        return 7

    def close(self):
        self.closed = True


class FakeScopedFileDb(FakeFileDb):
    def __init__(self, group_id=None):
        super().__init__()
        self.group_id = group_id


@unittest.skipUnless(HAS_GROUP_ROUTE_DEPS, "group route dependencies are not installed")
class GroupRoutesHelperTests(unittest.TestCase):
    def _run_async(self, coro):
        import asyncio

        return asyncio.run(coro)

    def test_default_local_group_fields_and_entry(self):
        fields = group_workflow_service._default_local_group_fields(123)
        entry = group_workflow_service._build_local_group_entry(123, fields)

        self.assertEqual(fields["local_name"], "本地群（123）")
        self.assertEqual(entry["group_id"], 123)
        self.assertEqual(entry["name"], "本地群（123）")
        self.assertEqual(entry["type"], "local")
        self.assertEqual(entry["source"], "local")
        self.assertIsNone(entry["account"])

    def test_build_local_group_entry_from_sources_applies_meta_then_db_fields(self):
        seen_fields = []

        def fake_load_local_group_db_fields(group_id, fields):
            seen_fields.append((group_id, dict(fields)))
            result = dict(fields)
            result["local_name"] = "数据库群"
            result["statistics"] = {"topics": {"topics_count": 3}}
            return result

        with (
            patch.object(
                group_workflow_service,
                "_read_local_group_meta",
                return_value={
                    "name": "Meta 群",
                    "background_url": "https://example.com/meta.png",
                    "join_time": "2024-01-01",
                },
            ),
            patch.object(
                group_workflow_service,
                "_load_local_group_db_fields",
                side_effect=fake_load_local_group_db_fields,
            ),
        ):
            entry = group_workflow_service._build_local_group_entry_from_sources(123)

        expected_fields_before_db_load = {
            "local_name": "Meta 群",
            "local_type": "local",
            "local_bg": "https://example.com/meta.png",
            "owner": {},
            "join_time": "2024-01-01",
            "expiry_time": None,
            "last_active_time": None,
            "description": "",
            "statistics": {},
        }

        self.assertEqual([(123, expected_fields_before_db_load)], seen_fields)
        self.assertEqual(123, entry["group_id"])
        self.assertEqual("数据库群", entry["name"])
        self.assertEqual({"topics": {"topics_count": 3}}, entry["statistics"])
        self.assertEqual("local", entry["source"])

    def test_apply_local_group_meta_preserves_defaults_for_empty_values(self):
        fields = group_workflow_service._default_local_group_fields(123)
        updated = group_workflow_service._apply_local_group_meta(
            fields,
            {
                "name": "Meta 群",
                "type": "paid",
                "background_url": "https://example.com/meta.png",
                "owner": {},
                "statistics": {},
                "join_time": "2024-01-01",
                "expiry_time": "2024-02-01",
                "last_active_time": "2024-02-02",
                "description": "desc",
            },
        )

        self.assertEqual(updated["local_name"], "Meta 群")
        self.assertEqual(updated["local_type"], "paid")
        self.assertEqual(updated["local_bg"], "https://example.com/meta.png")
        self.assertEqual(updated["owner"], {})
        self.assertEqual(updated["statistics"], {})
        self.assertEqual(updated["join_time"], "2024-01-01")
        self.assertEqual(updated["description"], "desc")

    def test_read_local_group_meta_reads_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "group_meta.json"
            meta_path.write_text(json.dumps({"name": "本地缓存群"}, ensure_ascii=False), encoding="utf-8")

            with patch.object(group_workflow_service, "get_db_path_manager", return_value=FakePathManager(group_dir=tmp)):
                meta = group_workflow_service._read_local_group_meta(123)

        self.assertEqual(meta, {"name": "本地缓存群"})

    def test_load_local_group_db_fields_fills_missing_values(self):
        fields = group_workflow_service._default_local_group_fields(123)

        with patch.object(
            group_workflow_service, "ZSXQDatabase", FakeDb
        ):
            updated = group_workflow_service._load_local_group_db_fields(123, fields)

        self.assertEqual(updated["local_name"], "数据库群")
        self.assertEqual(updated["local_type"], "paid")
        self.assertEqual(updated["local_bg"], "https://example.com/bg.png")
        self.assertEqual(updated["join_time"], "2024-01-01T00:00:00Z")
        self.assertEqual(updated["expiry_time"], "2024-02-01T00:00:00Z")
        self.assertEqual(updated["last_active_time"], "2024-02-01T00:00:00Z")
        self.assertEqual(updated["statistics"]["topics"]["topics_count"], 12)
        self.assertTrue(FakeDb.last_instance.closed)
        self.assertEqual(FakeDb.last_instance.group_id, "123")
        self.assertEqual([fields], FakeDb.last_instance.calls)

    def test_build_group_info_fallback_coerces_numeric_id_and_adds_note(self):
        result = group_routes._build_group_info_fallback(
            "123",
            account={"id": "a1"},
            files_count=5,
            note="no_cookie",
        )

        self.assertEqual(result["group_id"], 123)
        self.assertEqual(result["statistics"], {"files": {"count": 5}})
        self.assertEqual(result["account"], {"id": "a1"})
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["note"], "no_cookie")

    def test_build_group_info_fallback_keeps_non_numeric_id(self):
        result = group_routes._build_group_info_fallback("abc", account=None, files_count=0)

        self.assertEqual(result["group_id"], "abc")
        self.assertNotIn("note", result)

    def test_count_group_files_returns_zero_when_crawler_fails(self):
        with patch.object(group_routes, "ZSXQFileDatabase", side_effect=RuntimeError("boom")):
            self.assertEqual(group_routes._count_group_files("123"), 0)

    def test_count_group_files_filters_by_group_id(self):
        with patch.object(group_routes, "ZSXQFileDatabase", FakeScopedFileDb):
            self.assertEqual(group_routes._count_group_files("123"), 7)

        file_db = FakeScopedFileDb.last_instance

        self.assertEqual(1, file_db.count_calls)
        self.assertEqual([], file_db.cursor.calls)
        self.assertEqual(file_db.group_id, "123")
        self.assertTrue(file_db.closed)

    def test_get_group_stats_response_delegates_to_read_model(self):
        with patch.object(group_routes, "get_group_stats_read_model", return_value={"topics_count": 12}) as get_stats:
            result = group_routes._get_group_stats_response(123)

        self.assertEqual({"topics_count": 12}, result)
        get_stats.assert_called_once_with(123)

    def test_build_official_group_entry_maps_supported_fields(self):
        entry = group_workflow_service._build_official_group_entry(
            {
                "group_id": "123",
                "name": "官方群",
                "type": "paid",
                "background_url": "bg.png",
                "owner": {"user_id": "1"},
                "statistics": {"topics_count": 2},
                "description": "desc",
            },
            account={"id": "acc"},
        )

        self.assertEqual(123, entry["group_id"])
        self.assertEqual("官方群", entry["name"])
        self.assertEqual("account", entry["source"])
        self.assertEqual({"id": "acc"}, entry["account"])
        self.assertIsNone(entry["expiry_time"])

    def test_build_official_group_entry_skips_invalid_group_id(self):
        self.assertIsNone(group_workflow_service._build_official_group_entry({"group_id": "abc"}))

    def test_fetch_official_groups_uses_self_user_id(self):
        class FakeOfficialClient:
            def get_self_info(self):
                return {"user": {"user_id": "u1"}}

            def get_user_groups(self, user_id, limit=200, scope="all"):
                return {"groups": [{"group_id": "123"}], "count": 1}

        groups = group_workflow_service.fetch_official_groups(FakeOfficialClient())

        self.assertEqual([{"group_id": "123"}], groups)

    def test_get_groups_response_preserves_account_and_local_source_contract(self):
        persisted = []

        def fake_load_local_group_db_fields(group_id, fields):
            result = dict(fields)
            result["local_name"] = f"本地群 {group_id}"
            return result

        with (
            patch.object(group_workflow_service, "build_account_group_detection", return_value={"123": {"id": "acc"}}),
            patch.object(group_workflow_service, "get_cached_local_group_ids", return_value={"123", "456"}),
            patch.object(
                group_workflow_service,
                "fetch_official_groups",
                return_value=[
                    {
                        "group_id": "123",
                        "name": "官方群",
                        "type": "paid",
                    }
                ],
            ),
            patch.object(
                group_workflow_service,
                "_persist_group_meta_local",
                side_effect=lambda gid, info: persisted.append((gid, info["source"])),
            ),
            patch.object(group_workflow_service, "_read_local_group_meta", return_value={}),
            patch.object(
                group_workflow_service,
                "_load_local_group_db_fields",
                side_effect=fake_load_local_group_db_fields,
            ),
        ):
            response = group_workflow_service.get_groups_response()

        groups_by_id = {item["group_id"]: item for item in response["groups"]}
        self.assertEqual("account|local", groups_by_id[123]["source"])
        self.assertEqual({"id": "acc"}, groups_by_id[123]["account"])
        self.assertEqual("local", groups_by_id[456]["source"])
        self.assertEqual([(123, "account|local")], persisted)

    def test_group_read_routes_offload_sync_work_to_thread(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"called": func.__name__, "args": args}

        with patch("backend.routes.group_routes.asyncio.to_thread", side_effect=fake_to_thread):
            groups = self._run_async(group_routes.get_groups())
            info = self._run_async(group_routes.get_group_info("123"))
            stats = self._run_async(group_routes.get_group_stats(123))
            database_info = self._run_async(group_routes.get_group_database_info(123))

        self.assertEqual(
            [
                (group_routes._get_groups_response, ()),
                (group_routes._get_group_info_response, ("123",)),
                (group_routes._get_group_stats_response, (123,)),
                (group_routes._get_group_database_info_response, (123,)),
            ],
            calls,
        )
        self.assertEqual({"called": "get_groups_response", "args": ()}, groups)
        self.assertEqual({"called": "_get_group_info_response", "args": ("123",)}, info)
        self.assertEqual({"called": "_get_group_stats_response", "args": (123,)}, stats)
        self.assertEqual({"called": "_get_group_database_info_response", "args": (123,)}, database_info)

    def test_group_route_error_preserves_status_and_detail_format(self):
        error = group_routes._group_route_error("获取群组列表失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("获取群组列表失败: boom", error.detail)

    def test_group_read_routes_preserve_wrapped_unexpected_errors(self):
        cases = [
            (group_routes.get_groups, (), "_groups", "获取群组列表失败: boom"),
            (group_routes.get_group_info, ("123",), "_group_info", "获取群组信息失败: boom"),
            (group_routes.get_group_stats, (123,), "_group_stats", "获取群组统计失败: boom"),
            (
                group_routes.get_group_database_info,
                (123,),
                "_group_database_info",
                "获取数据库信息失败: boom",
            ),
        ]

        for route, route_args, helper_name, expected_detail in cases:
            with self.subTest(helper=helper_name), patch.object(
                group_routes,
                helper_name,
                side_effect=RuntimeError("boom"),
            ):
                with self.assertRaises(group_routes.HTTPException) as ctx:
                    self._run_async(route(*route_args))

                self.assertEqual(500, ctx.exception.status_code)
                self.assertEqual(expected_detail, ctx.exception.detail)

    def test_group_read_helpers_preserve_service_call_shapes(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func, args))
            return {"called": func.__name__, "args": args}

        with patch("backend.routes.group_routes.asyncio.to_thread", side_effect=fake_to_thread):
            groups = self._run_async(group_routes._groups())
            info = self._run_async(group_routes._group_info("123"))
            stats = self._run_async(group_routes._group_stats(123))
            database_info = self._run_async(group_routes._group_database_info(123))

        self.assertEqual(
            [
                (group_routes._get_groups_response, ()),
                (group_routes._get_group_info_response, ("123",)),
                (group_routes._get_group_stats_response, (123,)),
                (group_routes._get_group_database_info_response, (123,)),
            ],
            calls,
        )
        self.assertEqual({"called": "get_groups_response", "args": ()}, groups)
        self.assertEqual({"called": "_get_group_info_response", "args": ("123",)}, info)
        self.assertEqual({"called": "_get_group_stats_response", "args": (123,)}, stats)
        self.assertEqual({"called": "_get_group_database_info_response", "args": (123,)}, database_info)


if __name__ == "__main__":
    unittest.main()
