"""Resolve OpenAI-compatible model settings from env vars or project config."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_CONFIG_PATH = Path(
    os.getenv("PROJECT_CONFIG_PATH", str(PROJECT_ROOT / "config.toml"))
)
DEFAULT_PROJECT_ENV_PATH = Path(
    os.getenv("PROJECT_ENV_PATH", str(PROJECT_ROOT / ".env"))
)
# 兼容旧常量名，统一指向项目内 config.toml
DEFAULT_CODEX_CONFIG_PATH = DEFAULT_PROJECT_CONFIG_PATH
DEFAULT_CODEX_AUTH_PATH = DEFAULT_PROJECT_CONFIG_PATH
DEFAULT_FALLBACK_MODEL = "gpt-5.5"
DEFAULT_FALLBACK_BASE_URL = "https://api.openai.com/v1"
DEFAULT_FALLBACK_WIRE_API = "responses"
DEFAULT_FALLBACK_REASONING_EFFORT = "low"
DEFAULT_EXTRACTION_REASONING_EFFORT = "low"
DEFAULT_SUMMARY_REASONING_EFFORT = "high"


def _strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_project_env_file(path: Path = DEFAULT_PROJECT_ENV_PATH) -> None:
    """Load simple KEY=VALUE pairs from .env without overriding real env vars."""
    if not path.exists():
        return

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = _strip_env_value(value)


def _load_toml_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_openai_compatible_config() -> Dict[str, Any]:
    _load_project_env_file()

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


def get_extraction_reasoning_effort() -> str:
    _load_project_env_file()

    env_value = (
        os.getenv("OPENAI_EXTRACTION_REASONING_EFFORT")
        or os.getenv("AI_EXTRACTION_REASONING_EFFORT")
        or ""
    ).strip()
    project_config = _load_toml_file(DEFAULT_PROJECT_CONFIG_PATH)
    ai_config = project_config.get("ai") if isinstance(project_config.get("ai"), dict) else {}
    config_value = str(ai_config.get("extraction_reasoning_effort") or "").strip()
    return env_value or config_value or DEFAULT_EXTRACTION_REASONING_EFFORT


def get_summary_reasoning_effort() -> str:
    _load_project_env_file()

    env_value = (
        os.getenv("OPENAI_SUMMARY_REASONING_EFFORT")
        or os.getenv("AI_SUMMARY_REASONING_EFFORT")
        or ""
    ).strip()
    project_config = _load_toml_file(DEFAULT_PROJECT_CONFIG_PATH)
    ai_config = project_config.get("ai") if isinstance(project_config.get("ai"), dict) else {}
    config_value = str(ai_config.get("summary_reasoning_effort") or "").strip()
    return env_value or config_value or DEFAULT_SUMMARY_REASONING_EFFORT


def has_openai_api_key() -> bool:
    return bool(str(get_openai_compatible_config().get("api_key") or "").strip())


__all__ = [
    "DEFAULT_CODEX_AUTH_PATH",
    "DEFAULT_CODEX_CONFIG_PATH",
    "DEFAULT_PROJECT_ENV_PATH",
    "DEFAULT_PROJECT_CONFIG_PATH",
    "get_default_base_url",
    "get_default_model",
    "get_default_reasoning_effort",
    "get_default_wire_api",
    "get_extraction_reasoning_effort",
    "get_openai_compatible_config",
    "get_summary_reasoning_effort",
    "has_openai_api_key",
]
