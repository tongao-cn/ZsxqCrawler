from __future__ import annotations

from contextlib import closing
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT as A_SHARE_DEFAULT_REASONING_EFFORT,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
)
from backend.core.crawler_runtime import clear_crawler_instance
from backend.core.account_context import is_configured
from backend.core.app_config import load_config
from backend.storage.zsxq_database import ZSXQDatabase
from backend.storage.zsxq_file_database import ZSXQFileDatabase

router = APIRouter(tags=["core"])


def _empty_database_stats_response(configured: bool) -> Dict[str, Any]:
    return {
        "configured": configured,
        "topic_database": {
            "stats": {},
            "timestamp_info": {
                "total_topics": 0,
                "oldest_timestamp": "",
                "newest_timestamp": "",
                "has_data": False,
            },
        },
        "file_database": {
            "stats": {},
        },
    }


def _masked_config_cookie(cookie: str) -> str:
    return "***" if cookie and cookie != "your_cookie_here" else "未配置"


def _core_route_error(message: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


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
        config = load_config()
        auth_config = (config or {}).get("auth", {}) if config else {}
        cookie = auth_config.get("cookie", "") if auth_config else ""

        configured = is_configured()

        return {
            "configured": configured,
            "auth": {
                "cookie": _masked_config_cookie(cookie),
            },
            "database": config.get("database", {}) if config else {},
            "download": config.get("download", {}) if config else {},
        }
    except Exception as e:
        raise _core_route_error("获取配置失败", e)


@router.post("/api/config")
async def update_config(config: ConfigModel):
    """更新配置"""
    try:
        existing_config = load_config() or {}
        ai_config = existing_config.get("ai", {}) if isinstance(existing_config.get("ai"), dict) else {}
        ai_model = str(ai_config.get("model") or A_SHARE_DEFAULT_MODEL)
        ai_api_base = str(ai_config.get("api_base") or A_SHARE_DEFAULT_API_BASE)
        ai_wire_api = str(ai_config.get("wire_api") or A_SHARE_DEFAULT_WIRE_API)
        ai_reasoning_effort = str(ai_config.get("reasoning_effort") or A_SHARE_DEFAULT_REASONING_EFFORT)

        config_content = f"""# 知识星球数据采集器配置文件
# 通过Web界面自动生成

[auth]
# 知识星球登录Cookie
cookie = "{config.cookie}"

[download]
# 下载目录
dir = "downloads"

[ai]
# OpenAI 兼容模型配置（仅从项目内 config.toml 读取）
model = "{ai_model}"
api_base = "{ai_api_base}"
wire_api = "{ai_wire_api}"
reasoning_effort = "{ai_reasoning_effort}"
# API Key 请通过环境变量 OPENAI_API_KEY 提供，避免写入明文配置
api_key = ""
"""

        config_path = "config.toml"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        clear_crawler_instance()

        return {"message": "配置更新成功", "success": True}
    except Exception as e:
        raise _core_route_error("更新配置失败", e)


@router.get("/api/database/stats")
async def get_database_stats():
    """获取数据库统计信息"""
    try:
        configured = is_configured()
        if not configured:
            return _empty_database_stats_response(False)

        with closing(ZSXQDatabase()) as db:
            aggregated_topic_stats = db.get_database_stats()
            aggregated_timestamp_info = db.get_timestamp_range_info()

        with closing(ZSXQFileDatabase()) as fdb:
            aggregated_file_stats = fdb.get_database_stats()

        return {
            "configured": True,
            "topic_database": {
                "stats": aggregated_topic_stats,
                "timestamp_info": aggregated_timestamp_info,
            },
            "file_database": {
                "stats": aggregated_file_stats,
            },
        }
    except Exception as e:
        raise _core_route_error("获取数据库统计失败", e)
