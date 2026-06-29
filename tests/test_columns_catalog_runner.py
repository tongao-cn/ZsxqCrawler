import asyncio
import unittest

from backend.services.columns_fetch_summary import ColumnFetchStats


class ColumnsCatalogRunnerTests(unittest.TestCase):
    def test_process_columns_catalog_aggregates_column_stats_and_request_count(self):
        from backend.services.columns_catalog_runner import process_columns_catalog

        calls = []

        async def process_column(*args):
            calls.append(args)
            return ColumnFetchStats(columns_count=1, details_count=len(calls), request_count=2)

        result = asyncio.run(
            process_columns_catalog(
                task_id="task-1",
                group_id="123",
                columns=[{"column_id": 1}, {"column_id": 2}],
                db=object(),
                headers={"Cookie": "cookie"},
                request_count=3,
                config={"items_per_batch": 10},
                stats=ColumnFetchStats(),
                process_column=process_column,
                is_task_stopped=lambda _task_id: False,
                add_task_log=lambda *_args: None,
            )
        )

        self.assertEqual(2, result.stats.columns_count)
        self.assertEqual(3, result.stats.details_count)
        self.assertEqual(7, result.request_count)
        self.assertEqual([1, 2], [call[3] for call in calls])
        self.assertEqual([2, 2], [call[4] for call in calls])
        self.assertEqual([3, 5], [call[7] for call in calls])

    def test_process_columns_catalog_logs_and_stops_before_next_column(self):
        from backend.services.columns_catalog_runner import process_columns_catalog

        calls = []
        logs = []
        stop_values = iter([False, True])

        async def process_column(*args):
            calls.append(args)
            return ColumnFetchStats(columns_count=1, request_count=1)

        result = asyncio.run(
            process_columns_catalog(
                task_id="task-1",
                group_id="123",
                columns=[{"column_id": 1}, {"column_id": 2}],
                db=object(),
                headers={},
                request_count=0,
                config={},
                stats=ColumnFetchStats(),
                process_column=process_column,
                is_task_stopped=lambda _task_id: next(stop_values),
                add_task_log=lambda *args: logs.append(args),
            )
        )

        self.assertEqual(1, len(calls))
        self.assertEqual(1, result.stats.columns_count)
        self.assertEqual(1, result.request_count)
        self.assertEqual([("task-1", "🛑 任务已被用户停止")], logs)


if __name__ == "__main__":
    unittest.main()
