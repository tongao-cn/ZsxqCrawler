from __future__ import annotations

from typing import Any, Callable


WorkflowRunningMessage = str | Callable[[], str]
WorkflowCompletedMessage = str | Callable[[Any], str]


def _resolve_workflow_running_message(message: WorkflowRunningMessage) -> str:
    return message() if callable(message) else message


def _resolve_workflow_completed_message(message: WorkflowCompletedMessage, result: Any) -> str:
    return message(result) if callable(message) else message


def complete_task_unless_stopped(
    task_id: str,
    *,
    completed_message: str,
    result: Any,
    is_task_stopped: Callable[[str], bool],
    update_task_state: Callable[[str, str, str, Any], None],
) -> None:
    if is_task_stopped(task_id):
        return
    update_task_state(task_id, "completed", completed_message, result)


def fail_task_unless_stopped(
    task_id: str,
    *,
    failure_label: str,
    error: Exception,
    is_task_stopped: Callable[[str], bool],
    update_task_state: Callable[[str, str, str, Any], None],
    add_task_log: Callable[[str, str], None],
) -> None:
    if is_task_stopped(task_id):
        return
    message = f"{failure_label}失败: {str(error)}"
    add_task_log(task_id, f"❌ {message}")
    update_task_state(task_id, "failed", message, None)


def run_workflow_lifecycle(
    task_id: str,
    *,
    running_message: WorkflowRunningMessage,
    completed_message: WorkflowCompletedMessage,
    failure_label: str,
    work: Callable[[], Any],
    is_task_stopped: Callable[[str], bool],
    update_task_state: Callable[[str, str, str, Any], None],
    add_task_log: Callable[[str, str], None],
) -> None:
    try:
        if is_task_stopped(task_id):
            return

        update_task_state(task_id, "running", _resolve_workflow_running_message(running_message), None)
        result = work()

        complete_task_unless_stopped(
            task_id,
            completed_message=_resolve_workflow_completed_message(completed_message, result),
            result=result,
            is_task_stopped=is_task_stopped,
            update_task_state=update_task_state,
        )
    except Exception as exc:
        fail_task_unless_stopped(
            task_id,
            failure_label=failure_label,
            error=exc,
            is_task_stopped=is_task_stopped,
            update_task_state=update_task_state,
            add_task_log=add_task_log,
        )
