from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.services.postgres_activity import list_postgres_activity


router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("/postgres/activity")
async def get_postgres_activity(limit: int = Query(default=30, ge=1, le=200)):
    """查看当前 PostgreSQL 活动/等待会话。"""
    try:
        return {"activity": list_postgres_activity(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 PostgreSQL 活动失败: {str(e)}")
