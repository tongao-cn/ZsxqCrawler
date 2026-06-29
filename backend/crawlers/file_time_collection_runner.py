"""Time-ordered file collection runner for ZSXQ file metadata."""

from __future__ import annotations

import datetime
import random
import time
from typing import Any, Dict, NamedTuple, Optional, Protocol

from backend.crawlers.file_database_queries import (
    download_query_group_id,
    latest_file_create_time_query,
)
from backend.crawlers.file_list_page import file_list_page
from backend.crawlers.file_time_window import (
    page_crosses_stop_before,
    summarize_page_time_range,
    time_collection_mode,
    time_dedupe_page_messages,
    time_dedupe_page_plan,
)
from backend.crawlers.zsxq_file_downloader_helpers import (
    add_import_stats,
    empty_import_stats,
    time_collection_database_status_message,
    time_collection_empty_page_message,
    time_collection_exception_message,
    time_collection_fetch_failed_messages,
    time_collection_final_summary,
    time_collection_initial_stop_message,
    time_collection_interrupted_message,
    time_collection_latest_file_time_message,
    time_collection_loop_stop_message,
    time_collection_next_page_plan,
    time_collection_page_files_message,
    time_collection_page_import_messages,
    time_collection_page_message,
    time_collection_page_time_range_message,
    time_collection_start_messages,
    time_collection_stop_before_boundary_message,
    time_collection_storage_failed_message,
    time_collection_summary_messages,
)


class TimeCollectionRuntime(Protocol):
    group_id: Any
    file_db: Any

    def log(self, message: str) -> None:
        ...

    def check_stop(self) -> bool:
        ...

    def fetch_file_list(self, **kwargs: Any) -> Any:
        ...


class TimeCollectionPage(NamedTuple):
    data: Dict[str, Any]
    files: list[Dict[str, Any]]
    next_index: Optional[Any]


class TimeCollectionPageImportResult(NamedTuple):
    should_stop_after_insert: bool


class TimeCollectionLoopContext(NamedTuple):
    sort: str
    enable_time_dedupe: bool
    db_latest_time: Optional[Any]
    total_imported_stats: Dict[str, int]
    stop_before_time: Optional[datetime.datetime]


class TimeCollectionTarget(NamedTuple):
    sort: str
    start_time: Optional[str]
    stop_before_time: Optional[datetime.datetime]
    force_refresh: bool


class TimeCollectionDatabaseState(NamedTuple):
    initial_files: Any
    db_latest_time: Optional[Any]


class LatestFileCreateTimeRow(NamedTuple):
    create_time: Any


def latest_file_create_time_row(row: Any) -> Optional[LatestFileCreateTimeRow]:
    if not row:
        return None
    return LatestFileCreateTimeRow(row[0])


def latest_file_create_time(row: Any) -> Optional[Any]:
    latest_file = latest_file_create_time_row(row)
    if not latest_file:
        return None
    return latest_file.create_time or None


def load_time_collection_latest_file_time(
    runtime: TimeCollectionRuntime,
    enable_time_dedupe: bool,
    initial_files: int,
) -> Optional[Any]:
    if not enable_time_dedupe or initial_files <= 0:
        return None

    query, params = latest_file_create_time_query(download_query_group_id(runtime.group_id))
    runtime.file_db.cursor.execute(query, params)
    result = runtime.file_db.cursor.fetchone()
    db_latest_time = latest_file_create_time(result)
    if db_latest_time:
        runtime.log(time_collection_latest_file_time_message(db_latest_time))
        return db_latest_time

    return None


def load_time_collection_database_state(
    runtime: TimeCollectionRuntime,
    enable_time_dedupe: bool,
) -> TimeCollectionDatabaseState:
    initial_stats = runtime.file_db.get_database_stats()
    initial_files = initial_stats.get("files", 0)
    runtime.log(time_collection_database_status_message(initial_files))
    db_latest_time = load_time_collection_latest_file_time(
        runtime,
        enable_time_dedupe,
        initial_files,
    )
    return TimeCollectionDatabaseState(initial_files, db_latest_time)


def time_collection_dedupe_result(
    should_stop_before_insert: bool = False,
    should_stop_after_insert: bool = False,
) -> Dict[str, bool]:
    return {
        "should_stop_before_insert": should_stop_before_insert,
        "should_stop_after_insert": should_stop_after_insert,
    }


