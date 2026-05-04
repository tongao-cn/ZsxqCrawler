from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from zsxq_interactive_crawler import ZSXQInteractiveCrawler

router = APIRouter(prefix="/api/crawl", tags=["crawl"])


def _main_module():
    return sys.modules.get("main") or sys.modules.get("__main__")


def _get_main_attr(name: str):
    module = _main_module()
    if module is None or not hasattr(module, name):
        raise RuntimeError(f"主模块未初始化，无法访问 {name}")
    return getattr(module, name)


class CrawlHistoricalRequest(BaseModel):
    pages: int = Field(default=10, ge=1, le=1000, description="爬取页数")
    per_page: int = Field(default=20, ge=1, le=100, description="每页数量")
    crawlIntervalMin: Optional[float] = Field(default=None, ge=1.0, le=60.0, description="爬取间隔最小值(秒)")
    crawlIntervalMax: Optional[float] = Field(default=None, ge=1.0, le=60.0, description="爬取间隔最大值(秒)")
    longSleepIntervalMin: Optional[float] = Field(default=None, ge=60.0, le=3600.0, description="长休眠间隔最小值(秒)")
    longSleepIntervalMax: Optional[float] = Field(default=None, ge=60.0, le=3600.0, description="长休眠间隔最大值(秒)")
    pagesPerBatch: Optional[int] = Field(default=None, ge=5, le=50, description="每批次页面数")


class CrawlSettingsRequest(BaseModel):
    crawlIntervalMin: Optional[float] = Field(default=None, ge=1.0, le=60.0, description="爬取间隔最小值(秒)")
    crawlIntervalMax: Optional[float] = Field(default=None, ge=1.0, le=60.0, description="爬取间隔最大值(秒)")
    longSleepIntervalMin: Optional[float] = Field(default=None, ge=60.0, le=3600.0, description="长休眠间隔最小值(秒)")
    longSleepIntervalMax: Optional[float] = Field(default=None, ge=60.0, le=3600.0, description="长休眠间隔最大值(秒)")
    pagesPerBatch: Optional[int] = Field(default=None, ge=5, le=50, description="每批次页面数")


class CrawlTimeRangeRequest(BaseModel):
    startTime: Optional[str] = Field(default=None, description="开始时间，支持 YYYY-MM-DD 或 ISO8601，缺省则按 lastDays 推导")
    endTime: Optional[str] = Field(default=None, description="结束时间，默认当前时间（本地东八区）")
    lastDays: Optional[int] = Field(default=None, ge=1, le=3650, description="最近N天（与 startTime/endTime 互斥优先；当 startTime 缺省时可用）")
    perPage: Optional[int] = Field(default=20, ge=1, le=100, description="每页数量")
    crawlIntervalMin: Optional[float] = Field(default=None, ge=1.0, le=60.0, description="爬取间隔最小值(秒)")
    crawlIntervalMax: Optional[float] = Field(default=None, ge=1.0, le=60.0, description="爬取间隔最大值(秒)")
    longSleepIntervalMin: Optional[float] = Field(default=None, ge=60.0, le=3600.0, description="长休眠间隔最小值(秒)")
    longSleepIntervalMax: Optional[float] = Field(default=None, ge=60.0, le=3600.0, description="长休眠间隔最大值(秒)")
    pagesPerBatch: Optional[int] = Field(default=None, ge=5, le=50, description="每批次页面数")


