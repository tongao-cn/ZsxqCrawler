from __future__ import annotations

from datetime import time, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.core.account_context import get_cookie_for_group
from backend.crawlers.zsxq_interactive_crawler import ZSXQInteractiveCrawler
from backend.routes.ingestion_helpers import enqueue_ingestion_task
from backend.services.task_runtime import (
    add_task_log,
    is_task_stopped,
    register_task_crawler,
    unregister_task_crawler,
    update_task,
)

router = APIRouter(prefix="/api/crawl", tags=["crawl"])


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


INIT_STOPPED_MESSAGE = "🛑 任务在初始化过程中被停止"
CRAWLER_STARTUP_LOGS = ("📡 连接到知识星球API...", "🔍 检查数据库状态...")


def _should_stop_task(task_id: str) -> bool:
    return is_task_stopped(task_id)


def _build_task_callbacks(task_id: str) -> tuple[Callable[[str], None], Callable[[], bool]]:
    def log_callback(message: str) -> None:
        add_task_log(task_id, message)

    def stop_check() -> bool:
        return _should_stop_task(task_id)

    return log_callback, stop_check


def _log_crawler_startup(task_id: str) -> None:
    for message in CRAWLER_STARTUP_LOGS:
        add_task_log(task_id, message)


def _log_init_stopped(task_id: str) -> None:
    add_task_log(task_id, INIT_STOPPED_MESSAGE)


def _crawl_interval_kwargs(crawl_settings: Any) -> dict[str, Any]:
    return {
        "crawl_interval_min": crawl_settings.crawlIntervalMin,
        "crawl_interval_max": crawl_settings.crawlIntervalMax,
        "long_sleep_interval_min": crawl_settings.longSleepIntervalMin,
        "long_sleep_interval_max": crawl_settings.longSleepIntervalMax,
        "pages_per_batch": crawl_settings.pagesPerBatch,
    }


def _has_crawl_interval_overrides(crawl_settings: Any) -> bool:
    return any(_crawl_interval_kwargs(crawl_settings).values())


def _apply_crawl_settings(crawler: Any, crawl_settings: Any, require_overrides: bool = False) -> bool:
    if not crawl_settings:
        return False
    if require_overrides and not _has_crawl_interval_overrides(crawl_settings):
        return False

    crawler.set_custom_intervals(**_crawl_interval_kwargs(crawl_settings))
    return True


def _mark_expired_task(task_id: str, result: dict[str, Any], default_message: str = "成员体验已到期") -> None:
    message = result.get("message", default_message)
    add_task_log(task_id, f"❌ 会员已过期: {message}")
    update_task(task_id, "failed", "会员已过期", {"expired": True, "code": result.get("code"), "message": result.get("message")})


def _create_crawl_task_response(
    background_tasks: BackgroundTasks,
    task_type: str,
    description: str,
    task_func: Callable[..., Any],
    group_id: str,
    *task_args: Any,
) -> dict[str, str]:
    return enqueue_ingestion_task(
        background_tasks,
        task_type,
        description,
        task_func,
        group_id,
        *task_args,
    )


def _is_date_only(value: Optional[str]) -> bool:
    text = (value or "").strip()
    return len(text) == 10 and text[4] == "-" and text[7] == "-"


