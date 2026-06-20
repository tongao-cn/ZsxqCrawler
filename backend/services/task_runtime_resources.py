from __future__ import annotations

from typing import Any, Dict, List


def register_task_crawler(crawler_instances: Dict[str, Any], task_id: str, crawler: Any) -> None:
    crawler_instances[task_id] = crawler


def unregister_task_crawler(crawler_instances: Dict[str, Any], task_id: str) -> None:
    crawler_instances.pop(task_id, None)


def register_task_file_downloader(
    file_downloader_instances: Dict[str, Any],
    task_id: str,
    downloader: Any,
) -> None:
    file_downloader_instances[task_id] = downloader


def unregister_task_file_downloader(file_downloader_instances: Dict[str, Any], task_id: str) -> None:
    file_downloader_instances.pop(task_id, None)


def task_crawler(crawler_instances: Dict[str, Any], task_id: str) -> Any:
    return crawler_instances.get(task_id)


def task_file_downloader(file_downloader_instances: Dict[str, Any], task_id: str) -> Any:
    return file_downloader_instances.get(task_id)


def runtime_crawlers_snapshot(crawler_instances: Dict[str, Any]) -> List[Any]:
    return list(crawler_instances.values())


def runtime_file_downloaders_snapshot(file_downloader_instances: Dict[str, Any]) -> List[Any]:
    return list(file_downloader_instances.values())


def clear_runtime_resource_tracking(
    crawler_instances: Dict[str, Any],
    file_downloader_instances: Dict[str, Any],
) -> None:
    crawler_instances.clear()
    file_downloader_instances.clear()


def request_stop_for_task_resources(crawler: Any, downloader: Any, fallback_crawler: Any) -> None:
    if crawler is not None:
        crawler.set_stop_flag()
    elif fallback_crawler:
        fallback_crawler.set_stop_flag()

    if downloader is not None:
        downloader.set_stop_flag()


def request_stop_for_resources(resources: List[Any]) -> None:
    for resource in resources:
        if hasattr(resource, "set_stop_flag"):
            resource.set_stop_flag()
