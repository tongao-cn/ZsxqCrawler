import unittest


class ColumnsFetchSummaryTests(unittest.TestCase):
    def test_column_fetch_stats_adds_counts(self):
        from backend.services.columns_fetch_summary import ColumnFetchStats, combined_column_stats

        first = ColumnFetchStats(details_count=1, files_count=2, request_count=3)
        second = ColumnFetchStats(details_count=4, videos_count=5, request_count=6)

        combined = combined_column_stats(first, second)

        self.assertEqual(5, combined.details_count)
        self.assertEqual(2, combined.files_count)
        self.assertEqual(5, combined.videos_count)
        self.assertEqual(9, combined.request_count)

    def test_build_columns_fetch_result_includes_skip_summary(self):
        from backend.services.columns_fetch_summary import build_columns_fetch_result

        message, payload = build_columns_fetch_result(2, 5, 4, 3, 6, 1, 7, 8, 9)

        self.assertEqual("采集完成: 2 个专栏, 4 篇新文章, 3 个文件, 1 个视频, 跳过 7 篇已存在文章", message)
        self.assertEqual(
            {
                "columns_count": 2,
                "topics_count": 5,
                "details_count": 4,
                "files_count": 3,
                "images_count": 6,
                "videos_count": 1,
                "skipped_count": 7,
                "files_skipped": 8,
                "videos_skipped": 9,
            },
            payload,
        )

    def test_build_columns_progress_message(self):
        from backend.services.columns_fetch_summary import build_columns_progress_message

        self.assertEqual(
            "进度: 4 篇文章, 3 个文件, 2 个视频, 1 张图片",
            build_columns_progress_message(4, 3, 2, 1),
        )


if __name__ == "__main__":
    unittest.main()
