from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Dict, Optional

from backend.services.a_share_analysis_db_storage import load_topic_stock_extractions
from backend.services.research_radar_ai import summarize_radar_candidates
from backend.services.research_radar_signal import build_research_radar_candidates
from backend.services.research_radar_store import (
    load_latest_research_radar_run,
    load_research_radar_run_by_date,
    save_research_radar_run,
)
from backend.services.task_launch import TaskLaunchRecipe, launch_task_recipe
from backend.services.task_runtime import build_task_log_callback, run_workflow
from backend.services.topic_material import (
    DEFAULT_COMMENTS_PER_TOPIC,
    connect_topic_material_db,
    load_daily_topic_material,
    parse_topic_material_date,
)


LogCallback = Optional[Callable[[str], None]]


@dataclass(frozen=True)
class ResearchRadarTaskRequest:
    date: Optional[str] = None
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC

    def __post_init__(self) -> None:
        comments_per_topic = int(self.comments_per_topic)
        if comments_per_topic < 0 or comments_per_topic > 50:
            raise ValueError("comments_per_topic must be between 0 and 50")
        object.__setattr__(self, "comments_per_topic", comments_per_topic)


def _log(log_callback: LogCallback, message: str) -> None:
    if log_callback:
        log_callback(message)


def _baseline_range(report_date) -> tuple[str, str]:
    return (report_date - timedelta(days=7)).isoformat(), (report_date - timedelta(days=1)).isoformat()


def _summary_payload(logic_items: list[Dict[str, Any]]) -> Dict[str, Any]:
    tier_counts = {"strong": 0, "medium": 0, "weak": 0}
    directions = set()
    stocks = set()
    for item in logic_items:
        tier = item.get("tier")
        if tier in tier_counts:
            tier_counts[tier] += 1
        direction = str(item.get("direction") or "").strip()
        if direction:
            directions.add(direction)
        for stock in item.get("stocks") or []:
            if isinstance(stock, dict):
                stock_name = str(stock.get("stock_name") or stock.get("name") or "").strip()
                if stock_name:
                    stocks.add(stock_name)
    return {
        "logic_count": len(logic_items),
        "strong_count": tier_counts["strong"],
        "medium_count": tier_counts["medium"],
        "weak_count": tier_counts["weak"],
        "direction_count": len(directions),
        "stock_count": len(stocks),
    }


def generate_research_radar(
    group_id: str,
    report_date: Optional[str] = None,
    *,
    task_id: str = "",
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC,
    log_callback: LogCallback = None,
) -> Dict[str, Any]:
    parsed_date = parse_topic_material_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = connect_topic_material_db(group_id)
    try:
        _log(log_callback, f"加载 {report_date_text} 话题素材...")
        material = load_daily_topic_material(
            group_id,
            report_date=parsed_date,
            comments_per_topic=comments_per_topic,
        )
        _log(log_callback, f"加载 {report_date_text} 股票提取结果...")
        current_rows = load_topic_stock_extractions(
            group_id=group_id,
            start_date=report_date_text,
            end_date=report_date_text,
        )
        baseline_start, baseline_end = _baseline_range(parsed_date)
        baseline_rows = load_topic_stock_extractions(
            group_id=group_id,
            start_date=baseline_start,
            end_date=baseline_end,
        )
        candidates = build_research_radar_candidates(
            topics=material.topics,
            current_stock_rows=current_rows,
            baseline_stock_rows=baseline_rows,
            max_candidates=8,
        )
        _log(log_callback, f"生成 {len(candidates)} 条研究雷达候选...")
        logic_items, model = summarize_radar_candidates(candidates, report_date=report_date_text)
        run_id = save_research_radar_run(
            conn,
            group_id=group_id,
            report_date=report_date_text,
            task_id=task_id,
            status="completed",
            model=model,
            logic_items=logic_items,
            summary=_summary_payload(logic_items),
        )
        return {
            "group_id": group_id,
            "report_date": report_date_text,
            "run_id": run_id,
            "logic_count": len(logic_items),
        }
    finally:
        conn.close()


def run_research_radar_task(task_id: str, group_id: str, request: ResearchRadarTaskRequest) -> None:
    def work() -> Dict[str, Any]:
        return generate_research_radar(
            group_id,
            request.date,
            task_id=task_id,
            comments_per_topic=request.comments_per_topic,
            log_callback=build_task_log_callback(task_id),
        )

    run_workflow(
        task_id,
        running_message="开始生成研究雷达...",
        completed_message="研究雷达生成完成",
        failure_label="研究雷达生成",
        work=work,
    )


def create_research_radar_task(
    group_id: str,
    *,
    date: Optional[str] = None,
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC,
) -> Dict[str, str]:
    report_date = parse_topic_material_date(date).isoformat()
    request = ResearchRadarTaskRequest(date=report_date, comments_per_topic=comments_per_topic)
    return launch_task_recipe(
        TaskLaunchRecipe(
            task_type="research_radar",
            description=f"生成研究雷达 (群组: {group_id})",
            task_func=run_research_radar_task,
            args=(group_id, request),
            group_id=group_id,
            metadata={"report_date": report_date},
        )
    )


def get_research_radar(group_id: str, report_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = connect_topic_material_db(group_id)
    try:
        if report_date:
            parsed_date = parse_topic_material_date(report_date)
            return load_research_radar_run_by_date(
                conn,
                group_id=group_id,
                report_date=parsed_date.isoformat(),
            )
        return load_latest_research_radar_run(conn, group_id=group_id)
    finally:
        conn.close()