def run_crawl_historical_task(
    task_id: str,
    group_id: str,
    pages: int,
    per_page: int,
    crawl_settings: CrawlHistoricalRequest = None,
):
    """后台执行历史数据爬取任务"""
    try:
        is_task_stopped = _get_main_attr("is_task_stopped")
        update_task = _get_main_attr("update_task")
        add_task_log = _get_main_attr("add_task_log")

        if is_task_stopped(task_id):
            return

        update_task(task_id, "running", f"开始爬取历史数据 {pages} 页...")
        add_task_log(task_id, f"🚀 开始获取历史数据，{pages} 页，每页 {per_page} 条")

        if is_task_stopped(task_id):
            return

        def log_callback(message: str):
            add_task_log(task_id, message)

        def stop_check():
            return is_task_stopped(task_id)

        cookie = _get_main_attr("get_cookie_for_group")(group_id)
        path_manager = _get_main_attr("get_db_path_manager")()
        db_path = path_manager.get_topics_db_path(group_id)

        crawler = ZSXQInteractiveCrawler(cookie, group_id, db_path, log_callback)
        crawler.stop_check_func = stop_check

        if crawl_settings:
            crawler.set_custom_intervals(
                crawl_interval_min=crawl_settings.crawlIntervalMin,
                crawl_interval_max=crawl_settings.crawlIntervalMax,
                long_sleep_interval_min=crawl_settings.longSleepIntervalMin,
                long_sleep_interval_max=crawl_settings.longSleepIntervalMax,
                pages_per_batch=crawl_settings.pagesPerBatch,
            )

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        add_task_log(task_id, "📡 连接到知识星球API...")
        add_task_log(task_id, "🔍 检查数据库状态...")

        if is_task_stopped(task_id):
            return

        result = crawler.crawl_incremental(pages, per_page)

        if is_task_stopped(task_id):
            return

        if result and result.get("expired"):
            add_task_log(task_id, f"❌ 会员已过期: {result.get('message', '成员体验已到期')}")
            update_task(task_id, "failed", "会员已过期", {"expired": True, "code": result.get("code"), "message": result.get("message")})
            return

        add_task_log(task_id, f"✅ 获取完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        update_task(task_id, "completed", "历史数据爬取完成", result)
    except Exception as e:
        if not _get_main_attr("is_task_stopped")(task_id):
            add_task_log = _get_main_attr("add_task_log")
            update_task = _get_main_attr("update_task")
            add_task_log(task_id, f"❌ 获取失败: {str(e)}")
            update_task(task_id, "failed", f"爬取失败: {str(e)}")


def run_crawl_all_task(task_id: str, group_id: str, crawl_settings: CrawlSettingsRequest = None):
    try:
        update_task = _get_main_attr("update_task")
        add_task_log = _get_main_attr("add_task_log")
        is_task_stopped = _get_main_attr("is_task_stopped")

        update_task(task_id, "running", "开始全量爬取...")
        add_task_log(task_id, "🚀 开始全量爬取...")
        add_task_log(task_id, "⚠️ 警告：此模式将持续爬取直到没有数据，可能需要很长时间")

        def log_callback(message):
            add_task_log(task_id, message)

        def stop_check():
            return is_task_stopped(task_id)

        cookie = _get_main_attr("get_cookie_for_group")(group_id)
        path_manager = _get_main_attr("get_db_path_manager")()
        db_path = path_manager.get_topics_db_path(group_id)

        crawler = ZSXQInteractiveCrawler(cookie, group_id, db_path, log_callback)
        crawler.stop_check_func = stop_check

        if crawl_settings:
            crawler.set_custom_intervals(
                crawl_interval_min=crawl_settings.crawlIntervalMin,
                crawl_interval_max=crawl_settings.crawlIntervalMax,
                long_sleep_interval_min=crawl_settings.longSleepIntervalMin,
                long_sleep_interval_max=crawl_settings.longSleepIntervalMax,
                pages_per_batch=crawl_settings.pagesPerBatch,
            )

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        add_task_log(task_id, "📡 连接到知识星球API...")
        add_task_log(task_id, "🔍 检查数据库状态...")

        if is_task_stopped(task_id):
            return

        db_stats = crawler.db.get_database_stats()
        add_task_log(task_id, f"📊 当前数据库状态: 话题: {db_stats.get('topics', 0)}, 用户: {db_stats.get('users', 0)}")

        if is_task_stopped(task_id):
            return

        add_task_log(task_id, "🌊 开始无限历史爬取...")
        result = crawler.crawl_all_historical(per_page=20, auto_confirm=True)

        if is_task_stopped(task_id):
            return

        if result and result.get("expired"):
            add_task_log(task_id, f"❌ 会员已过期: {result.get('message', '成员体验已到期')}")
            update_task(task_id, "failed", "会员已过期", {"expired": True, "code": result.get("code"), "message": result.get("message")})
            return

        add_task_log(task_id, "🎉 全量爬取完成！")
        add_task_log(task_id, f"📊 最终统计: 新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}, 总页数: {result.get('pages', 0)}")
        update_task(task_id, "completed", "全量爬取完成", result)
    except Exception as e:
        add_task_log(task_id, f"❌ 全量爬取失败: {str(e)}")
        update_task(task_id, "failed", f"全量爬取失败: {str(e)}")


def run_crawl_incremental_task(
    task_id: str,
    group_id: str,
    pages: int,
    per_page: int,
    crawl_settings: CrawlHistoricalRequest = None,
):
    try:
        update_task = _get_main_attr("update_task")
        add_task_log = _get_main_attr("add_task_log")
        is_task_stopped = _get_main_attr("is_task_stopped")

        update_task(task_id, "running", "开始增量爬取...")

        def log_callback(message: str):
            add_task_log(task_id, message)

        def stop_check():
            return is_task_stopped(task_id)

        cookie = _get_main_attr("get_cookie_for_group")(group_id)
        path_manager = _get_main_attr("get_db_path_manager")()
        db_path = path_manager.get_topics_db_path(group_id)

        crawler = ZSXQInteractiveCrawler(cookie, group_id, db_path, log_callback)
        crawler.stop_check_func = stop_check

        if crawl_settings:
            crawler.set_custom_intervals(
                crawl_interval_min=crawl_settings.crawlIntervalMin,
                crawl_interval_max=crawl_settings.crawlIntervalMax,
                long_sleep_interval_min=crawl_settings.longSleepIntervalMin,
                long_sleep_interval_max=crawl_settings.longSleepIntervalMax,
                pages_per_batch=crawl_settings.pagesPerBatch,
            )

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        add_task_log(task_id, "📡 连接到知识星球API...")
        add_task_log(task_id, "🔍 检查数据库状态...")

        result = crawler.crawl_incremental(pages, per_page)

        if is_task_stopped(task_id):
            return

        add_task_log(task_id, f"✅ 增量爬取完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        update_task(task_id, "completed", "增量爬取完成", result)
    except Exception as e:
        if not _get_main_attr("is_task_stopped")(task_id):
            add_task_log = _get_main_attr("add_task_log")
            update_task = _get_main_attr("update_task")
            add_task_log(task_id, f"❌ 增量爬取失败: {str(e)}")
            update_task(task_id, "failed", f"增量爬取失败: {str(e)}")


def run_crawl_latest_task(task_id: str, group_id: str, crawl_settings: CrawlSettingsRequest = None):
    try:
        update_task = _get_main_attr("update_task")
        add_task_log = _get_main_attr("add_task_log")
        is_task_stopped = _get_main_attr("is_task_stopped")

        update_task(task_id, "running", "开始获取最新记录...")

        def log_callback(message: str):
            add_task_log(task_id, message)

        def stop_check():
            return is_task_stopped(task_id)

        cookie = _get_main_attr("get_cookie_for_group")(group_id)
        path_manager = _get_main_attr("get_db_path_manager")()
        db_path = path_manager.get_topics_db_path(group_id)

        crawler = ZSXQInteractiveCrawler(cookie, group_id, db_path, log_callback)
        crawler.stop_check_func = stop_check

        if crawl_settings:
            crawler.set_custom_intervals(
                crawl_interval_min=crawl_settings.crawlIntervalMin,
                crawl_interval_max=crawl_settings.crawlIntervalMax,
                long_sleep_interval_min=crawl_settings.longSleepIntervalMin,
                long_sleep_interval_max=crawl_settings.longSleepIntervalMax,
                pages_per_batch=crawl_settings.pagesPerBatch,
            )

        if is_task_stopped(task_id):
            add_task_log(task_id, "🛑 任务在初始化过程中被停止")
            return

        add_task_log(task_id, "📡 连接到知识星球API...")
        add_task_log(task_id, "🔍 检查数据库状态...")

        result = crawler.crawl_latest_until_complete()

        if is_task_stopped(task_id):
            return

        if result and result.get("expired"):
            add_task_log(task_id, f"❌ 会员已过期: {result.get('message', '成员体验已到期')}")
            update_task(task_id, "failed", "会员已过期", {"expired": True, "code": result.get("code"), "message": result.get("message")})
            return

        add_task_log(task_id, f"✅ 获取最新记录完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        update_task(task_id, "completed", "获取最新记录完成", result)
    except Exception as e:
        if not _get_main_attr("is_task_stopped")(task_id):
            add_task_log = _get_main_attr("add_task_log")
            update_task = _get_main_attr("update_task")
            add_task_log(task_id, f"❌ 获取最新记录失败: {str(e)}")
            update_task(task_id, "failed", f"获取最新记录失败: {str(e)}")


def run_crawl_time_range_task(task_id: str, group_id: str, request: "CrawlTimeRangeRequest"):
    """后台执行“按时间区间爬取”任务：仅导入位于区间 [startTime, endTime] 内的话题"""
    try:
        is_task_stopped = _get_main_attr("is_task_stopped")
        update_task = _get_main_attr("update_task")
        add_task_log = _get_main_attr("add_task_log")

        def parse_user_time(s: Optional[str]) -> Optional[datetime]:
            if not s:
                return None
            t = s.strip()
            try:
                if len(t) == 10 and t[4] == "-" and t[7] == "-":
                    dt = datetime.strptime(t, "%Y-%m-%d")
                    return dt.replace(tzinfo=timezone(timedelta(hours=8)))
                if "T" in t and len(t) == 16:
                    t = t + ":00"
                if t.endswith("Z"):
                    t = t.replace("Z", "+00:00")
                if len(t) >= 24 and (t[-5] in ["+", "-"]) and t[-3] != ":":
                    t = t[:-2] + ":" + t[-2:]
                dt = datetime.fromisoformat(t)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
                return dt
            except Exception:
                return None

        bj_tz = timezone(timedelta(hours=8))
        now_bj = datetime.now(bj_tz)

        start_dt = parse_user_time(request.startTime)
        end_dt = parse_user_time(request.endTime) if request.endTime else None

        if request.lastDays and request.lastDays > 0:
            if end_dt is None:
                end_dt = now_bj
            start_dt = end_dt - timedelta(days=request.lastDays)

        if end_dt is None:
            end_dt = now_bj
        if start_dt is None:
            start_dt = end_dt - timedelta(days=30)

        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        update_task(task_id, "running", "开始按时间区间爬取...")
        add_task_log(task_id, f"🗓️ 时间范围: {start_dt.isoformat()} ~ {end_dt.isoformat()}")

        def stop_check():
            return is_task_stopped(task_id)

        def log_callback(message: str):
            add_task_log(task_id, message)

        cookie = _get_main_attr("get_cookie_for_group")(group_id)
        path_manager = _get_main_attr("get_db_path_manager")()
        db_path = path_manager.get_topics_db_path(group_id)

        crawler = ZSXQInteractiveCrawler(cookie, group_id, db_path, log_callback)
        crawler.stop_check_func = stop_check

        if any(
            [
                request.crawlIntervalMin,
                request.crawlIntervalMax,
                request.longSleepIntervalMin,
                request.longSleepIntervalMax,
                request.pagesPerBatch,
            ]
        ):
            crawler.set_custom_intervals(
                crawl_interval_min=request.crawlIntervalMin,
                crawl_interval_max=request.crawlIntervalMax,
                long_sleep_interval_min=request.longSleepIntervalMin,
                long_sleep_interval_max=request.longSleepIntervalMax,
                pages_per_batch=request.pagesPerBatch,
            )

        per_page = request.perPage or 20
        total_stats = {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0}
        end_time_param = None
        max_retries_per_page = 10

        while True:
            if is_task_stopped(task_id):
                add_task_log(task_id, "🛑 任务已停止")
                break

            retry = 0
            page_processed = False
            last_time_dt_in_page = None

            while retry < max_retries_per_page:
                if is_task_stopped(task_id):
                    break

                data = crawler.fetch_topics_safe(
                    scope="all",
                    count=per_page,
                    end_time=end_time_param,
                    is_historical=True if end_time_param else False,
                )

                if data and isinstance(data, dict) and data.get("expired"):
                    add_task_log(task_id, f"❌ 会员已过期: {data.get('message')}")
                    update_task(task_id, "failed", "会员已过期", data)
                    return

                if not data:
                    retry += 1
                    total_stats["errors"] += 1
                    add_task_log(task_id, f"❌ 页面获取失败 (重试{retry}/{max_retries_per_page})")
                    continue

                topics = (data.get("resp_data", {}) or {}).get("topics", []) or []
                if not topics:
                    add_task_log(task_id, "📭 无更多数据，任务结束")
                    page_processed = True
                    break

                filtered = []
                for t in topics:
                    ts = t.get("create_time")
                    dt = None
                    try:
                        if ts:
                            ts_fixed = ts.replace("+0800", "+08:00") if ts.endswith("+0800") else ts
                            dt = datetime.fromisoformat(ts_fixed)
                    except Exception:
                        dt = None

                    if dt:
                        last_time_dt_in_page = dt
                        if start_dt <= dt <= end_dt:
                            filtered.append(t)

                if filtered:
                    filtered_data = {"succeeded": True, "resp_data": {"topics": filtered}}
                    page_stats = crawler.store_batch_data(filtered_data)
                    total_stats["new_topics"] += page_stats.get("new_topics", 0)
                    total_stats["updated_topics"] += page_stats.get("updated_topics", 0)
                    total_stats["errors"] += page_stats.get("errors", 0)

                total_stats["pages"] += 1
                page_processed = True

                oldest_in_page = topics[-1].get("create_time")
                try:
                    dt_oldest = datetime.fromisoformat(oldest_in_page.replace("+0800", "+08:00"))
                    dt_oldest = dt_oldest - timedelta(milliseconds=crawler.timestamp_offset_ms)
                    end_time_param = dt_oldest.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"
                except Exception:
                    end_time_param = oldest_in_page

                if last_time_dt_in_page and last_time_dt_in_page < start_dt:
                    add_task_log(task_id, "✅ 已到达起始时间之前，任务结束")
                    break

                crawler.check_page_long_delay()
                break

            if not page_processed:
                add_task_log(task_id, "🚫 当前页面达到最大重试次数，终止任务")
                break

            if not end_time_param or (last_time_dt_in_page and last_time_dt_in_page < start_dt):
                break

        update_task(task_id, "completed", "时间区间爬取完成", total_stats)
    except Exception as e:
        if not _get_main_attr("is_task_stopped")(task_id):
            add_task_log = _get_main_attr("add_task_log")
            update_task = _get_main_attr("update_task")
            add_task_log(task_id, f"❌ 时间区间爬取失败: {str(e)}")
            update_task(task_id, "failed", f"时间区间爬取失败: {str(e)}")


@router.post("/historical/{group_id}")
async def crawl_historical(group_id: str, request: CrawlHistoricalRequest, background_tasks: BackgroundTasks):
    """爬取历史数据"""
    try:
        task_id = _get_main_attr("create_task")("crawl_historical", f"爬取历史数据 {request.pages} 页 (群组: {group_id})")
        background_tasks.add_task(run_crawl_historical_task, task_id, group_id, request.pages, request.per_page, request)
        return {"task_id": task_id, "message": "任务已创建，正在后台执行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建爬取任务失败: {str(e)}")


@router.post("/all/{group_id}")
async def crawl_all(group_id: str, request: CrawlSettingsRequest, background_tasks: BackgroundTasks):
    """全量爬取所有历史数据"""
    try:
        task_id = _get_main_attr("create_task")("crawl_all", f"全量爬取所有历史数据 (群组: {group_id})")
        background_tasks.add_task(run_crawl_all_task, task_id, group_id, request)
        return {"task_id": task_id, "message": "任务已创建，正在后台执行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建全量爬取任务失败: {str(e)}")


@router.post("/incremental/{group_id}")
async def crawl_incremental(group_id: str, request: CrawlHistoricalRequest, background_tasks: BackgroundTasks):
    """增量爬取历史数据"""
    try:
        task_id = _get_main_attr("create_task")("crawl_incremental", f"增量爬取历史数据 {request.pages} 页 (群组: {group_id})")
        background_tasks.add_task(run_crawl_incremental_task, task_id, group_id, request.pages, request.per_page, request)
        return {"task_id": task_id, "message": "任务已创建，正在后台执行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建增量爬取任务失败: {str(e)}")


@router.post("/latest-until-complete/{group_id}")
async def crawl_latest_until_complete(group_id: str, request: CrawlSettingsRequest, background_tasks: BackgroundTasks):
    """获取最新记录：智能增量更新"""
    try:
        task_id = _get_main_attr("create_task")("crawl_latest_until_complete", f"获取最新记录 (群组: {group_id})")
        background_tasks.add_task(run_crawl_latest_task, task_id, group_id, request)
        return {"task_id": task_id, "message": "任务已创建，正在后台执行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建获取最新记录任务失败: {str(e)}")


@router.post("/range/{group_id}")
async def crawl_by_time_range(group_id: str, request: CrawlTimeRangeRequest, background_tasks: BackgroundTasks):
    """按时间区间爬取话题（支持最近N天或自定义开始/结束时间）"""
    try:
        task_id = _get_main_attr("create_task")("crawl_time_range", f"按时间区间爬取 (群组: {group_id})")
        background_tasks.add_task(run_crawl_time_range_task, task_id, group_id, request)
        return {"task_id": task_id, "message": "任务已创建，正在后台执行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建时间区间爬取任务失败: {str(e)}")


def _register_router() -> None:
    module = _main_module()
    if module is None or not hasattr(module, "app"):
        return
    if getattr(module, "_crawl_routes_registered", False):
        return
    module.app.include_router(router)
    setattr(module, "_crawl_routes_registered", True)


_register_router()
