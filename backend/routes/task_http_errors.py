from __future__ import annotations

from fastapi import HTTPException

from backend.services.task_launch import TaskLaunchConflict, ingestion_conflict_detail


def task_launch_route_error(message: str, error: Exception) -> HTTPException:
    if isinstance(error, TaskLaunchConflict):
        return HTTPException(status_code=409, detail=ingestion_conflict_detail(error.existing))
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")
