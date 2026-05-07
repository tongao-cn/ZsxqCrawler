import json
import unittest

from backend.storage.account_info_db import (
    _build_self_info_upsert_params,
    _close_quietly,
    _safe_load_json,
    _self_info_row_to_dict,
)


class AccountInfoDbHelperTests(unittest.TestCase):
    def test_build_self_info_upsert_params_preserves_order_and_json(self):
        params = _build_self_info_upsert_params(
            "acc-1",
            {
                "uid": "u1",
                "name": "张三",
                "avatar_url": "avatar.png",
                "location": "SH",
                "user_sid": "sid-1",
                "grade": "vip",
                "ignored": "value",
            },
            {"ok": True, "name": "张三"},
            "2026-05-07T10:11:12",
        )

        self.assertEqual("acc-1", params[0])
        self.assertEqual(("u1", "张三", "avatar.png", "SH", "sid-1", "vip"), params[1:7])
        self.assertEqual({"ok": True, "name": "张三"}, json.loads(params[7]))
        self.assertEqual("2026-05-07T10:11:12", params[8])

    def test_safe_load_json_returns_none_for_empty_or_invalid_values(self):
        self.assertIsNone(_safe_load_json(None))
        self.assertIsNone(_safe_load_json(""))
        self.assertIsNone(_safe_load_json("{bad json"))
        self.assertEqual({"a": 1}, _safe_load_json('{"a": 1}'))

    def test_self_info_row_to_dict_keeps_existing_return_shape(self):
        row = (
            "acc-1",
            "u1",
            "name",
            "avatar.png",
            "SH",
            "sid-1",
            "vip",
            '{"nested": true}',
            "2026-05-07T10:11:12",
        )

        self.assertEqual(
            {
                "account_id": "acc-1",
                "uid": "u1",
                "name": "name",
                "avatar_url": "avatar.png",
                "location": "SH",
                "user_sid": "sid-1",
                "grade": "vip",
                "raw_json": {"nested": True},
                "fetched_at": "2026-05-07T10:11:12",
            },
            _self_info_row_to_dict(row),
        )

    def test_close_quietly_swallows_close_errors(self):
        class BrokenClose:
            def close(self):
                raise RuntimeError("already closed")

        _close_quietly(BrokenClose())


if __name__ == "__main__":
    unittest.main()
