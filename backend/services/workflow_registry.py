from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional


WorkflowScope = Literal["group", "optional_group", "global"]
RetryPolicy = Literal["none", "manual"]
CheckpointPolicy = Literal["none", "business_state"]

INGESTION_LOCK_CATEGORY = "ingestion"


@dataclass(frozen=True)
class WorkflowSpec:
    task_type: str
    display_name: str
    scope: WorkflowScope
    lock_category: Optional[str] = None
    cancellable: bool = True
    retry_policy: RetryPolicy = "none"
    checkpoint_policy: CheckpointPolicy = "none"


def _spec(
    task_type: str,
    display_name: str,
    scope: WorkflowScope = "group",
    *,
    lock_category: Optional[str] = None,
    cancellable: bool = True,
    retry_policy: RetryPolicy = "none",
    checkpoint_policy: CheckpointPolicy = "none",
) -> WorkflowSpec:
    return WorkflowSpec(
        task_type=task_type,
        display_name=display_name,
        scope=scope,
        lock_category=lock_category,
        cancellable=cancellable,
        retry_policy=retry_policy,
        checkpoint_policy=checkpoint_policy,
    )


WORKFLOW_SPECS: Dict[str, WorkflowSpec] = {
    spec.task_type: spec
    for spec in (
        _spec("columns_fetch", "专栏采集", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_all", "全量采集", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_historical", "历史采集", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_incremental", "增量采集", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_latest_until_complete", "获取最新", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_time_range", "时间区间", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("collect_files", "收集文件", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("download_files", "下载文件", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("download_filtered_files", "筛选文件下载", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("download_selected_files", "选中文件下载", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("download_single_file", "单文件下载", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("sync_files_from_topics", "同步文件", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("retention_cleanup", "超期内容清理", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("analyze_file", "文件分析"),
        _spec("analyze_files", "批量文件分析"),
        _spec("daily_stock_concepts", "每日股票概念"),
        _spec("daily_topic_analysis", "每日话题分析"),
        _spec("daily_topic_crawl_and_analysis", "采集并分析日报"),
        _spec("research_radar", "研究雷达"),
        _spec(
            "a_share_analysis",
            "股票推荐池",
            scope="optional_group",
            cancellable=False,
            checkpoint_policy="business_state",
        ),
        _spec("stock_question_analysis", "A股问答"),
        _spec("stock_topic_analysis", "个股分析"),
        _spec("stock_topic_analysis_batch", "批量个股分析"),
    )
}

INGESTION_WORKFLOW_TYPES = frozenset(
    task_type
    for task_type, spec in WORKFLOW_SPECS.items()
    if spec.lock_category == INGESTION_LOCK_CATEGORY
)


def get_workflow_spec(task_type: str) -> Optional[WorkflowSpec]:
    return WORKFLOW_SPECS.get(task_type)


def workflow_types_for_lock(lock_category: str) -> frozenset[str]:
    return frozenset(
        task_type
        for task_type, spec in WORKFLOW_SPECS.items()
        if spec.lock_category == lock_category
    )