def _parse_user_time(value: Optional[str], date_end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    try:
        if _is_date_only(text):
            dt = datetime.combine(datetime.strptime(text, "%Y-%m-%d").date(), time.max if date_end else time.min)
            return dt.replace(tzinfo=timezone(timedelta(hours=8)))
        if "T" in text and len(text) == 16:
            text = text + ":00"
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        if len(text) >= 24 and (text[-5] in ["+", "-"]) and text[-3] != ":":
            text = text[:-2] + ":" + text[-2:]
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return dt
    except Exception:
        return None


def _resolve_time_range(request: CrawlTimeRangeRequest, now_bj: datetime) -> tuple[datetime, datetime]:
    start_dt = _parse_user_time(request.startTime)
    end_dt = _parse_user_time(request.endTime, date_end=True) if request.endTime else None

    if request.lastDays and request.lastDays > 0:
        if end_dt is None:
            end_dt = now_bj
        start_dt = end_dt - timedelta(days=request.lastDays)

    if end_dt is None:
        end_dt = now_bj
    if start_dt is None:
        start_dt = end_dt - timedelta(days=30)

    if start_dt > end_dt:
        if _is_date_only(request.startTime) and _is_date_only(request.endTime):
            start_dt = _parse_user_time(request.endTime)
            end_dt = _parse_user_time(request.startTime, date_end=True)
        else:
            start_dt, end_dt = end_dt, start_dt

    return start_dt, end_dt


def _format_zsxq_time(dt: datetime) -> str:
    return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"


def _create_task_crawler(task_id: str, group_id: str, log_callback: Callable[[str], None], stop_check: Callable[[], bool]) -> ZSXQInteractiveCrawler:
    cookie = get_cookie_for_group(group_id)
    crawler = ZSXQInteractiveCrawler(cookie, group_id, log_callback)
    crawler.stop_check_func = stop_check
    register_task_crawler(task_id, crawler)
    return crawler


def run_crawl_historical_task(
    task_id: str,
    group_id: str,
    pages: int,
    per_page: int,
    crawl_settings: CrawlHistoricalRequest = None,
):
    """后台执行历史数据爬取任务"""
    try:

        if is_task_stopped(task_id):
            return

        update_task(task_id, "running", f"开始爬取历史数据 {pages} 页...")
        add_task_log(task_id, f"🚀 开始获取历史数据，{pages} 页，每页 {per_page} 条")

        if is_task_stopped(task_id):
            return

        log_callback, stop_check = _build_task_callbacks(task_id)

        crawler = _create_task_crawler(task_id, group_id, log_callback, stop_check)

        _apply_crawl_settings(crawler, crawl_settings)

        if is_task_stopped(task_id):
            _log_init_stopped(task_id)
            return

        _log_crawler_startup(task_id)

        if is_task_stopped(task_id):
            return

        result = crawler.crawl_incremental(pages, per_page)

        if is_task_stopped(task_id):
            return

        if result and result.get("expired"):
            _mark_expired_task(task_id, result)
            return

        add_task_log(task_id, f"✅ 获取完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        update_task(task_id, "completed", "历史数据爬取完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 获取失败: {str(e)}")
            update_task(task_id, "failed", f"爬取失败: {str(e)}")
    finally:
        unregister_task_crawler(task_id)


def run_crawl_all_task(task_id: str, group_id: str, crawl_settings: CrawlSettingsRequest = None):
    try:

        update_task(task_id, "running", "开始全量爬取...")
        add_task_log(task_id, "🚀 开始全量爬取...")
        add_task_log(task_id, "⚠️ 警告：此模式将持续爬取直到没有数据，可能需要很长时间")

        log_callback, stop_check = _build_task_callbacks(task_id)

        crawler = _create_task_crawler(task_id, group_id, log_callback, stop_check)

        _apply_crawl_settings(crawler, crawl_settings)

        if is_task_stopped(task_id):
            _log_init_stopped(task_id)
            return

        _log_crawler_startup(task_id)

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
            _mark_expired_task(task_id, result)
            return

        add_task_log(task_id, "🎉 全量爬取完成！")
        add_task_log(task_id, f"📊 最终统计: 新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}, 总页数: {result.get('pages', 0)}")
        update_task(task_id, "completed", "全量爬取完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 全量爬取失败: {str(e)}")
            update_task(task_id, "failed", f"全量爬取失败: {str(e)}")
    finally:
        unregister_task_crawler(task_id)


def run_crawl_incremental_task(
    task_id: str,
    group_id: str,
    pages: int,
    per_page: int,
    crawl_settings: CrawlHistoricalRequest = None,
):
    try:

        update_task(task_id, "running", "开始增量爬取...")

        log_callback, stop_check = _build_task_callbacks(task_id)

        crawler = _create_task_crawler(task_id, group_id, log_callback, stop_check)

        _apply_crawl_settings(crawler, crawl_settings)

        if is_task_stopped(task_id):
            _log_init_stopped(task_id)
            return

        _log_crawler_startup(task_id)

        result = crawler.crawl_incremental(pages, per_page)

        if is_task_stopped(task_id):
            return

        add_task_log(task_id, f"✅ 增量爬取完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        update_task(task_id, "completed", "增量爬取完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 增量爬取失败: {str(e)}")
            update_task(task_id, "failed", f"增量爬取失败: {str(e)}")
    finally:
        unregister_task_crawler(task_id)


def run_crawl_latest_task(task_id: str, group_id: str, crawl_settings: CrawlSettingsRequest = None):
    try:

        update_task(task_id, "running", "开始获取最新记录...")

        log_callback, stop_check = _build_task_callbacks(task_id)

        crawler = _create_task_crawler(task_id, group_id, log_callback, stop_check)

        _apply_crawl_settings(crawler, crawl_settings)

        if is_task_stopped(task_id):
            _log_init_stopped(task_id)
            return

        _log_crawler_startup(task_id)

        result = crawler.crawl_latest_until_complete()

        if is_task_stopped(task_id):
            return

        if result and result.get("expired"):
            _mark_expired_task(task_id, result)
            return

        add_task_log(task_id, f"✅ 获取最新记录完成！新增话题: {result.get('new_topics', 0)}, 更新话题: {result.get('updated_topics', 0)}")
        update_task(task_id, "completed", "获取最新记录完成", result)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 获取最新记录失败: {str(e)}")
            update_task(task_id, "failed", f"获取最新记录失败: {str(e)}")
    finally:
        unregister_task_crawler(task_id)


def run_crawl_time_range_task(task_id: str, group_id: str, request: "CrawlTimeRangeRequest"):
    """后台执行“按时间区间爬取”任务：仅导入位于区间 [startTime, endTime] 内的话题"""
    try:
        bj_tz = timezone(timedelta(hours=8))
        now_bj = datetime.now(bj_tz)
        start_dt, end_dt = _resolve_time_range(request, now_bj)

        update_task(task_id, "running", "开始按时间区间爬取...")
        add_task_log(task_id, f"🗓️ 时间范围: {start_dt.isoformat()} ~ {end_dt.isoformat()}")

        log_callback, stop_check = _build_task_callbacks(task_id)

        crawler = _create_task_crawler(task_id, group_id, log_callback, stop_check)

        _apply_crawl_settings(crawler, request, require_overrides=True)

        per_page = request.perPage or 20
        total_stats = {"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0}
        begin_time_param = _format_zsxq_time(start_dt)
        end_time_param = _format_zsxq_time(end_dt)
        max_retries_per_page = 10

        while True:
            if is_task_stopped(task_id):
                add_task_log(task_id, "🛑 任务已停止")
                break

            retry = 0
            page_processed = False
            reached_end = False
            last_time_dt_in_page = None

            while retry < max_retries_per_page:
                if is_task_stopped(task_id):
                    break

                data = crawler.fetch_topics_safe(
                    scope="all",
                    count=per_page,
                    begin_time=begin_time_param,
                    end_time=end_time_param,
                    is_historical=True,
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
                    reached_end = True
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

                add_task_log(task_id, f"📄 本页获取 {len(topics)} 个话题，区间内 {len(filtered)} 个")

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

            if reached_end or (last_time_dt_in_page and last_time_dt_in_page < start_dt):
                break

        update_task(task_id, "completed", "时间区间爬取完成", total_stats)
    except Exception as e:
        if not is_task_stopped(task_id):
            add_task_log(task_id, f"❌ 时间区间爬取失败: {str(e)}")
            update_task(task_id, "failed", f"时间区间爬取失败: {str(e)}")
    finally:
        unregister_task_crawler(task_id)


@router.post("/historical/{group_id}")
async def crawl_historical(group_id: str, request: CrawlHistoricalRequest, background_tasks: BackgroundTasks):
    """爬取历史数据"""
    try:
        return _create_crawl_task_response(
            background_tasks,
            "crawl_historical",
            f"爬取历史数据 {request.pages} 页 (群组: {group_id})",
            run_crawl_historical_task,
            group_id,
            request.pages,
            request.per_page,
            request,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建爬取任务失败: {str(e)}")


@router.post("/all/{group_id}")
async def crawl_all(group_id: str, request: CrawlSettingsRequest, background_tasks: BackgroundTasks):
    """全量爬取所有历史数据"""
    try:
        return _create_crawl_task_response(
            background_tasks,
            "crawl_all",
            f"全量爬取所有历史数据 (群组: {group_id})",
            run_crawl_all_task,
            group_id,
            request,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建全量爬取任务失败: {str(e)}")


@router.post("/incremental/{group_id}")
async def crawl_incremental(group_id: str, request: CrawlHistoricalRequest, background_tasks: BackgroundTasks):
    """增量爬取历史数据"""
    try:
        return _create_crawl_task_response(
            background_tasks,
            "crawl_incremental",
            f"增量爬取历史数据 {request.pages} 页 (群组: {group_id})",
            run_crawl_incremental_task,
            group_id,
            request.pages,
            request.per_page,
            request,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建增量爬取任务失败: {str(e)}")


@router.post("/latest-until-complete/{group_id}")
async def crawl_latest_until_complete(group_id: str, request: CrawlSettingsRequest, background_tasks: BackgroundTasks):
    """获取最新记录：智能增量更新"""
    try:
        return _create_crawl_task_response(
            background_tasks,
            "crawl_latest_until_complete",
            f"获取最新记录 (群组: {group_id})",
            run_crawl_latest_task,
            group_id,
            request,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建获取最新记录任务失败: {str(e)}")


@router.post("/range/{group_id}")
async def crawl_by_time_range(group_id: str, request: CrawlTimeRangeRequest, background_tasks: BackgroundTasks):
    """按时间区间爬取话题（支持最近N天或自定义开始/结束时间）"""
    try:
        return _create_crawl_task_response(
            background_tasks,
            "crawl_time_range",
            f"按时间区间爬取 (群组: {group_id})",
            run_crawl_time_range_task,
            group_id,
            request,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建时间区间爬取任务失败: {str(e)}")
