from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.core import crawler_runtime
from backend.services.a_share_analysis_service import normalize_group_id
from backend.storage.task_store import TaskStore


task_store: Optional[TaskStore] = None


def get_task_store() -> TaskStore:
    global task_store
    if task_store is None:
        task_store = TaskStore()
    return task_store

current_tasks: Dict[str, Dict[str, Any]] = {}
task_counter = 0
task_logs: Dict[str, List[str]] = {}
sse_connections: Dict[str, List[Any]] = {}
task_stop_flags: Dict[str, bool] = {}
crawler_instances: Dict[str, Any] = {}
file_downloader_instances: Dict[str, Any] = {}

INGESTION_LOCK_TYPES = {
    "columns_fetch",
    "crawl_all",
    "crawl_historical",
    "crawl_incremental",
    "crawl_latest_until_complete",
    "crawl_time_range",
    "collect_files",
    "download_files",
    "sync_files_from_topics",
}
INGESTION_LOCK_KEY = "ingestion"


def _normalize_task_status(status: str) -> str:
    return "cancelled" if status == "stopped" else status


def _normalize_task(task: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not task:
        return None
    normalized = dict(task)
    normalized["status"] = _normalize_task_status(str(normalized.get("status") or ""))
    return normalized


def list_tasks(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    return [
        normalized
        for normalized in (_normalize_task(task) for task in get_task_store().list_tasks(limit=limit))
        if normalized is not None
    ]


def get_task_state(task_id: str) -> Optional[Dict[str, Any]]:
    return _normalize_task(get_task_store().get_task(task_id) or current_tasks.get(task_id))


def get_task_logs_state(task_id: str) -> Optional[List[str]]:
    task = get_task_state(task_id)
    if not task and task_id not in task_logs:
        return None
    persisted_logs = get_task_store().get_logs(task_id)
    if persisted_logs:
        return persisted_logs
    return task_logs.get(task_id, [])


def cleanup_tasks(keep_latest: int = 100) -> Dict[str, int]:
    keep_latest = max(0, keep_latest)
    store = get_task_store()
    tasks_before = store.list_tasks()
    result = store.cleanup_completed(keep_latest=keep_latest)
    remaining_ids = {task["task_id"] for task in store.list_tasks()}

    for task in tasks_before:
        task_id = task.get("task_id")
        if task_id and task_id not in remaining_ids:
            current_tasks.pop(task_id, None)
            task_logs.pop(task_id, None)
            task_stop_flags.pop(task_id, None)
            sse_connections.pop(task_id, None)

    return result


def create_task(task_type: str, description: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    global task_counter
    if task_counter == 0:
        task_counter = get_task_store().max_task_sequence()
    task_counter += 1
    task_id = f"task_{task_counter}_{int(datetime.now().timestamp())}"
    now = datetime.now()

    current_tasks[task_id] = {
        "task_id": task_id,
        "type": task_type,
        "status": "pending",
        "message": description,
        "result": None,
        "created_at": now,
        "updated_at": now,
    }
    if metadata:
        current_tasks[task_id].update(metadata)

    store = get_task_store()
    store.create_task(
        task_id,
        task_type,
        "pending",
        description,
        result=None,
        metadata=metadata,
        created_at=now,
        updated_at=now,
    )

    task_logs[task_id] = []
    task_stop_flags[task_id] = False
    store.set_stop_flag(task_id, False)
    add_task_log(task_id, f"任务创建: {description}")

    return task_id


def find_running_ingestion_task(group_id: str, exclude_task_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    normalized_group_id = normalize_group_id(group_id)
    if normalized_group_id is None:
        return None

    for task in list_tasks():
        if exclude_task_id and task.get("task_id") == exclude_task_id:
            continue
        if task.get("status") not in {"pending", "running"}:
            continue
        if task.get("ingestion_lock_key") != INGESTION_LOCK_KEY and task.get("type") not in INGESTION_LOCK_TYPES:
            continue
        if normalize_group_id(task.get("group_id")) == normalized_group_id:
            return task
    return None


def create_ingestion_task(task_type: str, description: str, group_id: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    existing = find_running_ingestion_task(group_id)
    if existing:
        return None, existing
    task_id = create_task(
        task_type,
        description,
        metadata={"group_id": str(group_id), "ingestion_lock_key": INGESTION_LOCK_KEY},
    )
    return task_id, None


def add_task_log(task_id: str, log_message: str) -> None:
    if task_id not in task_logs:
        task_logs[task_id] = []

    formatted_log = get_task_store().add_log(task_id, log_message)
    task_logs[task_id].append(formatted_log)
    broadcast_log(task_id, formatted_log)


def broadcast_log(task_id: str, log_message: str) -> None:
    pass


def update_task(
    task_id: str,
    status: str,
    message: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    status = _normalize_task_status(status)
    store = get_task_store()
    if task_id not in current_tasks and store.get_task(task_id) is None:
        return

    now = datetime.now()
    if task_id in current_tasks:
        current_tasks[task_id].update(
            {
                "status": status,
                "message": message,
                "result": result,
                "updated_at": now,
            }
        )

    store.update_task(task_id, status, message, result=result, updated_at=now)
    add_task_log(task_id, f"状态更新: {message}")


def register_task_crawler(task_id: str, crawler: Any) -> None:
    crawler_instances[task_id] = crawler


def unregister_task_crawler(task_id: str) -> None:
    crawler_instances.pop(task_id, None)


def stop_task(task_id: str) -> bool:
    task = get_task_state(task_id)
    if not task:
        return False

    if task["status"] not in ["pending", "running"]:
        return False

    task_stop_flags[task_id] = True
    get_task_store().set_stop_flag(task_id, True)
    add_task_log(task_id, "🛑 收到停止请求，正在停止任务...")

    if task_id in crawler_instances:
        crawler_instances[task_id].set_stop_flag()
    elif crawler_runtime.crawler_instance:
        crawler_runtime.crawler_instance.set_stop_flag()

    if task_id in file_downloader_instances:
        downloader = file_downloader_instances[task_id]
        downloader.set_stop_flag()

    update_task(task_id, "cancelled", "任务已被用户停止")
    return True


def request_runtime_shutdown() -> None:
    stopping_task_ids = [
        task_id
        for task_id, task in list(current_tasks.items())
        if task.get("status") in {"pending", "running"}
    ]

    for task_id in stopping_task_ids:
        task_stop_flags[task_id] = True

    for crawler in list(crawler_instances.values()):
        if hasattr(crawler, "set_stop_flag"):
            crawler.set_stop_flag()

    for downloader in list(file_downloader_instances.values()):
        if hasattr(downloader, "set_stop_flag"):
            downloader.set_stop_flag()

    for task_id, task in list(current_tasks.items()):
        if task.get("status") in {"pending", "running"}:
            get_task_store().set_stop_flag(task_id, True)
            update_task(task_id, "cancelled", "服务关闭，任务已停止")

    crawler_instances.clear()
    file_downloader_instances.clear()
    sse_connections.clear()


def is_task_stopped(task_id: str) -> bool:
    return task_stop_flags.get(task_id, False) or get_task_store().is_stopped(task_id)


def get_latest_task_by_type(
    task_type: str,
    status: Optional[str] = None,
    group_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    normalized_group_id = normalize_group_id(group_id)
    candidates = []
    for task in list_tasks():
        if task.get("type") != task_type:
            continue
        if status and task.get("status") != status:
            continue
        if normalized_group_id is not None and normalize_group_id(task.get("group_id")) != normalized_group_id:
            continue
        candidates.append(task)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.get("created_at") or datetime.min, reverse=True)
    return candidates[0]
