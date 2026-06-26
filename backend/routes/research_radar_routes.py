from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.routes.task_http_errors import task_launch_route_error
from backend.services.research_radar_workflow import create_research_radar_task, get_research_radar


router = APIRouter(prefix="/api/analysis/research-radar", tags=["research-radar"])


class ResearchRadarRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="雷达日期，格式 YYYY-MM-DD；默认今天（东八区）")
    commentsPerTopic: int = Field(default=8, ge=0, le=50, description="每个话题最多纳入的评论数")


def _create_research_radar_task_response(group_id: str, request: ResearchRadarRequest) -> dict[str, str]:
    return create_research_radar_task(group_id, date=request.date, comments_per_topic=request.commentsPerTopic)


def _research_radar_route_error(message: str, error: Exception) -> HTTPException:
    return task_launch_route_error(message, error)


def _research_radar_or_404(group_id: str, date: Optional[str]) -> dict:
    result = get_research_radar(group_id, date)
    if not result:
        raise HTTPException(status_code=404, detail="研究雷达结果不存在，请先生成")
    return result


@router.post("/{group_id}")
async def create_research_radar(group_id: str, request: ResearchRadarRequest):
    try:
        return _create_research_radar_task_response(group_id, request)
    except Exception as exc:
        raise _research_radar_route_error("创建研究雷达任务失败", exc)


@router.get("/{group_id}")
async def read_research_radar(
    group_id: str,
    date: Optional[str] = Query(default=None, description="雷达日期，格式 YYYY-MM-DD；不传则读取最近一次"),
):
    try:
        return _research_radar_or_404(group_id, date)
    except HTTPException:
        raise
    except Exception as exc:
        raise _research_radar_route_error("获取研究雷达失败", exc)
