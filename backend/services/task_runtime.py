from __future__ import annotations

import threading
import queue
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from backend.core import crawler_runtime
from backend.core.group_identity import normalize_group_id
from backend.services.task_runtime_memory import (
    should_apply_task_update,
)
from backend.services.task_runtime_executor import (
    enqueue_runtime_task as _executor_enqueue_runtime_task,
    run_runtime_task as _executor_run_runtime_task,
    start_task_lock_heartbeat as _executor_start_task_lock_heartbeat,
    stop_task_lock_heartbeat as _executor_stop_task_lock_heartbeat,
)
from backend.services.task_runtime_resources import (
    clear_runtime_resource_tracking,
    register_task_crawler as _register_resource_crawler,
    register_task_file_downloader as _register_resource_file_downloader,
    request_stop_for_resources,
    request_stop_for_task_resources,
    runtime_crawlers_snapshot,
    runtime_file_downloaders_snapshot,
    task_crawler,
    task_file_downloader,
    unregister_task_crawler as _unregister_resource_crawler,
    unregister_task_file_downloader as _unregister_resource_file_downloader,
)
from backend.services.task_runtime_status import (
    INGESTION_LOCK_KEY,
    INGESTION_LOCK_TYPES,  # noqa: F401 - compatibility re-export for task runtime callers
    TaskQuery,
    _is_active_task_status,
    _is_runtime_terminal_status,  # noqa: F401 - compatibility re-export for task runtime callers
    _matches_running_ingestion_task,
    _normalize_task,
    _normalize_task_status,
    is_terminal_task_status,
    latest_task_for_query,
    query_tasks,
)
from backend.services.task_runtime_state import create_task_runtime_state_bundle
from backend.services.task_transition_recorder import (
    record_task_transition,
    release_task_lock_on_terminal_status,
)
from backend.services.task_workflow_lifecycle import (
    WorkflowCompletedMessage,
    WorkflowCompletedHook,
    WorkflowCompletionDecision,  # noqa: F401 - compatibility re-export for task runtime callers
    WorkflowRunningMessage,
    complete_task_unless_stopped as _complete_task_unless_stopped,
    fail_task_with_message_unless_stopped as _fail_task_with_message_unless_stopped,
    fail_task_unless_stopped as _fail_task_unless_stopped,
    finish_workflow,  # noqa: F401 - compatibility re-export for task runtime callers
    run_workflow_lifecycle,
    skip_workflow_completion,  # noqa: F401 - compatibility re-export for task runtime callers
)
from backend.services.workflow_registry import get_workflow_spec
from backend.storage.task_store import TaskStore


task_store: Optional[TaskStore] = None
TASK_LOCK_LEASE_MINUTES = 30
TASK_LOCK_HEARTBEAT_SECONDS = 60
_state_lock = threading.RLock()
_GROUP_FILTER_UNSET = object()


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


_runtime_state_bundle = create_task_runtime_state_bundle()
current_tasks: Dict[str, Dict[str, Any]] = _runtime_state_bundle.current_tasks
task_counter = 0
task_logs: Dict[str, List[str]] = _runtime_state_bundle.task_logs
sse_connections: Dict[str, List[queue.Queue[str]]] = _runtime_state_bundle.sse_connections
task_stop_flags: Dict[str, bool] = _runtime_state_bundle.task_stop_flags
crawler_instances: Dict[str, Any] = {}
file_downloader_instances: Dict[str, Any] = {}
runtime_task_threads: Dict[str, threading.Thread] = _runtime_state_bundle.runtime_task_threads
runtime_task_heartbeats: Dict[str, threading.Event] = _runtime_state_bundle.runtime_task_heartbeats
_runtime_state = _runtime_state_bundle.state


def _initialize_task_tracking_locked(task_id: str) -> None:
    _runtime_state.initialize_task(task_id)


def _set_task_stop_flag_locked(task_id: str, stopped: bool) -> None:
    _runtime_state.set_task_stop_flag(task_id, stopped)


def _persist_task_creation_tracking(task_id: str, description: str, store: Optional[TaskStore] = None) -> None:
    (store or get_task_store()).set_stop_flag(task_id, False)
    add_task_log(task_id, f"任务创建: {description}")


def _forget_task_tracking_locked(task_id: str) -> None:
    _runtime_state.forget_task(task_id)


