"""
知识星球数据采集器 - FastAPI 后端服务
提供RESTful API接口来操作现有的爬虫功能
"""

import os
import asyncio
from typing import List
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from backend.core.logger_config import ensure_configured

from backend.core.local_group_runtime import scan_local_groups
from backend.routes.a_share_routes import router as a_share_router
from backend.routes.account_routes import router as account_router
from backend.routes.core_routes import router as core_router
from backend.routes.crawl_routes import router as crawl_router
from backend.routes.daily_analysis_routes import router as daily_analysis_router
from backend.routes.daily_stock_concept_routes import router as daily_stock_concept_router
from backend.routes.diagnostics_routes import router as diagnostics_router
from backend.routes.columns_routes import router as columns_router
from backend.routes.group_routes import router as group_router
from backend.routes.file_routes import router as file_router
from backend.routes.media_routes import router as media_router
from backend.routes.settings_routes import router as settings_router
from backend.routes.stock_topic_analysis_routes import router as stock_topic_analysis_router
from backend.routes.topic_routes import router as topic_router
from backend.routes.task_routes import router as task_router
from backend.services.task_runtime import request_runtime_shutdown

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
    request_runtime_shutdown()


def _get_cors_allow_origins() -> List[str]:
    """读取允许的 CORS 来源；默认仅放行本地前端。"""
    raw_origins = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if raw_origins:
        return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return [
        "http://localhost:3060",
        "http://127.0.0.1:3060",
    ]


def create_app() -> FastAPI:
    app = FastAPI(
        title="知识星球数据采集器 API",
        description="为知识星球数据采集器提供RESTful API接口",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_allow_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        a_share_router,
        account_router,
        core_router,
        crawl_router,
        daily_analysis_router,
        daily_stock_concept_router,
        diagnostics_router,
        columns_router,
        group_router,
        file_router,
        media_router,
        settings_router,
        stock_topic_analysis_router,
        topic_router,
        task_router,
    ):
        app.include_router(router)
    return app


app = create_app()

def run_server():
    import sys
    port = 8508  # 默认端口
    if len(sys.argv) > 2 and sys.argv[1] == "--port":
        try:
            port = int(sys.argv[2])
        except ValueError:
            port = 8508
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_graceful_shutdown=5)


if __name__ == "__main__":
    run_server()
