"""File-list API request and response-page contract."""

from __future__ import annotations

from typing import Any, Dict, NamedTuple, Optional, Tuple


class FileListPage(NamedTuple):
    files: Any
    next_index: Any


def file_list_request_params(count: int, sort: str, index: Optional[str]) -> Dict[str, str]:
    params = {
        "count": str(count),
        "sort": sort,
    }
    if index:
        params["index"] = index
    return params


def file_list_page(data: Dict[str, Any]) -> FileListPage:
    resp_data = data.get("resp_data", {})
    return FileListPage(resp_data.get("files", []), resp_data.get("index"))


def file_list_response_page(data: Dict[str, Any]) -> Tuple[Any, Any]:
    page = file_list_page(data)
    return page.files, page.next_index


__all__ = [
    "FileListPage",
    "file_list_page",
    "file_list_request_params",
    "file_list_response_page",
]
