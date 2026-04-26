"""Resolve OpenAI-compatible model settings from env vars or project config."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_PROJECT_CONFIG_PATH = Path(
    os.getenv("PROJECT_CONFIG_PATH", str(Path(__file__).resolve().with_name("config.toml")))
)
# 兼容旧常量名，统一指向项目内 config.toml
DEFAULT_CODEX_CONFIG_PATH = DEFAULT_PROJECT_CONFIG_PATH
DEFAULT_CODEX_AUTH_PATH = DEFAULT_PROJECT_CONFIG_PATH
DEFAULT_FALLBACK_MODEL = "gpt-5.4-mini"
DEFAULT_FALLBACK_BASE_URL = "https://api.openai.com/v1"
DEFAULT_FALLBACK_WIRE_API = "responses"
DEFAULT_FALLBACK_REASONING_EFFORT = "high"


def _load_toml_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_openai_compatible_config() -> Dict[str, Any]:
    env_model = (os.getenv("OPENAI_MODEL") or os.getenv("AI_MODEL") or "").strip()
    env_base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or "").strip()
    env_wire_api = (os.getenv("OPENAI_WIRE_API") or "").strip()
    env_reasoning_effort = (os.getenv("OPENAI_REASONING_EFFORT") or os.getenv("AI_REASONING_EFFORT") or "").strip()
    env_api_key = (os.getenv("OPENAI_API_KEY") or "").strip()

    project_config = _load_toml_file(DEFAULT_PROJECT_CONFIG_PATH)
    ai_config = project_config.get("ai") if isinstance(project_config.get("ai"), dict) else {}

    provider_name = str(ai_config.get("provider_name") or "OpenAI").strip() or "OpenAI"
    model = env_model or str(ai_config.get("model") or DEFAULT_FALLBACK_MODEL).strip() or DEFAULT_FALLBACK_MODEL
    base_url = (
        env_base_url
        or str(ai_config.get("api_base") or ai_config.get("base_url") or DEFAULT_FALLBACK_BASE_URL).strip()
        or DEFAULT_FALLBACK_BASE_URL
    )
    wire_api = env_wire_api or str(ai_config.get("wire_api") or DEFAULT_FALLBACK_WIRE_API).strip() or DEFAULT_FALLBACK_WIRE_API
    reasoning_effort = env_reasoning_effort or str(ai_config.get("reasoning_effort") or DEFAULT_FALLBACK_REASONING_EFFORT).strip() or DEFAULT_FALLBACK_REASONING_EFFORT
    api_key = env_api_key or str(ai_config.get("api_key") or "").strip()

    return {
        "provider_name": provider_name,
        "model": model,
        "base_url": base_url,
        "wire_api": wire_api,
        "reasoning_effort": reasoning_effort,
        "api_key": api_key,
        "requires_openai_auth": True,
        "project_config_path": str(DEFAULT_PROJECT_CONFIG_PATH),
        # 兼容旧键名，避免调用方直接取字段时报错
        "codex_config_path": str(DEFAULT_PROJECT_CONFIG_PATH),
        "codex_auth_path": str(DEFAULT_PROJECT_CONFIG_PATH),
    }


def get_default_model() -> str:
    return str(get_openai_compatible_config().get("model") or DEFAULT_FALLBACK_MODEL)


def get_default_base_url() -> str:
    return str(get_openai_compatible_config().get("base_url") or DEFAULT_FALLBACK_BASE_URL)


def get_default_wire_api() -> str:
    return str(get_openai_compatible_config().get("wire_api") or DEFAULT_FALLBACK_WIRE_API)


def get_default_reasoning_effort() -> str:
    return str(get_openai_compatible_config().get("reasoning_effort") or DEFAULT_FALLBACK_REASONING_EFFORT)


def has_openai_api_key() -> bool:
    return bool(str(get_openai_compatible_config().get("api_key") or "").strip())


__all__ = [
    "DEFAULT_CODEX_AUTH_PATH",
    "DEFAULT_CODEX_CONFIG_PATH",
    "DEFAULT_PROJECT_CONFIG_PATH",
    "get_default_base_url",
    "get_default_model",
    "get_default_reasoning_effort",
    "get_default_wire_api",
    "get_openai_compatible_config",
    "has_openai_api_key",
]
