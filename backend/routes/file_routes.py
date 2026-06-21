from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.schemas.files import (
    FileAIAnalysisBatchRequest,
    FileAIAnalysisRequest,
    FileCollectRequest,
    FileDownloadRequest,
    FileFilteredDownloadRequest,
    FileIdListRequest,
)
from backend.routes.task_http_errors import task_launch_route_error
from backend.services.ai_workflow_preflight import AIWorkflowPreflightError as FileAIAnalysisEntryError
from backend.services.file_ai_analysis_entry import (
    create_file_analysis_response,
    create_file_analysis_task_response,
    create_selected_file_analysis_task_response,
    get_file_analysis_response,
)
from backend.services.file_read_model import (
    check_local_file_status_response,
    clear_file_database_response,
    get_file_stats_response,
    get_file_status_response,
    get_files_response,
)
from backend.services.file_workflow_service import (
    create_filtered_file_download_task,
    create_file_collect_task,
    create_file_download_task,
    create_selected_file_download_task,
    create_single_file_download_task,
    create_sync_files_from_topics_task,
)

router = APIRouter(prefix="/api/files", tags=["files"])


def _file_route_error(message: str, error: Exception) -> HTTPException:
    return task_launch_route_error(message, error)


def _file_analysis_entry_http_error(error: FileAIAnalysisEntryError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _log_file_route_event(level: str, message: str) -> None:
    print(f"[{level}] {message}")


async def _file_status(group_id: str, file_id: int) -> dict:
    return await asyncio.to_thread(get_file_status_response, group_id, file_id)


async def _local_file_status(group_id: str, file_name: str, file_size: int) -> dict:
    return await asyncio.to_thread(check_local_file_status_response, group_id, file_name, file_size)


async def _file_stats(group_id: str) -> dict:
    return await asyncio.to_thread(get_file_stats_response, group_id)


async def _clear_file_database(group_id: str) -> dict:
    return await asyncio.to_thread(clear_file_database_response, group_id)


async def _files_page(
    group_id: str,
    page: int,
    per_page: int,
    status: Optional[str],
    search: Optional[str],
    analysis_status: Optional[str],
) -> dict:
    return await asyncio.to_thread(get_files_response, group_id, page, per_page, status, search, analysis_status)


async def _file_analysis(group_id: str, file_id: int) -> dict:
    return await asyncio.to_thread(get_file_analysis_response, group_id, file_id)


async def _created_file_analysis(group_id: str, file_id: int, force: bool) -> dict:
    return await asyncio.to_thread(create_file_analysis_response, group_id, file_id, force)


@router.post("/collect/{group_id}")
async def collect_files(group_id: str, request: FileCollectRequest):
    """收集文件列表"""
    try:
        return create_file_collect_task(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建文件收集任务失败", e)


@router.post("/download/{group_id}")
async def download_files(group_id: str, request: FileDownloadRequest):
    """下载文件"""
    try:
        return create_file_download_task(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建文件下载任务失败", e)


@router.post("/download-single/{group_id}/{file_id}")
async def download_single_file(
    group_id: str,
    file_id: int,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
):
    """下载单个文件"""
    try:
        return create_single_file_download_task(group_id, file_id, file_name, file_size)
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建单个文件下载任务失败", e)


@router.post("/download-selected/{group_id}")
async def download_selected_files(group_id: str, request: FileIdListRequest):
    """下载指定文件列表。"""
    try:
        return create_selected_file_download_task(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建选中文件下载任务失败", e)


@router.post("/download-filtered/{group_id}")
async def download_filtered_files(
    group_id: str,
    request: FileFilteredDownloadRequest,
):
    """下载当前筛选条件匹配的文件。"""
    try:
        return create_filtered_file_download_task(group_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建筛选结果下载任务失败", e)


@router.get("/status/{group_id}/{file_id}")
async def get_file_status(group_id: str, file_id: int):
    """获取文件下载状态"""
    try:
        return await _file_status(group_id, file_id)
    except Exception as e:
        raise _file_route_error("获取文件状态失败", e)


@router.get("/check-local/{group_id}")
async def check_local_file_status(group_id: str, file_name: str, file_size: int):
    """检查本地文件状态（不依赖数据库）"""
    try:
        return await _local_file_status(group_id, file_name, file_size)
    except Exception as e:
        raise _file_route_error("检查本地文件失败", e)


@router.get("/analysis/{group_id}/{file_id}")
async def get_file_analysis(group_id: str, file_id: int):
    """获取文件 AI 分析缓存"""
    try:
        return await _file_analysis(group_id, file_id)
    except Exception as e:
        raise _file_route_error("获取文件 AI 分析失败", e)


@router.post("/analysis/{group_id}/{file_id}")
async def create_file_analysis(group_id: str, file_id: int, request: FileAIAnalysisRequest):
    """分析文件内容并生成 AI 摘要"""
    try:
        return await _created_file_analysis(group_id, file_id, request.force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _file_route_error("文件 AI 分析失败", e)


@router.post("/analysis-task/{group_id}/{file_id}")
async def create_file_analysis_task(
    group_id: str,
    file_id: int,
    request: FileAIAnalysisRequest,
):
    """创建单文件 AI 分析后台任务。"""
    try:
        return create_file_analysis_task_response(group_id, file_id, request.force)
    except FileAIAnalysisEntryError as e:
        raise _file_analysis_entry_http_error(e)
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建文件 AI 分析任务失败", e)


@router.post("/analysis-selected/{group_id}")
async def create_selected_file_analysis_task(
    group_id: str,
    request: FileAIAnalysisBatchRequest,
):
    """创建批量文件 AI 分析后台任务。"""
    try:
        return create_selected_file_analysis_task_response(group_id, request)
    except FileAIAnalysisEntryError as e:
        raise _file_analysis_entry_http_error(e)
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建批量文件 AI 分析任务失败", e)


@router.get("/stats/{group_id}")
async def get_file_stats(group_id: str):
    """获取指定群组的文件统计信息"""
    try:
        return await _file_stats(group_id)
    except Exception as e:
        raise _file_route_error("获取文件统计失败", e)


@router.post("/clear/{group_id}")
async def clear_file_database(group_id: str):
    """删除指定群组的 PostgreSQL 文件数据"""
    try:
        return await _clear_file_database(group_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_file_route_event("ERROR", f"删除文件数据库失败: {str(e)}")
        raise _file_route_error("删除文件数据库失败", e)


@router.post("/sync-from-topics/{group_id}")
async def sync_files_from_topics(group_id: str):
    """从话题库 topic_files 回填/重建文件库记录。"""
    try:
        return create_sync_files_from_topics_task(group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建同步文件记录任务失败", e)


@router.get("/{group_id}")
async def get_files(
    group_id: str,
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    analysis_status: Optional[str] = None,
):
    """获取指定群组的文件列表"""
    try:
        return await _files_page(group_id, page, per_page, status, search, analysis_status)
    except Exception as e:
        raise _file_route_error("获取文件列表失败", e)
