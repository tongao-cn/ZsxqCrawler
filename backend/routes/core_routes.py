from __future__ import annotations

import os
from contextlib import closing
from datetime import datetime
from typing import Any, Dict, List, Optional

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
from backend.core.db_path_manager import get_db_path_manager
from backend.storage.zsxq_database import ZSXQDatabase
from backend.storage.zsxq_file_database import ZSXQFileDatabase
from backend.crawlers.zsxq_interactive_crawler import load_config

router = APIRouter(tags=["core"])


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
                "cookie": "***" if cookie and cookie != "your_cookie_here" else "未配置",
            },
            "database": config.get("database", {}) if config else {},
            "download": config.get("download", {}) if config else {},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@router.get("/api/database/stats")
async def get_database_stats():
    """获取数据库统计信息"""
    try:
        configured = is_configured()
        if not configured:
            return {
                "configured": False,
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

        path_manager = get_db_path_manager()
        groups_info = path_manager.list_all_groups()

        if not groups_info:
            return {
                "configured": True,
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

        aggregated_topic_stats: Dict[str, int] = {}
        aggregated_file_stats: Dict[str, int] = {}
        oldest_ts: Optional[str] = None
        newest_ts: Optional[str] = None
        total_topics = 0
        has_data = False

        for gi in groups_info:
            group_id = gi.get("group_id")
            topics_db_path = gi.get("topics_db")
            if not topics_db_path:
                continue

            with closing(ZSXQDatabase(topics_db_path)) as db:
                topic_stats = db.get_database_stats()
                ts_info = db.get_timestamp_range_info()

            for table, count in (topic_stats or {}).items():
                aggregated_topic_stats[table] = aggregated_topic_stats.get(table, 0) + int(count or 0)

            if ts_info.get("has_data"):
                has_data = True
                ot = ts_info.get("oldest_timestamp")
                nt = ts_info.get("newest_timestamp")
                if ot:
                    if oldest_ts is None or ot < oldest_ts:
                        oldest_ts = ot
                if nt:
                    if newest_ts is None or nt > newest_ts:
                        newest_ts = nt
                total_topics += int(ts_info.get("total_topics") or 0)

            db_paths = path_manager.list_group_databases(str(group_id))
            files_db_path = db_paths.get("files")
            if files_db_path:
                with closing(ZSXQFileDatabase(files_db_path)) as fdb:
                    file_stats = fdb.get_database_stats()

                for table, count in (file_stats or {}).items():
                    aggregated_file_stats[table] = aggregated_file_stats.get(table, 0) + int(count or 0)

        return {
            "configured": True,
            "topic_database": {
                "stats": aggregated_topic_stats,
                "timestamp_info": {
                    "total_topics": total_topics,
                    "oldest_timestamp": oldest_ts or "",
                    "newest_timestamp": newest_ts or "",
                    "has_data": has_data,
                },
            },
            "file_database": {
                "stats": aggregated_file_stats,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取数据库统计失败: {str(e)}")
