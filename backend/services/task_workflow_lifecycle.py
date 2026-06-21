from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


WorkflowRunningMessage = str | Callable[[], str]
WorkflowCompletedMessage = str | Callable[[Any], str]


@dataclass(frozen=True)
class WorkflowCompletionDecision:
    should_complete: bool
    result: Any = None
    status: str = "completed"
    message: str | None = None


def skip_workflow_completion() -> WorkflowCompletionDecision:
    return WorkflowCompletionDecision(should_complete=False)


def finish_workflow(status: str, message: str, result: Any = None) -> WorkflowCompletionDecision:
    return WorkflowCompletionDecision(should_complete=True, result=result, status=status, message=message)


def _workflow_completion_decision(result: Any) -> WorkflowCompletionDecision:
    if isinstance(result, WorkflowCompletionDecision):
        return result
    return WorkflowCompletionDecision(should_complete=True, result=result)


def _resolve_workflow_running_message(message: WorkflowRunningMessage) -> str:
    return message() if callable(message) else message


def _resolve_workflow_completed_message(message: WorkflowCompletedMessage, result: Any) -> str:
    return message(result) if callable(message) else message


def finish_task_unless_stopped(
    task_id: str,
    *,
    status: str,
    message: str,
    result: Any,
    is_task_stopped: Callable[[str], bool],
    update_task_state: Callable[[str, str, str, Any], None],
) -> None:
    if is_task_stopped(task_id):
        return
    update_task_state(task_id, status, message, result)


def complete_task_unless_stopped(
    task_id: str,
    *,
    completed_message: str,
    result: Any,
    is_task_stopped: Callable[[str], bool],
    update_task_state: Callable[[str, str, str, Any], None],
) -> None:
    finish_task_unless_stopped(
        task_id,
        status="completed",
        message=completed_message,
        result=result,
        is_task_stopped=is_task_stopped,
        update_task_state=update_task_state,
    )


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
        completion = _workflow_completion_decision(work())
        if not completion.should_complete:
            return

        message = completion.message or _resolve_workflow_completed_message(completed_message, completion.result)
        finish_task_unless_stopped(
            task_id,
            status=completion.status,
            message=message,
            result=completion.result,
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
