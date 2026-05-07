import json
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch


HAS_GROUP_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("requests") is not None

if HAS_GROUP_ROUTE_DEPS:
    from backend.routes import group_routes


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
        self.closed = False
        FakeDb.last_instance = self

    def close(self):
        self.closed = True


@unittest.skipUnless(HAS_GROUP_ROUTE_DEPS, "group route dependencies are not installed")
class GroupRoutesHelperTests(unittest.TestCase):
    def test_default_local_group_fields_and_entry(self):
        fields = group_routes._default_local_group_fields(123)
        entry = group_routes._build_local_group_entry(123, fields)

        self.assertEqual(fields["local_name"], "本地群（123）")
        self.assertEqual(entry["group_id"], 123)
        self.assertEqual(entry["name"], "本地群（123）")
        self.assertEqual(entry["type"], "local")
        self.assertEqual(entry["source"], "local")
        self.assertIsNone(entry["account"])

    def test_apply_local_group_meta_preserves_defaults_for_empty_values(self):
        fields = group_routes._default_local_group_fields(123)
        updated = group_routes._apply_local_group_meta(
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

            with patch.object(group_routes, "get_db_path_manager", return_value=FakePathManager(group_dir=tmp)):
                meta = group_routes._read_local_group_meta(123)

        self.assertEqual(meta, {"name": "本地缓存群"})

    def test_load_local_group_db_fields_fills_missing_values(self):
        fields = group_routes._default_local_group_fields(123)

        with patch.object(
            group_routes, "ZSXQDatabase", FakeDb
        ):
            updated = group_routes._load_local_group_db_fields(123, fields)

        self.assertEqual(updated["local_name"], "数据库群")
        self.assertEqual(updated["local_type"], "paid")
        self.assertEqual(updated["local_bg"], "https://example.com/bg.png")
        self.assertEqual(updated["join_time"], "2024-01-01T00:00:00Z")
        self.assertEqual(updated["expiry_time"], "2024-02-01T00:00:00Z")
        self.assertEqual(updated["last_active_time"], "2024-02-01T00:00:00Z")
        self.assertEqual(updated["statistics"]["topics"]["topics_count"], 12)
        self.assertTrue(FakeDb.last_instance.closed)
        self.assertEqual(FakeDb.last_instance.group_id, "123")
        self.assertEqual(len(FakeDb.last_instance.cursor.calls), 3)

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
        with patch.object(group_routes, "get_crawler_for_group", side_effect=RuntimeError("boom")):
            self.assertEqual(group_routes._count_group_files("123"), 0)


if __name__ == "__main__":
    unittest.main()
