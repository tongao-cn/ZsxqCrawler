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
from backend.schemas.files import FileAIAnalysisRequest, FileCollectRequest, FileDownloadRequest
from backend.services.file_ai_analysis_service import (
    DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
    analyze_group_file,
    get_group_file_analysis,
)
from backend.services.file_workflow_service import (
    _build_check_local_file_status_response,
    _build_file_status_response,
    _build_sync_files_response,
    _clear_group_file_data,
    _enqueue_file_task,
    _file_db,
    _get_download_file_status,
    _log_file_route_event,
    _query_group_id,
    _resolve_download_record_status,
    _safe_filename,
    run_collect_files_task,
    run_file_download_task,
    run_single_file_download_task_with_info,
)
from backend.routes.ingestion_helpers import create_ingestion_task_or_raise
from backend.services.task_runtime import update_task
from backend.storage.zsxq_database import ZSXQDatabase

router = APIRouter(prefix="/api/files", tags=["files"])


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
        raise HTTPException(status_code=500, detail=f"创建文件收集任务失败: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"创建文件下载任务失败: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"创建单个文件下载任务失败: {str(e)}")


@router.get("/status/{group_id}/{file_id}")
async def get_file_status(group_id: str, file_id: int):
    """获取文件下载状态"""
    try:
        with _file_db(group_id) as file_db:
            file_db.cursor.execute(
                """
                SELECT name, size, download_status
                FROM files
                WHERE file_id = ? AND group_id = ?
            """,
                (file_id, _query_group_id(group_id)),
            )

            result = file_db.cursor.fetchone()

            if not result:
                return _build_file_status_response(file_id, result)

            file_name, file_size, download_status = result

            local_status = _get_download_file_status(group_id, file_name, file_size, f"file_{file_id}")
            return _build_file_status_response(file_id, result, local_status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件状态失败: {str(e)}")


@router.get("/check-local/{group_id}")
async def check_local_file_status(group_id: str, file_name: str, file_size: int):
    """检查本地文件状态（不依赖数据库）"""
    try:
        local_status = _get_download_file_status(group_id, file_name, file_size, file_name)
        return _build_check_local_file_status_response(file_name, file_size, local_status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查本地文件失败: {str(e)}")


@router.get("/analysis/{group_id}/{file_id}")
async def get_file_analysis(group_id: str, file_id: int):
    """获取文件 AI 分析缓存"""
    try:
        result = await asyncio.to_thread(get_group_file_analysis, group_id, file_id)
        return {"analysis": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件 AI 分析失败: {str(e)}")


@router.post("/analysis/{group_id}/{file_id}")
async def create_file_analysis(group_id: str, file_id: int, request: FileAIAnalysisRequest):
    """分析文件内容并生成 AI 摘要"""
    try:
        if not has_openai_api_key():
            raise HTTPException(
                status_code=400,
                detail="未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key",
            )

        result = await asyncio.to_thread(
            analyze_group_file,
            group_id,
            file_id,
            force=request.force,
            model=A_SHARE_DEFAULT_MODEL,
            api_base=A_SHARE_DEFAULT_API_BASE,
            wire_api=A_SHARE_DEFAULT_WIRE_API,
            reasoning_effort=DEFAULT_FILE_ANALYSIS_REASONING_EFFORT,
        )
        return {"analysis": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件 AI 分析失败: {str(e)}")


@router.get("/stats/{group_id}")
async def get_file_stats(group_id: str):
    """获取指定群组的文件统计信息"""
    try:
        with _file_db(group_id) as file_db:
            stats = file_db.get_database_stats()

            file_db.cursor.execute(
                """
                SELECT
                    COUNT(*) as total_files,
                    COUNT(CASE WHEN download_status IN ('completed', 'downloaded', 'skipped') THEN 1 END) as downloaded,
                    COUNT(CASE WHEN download_status = 'pending' THEN 1 END) as pending,
                    COUNT(CASE WHEN download_status = 'failed' THEN 1 END) as failed
                FROM files
                WHERE group_id = ?
                """,
                (_query_group_id(group_id),),
            )
            download_stats = file_db.cursor.fetchone()

            return {
                "database_stats": stats,
                "download_stats": {
                    "total_files": download_stats[0] if download_stats else 0,
                    "downloaded": download_stats[1] if download_stats else 0,
                    "pending": download_stats[2] if download_stats else 0,
                    "failed": download_stats[3] if download_stats else 0,
                },
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件统计失败: {str(e)}")


@router.post("/clear/{group_id}")
async def clear_file_database(group_id: str):
    """删除指定群组的 PostgreSQL 文件数据"""
    try:
        deleted_counts = _clear_group_file_data(group_id)

        try:
            from backend.core.image_cache_manager import clear_group_cache_manager, get_image_cache_manager

            cache_manager = get_image_cache_manager(group_id)
            success, message = cache_manager.clear_cache()
            if success:
                _log_file_route_event("INFO", f"图片缓存已清空: {message}")
            else:
                _log_file_route_event("WARN", f"清空图片缓存失败: {message}")
            clear_group_cache_manager(group_id)
        except Exception as cache_error:
            _log_file_route_event("WARN", f"清空图片缓存时出错: {cache_error}")

        return {"message": f"群组 {group_id} 的文件数据和图片缓存已删除", "deleted": deleted_counts}
    except HTTPException:
        raise
    except Exception as e:
        _log_file_route_event("ERROR", f"删除文件数据库失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除文件数据库失败: {str(e)}")


@router.post("/sync-from-topics/{group_id}")
async def sync_files_from_topics(group_id: str):
    """从话题库 topic_files 回填/重建文件库记录。"""
    topics_db = None
    task_id = None
    try:
        task_id = create_ingestion_task_or_raise(
            "sync_files_from_topics",
            f"从话题同步文件记录 (群组: {group_id})",
            group_id,
        )
        update_task(task_id, "running", "开始从话题同步文件记录...")
        topics_db = ZSXQDatabase(group_id)
        stats = topics_db.backfill_topic_files_to_file_database()
        update_task(task_id, "completed", "从话题同步文件记录完成", stats)
        return _build_sync_files_response(group_id, stats)
    except HTTPException:
        if task_id:
            update_task(task_id, "failed", "从话题同步文件记录失败")
        raise
    except Exception as e:
        if task_id:
            update_task(task_id, "failed", f"从话题同步文件记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"同步文件记录失败: {str(e)}")
    finally:
        if topics_db:
            try:
                topics_db.close()
            except Exception:
                pass


@router.get("/{group_id}")
async def get_files(
    group_id: str,
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """获取指定群组的文件列表"""
    try:
        with _file_db(group_id) as file_db:
            offset = (page - 1) * per_page

            conditions = []
            params_prefix = [_query_group_id(group_id)]
            conditions.append("f.group_id = ?")

            if status:
                if status == "completed":
                    conditions.append("f.download_status IN (?, ?, ?)")
                    params_prefix.extend(["completed", "downloaded", "skipped"])
                else:
                    conditions.append("f.download_status = ?")
                    params_prefix.append(status)

            search_text = (search or "").strip()
            if search_text:
                conditions.append("f.name LIKE ?")
                params_prefix.append(f"%{search_text}%")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            query = f"""
                SELECT
                    f.file_id,
                    f.name,
                    f.size,
                    f.download_count,
                    f.create_time,
                    f.download_status,
                    f.local_path,
                    faa.updated_at
                FROM files f
                LEFT JOIN file_ai_analyses faa ON faa.file_id = f.file_id
                {where_clause}
                ORDER BY f.create_time DESC
                LIMIT ? OFFSET ?
            """
            params = (*params_prefix, per_page, offset)

            file_db.cursor.execute(query, params)
            files = file_db.cursor.fetchall()

            count_query = f"SELECT COUNT(*) FROM files f {where_clause}"
            file_db.cursor.execute(count_query, tuple(params_prefix))
            total = file_db.cursor.fetchone()[0]

            normalized_files = []
            for file in files:
                file_id = file[0]
                file_name = file[1]
                file_size = file[2]
                stored_status = file[5] if len(file) > 5 else "unknown"
                stored_local_path = file[6] if len(file) > 6 else None

                local_status = _resolve_download_record_status(
                    group_id,
                    file_id,
                    file_name,
                    stored_status,
                    stored_local_path,
                )

                if local_status["local_exists"] and (
                    stored_status != "completed"
                    or str(stored_local_path or "").strip() != local_status["local_path"]
                ):
                    file_db.update_file_download_status(file_id, "completed", local_status["local_path"])

                normalized_files.append(
                    {
                        "file_id": file_id,
                        "name": file_name,
                        "size": file_size,
                        "download_count": file[3],
                        "create_time": file[4],
                        "download_status": local_status["download_status"],
                        "local_exists": local_status["local_exists"],
                        "local_path": local_status["local_path"],
                        "has_ai_analysis": bool(file[7]) if len(file) > 7 and file[7] else False,
                        "analysis_updated_at": file[7] if len(file) > 7 else None,
                    }
                )

            return {
                "files": normalized_files,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "pages": (total + per_page - 1) // per_page,
                },
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")
