from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.routes.task_http_errors import internal_route_error
from backend.services.core_config_service import (
    get_public_config,
    masked_config_cookie,
    update_auth_config,
)
from backend.services.group_read_model import (
    empty_database_stats_response,
    get_global_database_stats_read_model,
)

router = APIRouter(tags=["core"])


def _empty_database_stats_response(configured: bool) -> Dict[str, Any]:
    return empty_database_stats_response(configured)


def _masked_config_cookie(cookie: str) -> str:
    return masked_config_cookie(cookie)


def _core_route_error(message: str, error: Exception) -> HTTPException:
    return internal_route_error(message, error)


class ConfigModel(BaseModel):
    cookie: str = Field(..., description="知识星球Cookie")


@router.get("/")
async def root():
    """根路径"""
    return {"message": "知识星球数据采集器 API 服务", "version": "1.0.0"}


@router.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": datetime.now()}


@router.get("/api/config")
async def get_config():
    """获取当前配置"""
    try:
        return get_public_config()
    except Exception as e:
        raise _core_route_error("获取配置失败", e)


@router.post("/api/config")
async def update_config(config: ConfigModel):
    """更新配置"""
    try:
        return update_auth_config(config.cookie)
    except Exception as e:
        raise _core_route_error("更新配置失败", e)


@router.get("/api/database/stats")
async def get_database_stats():
    """获取数据库统计信息"""
    try:
        return await asyncio.to_thread(get_global_database_stats_read_model)
    except Exception as e:
        raise _core_route_error("获取数据库统计失败", e)
