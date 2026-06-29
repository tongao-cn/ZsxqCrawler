from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set


CheckpointSave = Callable[..., Dict[str, Any]]
CheckpointLog = Callable[[str], None]
AggregateSuccessCallback = Callable[[str, str, List[Dict[str, Any]], List[str]], None]


@dataclass
class AShareAnalysisCheckpointManager:
    enabled: bool
    group_id: Optional[str]
    processed_keys: Set[str]
    save_checkpoint: CheckpointSave
    emit_log: CheckpointLog
    batch_size: int
    pending_daily: Dict[str, Dict[str, int]] = field(default_factory=dict)
    pending_keys: Set[str] = field(default_factory=set)
    pending_extractions: List[Dict[str, Any]] = field(default_factory=list)
    saved_topic_stock_extractions: int = 0

    def success_callback(self) -> Optional[AggregateSuccessCallback]:
        return self.record_success if self.enabled else None

    def record_success(
        self,
        item_key: str,
        day: str,
        stocks: List[Dict[str, Any]],
        companies: List[str],
    ) -> None:
        if not self.enabled:
            return
        if companies:
            day_bucket = self.pending_daily.setdefault(day, {})
            for company in companies:
                day_bucket[company] = day_bucket.get(company, 0) + 1
        self.pending_keys.add(item_key)
        self.pending_extractions.extend(stocks)
        self.flush()

    def flush(self, force: bool = False) -> None:
        if not self.enabled or not self.pending_keys:
            return
        if not force and len(self.pending_keys) < self.batch_size:
            return

        result = self.save_checkpoint(
            daily_delta=self.pending_daily,
            processed_keys=self.pending_keys,
            topic_stock_extractions=self.pending_extractions,
            group_id=self.group_id,
        )
        self.processed_keys.update(self.pending_keys)
        self.saved_topic_stock_extractions += int(result.get("topic_stock_extractions") or 0)
        self.emit_log(
            f"db checkpoint saved at {datetime.now().isoformat(timespec='seconds')}: "
            f"group_id={self.group_id}, daily_mentions={result.get('daily_mentions', 0)}, "
            f"topic_stock_extractions={result.get('topic_stock_extractions', 0)}, "
            f"processed_state={result.get('processed_state', 0)}",
        )
        self.pending_daily = {}
        self.pending_keys = set()
        self.pending_extractions = []
