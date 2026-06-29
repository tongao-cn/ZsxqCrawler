"""Download interval runner for ZSXQ file downloads."""

from __future__ import annotations

import random
import time
from typing import Optional, Protocol, Tuple

from backend.crawlers.file_download_policy import download_interval_plan
from backend.crawlers.zsxq_file_downloader_targets import (
    DownloadIntervalPlanTarget,
    DownloadIntervalValues,
)


class DownloadIntervalRuntime(Protocol):
    current_batch_count: int
    files_per_batch: int
    download_interval: float
    long_sleep_interval: float
    use_random_interval: bool
    download_interval_min: Optional[float]
    download_interval_max: Optional[float]
    long_sleep_interval_min: Optional[float]
    long_sleep_interval_max: Optional[float]

    def log(self, message: str) -> None:
        ...


def should_use_random_interval(runtime: DownloadIntervalRuntime) -> bool:
    return bool(getattr(runtime, "use_random_interval", False))


def should_use_random_long_sleep_interval(runtime: DownloadIntervalRuntime) -> bool:
    return (
        runtime.current_batch_count >= runtime.files_per_batch
        and runtime.long_sleep_interval_min is not None
        and runtime.long_sleep_interval_max is not None
    )


def has_random_download_interval_range(runtime: DownloadIntervalRuntime) -> bool:
    return runtime.download_interval_min is not None and runtime.download_interval_max is not None


def random_long_sleep_interval(runtime: DownloadIntervalRuntime) -> float:
    return random.uniform(
        runtime.long_sleep_interval_min,
        runtime.long_sleep_interval_max,
    )


def random_download_interval(runtime: DownloadIntervalRuntime) -> float:
    return random.uniform(runtime.download_interval_min, runtime.download_interval_max)


def download_interval_values(runtime: DownloadIntervalRuntime) -> DownloadIntervalValues:
    download_interval = runtime.download_interval
    long_sleep_interval = runtime.long_sleep_interval
    if should_use_random_interval(runtime):
        if should_use_random_long_sleep_interval(runtime):
            long_sleep_interval = random_long_sleep_interval(runtime)
        elif has_random_download_interval_range(runtime):
            download_interval = random_download_interval(runtime)
    return DownloadIntervalValues(download_interval, long_sleep_interval)


def download_interval_plan_for_target(
    target: DownloadIntervalPlanTarget,
) -> Tuple[Optional[float], Tuple[str, ...], bool]:
    interval_values = target.interval_values
    return download_interval_plan(
        target.current_batch_count,
        target.files_per_batch,
        interval_values.download_interval,
        interval_values.long_sleep_interval,
    )


def apply_download_interval_delay(
    runtime: DownloadIntervalRuntime,
    delay: Optional[float],
    messages: Tuple[str, ...],
    should_reset_batch: bool,
) -> None:
    if delay is None:
        return

    runtime.log(messages[0])
    time.sleep(delay)
    if should_reset_batch:
        runtime.current_batch_count = 0
        runtime.log(messages[1])


def apply_download_interval_plan_target(
    runtime: DownloadIntervalRuntime,
    target: DownloadIntervalPlanTarget,
) -> None:
    delay, messages, should_reset_batch = download_interval_plan_for_target(target)
    apply_download_interval_delay(runtime, delay, messages, should_reset_batch)


def apply_download_interval_plan(
    runtime: DownloadIntervalRuntime,
    interval_values: DownloadIntervalValues,
) -> None:
    apply_download_interval_plan_target(
        runtime,
        DownloadIntervalPlanTarget(
            runtime.current_batch_count,
            runtime.files_per_batch,
            interval_values,
        ),
    )


def apply_download_intervals(runtime: DownloadIntervalRuntime) -> None:
    apply_download_interval_plan_target(
        runtime,
        DownloadIntervalPlanTarget(
            runtime.current_batch_count,
            runtime.files_per_batch,
            download_interval_values(runtime),
        ),
    )
