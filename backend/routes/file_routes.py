from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE as A_SHARE_DEFAULT_API_BASE,
    DEFAULT_MODEL as A_SHARE_DEFAULT_MODEL,
    DEFAULT_WIRE_API as A_SHARE_DEFAULT_WIRE_API,
)
from backend.core.ai_provider_config import has_openai_api_key
from backend.schemas.files import (
    FileAIAnalysisBatchRequest,
    FileAIAnalysisRequest,
    FileCollectRequest,
    FileDownloadRequest,
    FileFilteredDownloadRequest,
    FileIdListRequest,
)
from backend.services.file_ai_analysis_service import (
    DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    analyze_group_file,
    get_group_file_analysis,
)
from backend.services.task_launch import TaskLaunchConflict, ingestion_conflict_detail
from backend.services.file_workflow_service import (
    _check_local_file_status_response,
    _clear_file_database_response,
    _enqueue_file_task,
    _get_file_stats_response,
    _get_file_status_response,
    _get_files_response,
    _log_file_route_event,
    run_collect_files_task,
    run_filtered_file_download_task,
    run_file_analysis_task,
    run_file_download_task,
    run_selected_file_download_task,
    run_single_file_download_task_with_info,
    run_sync_files_from_topics_task,
)

router = APIRouter(prefix="/api/files", tags=["files"])


def _file_route_error(message: str, error: Exception) -> HTTPException:
    if isinstance(error, TaskLaunchConflict):
        return HTTPException(status_code=409, detail=ingestion_conflict_detail(error.existing))
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


async def _file_status(group_id: str, file_id: int) -> dict:
    return await asyncio.to_thread(_get_file_status_response, group_id, file_id)


async def _local_file_status(group_id: str, file_name: str, file_size: int) -> dict:
    return await asyncio.to_thread(_check_local_file_status_response, group_id, file_name, file_size)


async def _file_stats(group_id: str) -> dict:
    return await asyncio.to_thread(_get_file_stats_response, group_id)


async def _clear_file_database(group_id: str) -> dict:
    return await asyncio.to_thread(_clear_file_database_response, group_id)


async def _files_page(
    group_id: str,
    page: int,
    per_page: int,
    status: Optional[str],
    search: Optional[str],
    analysis_status: Optional[str],
) -> dict:
    return await asyncio.to_thread(_get_files_response, group_id, page, per_page, status, search, analysis_status)


async def _file_analysis(group_id: str, file_id: int) -> dict:
    result = await asyncio.to_thread(get_group_file_analysis, group_id, file_id)
    return {"analysis": result}


async def _created_file_analysis(group_id: str, file_id: int, force: bool) -> dict:
    result = await asyncio.to_thread(
        analyze_group_file,
        group_id,
        file_id,
        force=force,
        model=A_SHARE_DEFAULT_MODEL,
        api_base=A_SHARE_DEFAULT_API_BASE,
        wire_api=A_SHARE_DEFAULT_WIRE_API,
        reasoning_effort=DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    )
    return {"analysis": result}


@router.post("/collect/{group_id}")
async def collect_files(group_id: str, request: FileCollectRequest, background_tasks: BackgroundTasks):
    """收集文件列表"""
    try:
        return _enqueue_file_task(
            background_tasks,
            "collect_files",
            "收集文件列表",
            run_collect_files_task,
            group_id,
            request,
            ingestion_group_id=group_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建文件收集任务失败", e)


@router.post("/download/{group_id}")
async def download_files(group_id: str, request: FileDownloadRequest, background_tasks: BackgroundTasks):
    """下载文件"""
    try:
        return _enqueue_file_task(
            background_tasks,
            "download_files",
            f"下载文件 (排序: {request.sort_by})",
            run_file_download_task,
            group_id,
            request.max_files,
            request.sort_by,
            request.start_time,
            request.end_time,
            request.last_days,
            request.download_interval,
            request.long_sleep_interval,
            request.files_per_batch,
            request.download_interval_min,
            request.download_interval_max,
            request.long_sleep_interval_min,
            request.long_sleep_interval_max,
            ingestion_group_id=group_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建文件下载任务失败", e)


@router.post("/download-single/{group_id}/{file_id}")
async def download_single_file(
    group_id: str,
    file_id: int,
    background_tasks: BackgroundTasks,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None,
):
    """下载单个文件"""
    try:
        return _enqueue_file_task(
            background_tasks,
            "download_single_file",
            f"下载单个文件 (ID: {file_id})",
            run_single_file_download_task_with_info,
            group_id,
            file_id,
            file_name,
            file_size,
            message="单个文件下载任务已创建",
            ingestion_group_id=group_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建单个文件下载任务失败", e)


@router.post("/download-selected/{group_id}")
async def download_selected_files(group_id: str, request: FileIdListRequest, background_tasks: BackgroundTasks):
    """下载指定文件列表。"""
    try:
        return _enqueue_file_task(
            background_tasks,
            "download_selected_files",
            f"下载选中文件 ({len(request.file_ids)} 个)",
            run_selected_file_download_task,
            group_id,
            request.file_ids,
            message="选中文件下载任务已创建",
            ingestion_group_id=group_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建选中文件下载任务失败", e)


@router.post("/download-filtered/{group_id}")
async def download_filtered_files(
    group_id: str,
    request: FileFilteredDownloadRequest,
    background_tasks: BackgroundTasks,
):
    """下载当前筛选条件匹配的文件。"""
    try:
        return _enqueue_file_task(
            background_tasks,
            "download_filtered_files",
            "下载筛选结果",
            run_filtered_file_download_task,
            group_id,
            request.status,
            request.search,
            request.max_files,
            message="筛选结果下载任务已创建",
            ingestion_group_id=group_id,
        )
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
        if not has_openai_api_key():
            raise HTTPException(
                status_code=400,
                detail="未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key",
            )

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
    background_tasks: BackgroundTasks,
):
    """创建单文件 AI 分析后台任务。"""
    try:
        if not has_openai_api_key():
            raise HTTPException(
                status_code=400,
                detail="未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key",
            )
        return _enqueue_file_task(
            background_tasks,
            "analyze_file",
            f"分析文件 (ID: {file_id})",
            run_file_analysis_task,
            group_id,
            [file_id],
            request.force,
            message="文件 AI 分析任务已创建",
            task_group_id=group_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _file_route_error("创建文件 AI 分析任务失败", e)


@router.post("/analysis-selected/{group_id}")
async def create_selected_file_analysis_task(
    group_id: str,
    request: FileAIAnalysisBatchRequest,
    background_tasks: BackgroundTasks,
):
    """创建批量文件 AI 分析后台任务。"""
    try:
        if not has_openai_api_key():
            raise HTTPException(
                status_code=400,
                detail="未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key",
            )
        return _enqueue_file_task(
            background_tasks,
            "analyze_files",
            f"批量分析文件 ({len(request.file_ids)} 个)",
            run_file_analysis_task,
            group_id,
            request.file_ids,
            request.force,
            message="批量文件 AI 分析任务已创建",
            task_group_id=group_id,
        )
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
async def sync_files_from_topics(group_id: str, background_tasks: BackgroundTasks):
    """从话题库 topic_files 回填/重建文件库记录。"""
    try:
        return _enqueue_file_task(
            background_tasks,
            "sync_files_from_topics",
            f"从话题同步文件记录 (群组: {group_id})",
            run_sync_files_from_topics_task,
            group_id,
            message="从话题同步文件记录任务已创建",
            ingestion_group_id=group_id,
        )
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