def list_tasks(
    limit: Optional[int] = None,
    group_id: Any = _GROUP_FILTER_UNSET,
    task_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    group_filter_provided = group_id is not _GROUP_FILTER_UNSET
    query = TaskQuery(
        task_type=task_type,
        group_id=group_id if group_filter_provided else None,
        group_filter_provided=group_filter_provided,
        limit=limit,
    )
    store_limit = None if query.has_filter else limit
    return query_tasks(get_task_store().list_tasks(limit=store_limit), query)


def _memory_task_state_locked(task_id: str) -> Optional[Dict[str, Any]]:
    return _runtime_state.memory_task_state(task_id)


def _set_pending_memory_task_locked(
    task_id: str,
    task_type: str,
    description: str,
    now: datetime,
    metadata: Optional[Dict[str, Any]] = None,
    task: Optional[Dict[str, Any]] = None,
) -> None:
    _runtime_state.set_pending_memory_task(
        task_id,
        task_type,
        description,
        now,
        metadata,
        task,
    )


def _memory_tasks_snapshot_locked() -> List[tuple[str, Dict[str, Any]]]:
    return _runtime_state.memory_tasks_snapshot()


def get_task_state(task_id: str) -> Optional[Dict[str, Any]]:
    task = get_task_store().get_task(task_id)
    if not task:
        with _state_lock:
            task = _memory_task_state_locked(task_id)
    return _normalize_task(task)


def _has_task_logs_locked(task_id: str) -> bool:
    return _runtime_state.has_task_logs(task_id)


def _task_logs_copy_locked(task_id: str) -> List[str]:
    return _runtime_state.task_logs_copy(task_id)


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
    _runtime_state.append_task_log(task_id, formatted_log)


def add_task_log(task_id: str, log_message: str) -> None:
    formatted_log = get_task_store().add_log(task_id, log_message)
    with _state_lock:
        _append_task_log_locked(task_id, formatted_log)
    broadcast_log(task_id, formatted_log)


def build_task_log_callback(
    task_id: str,
    log_writer: Optional[Callable[[str, str], None]] = None,
) -> Callable[[str], None]:
    def log_callback(message: str) -> None:
        (log_writer or add_task_log)(task_id, message)

    return log_callback


def _add_task_log_subscriber_locked(task_id: str, subscriber: queue.Queue[str]) -> None:
    _runtime_state.add_log_subscriber(task_id, subscriber)


def _remove_task_log_subscriber_locked(task_id: str, subscriber: queue.Queue[str]) -> None:
    _runtime_state.remove_log_subscriber(task_id, subscriber)


def subscribe_task_logs(task_id: str) -> queue.Queue[str]:
    subscriber: queue.Queue[str] = queue.Queue()
    with _state_lock:
        _add_task_log_subscriber_locked(task_id, subscriber)
    return subscriber


def unsubscribe_task_logs(task_id: str, subscriber: queue.Queue[str]) -> None:
    with _state_lock:
        _remove_task_log_subscriber_locked(task_id, subscriber)


def _task_log_subscribers_snapshot_locked(task_id: str) -> List[queue.Queue[str]]:
    return _runtime_state.log_subscribers_snapshot(task_id)


def broadcast_log(task_id: str, log_message: str) -> None:
    with _state_lock:
        subscribers = _task_log_subscribers_snapshot_locked(task_id)
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(log_message)
        except Exception:
            pass


def _has_memory_task_locked(task_id: str) -> bool:
    return _runtime_state.has_memory_task(task_id)


def _update_memory_task_locked(
    task_id: str,
    status: str,
    message: str,
    result: Optional[Dict[str, Any]],
    updated_at: datetime,
) -> None:
    _runtime_state.update_memory_task(task_id, status, message, result, updated_at)


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
        memory_task_exists = _has_memory_task_locked(task_id)
    if not should_apply_task_update(existing_task, memory_task_exists, status):
        return

    now = datetime.now()
    with _state_lock:
        _update_memory_task_locked(task_id, status, message, result, now)

    record_task_transition(
        store,
        task_id,
        status,
        message,
        result,
        now,
        add_task_log=add_task_log,
        is_terminal_status=is_terminal_task_status,
    )


def run_workflow(
    task_id: str,
    *,
    running_message: WorkflowRunningMessage,
    completed_message: WorkflowCompletedMessage,
    failure_label: str,
    work: Callable[[], Any],
    on_completed: WorkflowCompletedHook | None = None,
    swallow_failure_reporting_errors: bool = False,
) -> None:
    run_workflow_lifecycle(
        task_id,
        running_message=running_message,
        completed_message=completed_message,
        failure_label=failure_label,
        work=work,
        on_completed=on_completed,
        swallow_failure_reporting_errors=swallow_failure_reporting_errors,
        is_task_stopped=is_task_stopped,
        update_task_state=update_task,
        add_task_log=add_task_log,
    )


def complete_task_unless_stopped(
    task_id: str,
    message: str,
    result: Any,
) -> None:
    _complete_task_unless_stopped(
        task_id,
        completed_message=message,
        result=result,
        is_task_stopped=is_task_stopped,
        update_task_state=update_task,
    )


def fail_task_unless_stopped(task_id: str, failure_label: str, error: Exception) -> None:
    _fail_task_unless_stopped(
        task_id,
        failure_label=failure_label,
        error=error,
        is_task_stopped=is_task_stopped,
        update_task_state=update_task,
        add_task_log=add_task_log,
    )


def fail_task_with_message_unless_stopped(
    task_id: str,
    message: str,
    result: Any = None,
    log_message: str | None = None,
) -> None:
    _fail_task_with_message_unless_stopped(
        task_id,
        failed_message=message,
        result=result,
        failure_log_message=log_message,
        is_task_stopped=is_task_stopped,
        update_task_state=update_task,
        add_task_log=add_task_log,
    )


def _release_task_lock_on_terminal_status(
    task_id: str,
    status: str,
    released_at: datetime,
    store: TaskStore,
) -> None:
    release_task_lock_on_terminal_status(
        store,
        task_id,
        status,
        released_at,
        add_task_log=add_task_log,
        is_terminal_status=is_terminal_task_status,
    )


def _register_task_crawler_locked(task_id: str, crawler: Any) -> None:
    _register_resource_crawler(crawler_instances, task_id, crawler)


def _unregister_task_crawler_locked(task_id: str) -> None:
    _unregister_resource_crawler(crawler_instances, task_id)


def _register_task_file_downloader_locked(task_id: str, downloader: Any) -> None:
    _register_resource_file_downloader(file_downloader_instances, task_id, downloader)


def _unregister_task_file_downloader_locked(task_id: str) -> None:
    _unregister_resource_file_downloader(file_downloader_instances, task_id)


def _task_crawler_locked(task_id: str) -> Any:
    return task_crawler(crawler_instances, task_id)


def _task_file_downloader_locked(task_id: str) -> Any:
    return task_file_downloader(file_downloader_instances, task_id)


def _runtime_crawlers_snapshot_locked() -> List[Any]:
    return runtime_crawlers_snapshot(crawler_instances)


def _runtime_file_downloaders_snapshot_locked() -> List[Any]:
    return runtime_file_downloaders_snapshot(file_downloader_instances)


def _clear_runtime_resource_tracking_locked() -> None:
    clear_runtime_resource_tracking(crawler_instances, file_downloader_instances)


def register_task_crawler(task_id: str, crawler: Any) -> None:
    with _state_lock:
        _register_task_crawler_locked(task_id, crawler)


def unregister_task_crawler(task_id: str) -> None:
    with _state_lock:
        _unregister_task_crawler_locked(task_id)


def register_task_file_downloader(task_id: str, downloader: Any) -> None:
    with _state_lock:
        _register_task_file_downloader_locked(task_id, downloader)


def unregister_task_file_downloader(task_id: str) -> None:
    with _state_lock:
        _unregister_task_file_downloader_locked(task_id)


def _prepare_task_stop_resources_locked(task_id: str) -> tuple[Any, Any]:
    _set_task_stop_flag_locked(task_id, True)
    return _task_crawler_locked(task_id), _task_file_downloader_locked(task_id)


def is_task_cancellable(task: Dict[str, Any]) -> bool:
    spec = get_workflow_spec(str(task.get("type") or ""))
    return spec is None or spec.cancellable


def stop_task(task_id: str) -> bool:
    task = get_task_state(task_id)
    if not task:
        return False

    if not _is_active_task_status(task["status"]):
        return False

    if not is_task_cancellable(task):
        add_task_log(task_id, "⚠️ 该任务类型不支持停止请求")
        return False

    with _state_lock:
        crawler, downloader = _prepare_task_stop_resources_locked(task_id)
    get_task_store().set_stop_flag(task_id, True)
    add_task_log(task_id, "🛑 收到停止请求，正在停止任务...")

    _request_stop_for_task_resources(crawler, downloader)

    update_task(task_id, "cancelled", "任务已被用户停止")
    return True


def _request_stop_for_task_resources(crawler: Any, downloader: Any) -> None:
    request_stop_for_task_resources(crawler, downloader, crawler_runtime.crawler_instance)


def _register_task_lock_heartbeat_locked(task_id: str, stop_event: threading.Event) -> None:
    _runtime_state.register_task_lock_heartbeat(task_id, stop_event)


def _pop_task_lock_heartbeat_locked(task_id: str) -> Optional[threading.Event]:
    return _runtime_state.pop_task_lock_heartbeat(task_id)


def _task_lock_heartbeat_ids_locked() -> List[str]:
    return _runtime_state.task_lock_heartbeat_ids()


def _start_task_lock_heartbeat(task_id: str) -> None:
    task = get_task_state(task_id)
    _executor_start_task_lock_heartbeat(
        task_id,
        task=task,
        ingestion_lock_key=INGESTION_LOCK_KEY,
        heartbeat_seconds=TASK_LOCK_HEARTBEAT_SECONDS,
        lease_minutes=TASK_LOCK_LEASE_MINUTES,
        register_heartbeat=_register_task_heartbeat,
        heartbeat_task_lock=lambda active_task_id, lease_minutes: get_task_store().heartbeat_task_lock(
            active_task_id,
            lease_minutes=lease_minutes,
        ),
        event_factory=threading.Event,
        thread_factory=threading.Thread,
    )


def _register_task_heartbeat(task_id: str, stop_event: threading.Event) -> None:
    with _state_lock:
        _register_task_lock_heartbeat_locked(task_id, stop_event)


def _stop_task_lock_heartbeat(task_id: str) -> None:
    _executor_stop_task_lock_heartbeat(task_id, pop_heartbeat=_pop_task_heartbeat)


def _pop_task_heartbeat(task_id: str) -> Optional[threading.Event]:
    with _state_lock:
        return _pop_task_lock_heartbeat_locked(task_id)


def _request_stop_for_resources(resources: List[Any]) -> None:
    request_stop_for_resources(resources)


def _register_runtime_task_thread_locked(task_id: str, thread: threading.Thread) -> None:
    _runtime_state.register_runtime_task_thread(task_id, thread)


def _forget_runtime_task_thread_locked(task_id: str) -> None:
    _runtime_state.forget_runtime_task_thread(task_id)


def _clear_runtime_task_threads_locked() -> None:
    _runtime_state.clear_runtime_task_threads()


def _run_runtime_task(
    task_func: Callable[..., Any],
    task_id: str,
    task_args: tuple[Any, ...],
) -> None:
    _executor_run_runtime_task(
        task_func,
        task_id,
        task_args,
        start_heartbeat=_start_task_lock_heartbeat,
        stop_heartbeat=_stop_task_lock_heartbeat,
        forget_thread=_forget_runtime_task_thread,
    )


def _forget_runtime_task_thread(task_id: str) -> None:
    with _state_lock:
        _forget_runtime_task_thread_locked(task_id)


def enqueue_runtime_task(task_func: Callable[..., Any], task_id: str, *args: Any) -> None:
    _executor_enqueue_runtime_task(
        task_func,
        task_id,
        args,
        run_task=_run_runtime_task,
        register_thread=_register_runtime_task_thread,
        thread_factory=threading.Thread,
    )


def _register_runtime_task_thread(task_id: str, thread: threading.Thread) -> None:
    with _state_lock:
        _register_runtime_task_thread_locked(task_id, thread)


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
    _runtime_state.clear_log_subscribers()
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
    return _runtime_state.task_stop_flag(task_id)


def is_task_stopped(task_id: str) -> bool:
    with _state_lock:
        memory_stopped = _task_stop_flag_locked(task_id)
    return memory_stopped or get_task_store().is_stopped(task_id)


def get_latest_task_by_type(
    task_type: str,
    status: Optional[str] = None,
    group_id: Any = _GROUP_FILTER_UNSET,
) -> Optional[Dict[str, Any]]:
    group_filter_provided = group_id is not _GROUP_FILTER_UNSET
    return latest_task_for_query(
        get_task_store().list_tasks(),
        TaskQuery(
            task_type=task_type,
            status=status,
            group_id=group_id if group_filter_provided else None,
            group_filter_provided=group_filter_provided,
        ),
    )
