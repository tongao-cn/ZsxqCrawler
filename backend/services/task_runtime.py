from __future__ import annotations

import asyncio
import inspect
import threading
import queue
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from backend.core import crawler_runtime
from backend.services.a_share_analysis_service import normalize_group_id
from backend.storage.task_store import TaskStore


task_store: Optional[TaskStore] = None
TASK_LOCK_LEASE_MINUTES = 30
TASK_LOCK_HEARTBEAT_SECONDS = 60
_state_lock = threading.RLock()
ACTIVE_TASK_STATUSES = {"pending", "running"}
RUNTIME_TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}


def get_task_store() -> TaskStore:
    global task_store
    with _state_lock:
        if task_store is None:
            task_store = TaskStore()
        return task_store


def _allocate_task_id_locked(now: datetime) -> str:
    global task_counter
    if task_counter == 0:
        task_counter = get_task_store().max_task_sequence()
    task_counter += 1
    return f"task_{task_counter}_{int(now.timestamp())}"


current_tasks: Dict[str, Dict[str, Any]] = {}
task_counter = 0
task_logs: Dict[str, List[str]] = {}
sse_connections: Dict[str, List[queue.Queue[str]]] = {}
task_stop_flags: Dict[str, bool] = {}
crawler_instances: Dict[str, Any] = {}
file_downloader_instances: Dict[str, Any] = {}
runtime_task_threads: Dict[str, threading.Thread] = {}
runtime_task_heartbeats: Dict[str, threading.Event] = {}

INGESTION_LOCK_TYPES = {
    "columns_fetch",
    "crawl_all",
    "crawl_historical",
    "crawl_incremental",
    "crawl_latest_until_complete",
    "crawl_time_range",
    "collect_files",
    "download_files",
    "download_filtered_files",
    "download_selected_files",
    "download_single_file",
    "sync_files_from_topics",
}
INGESTION_LOCK_KEY = "ingestion"


def _initialize_task_tracking_locked(task_id: str) -> None:
    task_logs[task_id] = []
    _set_task_stop_flag_locked(task_id, False)


def _set_task_stop_flag_locked(task_id: str, stopped: bool) -> None:
    task_stop_flags[task_id] = stopped


def _persist_task_creation_tracking(task_id: str, description: str, store: Optional[TaskStore] = None) -> None:
    (store or get_task_store()).set_stop_flag(task_id, False)
    add_task_log(task_id, f"任务创建: {description}")


def _forget_task_tracking_locked(task_id: str) -> None:
    current_tasks.pop(task_id, None)
    task_logs.pop(task_id, None)
    task_stop_flags.pop(task_id, None)
    sse_connections.pop(task_id, None)