def apply_time_collection_dedupe_plan(
    runtime: TimeCollectionRuntime,
    data: Dict[str, Any],
    files: list[Dict[str, Any]],
    enable_time_dedupe: bool,
    db_latest_time: Optional[Any],
) -> Dict[str, bool]:
    if not enable_time_dedupe or not db_latest_time:
        return time_collection_dedupe_result()

    dedupe_plan = time_dedupe_page_plan(files, db_latest_time)
    for message in time_dedupe_page_messages(dedupe_plan):
        runtime.log(message)

    if dedupe_plan["should_stop_before_insert"]:
        return time_collection_dedupe_result(
            should_stop_before_insert=True,
        )

    if dedupe_plan["should_filter_before_insert"]:
        data["resp_data"]["files"] = dedupe_plan["newer_files"]
        return time_collection_dedupe_result(
            should_stop_after_insert=dedupe_plan["should_stop_after_insert"],
        )

    return time_collection_dedupe_result()


def import_time_collection_page(
    runtime: TimeCollectionRuntime,
    data: Dict[str, Any],
    page_count: int,
    should_stop_after_insert: bool,
    total_imported_stats: Dict[str, int],
) -> bool:
    try:
        page_stats = runtime.file_db.import_file_response(data)
        add_import_stats(total_imported_stats, page_stats)

        for message in time_collection_page_import_messages(
            page_count,
            page_stats,
            should_stop_after_insert,
        ):
            runtime.log(message)
        return True

    except Exception as e:
        runtime.log(time_collection_storage_failed_message(page_count, e))
        return False


def crossed_time_collection_stop_before(
    runtime: TimeCollectionRuntime,
    files: list[Dict[str, Any]],
    stop_before_time: Optional[datetime.datetime],
) -> bool:
    if not stop_before_time:
        return False

    crossed_stop_before, oldest_page_time = page_crosses_stop_before(files, stop_before_time)
    if crossed_stop_before and oldest_page_time:
        runtime.log(time_collection_stop_before_boundary_message(oldest_page_time, stop_before_time))
        return True

    return False


def next_time_collection_index(runtime: TimeCollectionRuntime, next_index: Optional[Any]) -> Optional[Any]:
    next_page = time_collection_next_page_plan(next_index)
    runtime.log(next_page["message"])
    if not next_page["has_next"]:
        return None

    time.sleep(random.uniform(2, 5))
    return next_page["next_index"]


def fetch_time_collection_page(
    runtime: TimeCollectionRuntime,
    page_count: int,
    current_index: Optional[Any],
    sort: str,
) -> Optional[TimeCollectionPage]:
    data = runtime.fetch_file_list(count=20, index=current_index, sort=sort)
    if not data:
        for message in time_collection_fetch_failed_messages(page_count):
            runtime.log(message)
        return None

    page = file_list_page(data)
    if not page.files:
        runtime.log(time_collection_empty_page_message())
        return None

    runtime.log(time_collection_page_files_message(len(page.files)))
    page_oldest, page_newest = summarize_page_time_range(page.files)
    time_range_message = time_collection_page_time_range_message(page_oldest, page_newest)
    if time_range_message:
        runtime.log(time_range_message)

    return TimeCollectionPage(data, page.files, page.next_index)


def next_time_collection_page_after_import(
    runtime: TimeCollectionRuntime,
    page: TimeCollectionPage,
    should_stop_after_insert: bool,
    stop_before_time: Optional[datetime.datetime],
) -> Optional[Any]:
    if should_stop_after_insert:
        return None

    if crossed_time_collection_stop_before(runtime, page.files, stop_before_time):
        return None

    return next_time_collection_index(runtime, page.next_index)


def time_collection_page_import_result(
    runtime: TimeCollectionRuntime,
    page: TimeCollectionPage,
    page_count: int,
    should_stop_after_insert: bool,
    total_imported_stats: Dict[str, int],
) -> Optional[TimeCollectionPageImportResult]:
    if not import_time_collection_page(
        runtime,
        page.data,
        page_count,
        should_stop_after_insert,
        total_imported_stats,
    ):
        return None

    return TimeCollectionPageImportResult(should_stop_after_insert)


def dedupe_and_import_time_collection_page(
    runtime: TimeCollectionRuntime,
    page: TimeCollectionPage,
    page_count: int,
    enable_time_dedupe: bool,
    db_latest_time: Optional[Any],
    total_imported_stats: Dict[str, int],
) -> Optional[TimeCollectionPageImportResult]:
    dedupe_result = apply_time_collection_dedupe_plan(
        runtime,
        page.data,
        page.files,
        enable_time_dedupe,
        db_latest_time,
    )
    if dedupe_result["should_stop_before_insert"]:
        return None
    should_stop_after_insert = dedupe_result["should_stop_after_insert"]

    return time_collection_page_import_result(
        runtime,
        page,
        page_count,
        should_stop_after_insert,
        total_imported_stats,
    )


