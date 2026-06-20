import unittest
from unittest.mock import patch


class FakeStatsDb:
    last_instance = None

    def __init__(self, group_id=None):
        self.group_id = group_id
        self.closed = False
        FakeStatsDb.last_instance = self

    def get_group_stats_summary(self):
        return {
            "group_id": int(self.group_id),
            "topics_count": 12,
            "users_count": 4,
            "latest_topic_time": "2024-02-01T00:00:00Z",
            "earliest_topic_time": "2024-01-01T00:00:00Z",
            "total_likes": 0,
            "total_comments": 5,
            "total_readings": 9,
        }

    def close(self):
        self.closed = True


class FakeDatabaseInfoDb:
    last_instance = None

    def __init__(self, group_id=None):
        self.group_id = group_id
        self.closed = False
        FakeDatabaseInfoDb.last_instance = self

    def get_database_stats(self):
        return {"topics_count": 12}

    def close(self):
        self.closed = True


class FakeDatabaseInfoFileDb:
    last_instance = None

    def __init__(self, group_id=None):
        self.group_id = group_id
        self.closed = False
        FakeDatabaseInfoFileDb.last_instance = self

    def get_database_stats(self):
        return {"files_count": 7}

    def close(self):
        self.closed = True


class FakeGlobalTopicDb:
    last_instance = None

    def __init__(self, group_id=None):
        self.group_id = group_id
        self.closed = False
        FakeGlobalTopicDb.last_instance = self

    def get_database_stats(self):
        return {"topics_count": 20}

    def get_timestamp_range_info(self):
        return {
            "total_topics": 20,
            "oldest_timestamp": "2024-01-01T00:00:00Z",
            "newest_timestamp": "2024-02-01T00:00:00Z",
            "has_data": True,
        }

    def close(self):
        self.closed = True


class FakeGlobalFileDb:
    last_instance = None

    def __init__(self, group_id=None):
        self.group_id = group_id
        self.closed = False
        FakeGlobalFileDb.last_instance = self

    def get_database_stats(self):
        return {"files_count": 8}

    def close(self):
        self.closed = True


class FakePathManager:
    def get_group_dir(self, group_id):
        return f"C:/tmp/groups/{group_id}"


class GroupReadModelHelperTests(unittest.TestCase):
    def test_empty_database_stats_response_keeps_endpoint_shape(self):
        from backend.services.group_read_model import empty_database_stats_response

        self.assertEqual(
            {
                "configured": False,
                "topic_database": {
                    "stats": {},
                    "timestamp_info": {
                        "total_topics": 0,
                        "oldest_timestamp": "",
                        "newest_timestamp": "",
                        "has_data": False,
                    },
                },
                "file_database": {
                    "stats": {},
                },
            },
            empty_database_stats_response(False),
        )
        self.assertTrue(empty_database_stats_response(True)["configured"])

    def test_group_stats_read_model_uses_storage_summary(self):
        from backend.services import group_read_model

        with patch.object(group_read_model, "ZSXQDatabase", FakeStatsDb):
            result = group_read_model.get_group_stats_read_model(123)

        self.assertEqual(
            {
                "group_id": 123,
                "topics_count": 12,
                "users_count": 4,
                "latest_topic_time": "2024-02-01T00:00:00Z",
                "earliest_topic_time": "2024-01-01T00:00:00Z",
                "total_likes": 0,
                "total_comments": 5,
                "total_readings": 9,
            },
            result,
        )
        self.assertEqual("123", FakeStatsDb.last_instance.group_id)
        self.assertTrue(FakeStatsDb.last_instance.closed)

    def test_group_database_info_read_model_preserves_payload_shape(self):
        from backend.services import group_read_model

        with (
            patch.object(group_read_model, "ZSXQDatabase", FakeDatabaseInfoDb),
            patch.object(group_read_model, "ZSXQFileDatabase", FakeDatabaseInfoFileDb),
            patch.object(group_read_model, "get_db_path_manager", return_value=FakePathManager()),
        ):
            result = group_read_model.get_group_database_info_read_model(123)

        self.assertEqual(
            {
                "group_id": 123,
                "database_info": {
                    "group_id": "123",
                    "schema": "zsxq_core",
                    "group_dir": "C:/tmp/groups/123",
                    "topics": {"topics_count": 12},
                    "files": {"files_count": 7},
                },
            },
            result,
        )
        self.assertEqual("123", FakeDatabaseInfoDb.last_instance.group_id)
        self.assertEqual("123", FakeDatabaseInfoFileDb.last_instance.group_id)
        self.assertTrue(FakeDatabaseInfoDb.last_instance.closed)
        self.assertTrue(FakeDatabaseInfoFileDb.last_instance.closed)

    def test_global_database_stats_read_model_returns_empty_when_unconfigured(self):
        from backend.services import group_read_model

        with patch.object(group_read_model, "is_configured", return_value=False):
            result = group_read_model.get_global_database_stats_read_model()

        self.assertEqual(group_read_model.empty_database_stats_response(False), result)

    def test_global_database_stats_read_model_preserves_aggregated_shape(self):
        from backend.services import group_read_model

        with (
            patch.object(group_read_model, "is_configured", return_value=True),
            patch.object(group_read_model, "ZSXQDatabase", FakeGlobalTopicDb),
            patch.object(group_read_model, "ZSXQFileDatabase", FakeGlobalFileDb),
        ):
            result = group_read_model.get_global_database_stats_read_model()

        self.assertEqual(
            {
                "configured": True,
                "topic_database": {
                    "stats": {"topics_count": 20},
                    "timestamp_info": {
                        "total_topics": 20,
                        "oldest_timestamp": "2024-01-01T00:00:00Z",
                        "newest_timestamp": "2024-02-01T00:00:00Z",
                        "has_data": True,
                    },
                },
                "file_database": {
                    "stats": {"files_count": 8},
                },
            },
            result,
        )
        self.assertIsNone(FakeGlobalTopicDb.last_instance.group_id)
        self.assertIsNone(FakeGlobalFileDb.last_instance.group_id)
        self.assertTrue(FakeGlobalTopicDb.last_instance.closed)
        self.assertTrue(FakeGlobalFileDb.last_instance.closed)
