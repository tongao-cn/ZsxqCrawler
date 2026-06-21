import unittest


class OfficialTopicPageImporterTests(unittest.TestCase):
    def test_import_official_topics_fetches_comments_imports_stats_and_commits(self):
        from backend.services.official_topic_page_importer import import_official_topics

        class FakeConnection:
            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

        class FakeDb:
            def __init__(self):
                self.conn = FakeConnection()

        db = FakeDb()
        client = object()
        topics = [
            {"topic_id": "10", "counts": {"comments": "2"}},
            {"topic_id": 11, "counts": {"comments": 0}},
            {"topic_id": 12},
        ]
        calls = []

        def fetch_comments(_client, topic_id, comments_count, task_id):
            calls.append(("fetch", topic_id, comments_count, task_id))
            return [{"comment_id": f"comment-{topic_id}"}]

        def normalize_topic(topic, group_id, comments=None):
            calls.append(("normalize", topic["topic_id"], group_id, comments))
            return {"topic_id": topic["topic_id"], "group_id": group_id, "comments": comments}

        def import_topic(_db, group_id, topic_data):
            calls.append(("import", group_id, topic_data))
            return {"10": "new", 11: "updated"}.get(topic_data["topic_id"], "error")

        stats = import_official_topics(
            db,
            client,
            "group-1",
            topics,
            "task-1",
            add_task_log=lambda _task_id, _message: None,
            fetch_comments=fetch_comments,
            normalize_topic=normalize_topic,
            import_topic=import_topic,
        )

        self.assertEqual({"new_topics": 1, "updated_topics": 1, "errors": 1}, stats)
        self.assertEqual(1, db.conn.commits)
        self.assertEqual(
            [
                ("fetch", 10, 2, "task-1"),
                ("normalize", "10", "group-1", [{"comment_id": "comment-10"}]),
                (
                    "import",
                    "group-1",
                    {"topic_id": "10", "group_id": "group-1", "comments": [{"comment_id": "comment-10"}]},
                ),
                ("fetch", 11, 0, "task-1"),
                ("normalize", 11, "group-1", None),
                ("import", "group-1", {"topic_id": 11, "group_id": "group-1", "comments": None}),
                ("fetch", 12, 0, "task-1"),
                ("normalize", 12, "group-1", None),
                ("import", "group-1", {"topic_id": 12, "group_id": "group-1", "comments": None}),
            ],
            calls,
        )

    def test_import_official_page_topics_accumulates_page_stats_after_import(self):
        from backend.services.official_topic_page_importer import import_official_page_topics

        total_stats = {"pages": 0, "new_topics": 0, "updated_topics": 0, "errors": 0}
        db = object()
        client = object()
        topics = [{"topic_id": 1}]
        page_stats = {"new_topics": 1, "updated_topics": 2, "errors": 0}
        calls = []

        def import_topics(*args):
            calls.append(("import", args))
            return page_stats

        def add_page_stats(*args):
            calls.append(("add", args))

        result = import_official_page_topics(
            total_stats,
            db,
            client,
            "group-1",
            topics,
            "task-1",
            add_task_log=lambda _task_id, _message: None,
            add_page_stats=add_page_stats,
            import_topics=import_topics,
        )

        self.assertIs(page_stats, result)
        self.assertEqual(
            [
                ("import", (db, client, "group-1", topics, "task-1")),
                ("add", (total_stats, page_stats)),
            ],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