def collect_time_collection_page(
    runtime: TimeCollectionRuntime,
    page_count: int,
    current_index: Optional[Any],
    context: TimeCollectionLoopContext,
) -> Optional[Any]:
    runtime.log(time_collection_page_message(page_count))

    page = fetch_time_collection_page(runtime, page_count, current_index, context.sort)
    if page is None:
        return None

    import_result = dedupe_and_import_time_collection_page(
        runtime,
        page,
        page_count,
        context.enable_time_dedupe,
        context.db_latest_time,
        context.total_imported_stats,
    )
    if import_result is None:
        return None

    return next_time_collection_page_after_import(
        runtime,
        page,
        import_result.should_stop_after_insert,
        context.stop_before_time,
    )


def should_stop_time_collection_loop(runtime: TimeCollectionRuntime) -> bool:
    if runtime.check_stop():
        runtime.log(time_collection_loop_stop_message())
        return True

    return False


def run_time_collection_loop(
    runtime: TimeCollectionRuntime,
    start_time: Optional[str],
    context: TimeCollectionLoopContext,
) -> int:
    current_index = start_time
    page_count = 0

    try:
        while True:
            if should_stop_time_collection_loop(runtime):
                break

            page_count += 1
            current_index = collect_time_collection_page(
                runtime,
                page_count,
                current_index,
                context,
            )
            if current_index is None:
                break

    except KeyboardInterrupt:
        runtime.log(time_collection_interrupted_message())
    except Exception as e:
        runtime.log(time_collection_exception_message(e))

    return page_count


def finalize_time_collection_result(
    runtime: TimeCollectionRuntime,
    initial_files: int,
    total_imported_stats: Dict[str, int],
    page_count: int,
) -> Dict[str, int]:
    final_stats = runtime.file_db.get_database_stats()
    summary = time_collection_final_summary(
        final_stats,
        initial_files,
        total_imported_stats,
        page_count,
    )

    for message in time_collection_summary_messages(summary, page_count):
        runtime.log(message)

    return summary["result"]


def initialize_time_collection_mode(
    runtime: TimeCollectionRuntime,
    sort: str,
    start_time: Optional[str],
    stop_before_time: Optional[datetime.datetime],
    force_refresh: bool,
) -> bool:
    for message in time_collection_start_messages(sort, start_time, stop_before_time):
        runtime.log(message)

    mode = time_collection_mode(sort, force_refresh, stop_before_time)
    if mode["mode_message"]:
        runtime.log(mode["mode_message"])
    return mode["enable_time_dedupe"]


def should_stop_time_collection_initially(runtime: TimeCollectionRuntime) -> bool:
    if runtime.check_stop():
        runtime.log(time_collection_initial_stop_message())
        return True

    return False


def prepare_time_collection_loop_context(
    sort: str,
    enable_time_dedupe: bool,
    db_latest_time: Optional[Any],
    stop_before_time: Optional[datetime.datetime],
) -> tuple[Dict[str, int], TimeCollectionLoopContext]:
    total_imported_stats = empty_import_stats()
    return total_imported_stats, TimeCollectionLoopContext(
        sort,
        enable_time_dedupe,
        db_latest_time,
        total_imported_stats,
        stop_before_time,
    )


def run_time_collection_after_initial_stop(
    runtime: TimeCollectionRuntime,
    start_time: Optional[str],
    sort: str,
    enable_time_dedupe: bool,
    stop_before_time: Optional[datetime.datetime],
) -> Dict[str, int]:
    database_state = load_time_collection_database_state(
        runtime,
        enable_time_dedupe,
    )

    total_imported_stats, loop_context = prepare_time_collection_loop_context(
        sort,
        enable_time_dedupe,
        database_state.db_latest_time,
        stop_before_time,
    )
    page_count = run_time_collection_loop(
        runtime,
        start_time,
        loop_context,
    )

    return finalize_time_collection_result(
        runtime,
        database_state.initial_files,
        total_imported_stats,
        page_count,
    )


def run_file_time_collection(
    runtime: TimeCollectionRuntime,
    target: TimeCollectionTarget,
) -> Dict[str, int]:
    enable_time_dedupe = initialize_time_collection_mode(
        runtime,
        target.sort,
        target.start_time,
        target.stop_before_time,
        target.force_refresh,
    )

    if should_stop_time_collection_initially(runtime):
        return {"total_files": 0, "new_files": 0}

    return run_time_collection_after_initial_stop(
        runtime,
        target.start_time,
        target.sort,
        enable_time_dedupe,
        target.stop_before_time,
    )


_latest_file_create_time = latest_file_create_time
