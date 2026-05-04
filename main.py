"""
知识星球数据采集器 - FastAPI 后端服务
提供RESTful API接口来操作现有的爬虫功能
"""

import os
import sys
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import asynccontextmanager
import runtime_helpers as runtime_helpers_module

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from logger_config import ensure_configured

# 添加项目根目录到Python路径（现在main.py就在根目录）
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入现有的业务逻辑模块
from db_path_manager import get_db_path_manager
from image_cache_manager import get_image_cache_manager
from accounts_sql_manager import get_accounts_sql_manager
from a_share_analysis_service import (
    normalize_group_id,
)
from runtime_helpers import (
    build_account_group_detection,
    build_stealth_headers,
    clear_account_detect_cache,
    delete_group_local,
    fetch_groups_from_api,
    get_account_summary_for_group_auto,
    get_cached_local_group_ids,
    get_cookie_for_group,
    get_crawler,
    get_crawler_for_group,
    get_crawler_safe,
    get_primary_cookie,
    is_configured,
    scan_local_groups,
)
from a_share_routes import router as a_share_router
from account_routes import router as account_router
from core_routes import router as core_router
from crawl_routes import router as crawl_router
from daily_analysis_routes import router as daily_analysis_router
from columns_routes import router as columns_router
from group_routes import router as group_router
from file_routes import router as file_router
from media_routes import router as media_router
from settings_routes import router as settings_router
from topic_routes import router as topic_router
from task_routes import router as task_router

# 初始化日志系统
ensure_configured()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时扫描本地群"""
    # 启动时执行
    try:
        await asyncio.to_thread(scan_local_groups)
    except Exception as e:
        print(f"⚠️ 启动扫描本地群失败: {e}")
    yield
    # 关闭时执行（如需要可添加清理逻辑）


app = FastAPI(
    title="知识星球数据采集器 API",
    description="为知识星球数据采集器提供RESTful API接口",
    version="1.0.0",
    lifespan=lifespan
)

def _get_cors_allow_origins() -> List[str]:
    """读取允许的 CORS 来源；默认仅放行本地前端。"""
    raw_origins = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if raw_origins:
        return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return [
        "http://localhost:3060",
        "http://127.0.0.1:3060",
    ]

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(a_share_router)
app.include_router(account_router)
app.include_router(core_router)
app.include_router(crawl_router)
app.include_router(daily_analysis_router)
app.include_router(columns_router)
app.include_router(group_router)
app.include_router(file_router)
app.include_router(media_router)
app.include_router(settings_router)
app.include_router(topic_router)
app.include_router(task_router)

current_tasks: Dict[str, Dict[str, Any]] = {}
task_counter = 0
task_logs: Dict[str, List[str]] = {}  # 存储任务日志
sse_connections: Dict[str, List] = {}  # 存储SSE连接
task_stop_flags: Dict[str, bool] = {}  # 任务停止标志
file_downloader_instances: Dict[str, Any] = {}  # 存储文件下载器实例

def create_task(task_type: str, description: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """创建新任务"""
    global task_counter
    task_counter += 1
    task_id = f"task_{task_counter}_{int(datetime.now().timestamp())}"
    
    current_tasks[task_id] = {
        "task_id": task_id,
        "type": task_type,
        "status": "pending",
        "message": description,
        "result": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    if metadata:
        current_tasks[task_id].update(metadata)

    # 初始化任务日志和停止标志
    task_logs[task_id] = []
    task_stop_flags[task_id] = False
    add_task_log(task_id, f"任务创建: {description}")

    return task_id

def add_task_log(task_id: str, log_message: str):
    """添加任务日志"""
    if task_id not in task_logs:
        task_logs[task_id] = []

    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_log = f"[{timestamp}] {log_message}"
    task_logs[task_id].append(formatted_log)

    # 广播日志到所有SSE连接
    broadcast_log(task_id, formatted_log)

def broadcast_log(task_id: str, log_message: str):
    """广播日志到SSE连接"""
    # 这个函数现在主要用于存储日志，实际的SSE广播在stream端点中实现
    pass

def update_task(task_id: str, status: str, message: str, result: Optional[Dict[str, Any]] = None):
    """更新任务状态"""
    if task_id in current_tasks:
        current_tasks[task_id].update({
            "status": status,
            "message": message,
            "result": result,
            "updated_at": datetime.now()
        })

        # 添加状态变更日志
        add_task_log(task_id, f"状态更新: {message}")

def stop_task(task_id: str) -> bool:
    """停止任务"""
    if task_id not in current_tasks:
        return False

    task = current_tasks[task_id]

    if task["status"] not in ["pending", "running"]:
        return False

    # 设置停止标志
    task_stop_flags[task_id] = True
    add_task_log(task_id, "🛑 收到停止请求，正在停止任务...")

    # 如果有爬虫实例，也设置爬虫的停止标志
    if runtime_helpers_module.crawler_instance:
        runtime_helpers_module.crawler_instance.set_stop_flag()

    # 如果有文件下载器实例，也设置停止标志
    if task_id in file_downloader_instances:
        downloader = file_downloader_instances[task_id]
        downloader.set_stop_flag()

    update_task(task_id, "cancelled", "任务已被用户停止")

    return True

def is_task_stopped(task_id: str) -> bool:
    """检查任务是否被停止"""
    stopped = task_stop_flags.get(task_id, False)
    return stopped


def get_latest_task_by_type(
    task_type: str,
    status: Optional[str] = None,
    group_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按任务类型获取最新任务，可选按状态过滤"""
    normalized_group_id = normalize_group_id(group_id)
    candidates = []
    for task in current_tasks.values():
        if task.get("type") != task_type:
            continue
        if status and task.get("status") != status:
            continue
        if normalized_group_id is not None and normalize_group_id(task.get("group_id")) != normalized_group_id:
            continue
        candidates.append(task)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.get("created_at") or datetime.min, reverse=True)
    return candidates[0]


if __name__ == "__main__":
    import sys
    port = 8508  # 默认端口
    if len(sys.argv) > 2 and sys.argv[1] == "--port":
        try:
            port = int(sys.argv[2])
        except ValueError:
            port = 8508
    uvicorn.run(app, host="0.0.0.0", port=port)
