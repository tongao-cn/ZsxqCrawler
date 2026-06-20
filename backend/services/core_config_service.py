from __future__ import annotations

from typing import Any, Dict

from backend.core.account_context import is_configured
from backend.core.app_config import load_config
from backend.core.crawler_runtime import clear_crawler_instance
from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT as A_SHARE_DEFAULT_REASONING_EFFORT,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
)


def masked_config_cookie(cookie: str) -> str:
    return "***" if cookie and cookie != "your_cookie_here" else "未配置"


def get_public_config() -> Dict[str, Any]:
    config = load_config()
    auth_config = (config or {}).get("auth", {}) if config else {}
    cookie = auth_config.get("cookie", "") if auth_config else ""

    return {
        "configured": is_configured(),
        "auth": {
            "cookie": masked_config_cookie(cookie),
        },
        "database": config.get("database", {}) if config else {},
        "download": config.get("download", {}) if config else {},
    }


def _ai_config_value(existing_config: dict, key: str, default: str) -> str:
    ai_config = existing_config.get("ai", {}) if isinstance(existing_config.get("ai"), dict) else {}
    return str(ai_config.get(key) or default)


def _auth_config_content(cookie: str, existing_config: dict) -> str:
    ai_model = _ai_config_value(existing_config, "model", A_SHARE_DEFAULT_MODEL)
    ai_api_base = _ai_config_value(existing_config, "api_base", A_SHARE_DEFAULT_API_BASE)
    ai_wire_api = _ai_config_value(existing_config, "wire_api", A_SHARE_DEFAULT_WIRE_API)
    ai_reasoning_effort = _ai_config_value(existing_config, "reasoning_effort", A_SHARE_DEFAULT_REASONING_EFFORT)

    return f"""# 知识星球数据采集器配置文件
# 通过Web界面自动生成

[auth]
# 知识星球登录Cookie
cookie = "{cookie}"

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


def update_auth_config(cookie: str) -> Dict[str, Any]:
    existing_config = load_config() or {}

    with open("config.toml", "w", encoding="utf-8") as f:
        f.write(_auth_config_content(cookie, existing_config))

    clear_crawler_instance()

    return {"message": "配置更新成功", "success": True}
