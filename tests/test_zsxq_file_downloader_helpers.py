import unittest

from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader


class FailingImportFileDb:
    def __init__(self):
        self.cursor = self
        self.conn = self
        self.import_calls = 0
        self.stats_calls = 0

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return (1,)

    def commit(self):
        pass

    def import_file_response(self, data):
        self.import_calls += 1
        raise RuntimeError("stable import failure")

    def get_database_stats(self):
        self.stats_calls += 1
        return {"files": 0}


class FileDownloaderPaginationTests(unittest.TestCase):
    def _downloader_with_failing_import(self):
        downloader = object.__new__(ZSXQFileDownloader)
        downloader.group_id = "group-1"
        downloader.file_db = FailingImportFileDb()
        downloader.logs = []
        downloader.fetch_calls = []
        downloader.log = downloader.logs.append
        downloader.check_stop = lambda: False

        def fetch_file_list(**kwargs):
            downloader.fetch_calls.append(kwargs)
            return {
                "succeeded": True,
                "resp_data": {
                    "index": "next-index",
                    "files": [{"file": {"file_id": 101, "create_time": "2026-02-01T10:00:00.000+0800"}}],
                },
            }

        downloader.fetch_file_list = fetch_file_list
        return downloader

    def test_collect_all_files_stops_when_page_import_fails(self):
        downloader = self._downloader_with_failing_import()

        stats = ZSXQFileDownloader.collect_all_files_to_database(downloader)

        self.assertEqual(1, len(downloader.fetch_calls))
        self.assertEqual(1, downloader.file_db.import_calls)
        self.assertEqual({"total_files": 0, "new_files": 0, "skipped_files": 0}, stats)

    def test_collect_files_by_time_stops_when_page_import_fails(self):
        downloader = self._downloader_with_failing_import()

        stats = ZSXQFileDownloader.collect_files_by_time(downloader)

        self.assertEqual(1, len(downloader.fetch_calls))
        self.assertEqual(1, downloader.file_db.import_calls)
        self.assertEqual(0, stats["files"])


if __name__ == "__main__":
    unittest.main()
