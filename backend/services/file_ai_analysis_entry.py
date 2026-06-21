from __future__ import annotations

from typing import Any, Dict

from backend.services.ai_workflow_preflight import require_openai_api_key
from backend.services.file_ai_analysis_service import (
    analyze_group_file,
    get_group_file_analysis,
)
from backend.services.file_workflow_service import (
    create_file_ai_analysis_task,
    create_selected_file_ai_analysis_task,
)


def ensure_file_analysis_api_key() -> None:
    require_openai_api_key()


def get_file_analysis_response(group_id: str, file_id: int) -> Dict[str, Any]:
    result = get_group_file_analysis(group_id, file_id)
    return {"analysis": result}


def create_file_analysis_response(group_id: str, file_id: int, force: bool) -> Dict[str, Any]:
    ensure_file_analysis_api_key()
    result = analyze_group_file(
        group_id,
        file_id,
        force=force,
    )
    return {"analysis": result}


def create_file_analysis_task_response(group_id: str, file_id: int, force: bool) -> Dict[str, str]:
    ensure_file_analysis_api_key()
    return create_file_ai_analysis_task(group_id, file_id, force)


def create_selected_file_analysis_task_response(group_id: str, request: Any) -> Dict[str, str]:
    ensure_file_analysis_api_key()
    return create_selected_file_ai_analysis_task(group_id, request)
