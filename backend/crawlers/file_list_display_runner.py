"""File-list display runner for ZSXQ files."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from backend.core.console_output import safe_console_print as print
from backend.crawlers.file_list_page import file_list_page
from backend.crawlers.zsxq_file_downloader_helpers import (
    file_list_item_display_lines,
    file_list_next_index_message,
)
from backend.crawlers.zsxq_file_downloader_targets import ShowFileListTarget


class FileListDisplayRuntime(Protocol):
    def fetch_file_list(self, **kwargs: Any) -> Any:
        ...


def print_file_list_page(
    files: list[Dict[str, Any]],
    next_index: Any,
) -> None:
    print(f"\n📋 文件列表 ({len(files)} 个文件):")
    print("=" * 80)

    for i, file_info in enumerate(files, 1):
        for line in file_list_item_display_lines(i, file_info):
            print(line)

    print(file_list_next_index_message(next_index))


def show_file_list(
    runtime: FileListDisplayRuntime,
    target: ShowFileListTarget,
) -> Optional[str]:
    data = runtime.fetch_file_list(count=target.count, index=target.index)
    if not data:
        return None

    page = file_list_page(data)
    print_file_list_page(page.files, page.next_index)

    return page.next_index
