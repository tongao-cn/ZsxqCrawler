"""Plain file collection runner for ZSXQ file metadata."""

from __future__ import annotations

import datetime
import random
import time
from typing import Any, Dict, Optional, Protocol

from backend.core.console_output import safe_console_print as print
from backend.crawlers.file_list_page import file_list_page
from backend.crawlers.zsxq_file_downloader_helpers import (
    add_file_collection_page_stats,
    file_collection_completion_messages,
    file_collection_empty_page_message,
    file_collection_exception_message,
    file_collection_fetch_failed_messages,
    file_collection_interrupted_message,
    file_collection_log_insert_query,
    file_collection_log_update_query,
    file_collection_next_page_plan,
    file_collection_page_files_message,
    file_collection_page_import_messages,
    file_collection_page_message,
    file_collection_page_stored_message,
    file_collection_start_message,
    file_collection_stats,
    file_collection_storage_failed_message,
)
from backend.crawlers.zsxq_file_downloader_targets import (
    FileCollectionLogRow,
    FileCollectionPage,
    FileCollectionTarget,
)


class FileCollectionRuntime(Protocol):
    file_db: Any

    def fetch_file_list(self, **kwargs: Any) -> Any:
        ...


def file_collection_log_row(row: Any) -> Optional[FileCollectionLogRow]:
    if not row:
        return None
    return FileCollectionLogRow(row[0])


def file_collection_log_id(row: Any) -> Optional[Any]:
    collection_log = file_collection_log_row(row)
    if not collection_log:
        return None
    return collection_log.log_id


def import_file_collection_page(
    runtime: FileCollectionRuntime,
    data: Dict[str, Any],
    file_count: int,
    page_count: int,
    stats: Dict[str, int],
) -> bool:
    try:
        page_stats = runtime.file_db.import_file_response(data)

        add_file_collection_page_stats(stats, file_count, page_stats)

        for message in file_collection_page_import_messages(page_stats):
            print(message)

    except Exception as e:
        print(file_collection_storage_failed_message(page_count, e))
        return False

    print(file_collection_page_stored_message(page_count))
    return True


def next_file_collection_index(next_index: Any) -> Optional[Any]:
    next_page = file_collection_next_page_plan(next_index)
    if not next_page["has_next"]:
        return None

    time.sleep(random.uniform(next_page["delay_min"], next_page["delay_max"]))
    return next_page["next_index"]


def fetch_file_collection_page(
    runtime: FileCollectionRuntime,
    page_count: int,
    current_index: Optional[Any],
) -> Optional[FileCollectionPage]:
    data = runtime.fetch_file_list(count=20, index=current_index)
    if not data:
        for message in file_collection_fetch_failed_messages(page_count):
            print(message)
        return None

    page = file_list_page(data)
    if not page.files:
        print(file_collection_empty_page_message())
        return None

    print(file_collection_page_files_message(len(page.files)))
    return FileCollectionPage(data, page.files, page.next_index)


def run_file_collection_page(
    runtime: FileCollectionRuntime,
    page_count: int,
    current_index: Optional[Any],
    stats: Dict[str, int],
) -> Optional[Any]:
    page = fetch_file_collection_page(runtime, page_count, current_index)
    if page is None:
        return None

    if not import_file_collection_page(
        runtime,
        page.data,
        len(page.files),
        page_count,
        stats,
    ):
        return None

    return next_file_collection_index(page.next_index)


def run_file_collection_loop(runtime: FileCollectionRuntime, stats: Dict[str, int]) -> int:
    current_index = None
    page_count = 0

    try:
        while True:
            page_count += 1
            print(file_collection_page_message(page_count))

            current_index = run_file_collection_page(
                runtime,
                page_count,
                current_index,
                stats,
            )
            if current_index is None:
                break

    except KeyboardInterrupt:
        print(file_collection_interrupted_message())
    except Exception as e:
        print(file_collection_exception_message(e))

    return page_count


def create_file_collection_log(runtime: FileCollectionRuntime) -> Optional[Any]:
    insert_query, insert_params = file_collection_log_insert_query(
        datetime.datetime.now().isoformat()
    )
    runtime.file_db.cursor.execute(insert_query, insert_params)
    row = runtime.file_db.cursor.fetchone()
    log_id = file_collection_log_id(row)
    runtime.file_db.conn.commit()
    return log_id


def update_file_collection_log(
    runtime: FileCollectionRuntime,
    stats: Dict[str, int],
    log_id: Optional[Any],
) -> None:
    update_query, update_params = file_collection_log_update_query(
        datetime.datetime.now().isoformat(),
        stats,
        log_id,
    )
    runtime.file_db.cursor.execute(update_query, update_params)
    runtime.file_db.conn.commit()


def collect_all_files_to_database(
    runtime: FileCollectionRuntime,
    target: FileCollectionTarget,
) -> Dict[str, int]:
    print(file_collection_start_message())

    log_id = create_file_collection_log(runtime)

    stats = file_collection_stats()
    page_count = run_file_collection_loop(runtime, stats)

    update_file_collection_log(runtime, stats, log_id)

    for message in file_collection_completion_messages(stats, page_count):
        print(message)

    return stats
