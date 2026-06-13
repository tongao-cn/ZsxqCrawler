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
    scope: WorkflowScope
    lock_category: Optional[str] = None
    cancellable: bool = True
    retry_policy: RetryPolicy = "none"
    checkpoint_policy: CheckpointPolicy = "none"


def _spec(
    task_type: str,
    scope: WorkflowScope = "group",
    *,
    lock_category: Optional[str] = None,
    cancellable: bool = True,
    retry_policy: RetryPolicy = "none",
    checkpoint_policy: CheckpointPolicy = "none",
) -> WorkflowSpec:
    return WorkflowSpec(
        task_type=task_type,
        scope=scope,
        lock_category=lock_category,
        cancellable=cancellable,
        retry_policy=retry_policy,
        checkpoint_policy=checkpoint_policy,
    )


WORKFLOW_SPECS: Dict[str, WorkflowSpec] = {
    spec.task_type: spec
    for spec in (
        _spec("columns_fetch", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_all", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_historical", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_incremental", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_latest_until_complete", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("crawl_time_range", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("collect_files", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("download_files", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("download_filtered_files", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("download_selected_files", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("download_single_file", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("sync_files_from_topics", lock_category=INGESTION_LOCK_CATEGORY),
        _spec("analyze_file"),
        _spec("analyze_files"),
        _spec("daily_stock_concepts"),
        _spec("daily_topic_analysis"),
        _spec("daily_topic_crawl_and_analysis"),
        _spec(
            "a_share_analysis",
            scope="optional_group",
            cancellable=False,
            checkpoint_policy="business_state",
        ),
        _spec("stock_question_analysis"),
        _spec("stock_topic_analysis"),
        _spec("stock_topic_analysis_batch"),
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

