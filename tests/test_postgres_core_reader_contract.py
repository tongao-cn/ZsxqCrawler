import unittest

from backend.storage.postgres_core_reader_contract import (
    READER_PROBE_TABLE,
    STATUS_REPORT_CORE_TABLES,
    SUPPORTED_READER_TABLES,
    reader_probe_table_name,
    status_report_table_names,
    supported_reader_table_names,
)


class PostgresCoreReaderContractTests(unittest.TestCase):
    def test_reader_contract_keeps_supported_tables_and_probe_explicit(self):
        self.assertEqual(SUPPORTED_READER_TABLES, supported_reader_table_names())
        self.assertEqual(STATUS_REPORT_CORE_TABLES, status_report_table_names())
        self.assertEqual(READER_PROBE_TABLE, reader_probe_table_name())
        self.assertIn(reader_probe_table_name(), supported_reader_table_names())


if __name__ == "__main__":
    unittest.main()
