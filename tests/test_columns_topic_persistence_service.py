import unittest

from backend.services.columns_topic_persistence_service import (
    extract_topic_data,
    prepare_column_topic,
    save_topic_detail,
)


class FakeColumnsDbWithDetails:
    def __init__(self):
        self.inserted_details = []

    def insert_topic_detail(self, group_id, topic_data, raw_json):
        self.inserted_details.append((group_id, topic_data, raw_json))


class FakeColumnsDbForTopicPrep:
    def __init__(self, exists=False):
        self.exists = exists
        self.inserted_topics = []

    def insert_column_topic(self, column_id, group_id, topic):
        self.inserted_topics.append((column_id, group_id, topic))

    def topic_detail_exists(self, topic_id):
        return self.exists


class ColumnsTopicPersistenceServiceTests(unittest.TestCase):
    def test_extract_topic_data_returns_topic_payload(self):
        topic = {"topic_id": 10, "title": "中文标题"}

        self.assertEqual(topic, extract_topic_data({"resp_data": {"topic": topic}}))
        self.assertIsNone(extract_topic_data({"resp_data": {}}))

    def test_save_topic_detail_inserts_unescaped_json(self):
        db = FakeColumnsDbWithDetails()
        topic_detail = {"succeeded": True, "resp_data": {"topic": {"topic_id": 10, "title": "中文标题"}}}

        saved = save_topic_detail(db=db, group_id="123", topic_detail=topic_detail)

        self.assertTrue(saved)
        self.assertEqual(1, len(db.inserted_details))
        group_id, topic_data, raw_json = db.inserted_details[0]
        self.assertEqual(123, group_id)
        self.assertEqual(topic_detail["resp_data"]["topic"], topic_data)
        self.assertIn("中文标题", raw_json)

    def test_save_topic_detail_returns_false_without_topic_data(self):
        db = FakeColumnsDbWithDetails()

        self.assertFalse(save_topic_detail(db=db, group_id="123", topic_detail={"succeeded": True, "resp_data": {}}))
        self.assertEqual([], db.inserted_details)

    def test_prepare_column_topic_inserts_and_marks_existing_topic_skipped(self):
        db = FakeColumnsDbForTopicPrep(exists=True)
        topic = {"topic_id": 10, "title": "一篇很长的文章标题"}
        logs = []

        topic_id, topic_title, skipped = prepare_column_topic(
            add_task_log=lambda task_id, message: logs.append((task_id, message)),
            column_id=3,
            db=db,
            group_id="123",
            incremental_mode=True,
            task_id="task-1",
            topic=topic,
            topic_idx=1,
            total_topics=2,
        )

        self.assertEqual(10, topic_id)
        self.assertEqual("一篇很长的文章标题", topic_title)
        self.assertTrue(skipped)
        self.assertEqual([(3, 123, topic)], db.inserted_topics)
        self.assertEqual([("task-1", "   📄 [1/2] 一篇很长的文章标题... ⏭️ 跳过（已存在）")], logs)


if __name__ == "__main__":
    unittest.main()
