from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.routes.task_http_errors import route_error
from backend.services.retention_cleanup_service import (
    DEFAULT_RETENTION_DAYS,
    create_retention_cleanup_task,
    preview_group_retention_cleanup,
)


router = APIRouter(prefix="/api/retention", tags=["retention"])


class RetentionCleanupRequest(BaseModel):
    retentionDays: int = Field(default=DEFAULT_RETENTION_DAYS, ge=1, le=3650, description="保留天数，默认 365 天")
    dryRun: bool = Field(default=True, description="仅预览，不执行删除")


def _retention_cleanup_response(group_id: str, request: RetentionCleanupRequest) -> dict:
    if request.dryRun:
        return preview_group_retention_cleanup(group_id, retention_days=request.retentionDays)
    return create_retention_cleanup_task(group_id, retention_days=request.retentionDays)


@router.post("/groups/{group_id}/cleanup")
async def cleanup_group_retention(group_id: str, request: RetentionCleanupRequest):
    try:
        return _retention_cleanup_response(group_id, request)
    except Exception as exc:
        raise route_error("创建超期内容清理任务失败", exc)
