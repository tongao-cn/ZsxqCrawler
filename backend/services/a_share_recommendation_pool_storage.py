from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Optional, Set, Tuple


DailyMentions = Dict[str, Dict[str, int]]


@dataclass(frozen=True)
class AShareRecommendationPoolStorageAdapters:
    should_use_db_storage: Callable[[Optional[str]], bool]
    resolve_analysis_paths: Callable[[str, str, Optional[str]], Tuple[str, str]]
    read_daily_file: Callable[[str], DailyMentions]
    write_daily_file: Callable[[DailyMentions, str], None]
    load_state_file: Callable[[str], Set[str]]
    save_state_file: Callable[[str, Iterable[str]], None]
    load_daily_mentions_from_db: Callable[..., DailyMentions]
    save_daily_mentions_to_db: Callable[..., None]
    load_processed_state_from_db: Callable[..., Set[str]]
    save_processed_state_to_db: Callable[..., None]
    normalize_group_id: Callable[[Optional[str]], str]
    log_info: Callable[[str], None]


class AShareRecommendationPoolStorage:
    def __init__(self, adapters: AShareRecommendationPoolStorageAdapters) -> None:
        self._adapters = adapters

    def read_daily(
        self,
        output_path: str,
        default_state_path: str,
        *,
        group_id: Optional[str] = None,
    ) -> DailyMentions:
        resolved_output_path, _resolved_state_path = self._adapters.resolve_analysis_paths(
            output_path,
            default_state_path,
            group_id,
        )
        if self._adapters.should_use_db_storage(group_id):
            try:
                return self._adapters.load_daily_mentions_from_db(group_id=group_id)
            except Exception as exc:
                raise RuntimeError(f"read daily mentions from PostgreSQL failed: {exc}") from exc
        return self._adapters.read_daily_file(resolved_output_path)

    def save_daily(
        self,
        daily: DailyMentions,
        output_path: str,
        default_state_path: str,
        *,
        group_id: Optional[str] = None,
    ) -> None:
        resolved_output_path, _resolved_state_path = self._adapters.resolve_analysis_paths(
            output_path,
            default_state_path,
            group_id,
        )
        if self._adapters.should_use_db_storage(group_id):
            try:
                self._adapters.save_daily_mentions_to_db(daily, group_id=group_id)
                self._log_db_daily_saved(daily, group_id)
                return
            except Exception as exc:
                raise RuntimeError(f"save daily mentions to PostgreSQL failed: {exc}") from exc
        self._adapters.write_daily_file(daily, resolved_output_path)

    def load_processed(
        self,
        default_output_path: str,
        state_path: str,
        *,
        group_id: Optional[str] = None,
    ) -> Set[str]:
        _resolved_output_path, resolved_state_path = self._adapters.resolve_analysis_paths(
            default_output_path,
            state_path,
            group_id,
        )
        if self._adapters.should_use_db_storage(group_id):
            try:
                return self._adapters.load_processed_state_from_db(group_id=group_id)
            except Exception as exc:
                raise RuntimeError(f"read processed state from PostgreSQL failed: {exc}") from exc
        return self._adapters.load_state_file(resolved_state_path)

    def save_processed(
        self,
        default_output_path: str,
        state_path: str,
        processed_keys: Optional[Iterable[str]],
        *,
        group_id: Optional[str] = None,
    ) -> None:
        normalized_keys = set(processed_keys or set())
        _resolved_output_path, resolved_state_path = self._adapters.resolve_analysis_paths(
            default_output_path,
            state_path,
            group_id,
        )
        if self._adapters.should_use_db_storage(group_id):
            try:
                self._adapters.save_processed_state_to_db(normalized_keys, group_id=group_id)
                return
            except Exception as exc:
                raise RuntimeError(f"save processed state to PostgreSQL failed: {exc}") from exc
        self._adapters.save_state_file(resolved_state_path, normalized_keys)

    def _log_db_daily_saved(self, daily: DailyMentions, group_id: Optional[str]) -> None:
        total_rows = sum(len(company_counts) for company_counts in daily.values())
        total_mentions = sum(sum(company_counts.values()) for company_counts in daily.values())
        self._adapters.log_info(
            f"db daily mentions saved: group_id={self._adapters.normalize_group_id(group_id) or 'GLOBAL'}, "
            f"days={len(daily)}, rows={total_rows}, mentions={total_mentions}"
        )
