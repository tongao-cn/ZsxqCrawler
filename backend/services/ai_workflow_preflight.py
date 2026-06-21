from __future__ import annotations

from typing import Callable

from backend.core.ai_provider_config import has_openai_api_key


MISSING_OPENAI_API_KEY_MESSAGE = (
    "未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key"
)


class AIWorkflowPreflightError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.status_code}: {self.detail}"


def require_openai_api_key() -> None:
    if not has_openai_api_key():
        raise AIWorkflowPreflightError(400, MISSING_OPENAI_API_KEY_MESSAGE)


def fail_task_if_openai_api_key_missing(
    task_id: str,
    *,
    update_task_state: Callable[[str, str, str], None],
    add_task_log: Callable[[str, str], None],
) -> bool:
    if has_openai_api_key():
        return False

    update_task_state(task_id, "failed", MISSING_OPENAI_API_KEY_MESSAGE)
    add_task_log(task_id, f"❌ {MISSING_OPENAI_API_KEY_MESSAGE}")
    return True