def _build_pending_task_state(
    task_id: str,
    task_type: str,
    description: str,
    now: datetime,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    task = {
        "task_id": task_id,
        "type": task_type,
        "status": "pending",
        "message": description,
        "result": None,
        "created_at": now,
        "updated_at": now,
    }
    if metadata:
        task.update(metadata)
    return task


def _normalize_task_status(status: str) -> str:
    return "cancelled" if status == "stopped" else status


def _is_active_task_status(status: Any) -> bool:
    return status in ACTIVE_TASK_STATUSES


def _is_runtime_terminal_status(status: Any) -> bool:
    return _normalize_task_status(str(status or "")) in RUNTIME_TERMINAL_TASK_STATUSES


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


def _memory_task_state_locked(task_id: str) -> Optional[Dict[str, Any]]:
    return current_tasks.get(task_id)


def _set_memory_task_locked(task_id: str, task: Dict[str, Any]) -> None:
    current_tasks[task_id] = task


def _set_pending_memory_task_locked(
    task_id: str,
    task_type: str,
    description: str,
    now: datetime,
    metadata: Optional[Dict[str, Any]] = None,
    task: Optional[Dict[str, Any]] = None,
) -> None:
    _set_memory_task_locked(
        task_id,
        task or _build_pending_task_state(
            task_id,
            task_type,
            description,
            now,
            metadata,
        ),
    )


def _memory_tasks_snapshot_locked() -> List[tuple[str, Dict[str, Any]]]:
    return list(current_tasks.items())


def get_task_state(task_id: str) -> Optional[Dict[str, Any]]:
    task = get_task_store().get_task(task_id)
    if not task:
        with _state_lock:
            task = _memory_task_state_locked(task_id)
    return _normalize_task(task)


def _has_task_logs_locked(task_id: str) -> bool:
    return task_id in task_logs


def _task_logs_copy_locked(task_id: str) -> List[str]:
    return list(task_logs.get(task_id, []))


def get_task_logs_state(task_id: str) -> Optional[List[str]]:
    task = get_task_state(task_id)
    with _state_lock:
        has_memory_logs = _has_task_logs_locked(task_id)
    if not task and not has_memory_logs:
        return None
    persisted_logs = get_task_store().get_logs(task_id)
    if persisted_logs:
        return persisted_logs
    with _state_lock:
        return _task_logs_copy_locked(task_id)


def cleanup_tasks(keep_latest: int = 100) -> Dict[str, int]:
    keep_latest = max(0, keep_latest)
    store = get_task_store()
    tasks_before = store.list_tasks()
    result = store.cleanup_completed(keep_latest=keep_latest)
    remaining_ids = {task["task_id"] for task in store.list_tasks()}

    for task in tasks_before:
        task_id = task.get("task_id")
        if task_id and task_id not in remaining_ids:
            with _state_lock:
                _forget_task_tracking_locked(task_id)

    return result


def create_task(task_type: str, description: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    now = datetime.now()
    with _state_lock:
        task_id = _allocate_task_id_locked(now)
        _set_pending_memory_task_locked(
            task_id,
            task_type,
            description,
            now,
            metadata,
        )

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

    with _state_lock:
        _initialize_task_tracking_locked(task_id)
    _persist_task_creation_tracking(task_id, description, store)

    return task_id


def _has_ingestion_lock_identity(task: Dict[str, Any]) -> bool:
    return task.get("ingestion_lock_key") == INGESTION_LOCK_KEY or task.get("type") in INGESTION_LOCK_TYPES


def _matches_running_ingestion_task(task: Dict[str, Any], normalized_group_id: str) -> bool:
    if not _is_active_task_status(task.get("status")):
        return False
    if not _has_ingestion_lock_identity(task):
        return False
    return normalize_group_id(task.get("group_id")) == normalized_group_id


def find_running_ingestion_task(group_id: str, exclude_task_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    normalized_group_id = normalize_group_id(group_id)
    if normalized_group_id is None:
        return None

    for task in list_tasks():
        if exclude_task_id and task.get("task_id") == exclude_task_id:
            continue
        if _matches_running_ingestion_task(task, normalized_group_id):
            return task
    return None


def create_ingestion_task(task_type: str, description: str, group_id: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    now = datetime.now()
    with _state_lock:
        task_id = _allocate_task_id_locked(now)
    metadata = {"group_id": str(group_id), "ingestion_lock_key": INGESTION_LOCK_KEY}
    task, existing = get_task_store().create_task_with_lock(
        task_id,
        task_type,
        description,
        str(group_id),
        INGESTION_LOCK_KEY,
        metadata=metadata,
        lease_minutes=TASK_LOCK_LEASE_MINUTES,
        created_at=now,
    )
    if existing:
        return None, _normalize_task(existing)
    with _state_lock:
        _set_pending_memory_task_locked(
            task_id,
            task_type,
            description,
            now,
            metadata,
            task=task,
        )
        _initialize_task_tracking_locked(task_id)
    _persist_task_creation_tracking(task_id, description)
    return task_id, None


def _append_task_log_locked(task_id: str, formatted_log: str) -> None:
    if task_id not in task_logs:
        task_logs[task_id] = []
    task_logs[task_id].append(formatted_log)


def add_task_log(task_id: str, log_message: str) -> None:
    formatted_log = get_task_store().add_log(task_id, log_message)
    with _state_lock:
        _append_task_log_locked(task_id, formatted_log)
    broadcast_log(task_id, formatted_log)


def _add_task_log_subscriber_locked(task_id: str, subscriber: queue.Queue[str]) -> None:
    sse_connections.setdefault(task_id, []).append(subscriber)


def _remove_task_log_subscriber_locked(task_id: str, subscriber: queue.Queue[str]) -> None:
    subscribers = sse_connections.get(task_id)
    if not subscribers:
        return
    try:
        subscribers.remove(subscriber)
    except ValueError:
        return
    if not subscribers:
        sse_connections.pop(task_id, None)


def subscribe_task_logs(task_id: str) -> queue.Queue[str]:
    subscriber: queue.Queue[str] = queue.Queue()
    with _state_lock:
        _add_task_log_subscriber_locked(task_id, subscriber)
    return subscriber


def unsubscribe_task_logs(task_id: str, subscriber: queue.Queue[str]) -> None:
    with _state_lock:
        _remove_task_log_subscriber_locked(task_id, subscriber)


def _task_log_subscribers_snapshot_locked(task_id: str) -> List[queue.Queue[str]]:
    return list(sse_connections.get(task_id, []))


def broadcast_log(task_id: str, log_message: str) -> None:
    with _state_lock:
        subscribers = _task_log_subscribers_snapshot_locked(task_id)
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(log_message)
        except Exception:
            pass


def _has_memory_task_locked(task_id: str) -> bool:
    return task_id in current_tasks


def _update_memory_task_locked(
    task_id: str,
    status: str,
    message: str,
    result: Optional[Dict[str, Any]],
    updated_at: datetime,
) -> None:
    if task_id in current_tasks:
        current_tasks[task_id].update(
            {
                "status": status,
                "message": message,
                "result": result,
                "updated_at": updated_at,
            }
        )


def _should_apply_task_update(
    existing_task: Optional[Dict[str, Any]],
    has_memory_task: bool,
    status: str,
) -> bool:
    if not has_memory_task and existing_task is None:
        return False
    if existing_task and existing_task.get("status") == "cancelled" and status != "cancelled":
        return False
    return True


def update_task(
    task_id: str,
    status: str,
    message: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    status = _normalize_task_status(status)
    store = get_task_store()
    existing_task = get_task_state(task_id)
    with _state_lock:
        has_memory_task = _has_memory_task_locked(task_id)
    if not _should_apply_task_update(existing_task, has_memory_task, status):
        return

    now = datetime.now()
    with _state_lock:
        _update_memory_task_locked(task_id, status, message, result, now)

    store.update_task(task_id, status, message, result=result, updated_at=now)
    add_task_log(task_id, f"状态更新: {message}")
    _release_task_lock_on_terminal_status(task_id, status, now, store)


def _release_task_lock_on_terminal_status(
    task_id: str,
    status: str,
    released_at: datetime,
    store: TaskStore,
) -> None:
    if not _is_runtime_terminal_status(status):
        return
    try:
        store.release_task_lock(task_id, status, released_at=released_at)
    except Exception as exc:
        add_task_log(task_id, f"⚠️ 释放任务锁失败: {exc}")


def _register_task_crawler_locked(task_id: str, crawler: Any) -> None:
    crawler_instances[task_id] = crawler


def _unregister_task_crawler_locked(task_id: str) -> None:
    crawler_instances.pop(task_id, None)


def _task_crawler_locked(task_id: str) -> Any:
    return crawler_instances.get(task_id)


def _task_file_downloader_locked(task_id: str) -> Any:
    return file_downloader_instances.get(task_id)


def _runtime_crawlers_snapshot_locked() -> List[Any]:
    return list(crawler_instances.values())


def _runtime_file_downloaders_snapshot_locked() -> List[Any]:
    return list(file_downloader_instances.values())


def _clear_runtime_resource_tracking_locked() -> None:
    crawler_instances.clear()
    file_downloader_instances.clear()


def register_task_crawler(task_id: str, crawler: Any) -> None:
    with _state_lock:
        _register_task_crawler_locked(task_id, crawler)


def unregister_task_crawler(task_id: str) -> None:
    with _state_lock:
        _unregister_task_crawler_locked(task_id)


def _prepare_task_stop_resources_locked(task_id: str) -> tuple[Any, Any]:
    _set_task_stop_flag_locked(task_id, True)
    return _task_crawler_locked(task_id), _task_file_downloader_locked(task_id)


def stop_task(task_id: str) -> bool:
    task = get_task_state(task_id)
    if not task:
        return False

    if not _is_active_task_status(task["status"]):
        return False

    with _state_lock:
        crawler, downloader = _prepare_task_stop_resources_locked(task_id)
    get_task_store().set_stop_flag(task_id, True)
    add_task_log(task_id, "🛑 收到停止请求，正在停止任务...")

    _request_stop_for_task_resources(crawler, downloader)

    update_task(task_id, "cancelled", "任务已被用户停止")
    return True


def _request_stop_for_task_resources(crawler: Any, downloader: Any) -> None:
    if crawler is not None:
        crawler.set_stop_flag()
    elif crawler_runtime.crawler_instance:
        crawler_runtime.crawler_instance.set_stop_flag()

    if downloader is not None:
        downloader.set_stop_flag()


def _register_task_lock_heartbeat_locked(task_id: str, stop_event: threading.Event) -> None:
    runtime_task_heartbeats[task_id] = stop_event


def _pop_task_lock_heartbeat_locked(task_id: str) -> Optional[threading.Event]:
    return runtime_task_heartbeats.pop(task_id, None)


def _task_lock_heartbeat_ids_locked() -> List[str]:
    return list(runtime_task_heartbeats)


def _start_task_lock_heartbeat(task_id: str) -> None:
    task = get_task_state(task_id)
    if not task or task.get("ingestion_lock_key") != INGESTION_LOCK_KEY:
        return
    stop_event = threading.Event()
    with _state_lock:
        _register_task_lock_heartbeat_locked(task_id, stop_event)

    def heartbeat() -> None:
        while not stop_event.wait(TASK_LOCK_HEARTBEAT_SECONDS):
            try:
                get_task_store().heartbeat_task_lock(task_id, lease_minutes=TASK_LOCK_LEASE_MINUTES)
            except Exception:
                pass

    thread = threading.Thread(
        target=heartbeat,
        name=f"zsxq-lock-heartbeat-{task_id}",
        daemon=True,
    )
    thread.start()


def _stop_task_lock_heartbeat(task_id: str) -> None:
    with _state_lock:
        stop_event = _pop_task_lock_heartbeat_locked(task_id)
    if stop_event:
        stop_event.set()


def _request_stop_for_resources(resources: List[Any]) -> None:
    for resource in resources:
        if hasattr(resource, "set_stop_flag"):
            resource.set_stop_flag()


def _register_runtime_task_thread_locked(task_id: str, thread: threading.Thread) -> None:
    runtime_task_threads[task_id] = thread


def _forget_runtime_task_thread_locked(task_id: str) -> None:
    runtime_task_threads.pop(task_id, None)


def _clear_runtime_task_threads_locked() -> None:
    runtime_task_threads.clear()


def _run_runtime_task(
    task_func: Callable[..., Any],
    task_id: str,
    task_args: tuple[Any, ...],
) -> None:
    try:
        _start_task_lock_heartbeat(task_id)
        result = task_func(task_id, *task_args)
        if inspect.isawaitable(result):
            asyncio.run(result)
    finally:
        _stop_task_lock_heartbeat(task_id)
        with _state_lock:
            _forget_runtime_task_thread_locked(task_id)


def enqueue_runtime_task(task_func: Callable[..., Any], task_id: str, *args: Any) -> None:
    thread = threading.Thread(
        target=_run_runtime_task,
        args=(task_func, task_id, args),
        name=f"zsxq-task-{task_id}",
        daemon=True,
    )
    with _state_lock:
        _register_runtime_task_thread_locked(task_id, thread)
    thread.start()


def _prepare_runtime_shutdown_snapshot_locked() -> tuple[List[tuple[str, Dict[str, Any]]], List[Any], List[Any]]:
    tasks_snapshot = _memory_tasks_snapshot_locked()
    stopping_task_ids = [
        task_id
        for task_id, task in tasks_snapshot
        if _is_active_task_status(task.get("status"))
    ]
    for task_id in stopping_task_ids:
        _set_task_stop_flag_locked(task_id, True)
    return tasks_snapshot, _runtime_crawlers_snapshot_locked(), _runtime_file_downloaders_snapshot_locked()


def _clear_runtime_shutdown_tracking_locked() -> List[str]:
    _clear_runtime_resource_tracking_locked()
    sse_connections.clear()
    return _task_lock_heartbeat_ids_locked()


def _cancel_active_runtime_tasks(tasks_snapshot: List[tuple[str, Dict[str, Any]]]) -> None:
    for task_id, task in tasks_snapshot:
        if _is_active_task_status(task.get("status")):
            get_task_store().set_stop_flag(task_id, True)
            update_task(task_id, "cancelled", "服务关闭，任务已停止")


def request_runtime_shutdown() -> None:
    with _state_lock:
        tasks_snapshot, crawler_snapshot, downloader_snapshot = _prepare_runtime_shutdown_snapshot_locked()

    _request_stop_for_resources(crawler_snapshot)
    _request_stop_for_resources(downloader_snapshot)
    _cancel_active_runtime_tasks(tasks_snapshot)

    with _state_lock:
        heartbeat_task_ids = _clear_runtime_shutdown_tracking_locked()
    for task_id in heartbeat_task_ids:
        _stop_task_lock_heartbeat(task_id)
    with _state_lock:
        _clear_runtime_task_threads_locked()


def _task_stop_flag_locked(task_id: str) -> bool:
    return task_stop_flags.get(task_id, False)


def is_task_stopped(task_id: str) -> bool:
    with _state_lock:
        memory_stopped = _task_stop_flag_locked(task_id)
    return memory_stopped or get_task_store().is_stopped(task_id)


def _matches_latest_task_query(
    task: Dict[str, Any],
    task_type: str,
    status: Optional[str],
    normalized_group_id: Optional[str],
) -> bool:
    if task.get("type") != task_type:
        return False
    if status and task.get("status") != status:
        return False
    if normalized_group_id is not None and normalize_group_id(task.get("group_id")) != normalized_group_id:
        return False
    return True


def _task_created_at_sort_value(task: Dict[str, Any]) -> Any:
    return task.get("created_at") or datetime.min


def get_latest_task_by_type(
    task_type: str,
    status: Optional[str] = None,
    group_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    normalized_group_id = normalize_group_id(group_id)
    candidates = [
        task
        for task in list_tasks()
        if _matches_latest_task_query(task, task_type, status, normalized_group_id)
    ]
    if not candidates:
        return None
    candidates.sort(key=_task_created_at_sort_value, reverse=True)
    return candidates[0]
