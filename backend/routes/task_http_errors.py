from __future__ import annotations

from fastapi import HTTPException

from backend.services.ai_workflow_preflight import AIWorkflowPreflightError
from backend.services.task_launch import TaskLaunchConflict, ingestion_conflict_detail


def route_error(
    message: str,
    error: Exception,
    *,
    value_error_status_code: int | None = 400,
    passthrough_http: bool = True,
) -> HTTPException:
    if passthrough_http and isinstance(error, HTTPException):
        return error
    if isinstance(error, AIWorkflowPreflightError):
        return HTTPException(status_code=error.status_code, detail=error.detail)
    if isinstance(error, TaskLaunchConflict):
        return HTTPException(status_code=409, detail=ingestion_conflict_detail(error.existing))
    if value_error_status_code is not None and isinstance(error, ValueError):
        return HTTPException(status_code=value_error_status_code, detail=str(error))
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


def task_launch_route_error(message: str, error: Exception) -> HTTPException:
    return route_error(message, error, value_error_status_code=None, passthrough_http=False)
