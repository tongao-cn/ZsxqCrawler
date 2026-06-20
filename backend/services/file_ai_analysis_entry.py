from __future__ import annotations

from typing import Any, Dict

from backend.core.ai_provider_config import has_openai_api_key
from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
)
from backend.services.file_ai_analysis_service import (
    DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    analyze_group_file,
    get_group_file_analysis,
)
from backend.services.file_workflow_service import (
    create_file_ai_analysis_task,
    create_selected_file_ai_analysis_task,
)

FILE_ANALYSIS_MISSING_API_KEY_MESSAGE = (
    "未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key"
)


class FileAIAnalysisEntryError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.status_code}: {self.detail}"


def ensure_file_analysis_api_key() -> None:
    if not has_openai_api_key():
        raise FileAIAnalysisEntryError(400, FILE_ANALYSIS_MISSING_API_KEY_MESSAGE)


def get_file_analysis_response(group_id: str, file_id: int) -> Dict[str, Any]:
    result = get_group_file_analysis(group_id, file_id)
    return {"analysis": result}


def create_file_analysis_response(group_id: str, file_id: int, force: bool) -> Dict[str, Any]:
    ensure_file_analysis_api_key()
    result = analyze_group_file(
        group_id,
        file_id,
        force=force,
        model=A_SHARE_DEFAULT_MODEL,
        api_base=A_SHARE_DEFAULT_API_BASE,
        wire_api=A_SHARE_DEFAULT_WIRE_API,
        reasoning_effort=DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    )
    return {"analysis": result}


def create_file_analysis_task_response(group_id: str, file_id: int, force: bool) -> Dict[str, str]:
    ensure_file_analysis_api_key()
    return create_file_ai_analysis_task(group_id, file_id, force)


def create_selected_file_analysis_task_response(group_id: str, request: Any) -> Dict[str, str]:
    ensure_file_analysis_api_key()
    return create_selected_file_ai_analysis_task(group_id, request)
