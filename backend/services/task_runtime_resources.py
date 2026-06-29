from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple


@dataclass(frozen=True)
class TaskRuntimeStopResources:
    crawler: Any
    downloader: Any


@dataclass(frozen=True)
class RuntimeShutdownResourceSnapshot:
    tasks: List[Tuple[str, Dict[str, Any]]]
    crawlers: List[Any]
    file_downloaders: List[Any]


class TaskRuntimeResourceRegistry:
    def __init__(self, crawler_instances: Dict[str, Any], file_downloader_instances: Dict[str, Any]) -> None:
        self._crawler_instances = crawler_instances
        self._file_downloader_instances = file_downloader_instances

    def register_crawler(self, task_id: str, crawler: Any) -> None:
        self._crawler_instances[task_id] = crawler

    def unregister_crawler(self, task_id: str) -> None:
        self._crawler_instances.pop(task_id, None)

    def register_file_downloader(self, task_id: str, downloader: Any) -> None:
        self._file_downloader_instances[task_id] = downloader

    def unregister_file_downloader(self, task_id: str) -> None:
        self._file_downloader_instances.pop(task_id, None)

    def task_crawler(self, task_id: str) -> Any:
        return self._crawler_instances.get(task_id)

    def task_file_downloader(self, task_id: str) -> Any:
        return self._file_downloader_instances.get(task_id)

    def crawlers_snapshot(self) -> List[Any]:
        return list(self._crawler_instances.values())

    def file_downloaders_snapshot(self) -> List[Any]:
        return list(self._file_downloader_instances.values())

    def clear(self) -> None:
        self._crawler_instances.clear()
        self._file_downloader_instances.clear()

    def prepare_task_stop(
        self,
        task_id: str,
        *,
        set_task_stop_flag: Callable[[str, bool], None],
    ) -> TaskRuntimeStopResources:
        set_task_stop_flag(task_id, True)
        return TaskRuntimeStopResources(
            crawler=self.task_crawler(task_id),
            downloader=self.task_file_downloader(task_id),
        )

    def request_stop_for_task(self, resources: TaskRuntimeStopResources, fallback_crawler: Any) -> None:
        if resources.crawler is not None:
            resources.crawler.set_stop_flag()
        elif fallback_crawler:
            fallback_crawler.set_stop_flag()

        if resources.downloader is not None:
            resources.downloader.set_stop_flag()

    def prepare_runtime_shutdown(
        self,
        tasks_snapshot: List[Tuple[str, Dict[str, Any]]],
        *,
        is_active_task_status: Callable[[Any], bool],
        set_task_stop_flag: Callable[[str, bool], None],
    ) -> RuntimeShutdownResourceSnapshot:
        for task_id, task in tasks_snapshot:
            if is_active_task_status(task.get("status")):
                set_task_stop_flag(task_id, True)
        return RuntimeShutdownResourceSnapshot(
            tasks=tasks_snapshot,
            crawlers=self.crawlers_snapshot(),
            file_downloaders=self.file_downloaders_snapshot(),
        )


def request_stop_for_resources(resources: List[Any]) -> None:
    for resource in resources:
        if hasattr(resource, "set_stop_flag"):
            resource.set_stop_flag()
